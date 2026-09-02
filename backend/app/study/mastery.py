"""掌握度计算服务 —— active-learning 的核心枢纽。

设计：
- AnswerLog 是 append-only 答题流水(对+错)。
- _record_answer 在每次作答后追加一行，并按 KP 重算掌握度写入 UserProfile.mastery。
- mastery[kp_code] = round(correct_count / total_count * 100)，覆盖式更新。
- UserProfile.mastery 是 JSON {kp_code: pct}，由 L1 路线图解锁门槛(_is_unlocked)消费。

修复的核心 bug：此前 mastery 从不被写入(content.py 只读不写)，
导致 L1 路线图解锁门槛永远拿到 0，下一步永远不解锁。本模块补上写路径。
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    AnswerLog,
    KnowledgePoint,
    Question,
    UserProfile,
)


def _kp_id_to_code(db: Session, kp_id: Optional[int]) -> Optional[str]:
    """知识点 id → code。"""
    if not kp_id:
        return None
    kp = db.get(KnowledgePoint, kp_id)
    return kp.code if kp else None


def _ensure_profile(db: Session, user_id: int) -> UserProfile:
    """获取或创建用户档案(对齐 study.diagnosis.get_or_create_profile 的轻量版)。"""
    profile = db.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    ).scalars().first()
    if profile is None:
        profile = UserProfile(user_id=user_id, level="L1", mastery="{}")
        db.add(profile)
        db.flush()
    return profile


def _recompute_kp_mastery(db: Session, user_id: int, kp_id: Optional[int]) -> Optional[int]:
    """按 (user_id, kp_id) 聚合 AnswerLog 算掌握度百分比；无记录返回 None。"""
    if not kp_id:
        return None
    total = db.scalar(
        select(func.count()).select_from(AnswerLog).where(
            AnswerLog.user_id == user_id,
            AnswerLog.kp_id == kp_id,
        )
    ) or 0
    if total == 0:
        return None
    correct = db.scalar(
        select(func.count()).select_from(AnswerLog).where(
            AnswerLog.user_id == user_id,
            AnswerLog.kp_id == kp_id,
            AnswerLog.is_correct.is_(True),
        )
    ) or 0
    return round(correct / total * 100)


def _write_mastery(db: Session, profile: UserProfile, kp_code: str, pct: int) -> None:
    """把某 KP 的掌握度合并写入 profile.mastery JSON。"""
    try:
        data = json.loads(profile.mastery or "{}")
        if not isinstance(data, dict):
            data = {}
    except (json.JSONDecodeError, TypeError):
        data = {}
    data[kp_code] = pct
    profile.mastery = json.dumps(data, ensure_ascii=False)


def _record_answer(db: Session, user_id: int, question_id: int, is_correct: bool) -> None:
    """记录一次作答 → 追加 AnswerLog + 重算该题 KP 的掌握度写入档案。

    幂等性：append-only 追加(每次作答都记一行)；掌握度按全量聚合覆盖式更新，
    因此重复调用不会累积错误，只会刷新该 KP 的掌握度数值。
    必须在调用方的同一事务内执行，由调用方决定 commit 时机。
    """
    q = db.get(Question, question_id)
    kp_id = q.knowledge_point_id if q else None
    log = AnswerLog(
        user_id=user_id,
        question_id=question_id,
        kp_id=kp_id,
        is_correct=is_correct,
    )
    db.add(log)
    db.flush()  # 让聚合查询看到新行
    kp_code = _kp_id_to_code(db, kp_id)
    if not kp_code:
        return
    pct = _recompute_kp_mastery(db, user_id, kp_id)
    profile = _ensure_profile(db, user_id)
    if pct is not None:
        _write_mastery(db, profile, kp_code, pct)


def recompute_all_mastery(db: Session, user_id: int) -> dict:
    """重算用户全部 KP 的掌握度(刷新端点用)。返回 {kp_code: pct}。"""
    profile = _ensure_profile(db, user_id)
    # 取所有有答题记录的 KP
    kp_ids = db.execute(
        select(AnswerLog.kp_id).where(
            AnswerLog.user_id == user_id,
            AnswerLog.kp_id.isnot(None),
        ).distinct()
    ).scalars().all()
    result: dict[str, int] = {}
    for kp_id in kp_ids:
        code = _kp_id_to_code(db, kp_id)
        if not code:
            continue
        pct = _recompute_kp_mastery(db, user_id, kp_id)
        if pct is not None:
            result[code] = pct
            _write_mastery(db, profile, code, pct)
    # 对没有答题记录的 KP，从 mastery 中清掉旧值，保证刷新后无残留
    try:
        data = json.loads(profile.mastery or "{}")
        if not isinstance(data, dict):
            data = {}
    except (json.JSONDecodeError, TypeError):
        data = {}
    data = {k: v for k, v in data.items() if k in result}
    profile.mastery = json.dumps(data, ensure_ascii=False)
    db.commit()
    return result
