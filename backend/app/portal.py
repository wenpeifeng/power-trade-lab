"""门户首页概览接口 —— 聚合三大模块的摘要数据。"""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Policy, Question, StudyRecord, TradeAccount, User, WrongAnswer
from app.common.auth import get_current_user
from app.policy.ranking import policy_order_by

router = APIRouter(prefix="/portal", tags=["门户"])


@router.get("/overview", summary="门户首页总览")
def overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """聚合：学习进度、模拟资金、未读公告、错题数。按当前登录用户隔离。"""
    uid = current_user.id
    # 学习侧
    total_q = db.execute(
        select(func.count()).select_from(select(Question).subquery())
    ).scalar() or 0
    wrong_cnt = db.execute(
        select(func.count())
        .select_from(
            select(WrongAnswer).where(
                WrongAnswer.reviewed.is_(False), WrongAnswer.user_id == uid
            ).subquery()
        )
    ).scalar() or 0
    answered = db.execute(
        select(func.count())
        .select_from(
            select(StudyRecord).where(
                StudyRecord.action.in_(["correct", "wrong"]),
                StudyRecord.user_id == uid,
            ).subquery()
        )
    ).scalar() or 0
    progress = min(100, int(answered / max(total_q, 1) * 100)) if total_q else 0

    # 交易侧（按用户隔离）
    acc = db.execute(select(TradeAccount).where(TradeAccount.user_id == uid)).scalars().first()
    balance = acc.balance if acc else 1_000_000.0

    # 政策侧
    unread = db.execute(
        select(func.count()).select_from(select(Policy).where(Policy.is_read.is_(False)).subquery())
    ).scalar() or 0
    latest_policies = db.execute(
        select(Policy).order_by(*policy_order_by()).limit(5)
    ).scalars().all()

    return {
        "learn": {
            "total_questions": total_q,
            "answered": answered,
            "wrong_count": wrong_cnt,
            "progress": progress,
        },
        "trade": {
            "balance": balance,
        },
        "policy": {
            "unread": unread,
            "latest": [
                {
                    "id": p.id,
                    "title": p.title,
                    "publish_date": p.publish_date,
                    "category": p.category,
                    "province": p.province,
                    "priority": p.priority,
                }
                for p in latest_policies
            ],
        },
    }
