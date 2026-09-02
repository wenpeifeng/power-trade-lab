#!/usr/bin/env python3
"""回填 knowledge_docs.knowledge_point_id —— 仅填 NULL，绝不覆盖已有值。

策略：
1. category_code（行上已有）→ CATEGORY_TO_KP 最长前缀映射 → KP code → id
2. category 为空或映射无果 → classifier.auto_classify(title, content) 得
   category_code 再映射
3. 仍无果 → KP_KEYWORDS 关键词回退直接选 KP
4. 全无命中 → 留 NULL（宁缺毋错）

仅处理 review_status='approved' 且 knowledge_point_id IS NULL 的文档，幂等。
"""
from __future__ import annotations

import argparse
import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal, init_db
from app.db.models import KnowledgeDoc, KnowledgePoint
from app.knowledge import classifier

logger = logging.getLogger("backfill_doc_kp")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


# ---- category_code → knowledge_point code 映射 ----
# 依据 backend/app/knowledge/categories.py 的分类树设计：
# 最长前缀匹配：如 '311' 优先于 '31' 优先于 '3'。
# 取值域：industry/wholesale/retail/mid_long_term/spot/ancillary/green/settlement。
CATEGORY_TO_KP: dict[str, str] = {
    # 0 总览与基础 → 行业认知
    "0": "industry",
    "01": "industry", "02": "industry", "03": "industry", "04": "industry",

    # 1 政策法规 → 行业认知（政策属行业认知背景）；细则按内容分流
    "1": "industry",
    "11": "industry", "12": "industry",
    "13": "industry",
    "131": "industry", "132": "settlement",  # 价格与容量机制
    "133": "green",   # 新能源与消纳
    "134": "green",   # 绿色权益
    "135": "industry",
    "14": "industry", "15": "industry", "16": "industry",

    # 2 市场主体 → 行业认知（主体概念性）
    "2": "industry",
    "21": "industry", "22": "industry", "23": "industry",
    "24": "industry", "25": "industry", "26": "industry",

    # 3 交易品种（核心分流）
    "3": "mid_long_term",  # 兜底归中长期（电能量市场主基调）
    "31": "mid_long_term",
    "311": "mid_long_term",
    "312": "spot",
    "313": "spot",          # 平衡市场 → 现货
    "32": "ancillary",
    "321": "ancillary", "322": "ancillary", "323": "ancillary",
    "33": "settlement",     # 容量市场与机制 → 结算
    "34": "settlement",     # 输电权 → 结算
    "35": "green",
    "351": "green", "352": "green", "353": "green", "354": "green",
    "36": "ancillary",      # 需求响应
    "37": "mid_long_term",  # 发电权与合同转让
    "38": "mid_long_term",  # 电力金融（期货/衍生品）

    # 4 产业链技术与运行 → 行业认知；调度运行 → 辅助服务
    "4": "industry",
    "41": "industry", "42": "industry", "43": "industry",
    "44": "ancillary",
    "45": "industry", "46": "industry",

    # 5 电价与结算 → 结算与信用
    "5": "settlement",
    "51": "settlement", "52": "settlement", "53": "settlement",
    "54": "settlement", "55": "settlement", "56": "settlement",

    # 6 新兴与交叉领域
    "6": "industry",
    "61": "ancillary",   # 储能
    "62": "ancillary",   # 虚拟电厂与负荷聚合
    "63": "industry",    # 综合能源服务
    "64": "retail",      # 分布式交易与隔墙售电
    "65": "green",       # 碳市场联动
    "66": "industry",    # 算电协同
    "67": "industry",    # 氢能
    "68": "industry",    # 电力数字化

    # 7 区域与省级市场 → 批发（省间/跨省跨区）
    "7": "wholesale",
    "71": "wholesale", "72": "wholesale", "73": "wholesale",

    # 8 国际与比较 → 行业认知
    "8": "industry",
    "81": "industry", "82": "industry",
}


def map_category_to_kp(category_code: str | None) -> str | None:
    """category_code → KP code（最长前缀匹配）。

    '311' 依次试 '311'→'31'→'3'；'08' 试 '08'→'0'（命中 '0'→industry）。
    返回 None 表示无映射。
    """
    if not category_code:
        return None
    code = category_code.strip()
    while code:
        kp_code = CATEGORY_TO_KP.get(code)
        if kp_code:
            return kp_code
        code = code[:-1]
    return None


# ---- 关键词回退：category 为空/无映射时直接选 KP ----
KP_KEYWORDS: dict[str, list[str]] = {
    "spot": ["现货", "日前", "实时", "出清", "LMP", "节点电价", "集中竞价出清"],
    "mid_long_term": [
        "中长期", "年度", "月度", "双边", "集中竞价", "挂牌", "合同", "发电权",
        "合同转让", "电力金融", "期货",
    ],
    "ancillary": [
        "辅助服务", "调频", "调峰", "备用", "黑启动", "AGC", "无功", "需求响应",
        "可调节负荷", "储能",
    ],
    "green": [
        "绿电", "绿证", "碳排放", "CCER", "绿色电力", "绿色权益", "碳市场",
        "电碳协同", "可再生能源",
    ],
    "settlement": [
        "结算", "电价", "输配电价", "容量电价", "偏差", "交叉补贴", "政府性基金",
        "电费", "两部制", "上网电价", "销售电价",
    ],
    "wholesale": ["批发", "省间", "跨省", "跨区", "区域市场"],
    "retail": ["零售", "售电", "隔墙", "分布式交易", "新能源直连"],
    "industry": [
        "行业", "装机", "用电量", "主体", "监管", "市场秩序", "概览", "电改",
        "体制改革", "名词", "术语",
        # 行业资讯/会议类（无品种指向的能源局动态归行业认知）
        "能源局", "能源体系", "能源行", "高质量发展", "论坛", "交流会",
        "研修班", "金砖", "动员部署",
    ],
}

# 评估顺序：高区分度品种优先（spot/mid_long_term/green/ancillary/settlement
# 优先于泛化的 wholesale/retail/industry）
_KP_ORDER = [
    "spot", "mid_long_term", "green", "ancillary",
    "settlement", "wholesale", "retail", "industry",
]


def keyword_fallback_kp(title: str, content: str) -> str | None:
    """直接对 title+content 命中 KP_KEYWORDS，取最高命中数的 KP。"""
    text = f"{title or ''} {content or ''}"
    if not text.strip():
        return None
    best_kp: str | None = None
    best_score = 0
    for kp in _KP_ORDER:
        kws = KP_KEYWORDS[kp]
        hits = sum(1 for kw in kws if kw in text)
        if hits > best_score:
            best_score = hits
            best_kp = kp
    return best_kp if best_score > 0 else None


def resolve_kp_id(
    doc: KnowledgeDoc,
    kp_by_code: dict[str, int],
) -> tuple[str | None, str | None]:
    """返回 (kp_code, kp_id)；用过的路径记入 kp_code 便于审计。

    顺序：行上 category_code → classifier.auto_classify → 关键词回退。
    """
    # 1) 行上已有 category_code
    kp_code = map_category_to_kp(doc.category_code)
    # 2) classifier
    if not kp_code:
        try:
            result = classifier.auto_classify(doc.title or "", doc.content or "")
        except Exception:  # classifier 不应崩主流程
            result = {"category_code": None}
        cat = result.get("category_code") if isinstance(result, dict) else None
        kp_code = map_category_to_kp(cat)
    # 3) 关键词回退
    if not kp_code:
        kp_code = keyword_fallback_kp(doc.title or "", doc.content or "")

    if not kp_code:
        return None, None
    kp_id = kp_by_code.get(kp_code)
    return kp_code, kp_id


def backfill(db: Session, *, apply: bool = True) -> dict:
    """对 NULL knowledge_point_id 的 approved 文档回填。

    幂等：只填 NULL，绝不覆盖已有 knowledge_point_id；只处理 approved。
    返回统计 dict。
    """
    total_approved = db.scalar(
        select(func.count(KnowledgeDoc.id)).where(
            KnowledgeDoc.review_status == "approved"
        )
    ) or 0
    was_linked = db.scalar(
        select(func.count(KnowledgeDoc.id)).where(
            KnowledgeDoc.review_status == "approved",
            KnowledgeDoc.knowledge_point_id.is_not(None),
        )
    ) or 0
    was_orphan = total_approved - was_linked

    # KP code → id 映射
    kp_rows = db.execute(
        select(KnowledgePoint.code, KnowledgePoint.id)
    ).all()
    kp_by_code: dict[str, int] = {code: kid for code, kid in kp_rows if code}

    # 仅取 NULL + approved
    orphans = db.scalars(
        select(KnowledgeDoc).where(
            KnowledgeDoc.review_status == "approved",
            KnowledgeDoc.knowledge_point_id.is_(None),
        )
    ).all()

    filled = 0
    still_orphan = 0
    skipped_existing = 0
    for doc in orphans:
        # 双重守卫：绝不覆盖非空值
        if doc.knowledge_point_id is not None:
            skipped_existing += 1
            continue
        _kp_code, kp_id = resolve_kp_id(doc, kp_by_code)
        if kp_id:
            doc.knowledge_point_id = kp_id
            filled += 1
        else:
            still_orphan += 1

    if apply:
        db.commit()
    else:
        db.rollback()

    now_linked = was_linked + filled
    return {
        "mode": "applied" if apply else "preview",
        "total_approved": total_approved,
        "was_linked": was_linked,
        "was_orphan": was_orphan,
        "filled": filled,
        "now_linked": now_linked,
        "still_orphan": was_orphan - filled,
        "skipped_existing": skipped_existing,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true",
        help="提交回填（默认仅预览、不提交）",
    )
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        stats = backfill(db, apply=args.apply)
        print(stats)
    finally:
        db.close()


if __name__ == "__main__":
    main()
