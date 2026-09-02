"""分层学习内容服务 —— 按用户层级提供不同内容。

L1 零基础：引导式入门，从行业概念开始，循序渐进
L2 进阶：系统学习交易品种+规则，主省份深入
L3 老手：政策变动对比+省份动态+新增考点速刷+情景演练
"""
import json
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models import (
    KnowledgePoint,
    LearningPath,
    Policy,
    ProvinceConfig,
    Question,
    UserProfile,
)
from app.policy.ranking import policy_order_by


# ============ L1：零基础引导式学习 ============

L1_ROADMAP = [
    {"step": 1, "title": "电力行业全景：发-输-配-用", "kp": "industry", "desc": "电从哪里来，怎么到你家"},
    {"step": 2, "title": "市场主体是谁", "kp": "industry", "desc": "发电企业、售电公司、电网、用户各扮演什么角色"},
    {"step": 3, "title": "什么是批发市场", "kp": "wholesale", "desc": "发电和售电之间的交易"},
    {"step": 4, "title": "什么是零售市场", "kp": "retail", "desc": "售电公司和用户之间的交易"},
    {"step": 5, "title": "中长期交易入门", "kp": "mid_long_term", "desc": "最常见的交易方式"},
    {"step": 6, "title": "现货交易是什么", "kp": "spot", "desc": "像买菜一样实时交易"},
    {"step": 7, "title": "辅助服务简介", "kp": "ancillary", "desc": "保证电网安全的幕后英雄"},
    {"step": 8, "title": "电费怎么算", "kp": "settlement", "desc": "结算与偏差考核基础"},
]


def get_l1_roadmap(db: Session, profile: UserProfile) -> dict:
    """L1 零基础学习路线图。

    每步对应一个知识点，附带该知识点的入门题（难度1），
    学完一步解锁下一步。
    """
    mastery = json.loads(profile.mastery or "{}")
    steps = []
    points = {p.code: p for p in db.execute(select(KnowledgePoint)).scalars().all() if p.code}

    for item in L1_ROADMAP:
        kp = points.get(item["kp"])
        kp_id = kp.id if kp else None
        # 该知识点有多少入门题
        q_count = 0
        if kp_id:
            q_count = db.execute(
                select(Question).where(
                    Question.knowledge_point_id == kp_id,
                    Question.difficulty <= 1,
                    Question.is_active.is_(True),
                )
            ).scalars().all()
            q_count = len(q_count)
        # 掌握度
        mastery_pct = mastery.get(item["kp"], 0)
        steps.append({
            **item,
            "knowledge_point_id": kp_id,
            "question_count": q_count,
            "mastery": mastery_pct,
            "unlocked": _is_unlocked(item["step"], mastery, steps),
        })
    return {"level": "L1", "level_label": "零基础", "roadmap": steps}


def _is_unlocked(step: int, mastery: dict, prev_steps: list) -> bool:
    """第一步始终解锁，后续需前一步掌握度>=60%。"""
    if step == 1:
        return True
    prev = L1_ROADMAP[step - 2]
    return mastery.get(prev["kp"], 0) >= 60


# ============ L2：进阶系统学习 ============

def get_l2_content(db: Session, profile: UserProfile) -> dict:
    """L2 进阶：系统学习 + 主省份深入。

    内容：交易品种深化 + 主省份规则 + 其他省份对比。
    """
    home = profile.home_province or "浙江"
    # 主省份配置
    home_cfg = db.execute(
        select(ProvinceConfig).where(ProvinceConfig.name == home)
    ).scalars().first()

    # 其他省份列表（用于对比）
    other_provinces = db.execute(
        select(ProvinceConfig).where(ProvinceConfig.name != home, ProvinceConfig.is_active.is_(True))
    ).scalars().all()

    # 主省份相关题目
    home_questions = db.execute(
        select(Question).where(
            Question.province == home, Question.is_active.is_(True)
        ).limit(20)
    ).scalars().all()

    return {
        "level": "L2",
        "level_label": "进阶",
        "home_province": home,
        "home_config": _province_brief(home_cfg),
        "other_provinces": [_province_brief(p) for p in other_provinces],
        "home_question_count": len(home_questions),
        "modules": _get_l2_modules(db),
    }


def _get_l2_modules(db: Session) -> list:
    """L2 学习模块：各交易品种深化。"""
    points = db.execute(
        select(KnowledgePoint).where(KnowledgePoint.level == 1).order_by(KnowledgePoint.sort)
    ).scalars().all()
    modules = []
    for kp in points:
        q_count = len(db.execute(
            select(Question).where(
                Question.knowledge_point_id == kp.id,
                Question.is_active.is_(True),
            )
        ).scalars().all())
        modules.append({
            "id": kp.id, "name": kp.name, "code": kp.code,
            "description": kp.description, "question_count": q_count,
        })
    return modules


# ============ L3：老手速查 ============

def get_l3_dashboard(db: Session, profile: UserProfile) -> dict:
    """L3 老手仪表盘：四大功能聚合。

    1. 政策变动对比（最新政策 + 标注变化）
    2. 省份动态速览（各省份最新公告/出清）
    3. 新增考点速刷（标记新增/政策关联的题）
    4. 政策情景演练题
    """
    home = profile.home_province or "浙江"

    # 1. 最新政策：日期绝对优先，同日再按紧急级别与分类排序。
    latest_policies = db.execute(
        select(Policy).order_by(*policy_order_by()).limit(8)
    ).scalars().all()

    # 2. 省份动态：主省份 + 其他重点省份的最新公告
    home_policies = db.execute(
        select(Policy).where(Policy.province == home)
        .order_by(desc(Policy.publish_date)).limit(5)
    ).scalars().all()
    other_province_policies = db.execute(
        select(Policy).where(Policy.province != home, Policy.province.isnot(None))
        .order_by(desc(Policy.publish_date)).limit(8)
    ).scalars().all()

    # 3. 新增考点题（标记了 prediction_tags 的题）
    new_questions = db.execute(
        select(Question).where(Question.prediction_tags.isnot(None)).limit(10)
    ).scalars().all()

    # 4. 情景演练题（难度3 + 政策关联标记）
    scenario_questions = db.execute(
        select(Question).where(
            Question.difficulty >= 2,
            Question.prediction_tags.isnot(None),
            Question.is_active.is_(True),
        ).limit(5)
    ).scalars().all()

    return {
        "level": "L3",
        "level_label": "老手",
        "home_province": home,
        "latest_policies": [_policy_brief(p) for p in latest_policies],
        "province_dynamics": {
            "home": [_policy_brief(p) for p in home_policies],
            "others": [_policy_brief(p) for p in other_province_policies],
        },
        "new_questions": [_question_brief(q) for q in new_questions],
        "scenario_questions": [_question_brief(q) for q in scenario_questions],
    }


def _province_brief(p: Optional[ProvinceConfig]) -> dict:
    if not p:
        return {}
    return {
        "name": p.name, "code": p.code, "grid": p.grid,
        "spot_pilot": p.spot_pilot, "spot_status": p.spot_status,
        "rule_summary": p.rule_summary,
    }


def _policy_brief(p: Policy) -> dict:
    return {
        "id": p.id, "title": p.title,
        "publish_date": p.publish_date, "doc_number": p.doc_number,
        "category": p.category, "province": p.province,
        "ai_summary": p.ai_summary, "priority": p.priority,
        "is_read": p.is_read,
    }


def _question_brief(q: Question) -> dict:
    tags = None
    if q.prediction_tags:
        try:
            tags = json.loads(q.prediction_tags)
        except (json.JSONDecodeError, TypeError):
            pass
    return {
        "id": q.id, "type": q.type, "stem": q.stem[:60],
        "difficulty": q.difficulty, "is_real_exam": q.is_real_exam,
        "prediction_tags": tags, "source": q.source,
    }
