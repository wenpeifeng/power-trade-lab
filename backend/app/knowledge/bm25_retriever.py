"""BM25 稀疏检索引擎 —— 关键词精确匹配。

与向量语义检索（embedding.py）互补：
- 向量检索：捕捉语义关联（"电价怎么算" → "结算规则"），但可能漏掉精确词
- BM25检索：对文号(143号文)、代号(LMP/SD003)、术语精确命中，召回稳定

混合检索策略：两路并行召回 → RRF 互逆排名融合 → 统一输出
索引策略：内存索引（从 DocChunk 表懒加载重建），适合万级以内分块
"""
import hashlib
import json
import logging
import threading
import time
from typing import Optional

import jieba
from rank_bm25 import BM25Okapi
from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger("bm25")

# 专业词词典（让 jieba 不切错电力术语）
DOMAIN_TERMS = [
    "电力现货", "中长期", "辅助服务", "节点电价", "节点边际电价", "出清价格", "日前市场",
    "实时市场", "调频", "备用", "黑启动", "绿电", "绿证", "需求响应", "容量市场",
    "双边协商", "集中竞价", "挂牌交易", "滚动撮合", "偏差考核", "输配电价", "目录电价",
    "峰谷电价", "尖峰电价", "峰平谷", "发售一体化", "售电公司", "增量配电", "分布式",
    "国家发改委", "国家能源局", "国家电网", "南方电网", "蒙西电网", "电力交易中心",
    "电力交易员", "市场化交易", "电网企业", "发电企业", "电力用户", "新型经营主体",
    "储能", "抽水蓄能", "虚拟电厂", "负荷聚合商", "碳市场", "碳排放权",
]
for t in DOMAIN_TERMS:
    jieba.add_word(t)

# 单字噪声过滤（BM25 对中文单字无区分度）
_STOPWORDS = set("的了是在和与及或而但若则对于给从被把将向以按据沿线随着")


def tokenize(text: str) -> list[str]:
    """中文分词（BM25 专用）。过滤单字噪声和停用词。"""
    if not text:
        return []
    tokens = jieba.lcut(text)
    return [t.strip() for t in tokens if len(t.strip()) > 1 and t not in _STOPWORDS]


# ============ 内存 BM25 索引 ============

class BM25Index:
    """基于 DocChunk 的内存 BM25 索引。

    懒加载：首次检索时构建，之后增量更新。
    语料规模上万级以下时内存索引性能远优于数据库 LIKE。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._bm25: Optional[BM25Okapi] = None
        self._chunks: list = []       # 对应的 DocChunk 元数据
        self._tokenized: list = []    # 对应的分词结果
        self._doc_chunk_ids: set = set()  # 已索引的 chunk_id，用于增量判断
        self._built_at: float = 0

    def _need_rebuild(self, db: Session) -> bool:
        """检查是否需要重建（有新分块或首次构建）。"""
        if self._bm25 is None:
            return True
        from app.db.models import DocChunk
        # 检查最新分块数是否变化
        current_ids = set(db.execute(
            select(DocChunk.id).where(DocChunk.embedding.isnot(None))
        ).scalars().all())
        return current_ids != self._doc_chunk_ids

    def _build(self, db: Session):
        """构建/重建索引。"""
        from app.db.models import DocChunk, KnowledgeDoc

        chunks = db.execute(
            select(DocChunk).where(DocChunk.embedding.isnot(None))
        ).scalars().all()

        if not chunks:
            self._bm25 = None
            self._chunks = []
            self._tokenized = []
            self._doc_chunk_ids = set()
            logger.info("BM25索引：无分块数据")
            return

        # 预加载文档标题（标题参与BM25，提升精确匹配权重）
        doc_ids = list({c.doc_id for c in chunks})
        doc_map = {d.id: d.title for d in db.execute(
            select(KnowledgeDoc).where(KnowledgeDoc.id.in_(doc_ids))
        ).scalars().all()}

        corpus = []
        self._chunks = []
        self._doc_chunk_ids = set()
        for c in chunks:
            # 标题重复一次（权重加权：标题命中更重要）
            title = doc_map.get(c.doc_id, "")
            text = f"{title} {title} {c.text}"
            corpus.append(tokenize(text))
            self._chunks.append({
                "doc_id": c.doc_id, "chunk_text": c.text,
                "doc_type": c.doc_type, "province": c.province,
                "knowledge_point_id": c.knowledge_point_id,
            })
            self._doc_chunk_ids.add(c.id)

        self._bm25 = BM25Okapi(corpus)
        self._built_at = time.time()
        logger.info(f"BM25索引构建完成: {len(corpus)}个分块")

    def search(
        self, db: Session, query: str, top_k: int = 10,
        doc_type: Optional[str] = None, province: Optional[str] = None,
        knowledge_point_id: Optional[int] = None,
    ) -> list[dict]:
        """BM25 检索，返回 [{doc_id, chunk_text, score, doc_type, province}]。"""
        with self._lock:
            if self._need_rebuild(db):
                self._build(db)
            if self._bm25 is None:
                return []
            bm25 = self._bm25
            chunks = self._chunks

        tokens = tokenize(query)
        if not tokens:
            return []

        scores = bm25.get_scores(tokens)
        # 排序
        ranked = sorted(enumerate(scores), key=lambda x: -x[1])

        results = []
        seen_docs = set()
        for idx, score in ranked:
            if score <= 0:
                break
            ch = chunks[idx]
            # 应用过滤
            if doc_type and ch["doc_type"] != doc_type:
                continue
            if province and ch["province"] != province:
                continue
            if knowledge_point_id and ch["knowledge_point_id"] != knowledge_point_id:
                continue
            # 同文档去重（BM25 取最高分块）
            if ch["doc_id"] in seen_docs:
                continue
            seen_docs.add(ch["doc_id"])
            results.append({
                "doc_id": ch["doc_id"],
                "chunk_text": ch["chunk_text"],
                "score": round(float(score), 4),
                "doc_type": ch["doc_type"],
                "province": ch["province"],
                "_retriever": "bm25",
            })
            if len(results) >= top_k:
                break
        return results


# 全局单例
_bm25_index: Optional[BM25Index] = None
_bm25_lock = threading.Lock()


def get_bm25_index() -> BM25Index:
    global _bm25_index
    if _bm25_index is not None:
        return _bm25_index
    with _bm25_lock:
        if _bm25_index is None:
            _bm25_index = BM25Index()
    return _bm25_index


# ============ RRF 融合 ============

def reciprocal_rank_fusion(
    dense_results: list[dict],
    sparse_results: list[dict],
    top_k: int = 5,
    k: int = 60,
) -> list[dict]:
    """Reciprocal Rank Fusion（互逆排名融合）。

    不依赖原始分数（向量cosine和BM25分数量纲不同），
    只用排名：score_rrf = Σ 1/(k + rank_i)

    RRF 是混合检索最稳健的融合方法，无需调参，被Elasticsearch等生产系统采用。
    """
    doc_scores: dict = {}  # doc_id -> {rrf, info}

    for rank, r in enumerate(dense_results):
        did = r["doc_id"]
        rrf = 1.0 / (k + rank + 1)
        if did not in doc_scores:
            doc_scores[did] = {"rrf": 0, "info": r, "dense_rank": rank + 1, "sparse_rank": None}
        doc_scores[did]["rrf"] += rrf
        doc_scores[did]["info"] = r  # 保留信息

    for rank, r in enumerate(sparse_results):
        did = r["doc_id"]
        rrf = 1.0 / (k + rank + 1)
        if did not in doc_scores:
            doc_scores[did] = {"rrf": 0, "info": r, "dense_rank": None, "sparse_rank": rank + 1}
        doc_scores[did]["rrf"] += rrf
        if doc_scores[did]["sparse_rank"] is None:
            doc_scores[did]["sparse_rank"] = rank + 1
        # 如果BM25命中了但dense没命中，用BM25的chunk_text
        if doc_scores[did]["dense_rank"] is None:
            doc_scores[did]["info"] = r

    # 排序输出
    ranked = sorted(doc_scores.values(), key=lambda x: -x["rrf"])[:top_k]
    output = []
    for item in ranked:
        info = item["info"]
        info["score"] = round(item["rrf"], 4)
        info["score_rrf"] = round(item["rrf"], 4)
        info["dense_rank"] = item["dense_rank"]
        info["sparse_rank"] = item["sparse_rank"]
        output.append(info)
    return output
