"""政策公告模块路由。

提供：政策新闻流（多维度筛选）、未读统计、标记已读、AI解读。
数据源：飞书知识库2基线 + 各省爬虫增量。
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.auth import get_current_user
from app.db.database import get_db
from app.db.models import Policy, PolicyAttachment, PolicyRead, User
from app.policy.ranking import CATEGORY_RANK, importance_info, policy_order_by

router = APIRouter(prefix="/policy", tags=["政策公告"])


@router.get("", summary="政策新闻流")
def list_policies(
    category: Optional[str] = None,
    province: Optional[str] = None,
    days: Optional[int] = Query(None, description="近N天"),
    unread_only: bool = False,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """政策列表，最新优先，支持按分类/省份/时间/未读筛选。"""
    stmt = select(Policy)
    if category:
        stmt = stmt.where(Policy.category == category)
    if province:
        stmt = stmt.where(Policy.province == province)
    if unread_only:
        read_policy_ids = select(PolicyRead.policy_id).where(
            PolicyRead.user_id == current_user.id
        )
        stmt = stmt.where(Policy.id.not_in(read_policy_ids))
    if days:
        # publish_date 存的是字符串 YYYY-MM-DD，用日期比较
        from datetime import date, timedelta

        cutoff = (date.today() - timedelta(days=days)).isoformat()
        stmt = stmt.where(Policy.publish_date >= cutoff)

    # 总数
    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.execute(total_stmt).scalar() or 0

    # 日期绝对优先；同日才比较紧急级别与分类优先级。
    stmt = stmt.order_by(*policy_order_by())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    items = db.execute(stmt).scalars().all()
    item_ids = [item.id for item in items]
    read_ids = set()
    if item_ids:
        read_ids = set(db.execute(
            select(PolicyRead.policy_id).where(
                PolicyRead.user_id == current_user.id,
                PolicyRead.policy_id.in_(item_ids),
            )
        ).scalars().all())

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_policy_to_dict(p, db, p.id in read_ids) for p in items],
    }


@router.get("/unread-count", summary="未读公告数")
def unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    read_policy_ids = select(PolicyRead.policy_id).where(
        PolicyRead.user_id == current_user.id
    )
    cnt = db.execute(
        select(func.count()).select_from(
            select(Policy).where(Policy.id.not_in(read_policy_ids)).subquery()
        )
    ).scalar() or 0
    return {"unread": cnt}


@router.get("/categories", summary="分类筛选项(含各分类数量)")
def categories(db: Session = Depends(get_db)):
    """返回各分类及其数量，供前端 Tab 渲染。"""
    rows = db.execute(
        select(Policy.category, func.count()).group_by(Policy.category)
    ).all()
    return [
        {"category": c, "count": n}
        for c, n in sorted(rows, key=lambda row: CATEGORY_RANK.get(row[0], 0), reverse=True)
    ]


@router.get("/provinces", summary="省份筛选项")
def provinces(db: Session = Depends(get_db)):
    rows = db.execute(
        select(Policy.province, func.count())
        .where(Policy.province.isnot(None))
        .group_by(Policy.province)
    ).all()
    return [{"province": p, "count": n} for p, n in rows if p]


@router.post("/{policy_id}/read", summary="标记单条已读")
def mark_read(
    policy_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = db.get(Policy, policy_id)
    if not p:
        raise HTTPException(status_code=404, detail="政策不存在")
    exists = db.execute(select(PolicyRead).where(
        PolicyRead.user_id == current_user.id,
        PolicyRead.policy_id == policy_id,
    )).scalars().first()
    if not exists:
        db.add(PolicyRead(user_id=current_user.id, policy_id=policy_id))
        db.commit()
    return {"ok": True}


@router.post("/read-all", summary="全部标记已读")
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = set(db.execute(select(PolicyRead.policy_id).where(
        PolicyRead.user_id == current_user.id
    )).scalars().all())
    policy_ids = db.execute(select(Policy.id)).scalars().all()
    unread_ids = [policy_id for policy_id in policy_ids if policy_id not in existing]
    for policy_id in unread_ids:
        db.add(PolicyRead(user_id=current_user.id, policy_id=policy_id))
    db.commit()
    return {"ok": True, "marked": len(unread_ids)}


@router.get("/{policy_id}", summary="政策详情")
def get_policy(
    policy_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = db.get(Policy, policy_id)
    if not p:
        raise HTTPException(status_code=404, detail="政策不存在")
    read = db.execute(select(PolicyRead).where(
        PolicyRead.user_id == current_user.id,
        PolicyRead.policy_id == policy_id,
    )).scalars().first()
    if not read:
        db.add(PolicyRead(user_id=current_user.id, policy_id=policy_id))
        db.commit()
    return _policy_to_dict(p, db, True)


def _policy_to_dict(p: Policy, db: Session, is_read: bool = False) -> dict:
    attachments = db.execute(
        select(PolicyAttachment).where(PolicyAttachment.policy_id == p.id)
    ).scalars().all()
    return {
        "id": p.id,
        "title": p.title,
        "publish_date": p.publish_date,
        "publish_date_status": p.publish_date_status,
        "publish_date_evidence": p.publish_date_evidence,
        "publish_date_verified_at": p.publish_date_verified_at,
        "doc_number": p.doc_number,
        "category": p.category,
        "province": p.province,
        "source": p.source,
        "source_url": p.source_url,
        "content": (p.content[:500] + "...") if p.content and len(p.content) > 500 else p.content,
        "ai_summary": p.ai_summary,
        "ai_analysis": p.ai_analysis,
        "ai_interpreted": p.ai_interpreted,
        "priority": p.priority,
        "is_read": is_read,
        **importance_info(p),
        "attachments": [
            {"id": a.id, "filename": a.filename, "file_type": a.file_type, "file_url": a.file_url}
            for a in attachments
        ],
    }
