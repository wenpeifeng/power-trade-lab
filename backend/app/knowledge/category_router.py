"""分类体系路由 —— 分类树浏览 + 按分类检索 + 多维标签。"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import CategoryNode, KnowledgeDoc, User
from app.common.auth import require_admin
from app.knowledge.categories import FACET_DIMENSIONS, CATEGORY_TREE
from app.knowledge.classifier import auto_classify, get_category_path
from app.knowledge.ordering import knowledge_doc_order_by

router = APIRouter(prefix="/category", tags=["分类体系"])


@router.get("/tree", summary="分类树(完整目录)")
def get_tree(db: Session = Depends(get_db)):
    """返回完整分类树，每个节点带文档数量。"""
    nodes = db.execute(
        select(CategoryNode).order_by(CategoryNode.code)
    ).scalars().all()

    # 统计每个分类下的文档数（含子分类）
    counts = {}
    for n in nodes:
        cnt = db.execute(
            select(func.count()).select_from(
                select(KnowledgeDoc).where(
                    KnowledgeDoc.category_code.like(n.code + "%")
                ).subquery()
            )
        ).scalar() or 0
        counts[n.code] = cnt

    # 构建树
    tree = _build_tree(nodes, counts)
    return {"tree": tree}


@router.get("/facet-dimensions", summary="多维标签维度定义")
def get_facets():
    """返回多维标签的维度定义，供前端筛选面板。"""
    return FACET_DIMENSIONS


@router.get("/docs", summary="按分类检索文档")
def docs_by_category(
    code: str = Query(..., description="分类编码，如311=中长期市场"),
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
):
    """按分类编码检索文档（含子分类）。"""
    # 前缀匹配：code=31 匹配 311/312/313
    stmt = select(KnowledgeDoc).where(
        KnowledgeDoc.category_code.like(code + "%"),
        KnowledgeDoc.review_status == "approved",
    )
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0
    stmt = stmt.order_by(*knowledge_doc_order_by()).offset((page - 1) * page_size).limit(page_size)
    items = db.execute(stmt).scalars().all()

    # 分类路径（面包屑）
    path = get_category_path(db, code)

    return {
        "category_code": code, "path": path, "total": total,
        "items": [_doc_brief(d) for d in items],
    }


@router.get("/by-facet", summary="按多维标签检索")
def docs_by_facet(
    facet: str = Query(..., description="维度: entity/product/timeframe/source_level"),
    value: str = Query(..., description="标签值，如 现货"),
    page: int = 1, page_size: int = 20,
    db: Session = Depends(get_db),
):
    """按多维标签交叉检索（如 product=现货 的所有文档）。"""
    stmt = select(KnowledgeDoc).where(
        KnowledgeDoc.facet_tags.like(f'%"{value}"%'),
        KnowledgeDoc.review_status == "approved",
    )
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0
    stmt = stmt.order_by(*knowledge_doc_order_by()).offset((page - 1) * page_size).limit(page_size)
    items = db.execute(stmt).scalars().all()
    return {"facet": facet, "value": value, "total": total,
            "items": [_doc_brief(d) for d in items]}


@router.post("/classify-preview", summary="预览自动归类(不入库)")
def classify_preview(
    title: str = Query("", max_length=500),
    content: str = Query("", max_length=20_000),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """预览：给定标题+内容，看系统会自动归到哪个分类。"""
    result = auto_classify(title, content)
    if result.get("category_code"):
        result["path"] = get_category_path(db, result["category_code"])
    return result


# ============ 工具 ============

def _build_tree(nodes, counts):
    node_map = {n.code: {
        "code": n.code, "name": n.name, "icon": n.icon,
        "level": n.level, "doc_count": counts.get(n.code, 0),
        "children": [],
    } for n in nodes}
    roots = []
    for n in nodes:
        node = node_map[n.code]
        if n.parent_code and n.parent_code in node_map:
            node_map[n.parent_code]["children"].append(node)
        else:
            roots.append(node)
    return roots


def _doc_brief(d):
    import json
    return {
        "id": d.id, "title": d.title, "doc_type": d.doc_type,
        "province": d.province, "category_code": d.category_code,
        "publish_date": d.publish_date, "source": d.source,
        "ai_summary": d.ai_summary,
        "facet_tags": json.loads(d.facet_tags) if d.facet_tags else None,
    }
