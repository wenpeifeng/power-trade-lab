"""向量知识库引擎 —— 分块 + 向量化 + 语义检索 + 混合召回。

三层架构：
1. Chunker：把文档切成语义分块（每块~300字，带重叠）
2. Embedder：本地 sentence-transformers 模型向量化（中文语义）
3. Retriever：查询→向量化→余弦相似度→召回topK

混合检索（推荐）：dense(向量语义) + sparse(BM25关键词) → RRF融合
  - 向量捕捉语义（"电价怎么算"→"结算规则"）
  - BM25 精确匹配文号/代号/术语（"143号文""LMP""SD003"）

模型可配置：语料小时用 bge-small-zh（快），语料大了切 bge-m3（准）。
重排预留：rerank() 接口已留，语料 200+ 篇后接入 Cross-Encoder。

设计目标：支撑AI助手问答召回、学习知识关联、交易规则检索、政策归纳。
"""
import hashlib
import json
import logging
import os
import threading
from typing import Optional

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings

logger = logging.getLogger("vector_kb")

# 国内镜像（huggingface.co 国内不可达，走 hf-mirror.com）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
# 模型已缓存到本地，强制离线：禁止加载时联网检查更新。
# 否则 sentence-transformers 每次加载都会去 HF/镜像校验，网络不稳时会卡几十秒~几分钟，
# 直接拖垮首次 RAG 检索 → 前端 AI 问答超时。实测：联网 >7min 未完成，离线仅 3.5s。
# 若日后要下载「未缓存」的新模型（如 bge-m3），临时用 HF_HUB_OFFLINE=0 启动一次即可。
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

# ============ 可配置项（语料大了随时切模型，不改代码）============
# 当前语料 <500 篇：bge-small-zh-v1.5（512维，轻量，已缓存）
# 语料 500+ 篇后切：BAAI/bge-m3（1024维，多语言，更准但2.3GB）
EMBEDDING_MODEL_NAME = settings.KB_EMBEDDING_MODEL
EMBEDDING_DIM = settings.KB_EMBEDDING_DIM
CHUNK_SIZE = 300      # 每块约300字
CHUNK_OVERLAP = 50    # 块间重叠50字，保证语义连贯

_embedder = None
_embedder_lock = threading.Lock()


# ============ Embedder（本地语义模型，懒加载）============

def get_embedder():
    """获取embedding模型（懒加载，首次调用时加载，线程安全）。"""
    global _embedder
    if _embedder is not None:
        return _embedder
    with _embedder_lock:
        if _embedder is not None:
            return _embedder
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"加载embedding模型: {EMBEDDING_MODEL_NAME}")
            _embedder = SentenceTransformer(EMBEDDING_MODEL_NAME)
            logger.info(f"模型加载完成，维度={_embedder.get_sentence_embedding_dimension()}")
        except Exception as e:
            logger.warning(f"embedding模型加载失败，降级TF-IDF: {e}")
            _embedder = _TFIDFFallback()
    return _embedder


class _TFIDFFallback:
    """无sentence-transformers时的TF-IDF降级方案。"""
    def __init__(self):
        from sklearn.feature_extraction.text import TfidfVectorizer
        self.vectorizer = TfidfVectorizer(max_features=EMBEDDING_DIM, token_pattern=r"(?u)\b\w+\b")
        self.fitted = False
        self.name = "tfidf-fallback"

    def encode(self, texts):
        import numpy as np
        texts = list(texts)
        if not self.fitted:
            self.vectors = self.vectorizer.fit_transform(texts).toarray()
            self.fitted = True
        else:
            self.vectors = self.vectorizer.transform(texts).toarray()
        return self.vectors

    def get_sentence_embedding_dimension(self):
        return EMBEDDING_DIM


def embed_texts(texts: list[str]) -> list[list[float]]:
    """文本批量向量化。返回float数组列表。"""
    if not texts:
        return []
    embedder = get_embedder()
    vectors = embedder.encode(texts)
    # 归一化（便于余弦相似度=点积）
    if hasattr(vectors, 'tolist'):
        vectors = vectors.tolist()
    else:
        vectors = [list(v) for v in vectors]
    return vectors


def embed_query(text: str) -> list[float]:
    """单条查询向量化。"""
    return embed_texts([text])[0]


# ============ Chunker（文档分块）============

def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """把长文本切成重叠的语义块。

    改进版策略（修复审查发现的问题）：
    1. 按句号/问号/换行/分号/**逗号**切句（之前逗号不切导致超长块）
    2. 超长句（>size）硬切（之前单句>300字直接成超大块）
    3. 重叠按**句子对齐**（之前按字符[-50:]会切断词语，破坏分词）
    4. 过滤超短块（<20字的噪声块不入库）
    """
    if not text:
        return []
    text = text.strip()
    if len(text) <= size:
        return [text] if len(text) >= 20 else []

    import re
    # 按句号/问号/换行/分号/逗号切句（增加了逗号和冒号）
    sentences = re.split(r'(?<=[。！？\n；;，,：:])', text)
    sentences = [s.strip() for s in sentences if s.strip()]

    # 超长句硬切（防止单句>size产生超大块）
    processed = []
    for s in sentences:
        if len(s) > size:
            for i in range(0, len(s), size - overlap):
                piece = s[i:i + size]
                if len(piece) >= 20:
                    processed.append(piece)
        else:
            processed.append(s)

    chunks = []
    current = ""
    overlap_sentences = []  # 按句子对齐的重叠
    for sent in processed:
        candidate = current + sent if current else sent
        if len(candidate) >= size:
            chunks.append(candidate)
            # 重叠：保留尾部几个句子（而非字符），保证语义完整
            if overlap > 0:
                overlap_sentences = []
                rev_len = 0
                for s in reversed(processed[:processed.index(sent) + 1] if sent in processed else []):
                    rev_len += len(s)
                    overlap_sentences.insert(0, s)
                    if rev_len >= overlap:
                        break
                current = "".join(overlap_sentences)
            else:
                current = ""
        else:
            current = candidate
    if current and len(current) >= 20:
        chunks.append(current)

    # 最终过滤：丢弃超短噪声块
    return [c for c in chunks if len(c) >= 20]


# ============ 向量化文档（入库流水线）============

def vectorize_document(db: Session, doc_id: int) -> dict:
    """把一篇文档分块+向量化+入库。

    供 ingest 流水线调用：文档入库后自动调用此函数建索引。
    """
    from app.db.models import DocChunk, KnowledgeDoc

    doc = db.get(KnowledgeDoc, doc_id)
    if not doc:
        return {"ok": False, "error": "文档不存在"}
    if not doc.content or len(doc.content) < 10:
        return {"ok": False, "error": "文档内容过短"}

    # 先清除旧分块（重建索引时用）
    db.query(DocChunk).filter(DocChunk.doc_id == doc_id).delete()
    db.flush()

    # 分块
    chunks = chunk_text(doc.content)
    if not chunks:
        return {"ok": False, "error": "分块结果为空"}

    # 二次过滤：确保入库分块都≥20字（防歛建索引后产生噪声块）
    chunks = [c for c in chunks if len(c) >= 20]
    if not chunks:
        return {"ok": False, "error": "过滤后无有效分块（原文过短）"}

    # 批量向量化
    try:
        embeddings = embed_texts(chunks)
    except Exception as e:
        logger.error(f"向量化失败: {e}")
        return {"ok": False, "error": f"向量化失败: {e}"}

    # 入库
    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        chunk_hash = hashlib.md5(chunk.encode()).hexdigest()[:16]
        db.add(DocChunk(
            doc_id=doc_id, chunk_index=i, text=chunk,
            embedding=json.dumps(emb),
            embedding_model=EMBEDDING_MODEL_NAME,
            chunk_hash=chunk_hash,
            doc_type=doc.doc_type, province=doc.province,
            knowledge_point_id=doc.knowledge_point_id,
        ))
    db.commit()
    logger.info(f"文档{doc_id}向量化完成: {len(chunks)}块")
    return {"ok": True, "doc_id": doc_id, "chunks": len(chunks)}


# ============ 语义检索召回 ============

def retrieve(
    db: Session, query: str, top_k: int = 5,
    doc_type: Optional[str] = None, province: Optional[str] = None,
    knowledge_point_id: Optional[int] = None,
    mode: str = "hybrid",
) -> list[dict]:
    """知识库检索（支持三种模式）。

    模式：
    - hybrid（推荐，默认）：向量语义 + BM25关键词 → RRF融合。兼顾语义理解和精确词命中
    - dense：纯向量语义检索（捕捉"意思相近"的文档）
    - sparse：纯BM25关键词检索（精确匹配文号/代号/术语）

    支撑过滤维度（类型/省份/知识点），支撑四个场景：
    - AI问答召回：query=用户问题，mode=hybrid
    - 学习关联：knowledge_point_id 过滤
    - 交易规则：doc_type=regulation/exchange_info + province 过滤
    - 政策归纳：相似政策聚类，mode=dense

    为什么默认 hybrid：
    电力文档有大量精确词（"143号文""LMP""SD003""节点电价"），
    纯向量检索会漏掉这些精确匹配；BM25 正好补上。
    """
    from app.db.models import DocChunk, KnowledgeDoc

    # ---- 稀疏检索（BM25）----
    sparse_results = []
    if mode in ("hybrid", "sparse"):
        from app.knowledge.bm25_retriever import get_bm25_index
        bm25 = get_bm25_index()
        sparse_results = bm25.search(
            db, query, top_k=top_k * 2,
            doc_type=doc_type, province=province,
            knowledge_point_id=knowledge_point_id,
        )

    # ---- 稠密检索（向量语义）----
    dense_results = []
    if mode in ("hybrid", "dense"):
        # 诚实化：当活跃 embedder 是 TF-IDF 降级方案时，所谓"稠密语义"
        # 实际是词频匹配。仅记录一次 debug，不改检索行为。
        embedder = get_embedder()
        if isinstance(embedder, _TFIDFFallback):
            logger.debug("dense mode requested but only TF-IDF available — results are lexical")
        dense_results = _dense_retrieve(
            db, query, top_k=top_k * 2,
            doc_type=doc_type, province=province,
            knowledge_point_id=knowledge_point_id,
        )

    # ---- 纯模式直接返回 ----
    if mode == "sparse":
        return _enrich_results(db, sparse_results[:top_k])
    if mode == "dense":
        return _enrich_results(db, dense_results[:top_k])

    # ---- 混合：RRF 融合 ----
    if not dense_results and not sparse_results:
        return []
    from app.knowledge.bm25_retriever import reciprocal_rank_fusion
    fused = reciprocal_rank_fusion(dense_results, sparse_results, top_k=top_k)
    return _enrich_results(db, fused)


def _dense_retrieve(
    db: Session, query: str, top_k: int = 10,
    doc_type: Optional[str] = None, province: Optional[str] = None,
    knowledge_point_id: Optional[int] = None,
) -> list[dict]:
    """纯向量语义检索（内部）。"""
    from app.db.models import DocChunk

    query_vec = embed_query(query)

    stmt = select(DocChunk)
    if doc_type:
        stmt = stmt.where(DocChunk.doc_type == doc_type)
    if province:
        stmt = stmt.where(DocChunk.province == province)
    if knowledge_point_id:
        stmt = stmt.where(DocChunk.knowledge_point_id == knowledge_point_id)
    stmt = stmt.where(DocChunk.embedding.isnot(None))

    chunks = db.execute(stmt).scalars().all()
    if not chunks:
        return []

    query_arr = np.array(query_vec)
    results = []
    for ch in chunks:
        try:
            chunk_vec = np.array(json.loads(ch.embedding))
            if len(chunk_vec) != len(query_arr):
                continue
            sim = float(np.dot(query_arr, chunk_vec) /
                        (np.linalg.norm(query_arr) * np.linalg.norm(chunk_vec) + 1e-8))
            results.append({
                "doc_id": ch.doc_id,
                "chunk_text": ch.text,
                "score": round(sim, 4),
                "doc_type": ch.doc_type,
                "province": ch.province,
                "_retriever": "dense",
            })
        except (json.JSONDecodeError, ValueError):
            continue

    results.sort(key=lambda x: -x["score"])
    # 同文档去重（取最高分块）
    seen = set()
    deduped = []
    for r in results:
        if r["doc_id"] in seen:
            continue
        seen.add(r["doc_id"])
        deduped.append(r)
    return deduped[:top_k]


def _enrich_results(db: Session, results: list[dict]) -> list[dict]:
    """补全文档标题、来源等元信息（稠密/BM25结果统一加工）。
    同时做可信层过滤：AI 检索只保留已过审(approved)文档，
    未审核/驳回数据不进入 AI 决策链路（交易决策不能基于未核实数据）。"""
    from app.db.models import KnowledgeDoc
    doc_cache = {}
    enriched = []
    for r in results:
        did = r["doc_id"]
        if did not in doc_cache:
            doc_cache[did] = db.get(KnowledgeDoc, did)
        doc = doc_cache[did]
        if doc is not None and getattr(doc, "review_status", "approved") != "approved":
            continue  # 未过审数据不给 AI 用
        r["title"] = doc.title if doc else ""
        r["source"] = doc.source if doc else ""
        r["publish_date"] = doc.publish_date if doc else ""
        if "doc_type" not in r:
            r["doc_type"] = doc.doc_type if doc else None
        if "province" not in r:
            r["province"] = doc.province if doc else None
        enriched.append(r)
    return enriched


# ============ 重排预留（语料 200+ 篇后启用）============

_reranker = None
_reranker_lock = threading.Lock()


def rerank(query: str, documents: list[dict], top_k: int = 5) -> list[dict]:
    """Cross-Encoder 重排（预留接口）。

    当前：语料 <200 篇，召回候选少，直接按现有分数返回，不引入重排。
    未来：语料大了、召回候选 >50 时，加载 BGE-reranker-base 做精排。

    启用方式（未来）：
      export KB_RERANKER_MODEL=BAAI/bge-reranker-base
    """
    global _reranker
    reranker_model = settings.KB_RERANKER_MODEL

    # 未配置重排模型 → 直接返回（当前阶段）
    if not reranker_model:
        return documents[:top_k]

    # 配置了才加载（预留）
    with _reranker_lock:
        if _reranker is None:
            try:
                from sentence_transformers import CrossEncoder
                _reranker = CrossEncoder(reranker_model)
                logger.info(f"重排模型加载: {reranker_model}")
            except Exception as e:
                logger.warning(f"重排模型加载失败，跳过重排: {e}")
                return documents[:top_k]

    pairs = [(query, d.get("chunk_text", "")) for d in documents]
    scores = _reranker.predict(pairs)
    for d, s in zip(documents, scores):
        d["rerank_score"] = round(float(s), 4)
    documents.sort(key=lambda x: -x.get("rerank_score", 0))
    return documents[:top_k]
