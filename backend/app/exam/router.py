"""考试刷题模块路由。

双模式：
- 学习模式（knowledge-driven）：按知识点刷题，看解析
- 考试模式（exam/predict）：按真实配比组卷，计时判分，考点预测
"""
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import ExamBlueprint, ExamSession, KnowledgePoint, Question, User, WrongAnswer
from app.common.auth import get_current_user
from app.exam.engine import (
    REAL_EXAM_CONFIG,
    analyze_weakness,
    build_exam_paper,
    get_prediction_report,
)

router = APIRouter(prefix="/exam", tags=["考试刷题"])


# ============ 请求模型 ============

class BuildPaperReq(BaseModel):
    mode: str = "exam"  # exam / predict / study
    level: Optional[str] = None  # four/three/...
    knowledge_point_id: Optional[int] = None
    count: int = 50
    focus_weak: bool = False


class StartExamReq(BaseModel):
    mode: str = "exam"  # exam / predict
    level: Optional[str] = None
    count: int = 50
    focus_weak: bool = False


class SubmitExamReq(BaseModel):
    session_id: int
    answers: list[dict]  # [{question_id, user_answer, time_cost}]


# ============ 蓝图与配比 ============

@router.get("/blueprint", summary="考试蓝图(真实题型配比)")
def get_blueprint(level: str = "four", db: Session = Depends(get_db)):
    """返回真实统考题型配比 + 官方各模块权重。"""
    bp = db.execute(
        select(ExamBlueprint).where(ExamBlueprint.level == level, ExamBlueprint.is_active.is_(True))
    ).scalars().first()

    # 没有自定义蓝图时，返回真实统考默认配比
    if bp:
        type_config = json.loads(bp.type_config)
    else:
        type_config = REAL_EXAM_CONFIG

    return {
        "level": level,
        "level_label": {"four": "中级工", "three": "高级工", "two": "技师", "one": "高级技师"}.get(level, level),
        "type_config": type_config,
        "total_score": 100.0,
        "pass_score": 60.0,
        "duration_min": 90,
        "total_questions": sum(t["count"] for t in type_config.values()),
    }


# ============ 学习模式组卷（知识驱动） ============

@router.post("/study-paper", summary="学习模式组卷(按知识点)")
def build_study_paper(req: BuildPaperReq, db: Session = Depends(get_db)):
    """学习模式：按知识点驱动抽题，不计时，重在看解析理解。"""
    questions = build_exam_paper(
        db, mode="study", knowledge_point_id=req.knowledge_point_id,
        target_count=req.count,
    )
    if not questions:
        raise HTTPException(status_code=404, detail="该知识点暂无题目")
    return [_question_out(q) for q in questions]


# ============ 历年真题 ============

@router.get("/real-exam/years", summary="历年真题年份与题量")
def real_exam_years(level: Optional[str] = None, db: Session = Depends(get_db)):
    """列出有真题的年份及各题型数量，供前端展示真题入口。

    中级为主，高级可选。
    """
    stmt = select(Question).where(Question.is_active.is_(True), Question.is_real_exam.is_(True))
    if level:
        stmt = stmt.where((Question.exam_level == level) | (Question.exam_level.is_(None)))
    questions = db.execute(stmt).scalars().all()

    # 按年份+级别聚合
    from collections import defaultdict
    by_year_level = defaultdict(lambda: defaultdict(int))
    no_year_count = 0
    for q in questions:
        if q.exam_year:
            key = f"{q.exam_year}"
            by_year_level[key][q.type] += 1
        else:
            no_year_count += 1

    years = []
    for y, types in sorted(by_year_level.items(), reverse=True):
        years.append({
            "year": y,
            "total": sum(types.values()),
            "single": types.get("single", 0),
            "multiple": types.get("multiple", 0),
            "judge": types.get("judge", 0),
        })
    if no_year_count:
        years.append({"year": "未标注年份", "total": no_year_count, "single": 0, "multiple": 0, "judge": 0})

    return {
        "level": level,
        "level_label": {"four": "中级工", "three": "高级工", None: "全部级别"}.get(level, level),
        "years": years,
        "total_real": len(questions),
    }


# ============ 考试/押题模式 ============

@router.post("/start", summary="开始考试/押题模考")
def start_exam(
    req: StartExamReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """开始一次考试会话，返回组卷结果 + 会话ID。"""
    questions = build_exam_paper(
        db, mode=req.mode, level=req.level,
        target_count=req.count, focus_weak=req.focus_weak, user_id=current_user.id,
    )
    if not questions:
        raise HTTPException(status_code=404, detail="题库不足，无法组卷")

    session = ExamSession(
        user_id=current_user.id, mode=req.mode, level=req.level,
        question_ids=json.dumps([q.id for q in questions]),
        answers="[]", started_at=datetime.now().isoformat(),
        status="ongoing",
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return {
        "session_id": session.id,
        "mode": req.mode,
        "total": len(questions),
        "duration_min": 90 if req.mode in ("exam", "predict", "real") else None,
        "questions": [_question_out(q, hide_answer=True) for q in questions],
    }


@router.post("/submit", summary="交卷判分")
def submit_exam(
    req: SubmitExamReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """交卷：逐题判分，计算得分，生成薄弱点分析。"""
    session = db.get(ExamSession, req.session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="考试会话不存在")

    blueprint = get_blueprint(level="four", db=db)
    type_config = blueprint["type_config"]

    correct_count = {"single": 0, "multiple": 0, "judge": 0}
    wrong_count = {"single": 0, "multiple": 0, "judge": 0}
    score = 0.0
    full_score = 0.0
    answer_records = []

    for a in req.answers:
        q = db.get(Question, a.get("question_id"))
        if not q:
            continue
        ua = (a.get("user_answer") or "").strip().replace(" ", "").upper()
        ca = (q.answer or "").strip().replace(" ", "").upper()
        correct = ua == ca

        per_score = type_config.get(qtype_cfg_key(q.type), {}).get("score", 0.5)
        full_score += per_score
        if correct:
            score += per_score
            correct_count[q.type if q.type in correct_count else "single"] += 1
        else:
            wrong_count[q.type if q.type in wrong_count else "single"] += 1
            # 错题入错题本
            db.add(WrongAnswer(user_id=current_user.id, question_id=q.id, user_answer=a.get("user_answer", "")))

        answer_records.append({
            "question_id": q.id, "user_answer": a.get("user_answer"),
            "correct": correct, "time_cost": a.get("time_cost"),
        })

    # 归一化到百分制：本次试卷题量常少于真实考试(170题满分100)，按本卷满分折算到 100
    final_score = round(score / full_score * 100, 1) if full_score else 0.0

    session.answers = json.dumps(answer_records, ensure_ascii=False)
    session.score = final_score
    session.finished_at = datetime.now().isoformat()
    session.status = "finished"
    db.commit()

    # 薄弱点分析
    weak = analyze_weakness(db, session.id)

    return {
        "session_id": session.id,
        "score": session.score,
        "total_score": 100.0,
        "passed": session.score >= 60,
        "stats": {
            "correct": correct_count,
            "wrong": wrong_count,
            "total_answered": len(answer_records),
        },
        "weak_points": weak.get("weak_points", []),
    }


def qtype_cfg_key(t: str) -> str:
    """题型的配置键。"""
    return t if t in ("single", "multiple", "judge") else "single"


# ============ 考点预测 ============

@router.get("/prediction", summary="考点预测报告")
def prediction(level: str = "four", db: Session = Depends(get_db)):
    """智能押题：当年各模块预测考点占比 + 高频真题 + 政策关联新考点。"""
    return get_prediction_report(db, level=level)


# ============ 历史考试记录 ============

@router.get("/history", summary="考试历史记录")
def exam_history(
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sessions = db.execute(
        select(ExamSession).where(
            ExamSession.status == "finished",
            ExamSession.user_id == current_user.id,
        )
        .order_by(ExamSession.id.desc()).limit(limit)
    ).scalars().all()
    return [
        {
            "id": s.id, "mode": s.mode, "score": s.score,
            "started_at": s.started_at, "finished_at": s.finished_at,
        }
        for s in sessions
    ]


@router.get("/result/{session_id}", summary="考试结果详情（按 session 重取，含逐题对错）")
def exam_result(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = db.get(ExamSession, session_id)
    if (
        not session
        or session.status != "finished"
        or session.user_id != current_user.id
    ):
        raise HTTPException(status_code=404, detail="考试记录不存在")
    records = json.loads(session.answers or "[]")
    correct_count = {"single": 0, "multiple": 0, "judge": 0}
    wrong_count = {"single": 0, "multiple": 0, "judge": 0}
    questions = []
    for r in records:
        q = db.get(Question, r.get("question_id"))
        if not q:
            continue
        t = q.type if q.type in correct_count else "single"
        if r.get("correct"):
            correct_count[t] += 1
        else:
            wrong_count[t] += 1
        try:
            options = json.loads(q.options or "[]")
        except Exception:
            options = []
        questions.append({
            "question_id": q.id, "type": q.type, "stem": q.stem,
            "options": options, "answer": q.answer, "analysis": q.analysis,
            "user_answer": r.get("user_answer"), "correct": r.get("correct"),
        })
    weak = analyze_weakness(db, session.id)
    return {
        "session_id": session.id, "score": session.score, "total_score": 100.0,
        "passed": (session.score or 0) >= 60,
        "stats": {"correct": correct_count, "wrong": wrong_count, "total_answered": len(questions)},
        "weak_points": weak.get("weak_points", []),
        "questions": questions,
    }


# ============ 工具 ============

def _question_out(q: Question, hide_answer: bool = True) -> dict:
    opts = json.loads(q.options) if q.options else []
    if hide_answer:
        opts = [{"key": o.get("key"), "text": o.get("text")} for o in opts]
    data = {
        "id": q.id, "type": q.type, "stem": q.stem,
        "options": opts, "difficulty": q.difficulty,
        "knowledge_point_id": q.knowledge_point_id,
        "source": q.source, "is_real_exam": q.is_real_exam,
        "exam_year": q.exam_year, "prediction_tags": _safe_json(q.prediction_tags),
    }
    if not hide_answer:
        data["answer"] = q.answer
        data["analysis"] = q.analysis
    return data


def _safe_json(s: Optional[str]):
    if not s:
        return None
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return None
