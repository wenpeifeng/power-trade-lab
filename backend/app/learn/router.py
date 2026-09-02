"""学习刷题模块路由。

提供：知识点树、组卷、判题、错题本。
"""
import json
import random
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import KnowledgePoint, Question, User, WrongAnswer, now_utc
from app.common.auth import get_current_user
from app.learn.schemas import (
    AnswerIn,
    AnswerResult,
    KnowledgePointOut,
    QuestionDetail,
    QuestionOut,
    QuizRequest,
    WrongAnswerOut,
)
from app.study.mastery import _record_answer

router = APIRouter(prefix="/learn", tags=["学习刷题"])


def _options_to_list(options_json: str) -> list[dict]:
    """把数据库里 JSON 字符串的选项解析为列表。"""
    try:
        return json.loads(options_json) if options_json else []
    except (json.JSONDecodeError, TypeError):
        return []


def _question_to_out(q: Question, hide_answer: bool = True) -> dict:
    """题目 ORM -> 输出 dict。hide_answer=True 时屏蔽正确答案。"""
    opts = _options_to_list(q.options)
    if hide_answer:
        opts = [{"key": o.get("key"), "text": o.get("text"), "is_correct": False} for o in opts]
    data = {
        "id": q.id,
        "type": q.type,
        "stem": q.stem,
        "options": opts,
        "difficulty": q.difficulty,
        "knowledge_point_id": q.knowledge_point_id,
        "province": q.province,
    }
    if not hide_answer:
        data["answer"] = q.answer
        data["analysis"] = q.analysis
    return data


@router.get("/knowledge-tree", response_model=list[KnowledgePointOut], summary="知识点树")
def get_knowledge_tree(db: Session = Depends(get_db)):
    """返回知识点树（带各知识点题目数）。"""
    points = db.execute(select(KnowledgePoint).order_by(KnowledgePoint.sort)).scalars().all()
    # 统计每个知识点下的题目数
    counts: dict[int, int] = {}
    for p in points:
        cnt = db.execute(
            select(Question).where(Question.knowledge_point_id == p.id, Question.is_active.is_(True))
        ).scalars().all()
        counts[p.id] = len(cnt)
    return [
        KnowledgePointOut(
            id=p.id, name=p.name, code=p.code, parent_id=p.parent_id,
            level=p.level, description=p.description, question_count=counts.get(p.id, 0),
        )
        for p in points
    ]


@router.post("/quiz", response_model=list[QuestionOut], summary="组卷刷题")
def build_quiz(req: QuizRequest, db: Session = Depends(get_db)):
    """按条件随机抽题组卷。"""
    stmt = select(Question).where(Question.is_active.is_(True))
    if req.type:
        stmt = stmt.where(Question.type == req.type)
    if req.difficulty:
        stmt = stmt.where(Question.difficulty == req.difficulty)
    if req.knowledge_point_id:
        stmt = stmt.where(Question.knowledge_point_id == req.knowledge_point_id)
    if req.province:
        stmt = stmt.where(Question.province == req.province)

    questions = db.execute(stmt).scalars().all()
    if not questions:
        # 筛选无匹配题目是合法状态：返回空列表(200)而非 404，
        # 让前端展示"暂无题目，试试放宽筛选"的空状态而非错误提示。
        return []

    # 随机抽取
    pick_n = min(req.count, len(questions))
    picked = random.sample(list(questions), pick_n)
    return [_question_to_out(q, hide_answer=True) for q in picked]


@router.post("/answer", response_model=AnswerResult, summary="提交答案并判分")
def submit_answer(
    req: AnswerIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """判分：判断题的 user_answer 可能是"对"/"错"或选项key。"""
    q = db.get(Question, req.question_id)
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")

    # 标准化比较：忽略空格大小写
    ua = (req.user_answer or "").strip().replace(" ", "").upper()
    ca = (q.answer or "").strip().replace(" ", "").upper()
    correct = ua == ca

    # 记录答题流水 + 重算掌握度（与错题写入同一事务）
    _record_answer(db, current_user.id, q.id, correct)

    # 错题入错题本（幂等去重：同一 user+question 只保留一行，避免重复提交产生重复行）
    # 表上有 (user_id, question_id) 唯一约束兜底；正常路径 query-before-insert
    # 已覆盖绝大多数情况，并发滑触发 IntegrityError 时回退到 UPDATE，绝不 500。
    if not correct:
        now = now_utc()
        existing = db.execute(
            select(WrongAnswer).where(
                WrongAnswer.user_id == current_user.id,
                WrongAnswer.question_id == q.id,
            )
        ).scalars().first()
        if existing:
            # 已有记录：重置为未复习，刷新本次作答与时间（updated_at 由 onupdate 自动更新）
            # 再答错 → 间隔重置为 1，下次复习 now+1 天
            existing.reviewed = False
            existing.user_answer = req.user_answer
            existing.review_interval = 1
            existing.next_review_at = now + timedelta(days=1)
        else:
            db.add(
                WrongAnswer(
                    user_id=current_user.id, question_id=q.id,
                    user_answer=req.user_answer, reviewed=False,
                    review_interval=1, next_review_at=now + timedelta(days=1),
                )
            )
        try:
            db.commit()
        except IntegrityError:
            # 并发滑：另一请求先插入了同一 user+question 行。回滚后改走 UPDATE。
            # _record_answer 的 AnswerLog/mastery 也会随 rollback 丢失，故重新记录一次。
            db.rollback()
            _record_answer(db, current_user.id, q.id, correct)
            existing = db.execute(
                select(WrongAnswer).where(
                    WrongAnswer.user_id == current_user.id,
                    WrongAnswer.question_id == q.id,
                )
            ).scalars().first()
            if existing:
                existing.reviewed = False
                existing.user_answer = req.user_answer
                existing.review_interval = 1
                existing.next_review_at = now + timedelta(days=1)
                db.commit()
            # 若仍没有（极端：被删除/事务隔离）：忽略，错题入不了库不阻塞判分
        except Exception:
            db.rollback()
            raise
    else:
        # 答对：_record_answer 已 flush AnswerLog+mastery，需提交
        db.commit()

    return AnswerResult(
        question_id=q.id, correct=correct, correct_answer=q.answer, analysis=q.analysis
    )


@router.get("/questions/{question_id}", response_model=QuestionDetail, summary="题目详情(含答案)")
def get_question_detail(question_id: int, db: Session = Depends(get_db)):
    q = db.get(Question, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")
    return _question_to_out(q, hide_answer=False)


@router.get("/wrong-answers", response_model=list[WrongAnswerOut], summary="错题本")
def list_wrong_answers(
    reviewed: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出错题。"""
    stmt = select(WrongAnswer).where(WrongAnswer.user_id == current_user.id).order_by(WrongAnswer.id.desc())
    if reviewed is not None:
        stmt = stmt.where(WrongAnswer.reviewed == reviewed)
    wrongs = db.execute(stmt).scalars().all()
    result = []
    for w in wrongs:
        q = db.get(Question, w.question_id)
        result.append(
            WrongAnswerOut(
                id=w.id, question_id=w.question_id, user_answer=w.user_answer,
                reviewed=w.reviewed,
                question=_question_to_out(q, hide_answer=False) if q else None,
            )
        )
    return result


def _wrong_reason(question: Question, user_answer: str) -> str:
    """根据答案差异给出可操作的错因标签，供错题复盘筛选。"""
    user = set((user_answer or "").strip().replace(" ", "").upper())
    correct = set((question.answer or "").strip().replace(" ", "").upper())
    if not user:
        return "未作答"
    if question.type == "multiple":
        if user < correct:
            return "漏选"
        if correct < user:
            return "多选"
        return "选项混淆"
    if question.type == "judge":
        return "判断失误"
    return "概念混淆"


@router.get("/wrong-answers-paged", summary="错题本分页查询")
def list_wrong_answers_paged(
    page: int = 1,
    page_size: int = 10,
    reviewed: Optional[bool] = None,
    question_type: Optional[str] = None,
    knowledge_point_id: Optional[int] = None,
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """按题目去重后分页返回错题，并附带统计和知识模块筛选项。

    同一道题多次答错时只展示最近一次记录，避免错题本随练习次数无限膨胀。
    """
    page = max(1, page)
    page_size = min(50, max(5, page_size))

    latest_ids = (
        select(func.max(WrongAnswer.id).label("id"))
        .where(WrongAnswer.user_id == current_user.id)
        .group_by(WrongAnswer.question_id)
        .subquery()
    )

    filters = []
    if reviewed is not None:
        filters.append(WrongAnswer.reviewed == reviewed)
    if question_type:
        filters.append(Question.type == question_type)
    if knowledge_point_id:
        filters.append(Question.knowledge_point_id == knowledge_point_id)
    if keyword and keyword.strip():
        term = f"%{keyword.strip()}%"
        filters.append(or_(Question.stem.ilike(term), Question.analysis.ilike(term)))

    base_from = (
        select(WrongAnswer, Question, KnowledgePoint)
        .join(latest_ids, latest_ids.c.id == WrongAnswer.id)
        .join(Question, Question.id == WrongAnswer.question_id)
        .outerjoin(KnowledgePoint, KnowledgePoint.id == Question.knowledge_point_id)
        .where(*filters)
    )
    count_stmt = (
        select(func.count())
        .select_from(WrongAnswer)
        .join(latest_ids, latest_ids.c.id == WrongAnswer.id)
        .join(Question, Question.id == WrongAnswer.question_id)
        .where(*filters)
    )
    total = db.scalar(count_stmt) or 0
    rows = db.execute(
        base_from
        .order_by(WrongAnswer.created_at.desc(), WrongAnswer.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    stat_rows = db.execute(
        select(WrongAnswer.reviewed, func.count())
        .join(latest_ids, latest_ids.c.id == WrongAnswer.id)
        .group_by(WrongAnswer.reviewed)
    ).all()
    status_counts = {bool(status): count for status, count in stat_rows}

    knowledge_rows = db.execute(
        select(KnowledgePoint.id, KnowledgePoint.name, func.count())
        .select_from(WrongAnswer)
        .join(latest_ids, latest_ids.c.id == WrongAnswer.id)
        .join(Question, Question.id == WrongAnswer.question_id)
        .join(KnowledgePoint, KnowledgePoint.id == Question.knowledge_point_id)
        .group_by(KnowledgePoint.id, KnowledgePoint.name)
        .order_by(func.count().desc(), KnowledgePoint.sort)
    ).all()

    items = []
    for wrong, question, knowledge in rows:
        items.append({
            "id": wrong.id,
            "question_id": wrong.question_id,
            "user_answer": wrong.user_answer,
            "reviewed": wrong.reviewed,
            "created_at": wrong.created_at.isoformat() if wrong.created_at else None,
            "error_reason": _wrong_reason(question, wrong.user_answer),
            "knowledge_point": (
                {"id": knowledge.id, "name": knowledge.name} if knowledge else None
            ),
            "question": _question_to_out(question, hide_answer=False),
        })

    pending = int(status_counts.get(False, 0))
    mastered = int(status_counts.get(True, 0))
    all_count = pending + mastered
    return {
        "items": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": int(total),
            "pages": max(1, (int(total) + page_size - 1) // page_size),
        },
        "stats": {
            "total": all_count,
            "pending": pending,
            "mastered": mastered,
            "mastery_rate": round(mastered / all_count * 100) if all_count else 0,
        },
        "knowledge_points": [
            {"id": kp_id, "name": name, "count": count}
            for kp_id, name, count in knowledge_rows
        ],
    }


# 间隔重复间隔阶梯：1→2→4→7→14→30，封顶 30
_REVIEW_INTERVAL_STEPS = [1, 2, 4, 7, 14, 30]


class ReviewReq(BaseModel):
    """标记复习结果。correct 缺省 True 以保持向后兼容(旧行为=已掌握)。"""
    correct: bool = True


@router.post("/wrong-answers/{wrong_id}/reviewed", summary="标记错题复习结果(间隔重复)")
def mark_reviewed(
    wrong_id: int,
    req: ReviewReq = ReviewReq(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """根据复习对错调整间隔：
    - correct=True：reviewed=True；间隔按阶梯增长(1→2→4→7→14→30，封顶30)；
      next_review_at = now + 新间隔 天。
    - correct=False：reviewed=False；间隔重置为 1；next_review_at = now + 1 天。

    向后兼容：不传 body 或不传 correct 时按 True 处理(旧标记已掌握行为)。
    """
    w = db.get(WrongAnswer, wrong_id)
    if not w or w.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="错题记录不存在")
    now = now_utc()
    if req.correct:
        w.reviewed = True
        cur = w.review_interval or 1
        # 在阶梯里找到当前位置并前进一步，封顶 30
        if cur in _REVIEW_INTERVAL_STEPS:
            idx = _REVIEW_INTERVAL_STEPS.index(cur)
            nxt = _REVIEW_INTERVAL_STEPS[min(idx + 1, len(_REVIEW_INTERVAL_STEPS) - 1)]
        else:
            nxt = min(cur * 2, 30)
        w.review_interval = nxt
        w.next_review_at = now + timedelta(days=nxt)
    else:
        w.reviewed = False
        w.review_interval = 1
        w.next_review_at = now + timedelta(days=1)
    db.commit()
    return {
        "ok": True,
        "reviewed": w.reviewed,
        "review_interval": w.review_interval,
        "next_review_at": w.next_review_at.isoformat() if w.next_review_at else None,
    }


@router.get("/wrong-answers/due", summary="到期待复习错题(间隔重复)")
def list_due_wrong_answers(
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回 next_review_at 为空或 <= now 且未复习的错题，分页，复用 paged 形状。"""
    page = max(1, page)
    page_size = min(50, max(5, page_size))
    now = now_utc()
    base = (
        select(WrongAnswer, Question, KnowledgePoint)
        .join(Question, Question.id == WrongAnswer.question_id)
        .outerjoin(KnowledgePoint, KnowledgePoint.id == Question.knowledge_point_id)
        .where(
            WrongAnswer.user_id == current_user.id,
            WrongAnswer.reviewed.is_(False),
            or_(WrongAnswer.next_review_at.is_(None), WrongAnswer.next_review_at <= now),
        )
    )
    total = db.scalar(
        select(func.count()).select_from(WrongAnswer).where(
            WrongAnswer.user_id == current_user.id,
            WrongAnswer.reviewed.is_(False),
            or_(WrongAnswer.next_review_at.is_(None), WrongAnswer.next_review_at <= now),
        )
    ) or 0
    rows = db.execute(
        base.order_by(WrongAnswer.next_review_at.asc().nulls_first(), WrongAnswer.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = []
    for wrong, question, knowledge in rows:
        items.append({
            "id": wrong.id,
            "question_id": wrong.question_id,
            "user_answer": wrong.user_answer,
            "reviewed": wrong.reviewed,
            "review_interval": wrong.review_interval,
            "next_review_at": wrong.next_review_at.isoformat() if wrong.next_review_at else None,
            "created_at": wrong.created_at.isoformat() if wrong.created_at else None,
            "knowledge_point": (
                {"id": knowledge.id, "name": knowledge.name} if knowledge else None
            ),
            "question": _question_to_out(question, hide_answer=False),
        })
    return {
        "items": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": int(total),
            "pages": max(1, (int(total) + page_size - 1) // page_size),
        },
    }


@router.get("/check", response_model=list[QuestionOut], summary="按知识点抽题自检")
def check_by_kp(
    kp: int,
    count: int = 1,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回指定知识点的 count 道随机题(hide_answer=True)，复用组卷抽题逻辑。"""
    stmt = select(Question).where(
        Question.is_active.is_(True), Question.knowledge_point_id == kp
    )
    questions = db.execute(stmt).scalars().all()
    if not questions:
        raise HTTPException(status_code=404, detail="该知识点暂无题目")
    pick_n = min(max(1, count), len(questions))
    picked = random.sample(list(questions), pick_n)
    return [_question_to_out(q, hide_answer=True) for q in picked]


# ============ 错题 → 知识库关联（学习闭环）============

@router.get("/wrong-answers/{wrong_id}/related-docs", summary="错题关联知识库文档")
def get_related_docs(
    wrong_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """根据错题内容，用混合检索推荐相关知识库文档。

    形成"答错→看相关知识→学会了"的学习闭环。
    """
    w = db.get(WrongAnswer, wrong_id)
    if not w or w.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="错题记录不存在")

    q = db.get(Question, w.question_id)
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")

    # 用题干+解析做检索 query
    query_text = q.stem + " " + (q.analysis or "")
    from app.knowledge.embedding import retrieve
    docs = retrieve(db, query_text, top_k=3, mode="hybrid")

    return {
        "wrong_id": wrong_id,
        "question": q.stem[:60],
        "related_docs": [
            {
                "doc_id": d.get("doc_id"),
                "title": d.get("title", ""),
                "chunk_text": d.get("chunk_text", "")[:200],
                "score": d.get("score", 0),
            }
            for d in docs
        ],
    }


@router.get("/recommend", summary="根据学习进度推荐知识库内容")
def recommend_content(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """根据用户的薄弱点（错题集中的知识点），推荐知识库文档。

    实现：统计错题最多的知识点 → 检索相关文档 → 推荐学习。
    """
    from sqlalchemy import func
    # 统计错题最多的知识点
    wrong_kp = db.execute(
        select(Question.knowledge_point_id, func.count().label("cnt"))
        .join(WrongAnswer, WrongAnswer.question_id == Question.id)
        .where(WrongAnswer.user_id == current_user.id, WrongAnswer.reviewed.is_(False))
        .group_by(Question.knowledge_point_id)
        .order_by(func.count().desc())
        .limit(3)
    ).all()

    from app.db.models import KnowledgePoint
    recommendations = []
    for kp_id, cnt in wrong_kp:
        if not kp_id:
            continue
        kp = db.get(KnowledgePoint, kp_id)
        if not kp:
            continue
        # 检索该知识点的相关文档
        docs = []
        try:
            from app.knowledge.embedding import retrieve
            docs = retrieve(db, kp.name, top_k=2, mode="hybrid")
        except Exception:
            pass
        recommendations.append({
            "knowledge_point": kp.name,
            "wrong_count": cnt,
            "docs": [
                {"doc_id": d.get("doc_id"), "title": d.get("title", "")}
                for d in docs
            ],
        })

    return {"recommendations": recommendations}
