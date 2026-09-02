"""知识资产的统一业务时间排序规则。"""
from __future__ import annotations

from sqlalchemy import case, or_

from app.db.models import KnowledgeDoc


# 同一发布日期内，先展示对交易决策和合规影响更直接的内容。
DOC_TYPE_RANK = {
    "national_policy": 6,
    "policy": 6,
    "regulation": 5,
    "clearing": 4,
    "exchange_info": 3,
    "market_announcement": 3,
    "exam_info": 2,
    "industry_news": 1,
}


def knowledge_doc_order_by():
    """发布日期倒排；未知日期沉底；同日按类型重要性和 ID 稳定排序。"""
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
    type_rank = case(DOC_TYPE_RANK, value=KnowledgeDoc.doc_type, else_=0)
    return (
        unknown_date.asc(),
        KnowledgeDoc.publish_date.desc(),
        type_rank.desc(),
        KnowledgeDoc.id.desc(),
    )
