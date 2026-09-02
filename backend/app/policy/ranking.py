"""政策公告的日期、分类、重要性和稳定排序规则。"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import case, or_

from app.db.models import Policy

# 同一天内的业务优先级。紧急级别会在分类之前。
CATEGORY_RANK = {
    "national": 4,
    "regulation": 3,
    "clearing": 2,
    "market": 1,
}

CATEGORY_LABEL = {
    "national": "国家政策",
    "regulation": "交易规则",
    "clearing": "出清结果",
    "market": "市场公告",
}

NORMATIVE_KEYWORDS = (
    "实施意见", "通知", "办法", "规则", "规定", "细则", "方案",
    "通告", "公告", "批复", "决定", "指导意见",
)
REGULATION_KEYWORDS = (
    "交易规则", "市场规则", "实施细则", "管理办法", "监管办法",
    "信息披露", "市场准入", "资质许可", "信用管理", "违约",
    "结算", "电价", "价格机制", "交易限价",
)
CLEARING_KEYWORDS = (
    "出清结果", "成交结果", "交易结果", "竞价结果", "结算结果",
)
URGENT_KEYWORDS = (
    "暂停交易", "市场干预", "风险预警", "系统故障", "紧急",
    "应急", "违规", "处罚", "限价",
)
IMPORTANT_KEYWORDS = (
    "电力市场", "现货市场", "中长期交易", "辅助服务", "绿电交易",
    "代理购电", "输配电价", "偏差结算", "信息披露", "市场准入",
)


def classify_policy(title: str, current: Optional[str] = None) -> str:
    """按内容而不是站点名称分类，避免“监管局新闻=交易规则”。"""
    title = title or ""
    if any(keyword in title for keyword in CLEARING_KEYWORDS):
        return "clearing"

    is_national_issuer = any(
        issuer in title
        for issuer in ("国务院", "国家发展改革委", "国家发改委", "国家能源局")
    )
    is_normative = any(keyword in title for keyword in NORMATIVE_KEYWORDS)
    if is_national_issuer and is_normative:
        return "national"
    if any(keyword in title for keyword in REGULATION_KEYWORDS):
        return "regulation"

    # 明确可信的既有分类保留；监管局抓来的普通动态则归市场公告。
    if current in {"national", "clearing", "market"}:
        return current
    return "market"


def infer_priority(title: str, category: str, current: int = 0) -> int:
    """0普通、1重要、2紧急；保留人工设置的更高等级。"""
    title = title or ""
    inferred = 0
    if any(keyword in title for keyword in URGENT_KEYWORDS):
        inferred = 2
    elif (
        category in {"national", "regulation", "clearing"}
        or any(keyword in title for keyword in IMPORTANT_KEYWORDS)
    ):
        inferred = 1
    return max(int(current or 0), inferred)


def importance_info(policy: Policy) -> dict:
    priority = infer_priority(policy.title, policy.category, policy.priority)
    reasons = []
    if priority >= 2:
        reasons.append("含风险、干预、违规或应急事项")
    if policy.category in {"national", "regulation", "clearing"}:
        reasons.append(CATEGORY_LABEL.get(policy.category, policy.category))
    matched = next((k for k in IMPORTANT_KEYWORDS if k in (policy.title or "")), None)
    if matched:
        reasons.append(f"涉及{matched}")
    return {
        "importance_level": "urgent" if priority >= 2 else "important" if priority >= 1 else "normal",
        "importance_label": "紧急" if priority >= 2 else "重要" if priority >= 1 else "一般",
        "importance_reasons": list(dict.fromkeys(reasons)),
        "category_rank": CATEGORY_RANK.get(policy.category, 0),
    }


def policy_order_by():
    """日期绝对优先；同日按紧急级别、分类优先级和 ID 稳定排序。"""
    category_rank = case(CATEGORY_RANK, value=Policy.category, else_=0)
    unknown_date = case((
        or_(
            Policy.publish_date.is_(None),
            Policy.publish_date_status != "verified",
        ),
        1,
    ), else_=0)
    return (
        unknown_date.asc(),
        Policy.publish_date.desc(),
        Policy.priority.desc(),
        category_rank.desc(),
        Policy.id.desc(),
    )
