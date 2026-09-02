"""知识库沉淀与检索服务。

核心能力：
1. 沉淀：爬取内容 → 清洗分类 → AI摘要 → 存 KnowledgeDoc
2. 检索：按省份/类型/时间/关键词全文搜索
3. 关联：自动关联知识点，形成「政策→知识→题目」网络
4. 公共数据：出清价/负荷等时序数据查询
"""
import hashlib
import json
import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import case, func, literal, or_, select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import (
    KnowledgeDoc,
    KnowledgePoint,
    KnowledgePointPrerequisite,
    PublicData,
    User,
)
from app.common.auth import get_current_user, require_admin
from app.common.input_security import UnsafeInputError, validate_outbound_url
from app.knowledge.ordering import knowledge_doc_order_by

logger = logging.getLogger("knowledge")
router = APIRouter(prefix="/knowledge", tags=["知识库"])


# ============ 知识库文档检索 ============

@router.get("/docs", summary="知识库文档列表(多维筛选+全文搜索)")
def list_docs(
    q: Optional[str] = Query(None, max_length=200, description="全文搜索关键词"),
    doc_type: Optional[str] = None,
    province: Optional[str] = None,
    region: Optional[str] = None,
    knowledge_point_id: Optional[int] = None,
    days: Optional[int] = None,
    starred_only: bool = False,
    only_approved: bool = True,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """知识库文档检索，支持全文搜索和多维筛选。"""
    stmt = select(KnowledgeDoc)
    if only_approved:
        # 可信层：只返回已过审数据（爬虫数据默认 pending，审核后才可见）
        stmt = stmt.where(KnowledgeDoc.review_status == "approved")
    if q:
        # 全文搜索：标题或内容包含关键词
        kw = f"%{q}%"
        stmt = stmt.where(
            or_(KnowledgeDoc.title.like(kw), KnowledgeDoc.content.like(kw),
                KnowledgeDoc.ai_summary.like(kw), KnowledgeDoc.ai_keywords.like(kw))
        )
    if doc_type:
        stmt = stmt.where(KnowledgeDoc.doc_type == doc_type)
    if province:
        stmt = stmt.where(KnowledgeDoc.province == province)
    if region:
        stmt = stmt.where(KnowledgeDoc.region == region)
    if knowledge_point_id:
        stmt = stmt.where(KnowledgeDoc.knowledge_point_id == knowledge_point_id)
    if starred_only:
        stmt = stmt.where(KnowledgeDoc.is_starred.is_(True))
    if days:
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        stmt = stmt.where(KnowledgeDoc.publish_date >= cutoff)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0
    stmt = stmt.order_by(*knowledge_doc_order_by())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    items = db.execute(stmt).scalars().all()
    return {
        "total": total, "page": page, "page_size": page_size,
        "items": [_doc_brief(d) for d in items],
    }


@router.get("/docs/{doc_id}", summary="文档详情")
def get_doc(doc_id: int, db: Session = Depends(get_db)):
    d = db.get(KnowledgeDoc, doc_id)
    if not d or d.review_status != "approved":
        raise HTTPException(status_code=404, detail="文档不存在")
    d.view_count += 1
    db.commit()
    return _doc_detail(d)


@router.post("/docs/{doc_id}/star", summary="收藏/取消收藏")
def toggle_star(
    doc_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    d = db.get(KnowledgeDoc, doc_id)
    if not d or d.review_status != "approved":
        raise HTTPException(status_code=404, detail="文档不存在")
    d.is_starred = not d.is_starred
    db.commit()
    return {"ok": True, "starred": d.is_starred}


@router.get("/facets", summary="筛选项(类型/省份/区域 + 数量)")
def facets(db: Session = Depends(get_db)):
    """返回各类型、省份、区域的文档数，供前端筛选面板。"""
    type_counts = db.execute(
        select(KnowledgeDoc.doc_type, func.count())
        .where(KnowledgeDoc.review_status == "approved")
        .group_by(KnowledgeDoc.doc_type)
    ).all()
    province_counts = db.execute(
        select(KnowledgeDoc.province, func.count())
        .where(
            KnowledgeDoc.province.isnot(None),
            KnowledgeDoc.review_status == "approved",
        ).group_by(KnowledgeDoc.province)
    ).all()
    region_counts = db.execute(
        select(KnowledgeDoc.region, func.count())
        .where(
            KnowledgeDoc.region.isnot(None),
            KnowledgeDoc.review_status == "approved",
        ).group_by(KnowledgeDoc.region)
    ).all()
    return {
        "doc_types": [{"key": t, "count": n} for t, n in type_counts],
        "provinces": [{"key": p, "count": n} for p, n in province_counts if p],
        "regions": [{"key": r, "count": n} for r, n in region_counts if r],
    }


# ============ 公共数据查询 ============

@router.get("/public-data", summary="公共数据查询(出清价/负荷/煤价/碳价)")
def query_public_data(
    data_type: str = Query(..., description="clearing/coal/carbon/load/renewable"),
    province: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """查询结构化公共数据。"""
    stmt = select(PublicData).where(PublicData.data_type == data_type)
    if province:
        stmt = stmt.where(PublicData.province == province)
    if start_date:
        stmt = stmt.where(PublicData.data_date >= start_date)
    if end_date:
        stmt = stmt.where(PublicData.data_date <= end_date)
    stmt = stmt.order_by(PublicData.data_date.desc()).limit(limit)
    items = db.execute(stmt).scalars().all()
    return {
        "data_type": data_type, "count": len(items),
        "items": [
            {
                "date": d.data_date,
                "province": d.province,
                "metrics": _safe_json(d.metrics),
                "source": d.source,
                "source_url": d.source_url,
                "provenance_level": d.provenance_level,
                "disclosure_scope": d.disclosure_scope,
                "fetched_at": d.fetched_at,
                "quality_status": d.quality_status,
                "raw_sha256": d.raw_sha256,
            }
            for d in items
        ],
    }


# ============ 知识网络：政策→知识点→题目关联 ============

@router.get("/network/{doc_id}", summary="文档的知识网络(关联知识点和题目)")
def knowledge_network(doc_id: int, db: Session = Depends(get_db)):
    """展示一篇文档关联的知识点和相关题目，形成知识网络。"""
    from app.db.models import Question
    d = db.get(KnowledgeDoc, doc_id)
    if not d or d.review_status != "approved":
        raise HTTPException(status_code=404, detail="文档不存在")
    kp = db.get(KnowledgePoint, d.knowledge_point_id) if d.knowledge_point_id else None
    related_questions = []
    prerequisites: list[dict] = []
    if kp:
        qs = db.execute(
            select(Question).where(Question.knowledge_point_id == kp.id).limit(5)
        ).scalars().all()
        related_questions = [{"id": q.id, "stem": q.stem[:60], "type": q.type} for q in qs]
        # 前置知识点：学这个 KP 之前应先懂哪些
        prereqs = db.execute(
            select(KnowledgePoint)
            .join(KnowledgePointPrerequisite,
                  KnowledgePointPrerequisite.prereq_kp_id == KnowledgePoint.id)
            .where(KnowledgePointPrerequisite.kp_id == kp.id)
        ).scalars().all()
        prerequisites = [
            {"id": p.id, "code": p.code, "name": p.name} for p in prereqs
        ]
    return {
        "doc": _doc_brief(d),
        "knowledge_point": {"id": kp.id, "name": kp.name} if kp else None,
        "related_questions": related_questions,
        "prerequisites": prerequisites,
    }


# ============ 沉淀接口（供爬虫调用）============


@router.get("/prerequisites/{kp_code}", summary="某知识点的前置知识点(学这个之前先懂…)")
def list_prerequisites(kp_code: str, db: Session = Depends(get_db)):
    """返回某知识点的前置知识点列表，供前端展示学习路径。"""
    kp = db.execute(
        select(KnowledgePoint).where(KnowledgePoint.code == kp_code)
    ).scalars().first()
    if not kp:
        raise HTTPException(status_code=404, detail="知识点不存在")
    prereqs = db.execute(
        select(KnowledgePoint)
        .join(KnowledgePointPrerequisite,
              KnowledgePointPrerequisite.prereq_kp_id == KnowledgePoint.id)
        .where(KnowledgePointPrerequisite.kp_id == kp.id)
    ).scalars().all()
    return {
        "kp": {"id": kp.id, "code": kp.code, "name": kp.name},
        "prerequisites": [
            {
                "id": p.id,
                "code": p.code,
                "name": p.name,
                "description": p.description,
            }
            for p in prereqs
        ],
    }


class SedimentReq(BaseModel):
    """爬虫抓取后调用此接口沉淀到知识库。"""
    title: str = Field(..., min_length=2, max_length=500)
    doc_type: str = Field(..., min_length=2, max_length=30)
    province: Optional[str] = None
    region: Optional[str] = None
    grid: Optional[str] = None
    publish_date: Optional[str] = None
    doc_number: Optional[str] = None
    source: str = ""
    source_url: Optional[str] = None
    content: Optional[str] = Field(None, max_length=2_000_000)
    ai_summary: Optional[str] = Field(None, max_length=10_000)
    ai_keywords: Optional[list[str]] = None
    knowledge_point_code: Optional[str] = None
    tags: Optional[list[str]] = None


@router.post("/sediment", summary="沉淀文档到知识库(爬虫调用)")
def sediment(
    req: SedimentReq,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """爬虫抓取后，清洗分类沉淀到知识库。自动去重。"""
    dedup = hashlib.md5(f"{req.title}|{req.publish_date or ''}".encode()).hexdigest()[:16]
    exists = db.execute(
        select(KnowledgeDoc).where(KnowledgeDoc.dedup_key == dedup)
    ).scalars().first()
    if exists:
        return {"ok": True, "dedup": True, "id": exists.id}

    # 关联知识点
    kp_id = None
    if req.knowledge_point_code:
        kp = db.execute(
            select(KnowledgePoint).where(KnowledgePoint.code == req.knowledge_point_code)
        ).scalars().first()
        if kp:
            kp_id = kp.id

    doc = KnowledgeDoc(
        title=req.title, doc_type=req.doc_type, province=req.province,
        region=req.region, grid=req.grid, publish_date=req.publish_date,
        doc_number=req.doc_number, source=req.source, source_url=req.source_url,
        content=req.content, ai_summary=req.ai_summary,
        ai_keywords=json.dumps(req.ai_keywords, ensure_ascii=False) if req.ai_keywords else None,
        knowledge_point_id=kp_id,
        tags=json.dumps(req.tags, ensure_ascii=False) if req.tags else None,
        dedup_key=dedup,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return {"ok": True, "dedup": False, "id": doc.id}


# ============ 附件下载 ============

@router.get("/attachments/{att_id}/download", summary="下载附件原文")
def download_attachment(att_id: int, db: Session = Depends(get_db)):
    """下载知识库文档的附件原文（PDF/Word等）。"""
    import os
    from fastapi.responses import FileResponse
    from app.db.models import AssetAttachment

    att = db.get(AssetAttachment, att_id)
    if not att or not att.doc or att.doc.review_status != "approved":
        raise HTTPException(status_code=404, detail="附件不存在")
    # 优先本地文件，其次远程URL
    if att.local_path and os.path.exists(att.local_path):
        return FileResponse(
            att.local_path, filename=att.filename,
            media_type="application/octet-stream",
        )
    if att.file_url:
        from fastapi.responses import RedirectResponse
        try:
            safe_url = validate_outbound_url(att.file_url)
        except UnsafeInputError as exc:
            raise HTTPException(status_code=400, detail="附件原始地址不安全") from exc
        return RedirectResponse(safe_url)
    raise HTTPException(status_code=404, detail="附件文件不存在")


# ============ 工具 ============

def _doc_brief(d: KnowledgeDoc) -> dict:
    return {
        "id": d.id, "title": d.title, "doc_type": d.doc_type,
        "province": d.province, "region": d.region,
        "category_code": d.category_code,
        "facet_tags": _safe_json(d.facet_tags),
        "publish_date": d.publish_date, "doc_number": d.doc_number,
        "source": d.source, "ai_summary": d.ai_summary,
        "view_count": d.view_count, "is_starred": d.is_starred,
        "tags": _safe_json(d.tags),
    }


def _doc_detail(d: KnowledgeDoc) -> dict:
    data = _doc_brief(d)
    # 附件列表（开放浏览可下载原文）
    attachments = []
    if d.attachments:
        for a in d.attachments:
            attachments.append({
                "id": a.id, "filename": a.filename,
                "file_type": a.file_type, "file_url": a.file_url,
            })
    data.update({
        "source_url": d.source_url,
        "content": d.content,
        "ai_keywords": _safe_json(d.ai_keywords),
        "grid": d.grid,
        "ingest_type": d.ingest_type,
        "attachments": attachments,
    })
    return data


def _safe_json(s):
    if not s:
        return None
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return None


# ============ 语义检索（AI检索召回）============

@router.get("/by-concept", summary="按概念标题召回相关原文(进阶/专家溯源)")
def by_concept(
    title: str = Query(..., min_length=1, max_length=200, description="概念标题（前端 curriculum 的 title，如「双边协商」）"),
    kp: Optional[str] = Query(None, description="知识点 code（如 mid_long_term），命中则加权"),
    limit: int = Query(3, ge=1, le=10),
    db: Session = Depends(get_db),
):
    """为知识书概念文章召回 2-3 篇最相关的真实文档，供进阶/专家级读者溯源。

    策略（简单且可靠）：
    - 在 approved 文档的 title/content/ai_summary/ai_keywords 上做关键词 ILIKE 搜索，
      query 取概念标题整体（中文描述性标题如「双边协商」本身就是强信号）。
    - 若给出 ``kp``（知识点 code）：先解析为 knowledge_point_id，对命中该 KP 的文档加权
      （排到前面），但不硬过滤——避免 KP 映射缺失时召回为空。
    - 按发布日期倒排，取前 ``limit`` 篇。
    - 复用 ``_doc_brief``，并补 ``source_url`` 供前端「查看原文」外链。
    """
    kw = f"%{title.strip()}%"
    stmt = (
        select(KnowledgeDoc)
        .where(KnowledgeDoc.review_status == "approved")
        .where(
            or_(
                KnowledgeDoc.title.like(kw),
                KnowledgeDoc.content.like(kw),
                KnowledgeDoc.ai_summary.like(kw),
                KnowledgeDoc.ai_keywords.like(kw),
            )
        )
    )

    # 解析 kp code -> id（用于加权，失败静默）
    kp_id: Optional[int] = None
    if kp:
        kp_row = db.execute(
            select(KnowledgePoint).where(KnowledgePoint.code == kp)
        ).scalars().first()
        if kp_row:
            kp_id = kp_row.id

    # 加权排序：命中该 KP 的文档排前（0），其余排后（1）；再按发布日期倒排
    if kp_id is not None:
        kp_priority = case(
            (KnowledgeDoc.knowledge_point_id == kp_id, 0),
            else_=1,
        )
    else:
        kp_priority = literal(0)
    unknown_date = case(
        (
            or_(
                KnowledgeDoc.publish_date.is_(None),
                KnowledgeDoc.publish_date == "",
            ),
            1,
        ),
        else_=0,
    )
    stmt = stmt.order_by(
        kp_priority,
        unknown_date,
        KnowledgeDoc.publish_date.desc(),
        KnowledgeDoc.id.desc(),
    ).limit(limit)

    items = db.execute(stmt).scalars().all()
    return {
        "title": title, "kp": kp, "count": len(items),
        "items": [{**_doc_brief(d), "source_url": d.source_url} for d in items],
    }


@router.get("/search", summary="知识库检索(混合:向量语义+BM25关键词)")
def semantic_search(
    q: str = Query(..., min_length=1, max_length=500, description="查询文本（自然语言或关键词）"),
    top_k: int = Query(5, ge=1, le=20),
    mode: str = Query("hybrid", description="检索模式: hybrid(混合,默认)/dense(纯语义)/sparse(纯BM25)"),
    doc_type: Optional[str] = None,
    province: Optional[str] = None,
    knowledge_point_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """知识库检索，三种模式可切换：

    - **hybrid（默认，推荐）**：向量语义 + BM25关键词，RRF融合。
      既能理解"电价怎么算"的语义，也能精确命中"143号文""LMP"等代号。
    - **dense**：纯向量语义检索。适合找"意思相近"的文档。
    - **sparse**：纯BM25关键词检索。适合精确匹配文号/条款/术语。

    支撑场景：
    - AI助手问答：q=用户问题，mode=hybrid，返回最相关的知识片段
    - 学习关联：传 knowledge_point_id 过滤某知识点的资料
    - 交易规则：doc_type=regulation + province 过滤适用规则
    """
    from app.knowledge.embedding import retrieve
    results = retrieve(db, q, top_k=top_k, mode=mode,
                       doc_type=doc_type, province=province,
                       knowledge_point_id=knowledge_point_id)
    return {"query": q, "mode": mode, "count": len(results), "results": results}


@router.post("/rebuild-index", summary="重建向量索引(全量向量化)")
def rebuild_index(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """对所有文档重新分块+向量化。新增文档后或切换模型后执行。"""
    from app.knowledge.embedding import vectorize_document

    docs = db.execute(select(KnowledgeDoc)).scalars().all()
    success, fail = 0, 0
    for d in docs:
        result = vectorize_document(db, d.id)
        if result.get("ok"):
            success += 1
        else:
            fail += 1
    return {"ok": True, "total": len(docs), "success": success, "fail": fail}


@router.get("/search-status", summary="检索引擎状态(诚实化:语义是否可用)")
def search_status():
    """报告当前知识库检索后端使用的引擎，供前端诚实标注。

    embedder 取值：
    - ``uninitialized``：embedder 尚未懒加载（首次检索前）；``semantic_available``
      反映 sentence-transformers 是否可导入（安装了但未必加载成功）。
    - ``tfidf``：sentence-transformers 加载失败，降级为 TF-IDF 词频匹配，
      ``semantic_available=false``。
    - ``sentence-transformer``：真实语义模型在线，``semantic_available=true``，
      ``model_name`` 为 EMBEDDING_MODEL_NAME。

    本端点不强制加载 embedder —— 仅当它已被某次检索初始化时才报实际引擎，
    否则报 ``uninitialized``，避免一次状态查询触发模型加载。
    """
    import importlib.util
    from app.knowledge import embedding as _emb

    st_importable = importlib.util.find_spec("sentence_transformers") is not None

    active = _emb._embedder  # 模块级缓存，可能为 None（未懒加载）
    if active is None:
        return {
            "embedder": "uninitialized",
            "semantic_available": st_importable,
            "model_name": _emb.EMBEDDING_MODEL_NAME,
        }
    # 已加载：判断是 TF-IDF 降级还是真实 SentenceTransformer
    if isinstance(active, _emb._TFIDFFallback):
        return {
            "embedder": "tfidf",
            "semantic_available": False,
            "model_name": _emb.EMBEDDING_MODEL_NAME,
        }
    # 真实语义模型（SentenceTransformer 实例）
    return {
        "embedder": "sentence-transformer",
        "semantic_available": True,
        "model_name": _emb.EMBEDDING_MODEL_NAME,
    }
