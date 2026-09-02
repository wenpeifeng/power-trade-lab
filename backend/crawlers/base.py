"""爬虫基类 —— 所有数据源的统一框架。

职责：
- 限速（≤1 req/s，规避反爬）
- 去重（标题/URL hash）
- 入库（Policy 或 Question）
- 错误重试与日志

子类只需实现 fetch_items() 返回标准化数据。
"""
import hashlib
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import SessionLocal
from app.db.models import Policy, PolicyAttachment, Question

logger = logging.getLogger("crawler")


@dataclass
class CrawledPolicy:
    """爬取到的政策/公告标准化结构。"""
    title: str
    publish_date: Optional[str] = None
    publish_date_status: str = "unverified"
    publish_date_evidence: Optional[str] = None
    doc_number: Optional[str] = None
    category: str = "market"  # national/market/clearing/regulation
    province: Optional[str] = None
    source: str = ""
    source_url: Optional[str] = None
    content: Optional[str] = None
    ai_summary: Optional[str] = None
    priority: int = 0
    attachments: list = field(default_factory=list)  # [{filename, file_url, file_type}]


@dataclass
class CrawledQuestion:
    """爬取到的题目标准化结构。"""
    type: str  # single/multiple/judge
    stem: str
    options: list  # [{key, text, is_correct}]
    answer: str
    analysis: Optional[str] = None
    difficulty: int = 2
    knowledge_point_code: Optional[str] = None
    province: Optional[str] = None
    source: str = ""
    source_url: Optional[str] = None
    is_real_exam: bool = False
    exam_year: Optional[int] = None
    exam_level: Optional[str] = None
    prediction_tags: Optional[list] = None


class BaseCrawler(ABC):
    """爬虫基类。子类实现 fetch_items()。"""

    name: str = "base"
    rate_limit: float = 1.0  # 请求间隔秒

    def __init__(self, db: Optional[Session] = None):
        self.db = db or SessionLocal()
        self._last_request_time = 0

    def _throttle(self):
        """限速：距上次请求不足 rate_limit 秒则等待。"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self._last_request_time = time.time()

    @abstractmethod
    def fetch_items(self) -> tuple[list[CrawledPolicy], list[CrawledQuestion]]:
        """子类实现：返回 (policies, questions)。"""
        ...

    def run(self) -> dict:
        """执行爬取并入库。返回统计。"""
        logger.info(f"[{self.name}] 开始爬取...")
        stats = {"source": self.name, "policies_new": 0, "policies_dup": 0,
                 "questions_new": 0, "questions_dup": 0, "errors": 0}

        try:
            policies, questions = self.fetch_items()
        except Exception as e:
            logger.error(f"[{self.name}] 爬取失败: {e}")
            stats["errors"] = 1
            stats["error_msg"] = str(e)
            return stats

        # 政策入库（去重）
        for p in policies:
            if self._policy_exists(p):
                stats["policies_dup"] += 1
            else:
                self._save_policy(p)
                stats["policies_new"] += 1

        # 题目入库（去重）
        for q in questions:
            if self._question_exists(q):
                stats["questions_dup"] += 1
            else:
                self._save_question(q)
                stats["questions_new"] += 1

        self.db.commit()
        logger.info(f"[{self.name}] 完成: 政策+{stats['policies_new']}(重复{stats['policies_dup']}), "
                     f"题目+{stats['questions_new']}(重复{stats['questions_dup']})")
        return stats

    def _policy_dedup_key(self, p: CrawledPolicy) -> str:
        # 优先用 source_url(原文URL,全局唯一)做内容级去重；无URL再退回标题+日期。
        # 这样同一篇原文不管从第几页、抓多少次，只入库一次。
        raw = (p.source_url or "").strip() or f"{p.title}|{p.publish_date or ''}"
        return hashlib.md5(raw.encode()).hexdigest()[:16]

    def _policy_exists(self, p: CrawledPolicy) -> bool:
        key = self._policy_dedup_key(p)
        return self.db.query(Policy).filter(Policy.dedup_key == key).first() is not None

    def _save_policy(self, p: CrawledPolicy):
        from app.policy.ranking import classify_policy, infer_priority

        p.category = classify_policy(p.title, p.category)
        p.priority = infer_priority(p.title, p.category, p.priority)
        policy = Policy(
            title=p.title, publish_date=p.publish_date, doc_number=p.doc_number,
            publish_date_status=p.publish_date_status,
            publish_date_evidence=p.publish_date_evidence,
            publish_date_verified_at=(
                datetime.now().astimezone().isoformat()
                if p.publish_date_status == "verified" else None
            ),
            category=p.category, province=p.province, source=p.source or self.name,
            source_url=p.source_url, content=p.content, ai_summary=p.ai_summary,
            priority=p.priority, dedup_key=self._policy_dedup_key(p), is_read=False,
        )
        self.db.add(policy)
        self.db.flush()
        for att in p.attachments:
            self.db.add(PolicyAttachment(
                policy_id=policy.id, filename=att.get("filename", ""),
                file_type=att.get("file_type", ""), file_url=att.get("file_url"),
            ))
        # 数据汇流：同步写入 KnowledgeDoc，让资产中心看到爬虫数据
        self._mirror_to_knowledge_doc(p)

    def _mirror_to_knowledge_doc(self, p: CrawledPolicy):
        """把爬虫抓到的政策汇流到统一数据资产表 KnowledgeDoc。

        保证定时爬虫(原落 Policy 表)与手动 ingest(落 KnowledgeDoc 表)
        两条通道在资产中心统一可见。
        """
        try:
            from app.db.models import KnowledgeDoc
            from app.knowledge.classifier import auto_classify
            dedup = self._policy_dedup_key(p)
            exists = self.db.query(KnowledgeDoc).filter(KnowledgeDoc.dedup_key == dedup).first()
            if exists:
                # 原文元数据是权威值；修复过的标题/日期应同步到资产层，
                # 不能继续保留首次抓取时的列表日期或被截断标题。
                if p.title:
                    exists.title = p.title
                if p.publish_date_status == "verified":
                    exists.publish_date = p.publish_date
                if p.source_url:
                    exists.source_url = p.source_url
                return
            classify = auto_classify(p.title, p.content or "")
            doc = KnowledgeDoc(
                title=p.title,
                doc_type={"national": "national_policy", "market": "exchange_info",
                          "clearing": "exchange_info", "regulation": "regulation"}.get(
                    p.category, "industry_news"),
                province=p.province,
                publish_date=p.publish_date,
                doc_number=p.doc_number,
                source=p.source or self.name,
                source_url=p.source_url,
                content=p.content,
                ai_summary=p.ai_summary,
                ingest_type="crawler",
                review_status="pending",  # 外部爬虫数据先审后用：审核通过才进可信层对上层可见
                category_code=classify.get("category_code"),
                facet_tags=__import__("json").dumps(
                    classify.get("facet_tags", {}), ensure_ascii=False),
                dedup_key=dedup,
            )
            self.db.add(doc)
            self.db.flush()
            # 同步向量化（失败不影响主流程）
            try:
                from app.knowledge.embedding import vectorize_document
                vectorize_document(self.db, doc.id)
            except Exception as ve:
                logger.debug(f"向量化失败(不影响入库): {ve}")
        except Exception as e:
            logger.debug(f"汇流到KnowledgeDoc失败(不影响主流程): {e}")

    def _question_dedup_key(self, q: CrawledQuestion) -> str:
        return hashlib.md5(q.stem.encode()).hexdigest()[:16]

    def _question_exists(self, q: CrawledQuestion) -> bool:
        key = self._question_dedup_key(q)
        return self.db.query(Question).filter(Question.stem_hash == key).first() is not None

    def _save_question(self, q: CrawledQuestion):
        import json
        from app.db.models import KnowledgePoint

        kp_id = None
        if q.knowledge_point_code:
            kp = self.db.query(KnowledgePoint).filter(
                KnowledgePoint.code == q.knowledge_point_code
            ).first()
            if kp:
                kp_id = kp.id

        question = Question(
            type=q.type, stem=q.stem,
            options=json.dumps(q.options, ensure_ascii=False),
            answer=q.answer, analysis=q.analysis, difficulty=q.difficulty,
            knowledge_point_id=kp_id, province=q.province,
            source=q.source or self.name, source_type="crawler",
            is_real_exam=q.is_real_exam, exam_year=q.exam_year, exam_level=q.exam_level,
            prediction_tags=json.dumps(q.prediction_tags, ensure_ascii=False) if q.prediction_tags else None,
            stem_hash=self._question_dedup_key(q),
        )
        self.db.add(question)
