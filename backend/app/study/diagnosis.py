"""能力诊断引擎 —— 判定用户属于 L1/L2/L3 哪一层。

诊断逻辑：
  出 8 道梯度题（2基础+3进阶+3老手），根据正确率判定：
  - 基础题正确率<50% → L1 零基础
  - 基础题OK但进阶题<50% → L2 进阶
  - 进阶题OK → L3 老手（再看老手题判断政策敏感度）
"""
import json
import logging
import random
from collections import defaultdict
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import KnowledgePoint, Question, UserProfile

logger = logging.getLogger(__name__)

# 诊断题的难度映射：难度1=L1基础, 难度2=L2进阶, 难度3=L3老手
DIAGNOSIS_CONFIG = {
    "basic": {"difficulty": 1, "count": 3, "weight": 0.4},      # L1 基础概念
    "intermediate": {"difficulty": 2, "count": 3, "weight": 0.4},  # L2 进阶实操
    "advanced": {"difficulty": 3, "count": 2, "weight": 0.2},    # L3 政策敏感
}


def build_diagnosis_paper(db: Session) -> list[dict]:
    """生成诊断卷：3基础+3进阶+2老手 = 8题。

    某难度档题量不足时，取现有全部并告警，仍尽量返回而非崩溃。
    """
    result = []
    for tier_name, cfg in DIAGNOSIS_CONFIG.items():
        stmt = select(Question).where(
            Question.is_active.is_(True), Question.difficulty == cfg["difficulty"]
        )
        candidates = list(db.execute(stmt).scalars().all())
        if len(candidates) < cfg["count"]:
            logger.warning(
                "诊断卷 %s 档题量不足：需 %d 题，仅有 %d 题（difficulty=%d）",
                tier_name, cfg["count"], len(candidates), cfg["difficulty"],
            )
        if candidates:
            picked = random.sample(candidates, min(cfg["count"], len(candidates)))
            for q in picked:
                result.append(_question_brief(q, tier_name))
    random.shuffle(result)
    return result


def evaluate_diagnosis(
    db: Session, answers: list[dict], user_id: int
) -> dict:
    """评估诊断结果，判定层级。

    answers: [{question_id, user_answer, tier}, ...]
    返回: {level, score, detail, recommended_path}
    """
    tier_stats = defaultdict(lambda: {"correct": 0, "total": 0})
    by_module = defaultdict(lambda: {"correct": 0, "total": 0})

    for a in answers:
        q = db.get(Question, a.get("question_id"))
        if not q:
            continue
        ua = (a.get("user_answer") or "").strip().replace(" ", "").upper()
        ca = (q.answer or "").strip().replace(" ", "").upper()
        correct = ua == ca
        tier = a.get("tier", "intermediate")
        tier_stats[tier]["total"] += 1
        if correct:
            tier_stats[tier]["correct"] += 1
        # 按知识点统计
        if q.knowledge_point_id:
            kp = db.get(KnowledgePoint, q.knowledge_point_id)
            if kp:
                by_module[kp.name]["total"] += 1
                if correct:
                    by_module[kp.name]["correct"] += 1

    # 计算各层正确率
    basic_rate = _rate(tier_stats["basic"])
    inter_rate = _rate(tier_stats["intermediate"])
    adv_rate = _rate(tier_stats["advanced"])

    # 判定层级
    if basic_rate < 0.5:
        level = "L1"
        level_label = "零基础"
        reason = "基础概念题正确率偏低，建议从行业认知开始系统学习"
    elif inter_rate < 0.5:
        level = "L2"
        level_label = "进阶"
        reason = "已掌握基础，但进阶实操还需加强，建议系统学习交易品种与规则"
    else:
        level = "L3"
        level_label = "老手"
        reason = "基础扎实、实操熟练，建议聚焦最新政策变动与省份动态"

    # 综合得分
    score = round(
        basic_rate * DIAGNOSIS_CONFIG["basic"]["weight"] +
        inter_rate * DIAGNOSIS_CONFIG["intermediate"]["weight"] +
        adv_rate * DIAGNOSIS_CONFIG["advanced"]["weight"]
        , 1) * 100

    # 薄弱模块
    weak_modules = []
    for mod, stats in by_module.items():
        if stats["total"] > 0:
            r = stats["correct"] / stats["total"]
            if r < 0.5:
                weak_modules.append({"module": mod, "rate": round(r * 100)})

    result = {
        "level": level,
        "level_label": level_label,
        "reason": reason,
        "score": int(score),
        "tier_rates": {
            "basic": round(basic_rate * 100),
            "intermediate": round(inter_rate * 100),
            "advanced": round(adv_rate * 100),
        },
        "weak_modules": weak_modules,
    }

    # 保存到用户档案
    _save_profile(db, user_id, level, result)
    return result


def _rate(stats: dict) -> float:
    if stats["total"] == 0:
        return 0.0
    return stats["correct"] / stats["total"]


def _save_profile(db: Session, user_id: int, level: str, diagnosis: dict):
    """保存诊断结果到用户档案。"""
    from datetime import datetime

    profile = db.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    ).scalars().first()
    if not profile:
        profile = UserProfile(user_id=user_id, home_province="浙江")
        db.add(profile)
    profile.level = level
    profile.diagnosis = json.dumps(diagnosis, ensure_ascii=False)
    profile.last_diagnosed_at = datetime.now().isoformat()
    profile.diagnosed = True
    db.commit()


def get_or_create_profile(db: Session, user_id: int) -> UserProfile:
    """获取或创建用户档案。"""
    profile = db.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    ).scalars().first()
    if not profile:
        profile = UserProfile(user_id=user_id, home_province="浙江")
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def _question_brief(q: Question, tier: str) -> dict:
    import json as _json
    opts = _json.loads(q.options) if q.options else []
    opts = [{"key": o.get("key"), "text": o.get("text")} for o in opts]
    return {
        "id": q.id, "tier": tier, "type": q.type,
        "stem": q.stem, "options": opts, "difficulty": q.difficulty,
    }
