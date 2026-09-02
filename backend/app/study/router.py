"""分层学习刷题路由。

入口：/api/study
- 诊断：/diagnosis/paper 生成诊断卷, /diagnosis/evaluate 评估层级
- 内容：/dashboard 根据层级返回 L1/L2/L3 内容
- 省份：/province 对比, /set-home-province 设置主省份
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import (
    AnswerLog,
    ConceptReading,
    GuidedLessonProgress,
    KnowledgeDoc,
    KnowledgePoint,
    ProvinceConfig,
    Question,
    User,
    UserProfile,
    WrongAnswer,
)
from app.common.auth import get_current_user
from app.study.content import get_l1_roadmap, get_l2_content, get_l3_dashboard
from app.study.diagnosis import (
    build_diagnosis_paper,
    evaluate_diagnosis,
    get_or_create_profile,
)
from app.study.guided import GUIDED_UNITS, get_unit
from app.knowledge.ordering import knowledge_doc_order_by

router = APIRouter(prefix="/study", tags=["分层学习"])


# ============ 请求模型 ============

class EvaluateReq(BaseModel):
    answers: list[dict]  # [{question_id, user_answer, tier}]


class SetProvinceReq(BaseModel):
    province: str


class GuidedProgressReq(BaseModel):
    action: str  # start/check/save/complete
    deliverable_text: Optional[str] = None
    check_score: Optional[float] = None
    answers: Optional[list[Optional[int]]] = None


class ReadingStatusReq(BaseModel):
    """概念阅读状态上报。"""
    status: str  # read / understood


# ============ 用户档案 ============

def _effective_level(profile: UserProfile) -> str:
    """有效层级：用户手选优先于诊断结果。"""
    return profile.manual_level or profile.level


@router.get("/profile", summary="用户能力档案+偏好")
def get_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取用户档案：诊断层级 + 手选层级 + 主省份 + 偏好设置。"""
    profile = get_or_create_profile(db, current_user.id)
    import json

    diagnosis = None
    if profile.diagnosis:
        try:
            diagnosis = json.loads(profile.diagnosis)
        except Exception:
            pass

    watched = _safe_json(profile.watched_provinces) or ["浙江"]
    interests = _safe_json(profile.content_interests) or ["all"]
    eff_level = _effective_level(profile)

    return {
        "user_id": profile.user_id,
        # 诊断层级（系统判定的）
        "diagnosed_level": profile.level,
        "diagnosed_level_label": {"L1": "零基础", "L2": "进阶", "L3": "老手"}.get(profile.level, profile.level),
        # 有效层级（手选优先，实际生效的）
        "level": eff_level,
        "level_label": {"L1": "零基础", "L2": "进阶", "L3": "老手"}.get(eff_level, eff_level),
        "manual_level": profile.manual_level,  # None=跟随诊断
        "diagnosed": profile.diagnosed,
        "last_diagnosed_at": profile.last_diagnosed_at,
        "diagnosis": diagnosis,
        # 偏好
        "home_province": profile.home_province,
        "watched_provinces": watched,
        "preferred_difficulty": profile.preferred_difficulty,
        "content_interests": interests,
        "daily_goal": profile.daily_goal,
    }


class UpdatePrefsReq(BaseModel):
    """用户偏好更新 —— 所有字段可选，只更新传入的。"""
    manual_level: Optional[str] = None  # L1/L2/L3/None(跟随诊断)
    home_province: Optional[str] = None
    preferred_difficulty: Optional[int] = None  # 0自适应/1/2/3
    watched_provinces: Optional[list[str]] = None
    content_interests: Optional[list[str]] = None
    daily_goal: Optional[int] = None


@router.put("/preferences", summary="更新用户偏好(省份/层级/难度等)")
def update_preferences(
    req: UpdatePrefsReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新用户偏好。所有字段可选，只更新传入的。

    - manual_level: 设为 None 则跟随诊断结果
    - home_province: 主省份，会自动加入关注列表
    - preferred_difficulty: 0自适应/1简单/2中等/3困难
    - watched_provinces: 关注的省份列表
    """
    import json

    profile = get_or_create_profile(db, current_user.id)
    changed = []

    if req.manual_level is not None:
        # 空字符串表示"清空手选，回到跟随诊断"
        if req.manual_level == "":
            profile.manual_level = None
            changed.append("manual_level(cleared)")
        elif req.manual_level in ("L1", "L2", "L3"):
            profile.manual_level = req.manual_level
            changed.append("manual_level")
        else:
            raise HTTPException(status_code=400, detail="manual_level 必须是 L1/L2/L3 或空串(清空)")

    if req.home_province is not None:
        exists = db.execute(
            select(ProvinceConfig).where(ProvinceConfig.name == req.home_province)
        ).scalars().first()
        if not exists:
            raise HTTPException(status_code=400, detail=f"省份 {req.home_province} 不在支持列表中")
        profile.home_province = req.home_province
        # 主省份自动加入关注列表
        watched = _safe_json(profile.watched_provinces) or []
        if req.home_province not in watched:
            watched.append(req.home_province)
            profile.watched_provinces = json.dumps(watched, ensure_ascii=False)
        changed.append("home_province")

    if req.preferred_difficulty is not None:
        if req.preferred_difficulty not in (0, 1, 2, 3):
            raise HTTPException(status_code=400, detail="preferred_difficulty 必须是 0/1/2/3")
        profile.preferred_difficulty = req.preferred_difficulty
        changed.append("preferred_difficulty")

    if req.watched_provinces is not None:
        # 主省份必须始终在列表中
        provinces = list(set(req.watched_provinces))
        if profile.home_province not in provinces:
            provinces.append(profile.home_province)
        profile.watched_provinces = json.dumps(provinces, ensure_ascii=False)
        changed.append("watched_provinces")

    if req.content_interests is not None:
        profile.content_interests = json.dumps(req.content_interests, ensure_ascii=False)
        changed.append("content_interests")

    if req.daily_goal is not None:
        profile.daily_goal = max(1, min(100, req.daily_goal))
        changed.append("daily_goal")

    if changed:
        db.commit()
    return {"ok": True, "changed": changed}


# 保留旧接口兼容
@router.post("/set-home-province", summary="设置主省份(兼容旧接口)")
def set_home_province(
    req: SetProvinceReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = get_or_create_profile(db, current_user.id)
    import json
    profile.home_province = req.province
    watched = set(_safe_json(profile.watched_provinces) or [])
    watched.add(req.province)
    profile.watched_provinces = json.dumps(list(watched), ensure_ascii=False)
    db.commit()
    return {"ok": True, "home_province": profile.home_province}


# ============ 能力诊断 ============

@router.get("/diagnosis/paper", summary="生成诊断卷(8题)")
def get_diagnosis_paper(db: Session = Depends(get_db)):
    """生成8道梯度诊断题：3基础+3进阶+2老手。"""
    return {"questions": build_diagnosis_paper(db)}


@router.post("/diagnosis/evaluate", summary="评估诊断结果，判定层级")
def evaluate(
    req: EvaluateReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """提交诊断答案，判定 L1/L2/L3。"""
    if not req.answers:
        raise HTTPException(status_code=400, detail="答案不能为空")
    return evaluate_diagnosis(db, req.answers, current_user.id)


# ============ 分层内容仪表盘 ============

@router.get("/dashboard", summary="分层学习仪表盘")
def get_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """根据用户有效层级（手选优先于诊断）返回对应内容：
    L1 → 零基础引导路线图
    L2 → 进阶系统学习 + 主省份深入
    L3 → 老手速查（政策变动+省份动态+新增考点+情景演练）
    """
    profile = get_or_create_profile(db, current_user.id)
    eff_level = _effective_level(profile)  # 手选优先

    if eff_level == "L1":
        return get_l1_roadmap(db, profile)
    elif eff_level == "L2":
        return get_l2_content(db, profile)
    else:
        return get_l3_dashboard(db, profile)


# ============ 主动引导课程 ============

def _progress_map(db: Session, user_id: int) -> dict[str, GuidedLessonProgress]:
    rows = db.execute(
        select(GuidedLessonProgress).where(GuidedLessonProgress.user_id == user_id)
    ).scalars().all()
    return {row.unit_code: row for row in rows}


def _unit_sources(db: Session, unit: dict, limit: int = 5) -> list[dict]:
    from sqlalchemy import or_

    keywords = unit.get("source_keywords") or []
    if not keywords:
        return []
    clauses = []
    for keyword in keywords:
        pattern = f"%{keyword}%"
        clauses.extend([
            KnowledgeDoc.title.like(pattern),
            KnowledgeDoc.content.like(pattern),
            KnowledgeDoc.ai_summary.like(pattern),
        ])
    rows = db.execute(
        select(KnowledgeDoc).where(
            KnowledgeDoc.review_status == "approved",
            or_(*clauses),
        ).order_by(*knowledge_doc_order_by()).limit(limit)
    ).scalars().all()
    return [
        {
            "id": row.id,
            "title": row.title,
            "publish_date": row.publish_date,
            "source": row.source,
            "source_url": row.source_url,
            "doc_type": row.doc_type,
        }
        for row in rows
    ]


def _attempts(row: Optional[GuidedLessonProgress]) -> list[dict]:
    if not row or not row.check_attempts:
        return []
    import json
    try:
        value = json.loads(row.check_attempts)
        return value if isinstance(value, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _progress_brief(row: Optional[GuidedLessonProgress]) -> dict:
    if not row:
        return {"status": "not_started", "progress_pct": 0}
    attempts = _attempts(row)
    latest = attempts[-1] if attempts else None
    return {
        "status": row.status,
        "progress_pct": row.progress_pct,
        "deliverable_text": row.deliverable_text,
        "check_score": row.check_score,
        "attempt_count": len(attempts),
        "wrong_count": latest.get("wrong_count") if latest else None,
        "latest_check_at": latest.get("submitted_at") if latest else None,
        "started_at": row.started_at,
        "completed_at": row.completed_at,
    }


def _public_unit(unit: dict) -> dict:
    """提交前不下发正确答案，答案只通过后端判分后的复盘返回。"""
    return {
        **unit,
        "checks": [
            {key: value for key, value in check.items() if key != "answer"}
            for check in unit.get("checks") or []
        ],
    }


def _evaluate_checks(unit: dict, answers: list[Optional[int]], submitted_at: str) -> dict:
    checks = unit.get("checks") or []
    if len(answers) != len(checks):
        raise HTTPException(status_code=400, detail=f"请完整回答{len(checks)}道即时检查题")
    items = []
    correct_count = 0
    concept_titles = [item["title"] for item in unit.get("concepts") or []]
    for index, check in enumerate(checks):
        answer = answers[index]
        if answer is not None and (
            not isinstance(answer, int)
            or answer < 0
            or answer >= len(check["options"])
        ):
            raise HTTPException(status_code=400, detail=f"第{index + 1}题答案无效")
        correct_index = int(check["answer"])
        is_correct = answer == correct_index
        correct_count += int(is_correct)
        review_target = (
            concept_titles[min(index, len(concept_titles) - 1)]
            if concept_titles else unit["title"]
        )
        items.append({
            "index": index,
            "question": check["question"],
            "options": check["options"],
            "user_answer_index": answer,
            "user_answer_text": check["options"][answer] if answer is not None else "未作答",
            "correct_answer_index": correct_index,
            "correct_answer_text": check["options"][correct_index],
            "is_correct": is_correct,
            "explanation": check["explanation"],
            "knowledge_code": unit.get("knowledge_code"),
            "review_action": f"回看本课「{review_target}」",
        })
    total = len(checks)
    score = round(correct_count / total * 100) if total else 100
    wrong_items = [item for item in items if not item["is_correct"]]
    return {
        "submitted_at": submitted_at,
        "record_available": True,
        "score": score,
        "correct_count": correct_count,
        "wrong_count": len(wrong_items),
        "total": total,
        "answers": answers,
        "items": items,
        "weak_points": list(dict.fromkeys(
            item["review_action"] for item in wrong_items
        )),
    }


def _record_guided_wrong_answers(
    db: Session, user_id: int, unit: dict, attempt: dict
) -> None:
    """把本次引导课即时检查中的错题写入 wrong_answers（幂等：同一 user+question 不重复）。

    镜像 learn/router.py:submit_answer 的 WrongAnswer 创建模式：
    - 仅对答错的 check 写一行 WrongAnswer（user_answer=用户选项文本）
    - 同一 user+question 已存在记录则跳过（避免重复提交产生重复行）
    - 正确答题不写错题本；若该 user+question 已有未复习错题记录，标记为已掌握(reviewed=True)
    - 同时对每一道 check（对+错）调用 _record_answer，让答题流水与掌握度更新

    learn/router 的 submit_answer 写 next_review_at；导学路径同样在答错时设到期复习。
    """
    from datetime import timedelta

    from app.db.models import now_utc
    from app.study.mastery import _record_answer

    checks = unit.get("checks") or []
    items = attempt.get("items") or []
    if not items or len(items) != len(checks):
        return
    now = now_utc()
    for index, item in enumerate(items):
        check = checks[index]
        stem = check["question"]
        # 按 source=unit_code + stem 定位已灌入的 question 行
        q = db.execute(
            select(Question).where(
                Question.source_type == "guided",
                Question.source == unit["code"],
                Question.stem == stem,
            )
        ).scalars().first()
        if not q:
            continue
        is_correct = bool(item.get("is_correct"))
        # 记录答题流水 + 掌握度（与错题写入同一事务）
        _record_answer(db, user_id, q.id, is_correct)
        existing = db.execute(
            select(WrongAnswer).where(
                WrongAnswer.user_id == user_id,
                WrongAnswer.question_id == q.id,
            )
        ).scalars().first()
        if is_correct:
            # 答对了：若存在历史未复习错题记录，标记已掌握
            if existing and not existing.reviewed:
                existing.reviewed = True
        else:
            if existing:
                # 重答错：重置为未复习、间隔归 1、刷新作答
                existing.reviewed = False
                existing.user_answer = item.get("user_answer_text") or ""
                existing.review_interval = 1
                existing.next_review_at = now + timedelta(days=1)
            else:
                db.add(
                    WrongAnswer(
                        user_id=user_id,
                        question_id=q.id,
                        user_answer=item.get("user_answer_text") or "",
                        reviewed=False,
                        review_interval=1,
                        next_review_at=now + timedelta(days=1),
                    )
                )


def _legacy_review(unit: dict, row: Optional[GuidedLessonProgress]) -> Optional[dict]:
    """旧版本只存总分时仍展示正确答案，并明确无法恢复用户当时选择。"""
    if not row or row.status != "completed" or row.check_score is None:
        return None
    checks = unit.get("checks") or []
    return {
        "submitted_at": row.completed_at,
        "record_available": False,
        "legacy": True,
        "score": row.check_score,
        "correct_count": None,
        "wrong_count": None,
        "total": len(checks),
        "answers": [],
        "items": [
            {
                "index": index,
                "question": check["question"],
                "options": check["options"],
                "user_answer_index": None,
                "user_answer_text": "历史版本未保存逐题选择",
                "correct_answer_index": int(check["answer"]),
                "correct_answer_text": check["options"][int(check["answer"])],
                "is_correct": None,
                "explanation": check["explanation"],
                "knowledge_code": unit.get("knowledge_code"),
                "review_action": f"回看本课「{unit['title']}」",
            }
            for index, check in enumerate(checks)
        ],
        "weak_points": [],
    }


@router.get("/guided", summary="小白主动学习课程目录")
def guided_catalog(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    progress = _progress_map(db, current_user.id)
    completed_codes = {
        code for code, row in progress.items() if row.status == "completed"
    }
    units = []
    for unit in GUIDED_UNITS:
        prerequisites = unit.get("prerequisites") or []
        units.append({
            "code": unit["code"],
            "order": unit["order"],
            "title": unit["title"],
            "subtitle": unit["subtitle"],
            "duration_min": unit["duration_min"],
            "objectives": unit["objectives"],
            "unlocked": all(code in completed_codes for code in prerequisites),
            "progress": _progress_brief(progress.get(unit["code"])),
        })
    return {
        "completed": len(completed_codes),
        "total": len(GUIDED_UNITS),
        "units": units,
    }


@router.get("/today", summary="系统安排的今日学习任务")
def today_plan(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    progress = _progress_map(db, current_user.id)
    completed = {
        code for code, row in progress.items() if row.status == "completed"
    }
    current = next(
        (unit for unit in GUIDED_UNITS if unit["code"] not in completed),
        GUIDED_UNITS[-1],
    )
    current_progress = progress.get(current["code"])
    return {
        "date_label": "今日学习安排",
        "completed_units": len(completed),
        "total_units": len(GUIDED_UNITS),
        "unit": {
            "code": current["code"],
            "order": current["order"],
            "title": current["title"],
            "subtitle": current["subtitle"],
            "duration_min": current["duration_min"],
            "progress": _progress_brief(current_progress),
        },
        "tasks": [
            {"key": "learn", "label": "理解核心概念", "minutes": max(current["duration_min"] - 15, 10)},
            {"key": "observe", "label": current["observation"]["title"], "minutes": 5},
            {"key": "check", "label": "完成即时检查", "minutes": 3},
            {"key": "deliver", "label": current["deliverable"]["title"], "minutes": 10},
        ],
    }


@router.get("/guided/{code}", summary="主动学习课详情")
def guided_detail(
    code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    unit = get_unit(code)
    if not unit:
        raise HTTPException(status_code=404, detail="课程不存在")
    progress = _progress_map(db, current_user.id)
    completed = {
        unit_code for unit_code, row in progress.items() if row.status == "completed"
    }
    locked_by = [
        prereq for prereq in unit.get("prerequisites") or [] if prereq not in completed
    ]
    return {
        **_public_unit(unit),
        "unlocked": not locked_by,
        "locked_by": locked_by,
        "progress": _progress_brief(progress.get(code)),
        "sources": _unit_sources(db, unit),
        "attempts": _attempts(progress.get(code)),
        "review": (
            _attempts(progress.get(code))[-1]
            if _attempts(progress.get(code))
            else _legacy_review(unit, progress.get(code))
        ),
    }


@router.post("/guided/{code}/progress", summary="保存课程进度与业务成果")
def update_guided_progress(
    code: str,
    req: GuidedProgressReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from datetime import datetime

    unit = get_unit(code)
    if not unit:
        raise HTTPException(status_code=404, detail="课程不存在")
    row = db.execute(
        select(GuidedLessonProgress).where(
            GuidedLessonProgress.user_id == current_user.id,
            GuidedLessonProgress.unit_code == code,
        )
    ).scalars().first()
    if not row:
        row = GuidedLessonProgress(user_id=current_user.id, unit_code=code)
        db.add(row)
    now = datetime.now().astimezone().isoformat()
    if req.action == "start":
        if row.status != "completed":
            row.status = "in_progress"
        row.progress_pct = max(row.progress_pct or 0, 10)
        row.started_at = row.started_at or now
    elif req.action == "check":
        if req.answers is None:
            raise HTTPException(status_code=400, detail="请提交逐题答案")
        attempt = _evaluate_checks(unit, req.answers, now)
        _record_guided_wrong_answers(db, current_user.id, unit, attempt)
        attempts = _attempts(row)
        attempts.append(attempt)
        import json
        row.check_attempts = json.dumps(attempts[-20:], ensure_ascii=False)
        row.check_score = attempt["score"]
        if row.status != "completed":
            row.status = "in_progress"
        row.progress_pct = max(row.progress_pct or 0, 60)
        row.started_at = row.started_at or now
    elif req.action == "save":
        if req.deliverable_text is not None:
            row.deliverable_text = req.deliverable_text.strip()
        if row.status != "completed":
            row.status = "in_progress"
        row.progress_pct = max(row.progress_pct or 0, 60)
        row.started_at = row.started_at or now
    elif req.action == "complete":
        if req.answers is not None:
            attempt = _evaluate_checks(unit, req.answers, now)
            _record_guided_wrong_answers(db, current_user.id, unit, attempt)
            attempts = _attempts(row)
            attempts.append(attempt)
            import json
            row.check_attempts = json.dumps(attempts[-20:], ensure_ascii=False)
            row.check_score = attempt["score"]
        deliverable = (req.deliverable_text or row.deliverable_text or "").strip()
        score = row.check_score
        if len(deliverable) < 20:
            raise HTTPException(status_code=400, detail="请先完成本课业务成果，至少20个字")
        if score is None or score < 60:
            raise HTTPException(status_code=400, detail="即时检查达到60分后才能完成本课")
        row.deliverable_text = deliverable
        row.check_score = score
        row.status = "completed"
        row.progress_pct = 100
        row.started_at = row.started_at or now
        row.completed_at = now
    else:
        raise HTTPException(status_code=400, detail="action 必须是 start/check/save/complete")
    db.commit()
    db.refresh(row)
    attempts = _attempts(row)
    return {
        "ok": True,
        "code": code,
        "progress": _progress_brief(row),
        "review": attempts[-1] if attempts else _legacy_review(unit, row),
        "attempt_count": len(attempts),
    }


# ============ 省份对比 ============

@router.get("/provinces", summary="省份列表(含规则对比)")
def list_provinces(db: Session = Depends(get_db)):
    """所有支持的省份及其交易规则、现货状态。"""
    provinces = db.execute(
        select(ProvinceConfig).where(ProvinceConfig.is_active.is_(True))
        .order_by(ProvinceConfig.name)
    ).scalars().all()
    import json
    return [
        {
            "name": p.name, "code": p.code, "grid": p.grid,
            "grid_label": {"sgcc": "国家电网", "csg": "南方电网", "impc": "蒙西电网"}.get(p.grid, p.grid),
            "spot_pilot": p.spot_pilot, "spot_status": p.spot_status,
            "platform_url": p.platform_url,
            "rule_summary": p.rule_summary,
            "differences": _safe_json(p.differences),
        }
        for p in provinces
    ]


@router.get("/province/{name}", summary="省份详情(规则+与他省差异)")
def province_detail(name: str, db: Session = Depends(get_db)):
    """某省份的详细规则和与其他省份的差异对比。"""
    p = db.execute(
        select(ProvinceConfig).where(ProvinceConfig.name == name)
    ).scalars().first()
    if not p:
        raise HTTPException(status_code=404, detail="省份不存在")
    # 该省最新政策
    from app.db.models import Policy
    from app.policy.ranking import policy_order_by
    policies = db.execute(
        select(Policy).where(Policy.province == name)
        .order_by(*policy_order_by()).limit(10)
    ).scalars().all()
    return {
        "name": p.name, "code": p.code, "grid": p.grid,
        "spot_pilot": p.spot_pilot, "spot_status": p.spot_status,
        "platform_url": p.platform_url, "info_path": p.info_path,
        "rule_summary": p.rule_summary,
        "differences": _safe_json(p.differences),
        "recent_policies": [
            {"id": pp.id, "title": pp.title, "publish_date": pp.publish_date,
             "category": pp.category, "ai_summary": pp.ai_summary}
            for pp in policies
        ],
    }


def _safe_json(s):
    if not s:
        return None
    import json
    try:
        return json.loads(s)
    except Exception:
        return None


# ============ 概念阅读状态 ============

@router.post("/reading/{concept_code}", summary="上报概念阅读状态(read/understood)")
def upsert_reading(
    concept_code: str,
    req: ReadingStatusReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """upsert ConceptReading(user_id+concept_code 唯一)；设置 status。"""
    if req.status not in ("read", "understood"):
        raise HTTPException(status_code=400, detail="status 必须是 read 或 understood")
    row = db.execute(
        select(ConceptReading).where(
            ConceptReading.user_id == current_user.id,
            ConceptReading.concept_code == concept_code,
        )
    ).scalars().first()
    if row:
        row.status = req.status
    else:
        row = ConceptReading(
            user_id=current_user.id,
            concept_code=concept_code,
            status=req.status,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "concept_code": row.concept_code,
        "status": row.status,
        "read_at": row.updated_at,
    }


@router.get("/reading", summary="概念阅读状态列表")
def list_reading(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = db.execute(
        select(ConceptReading).where(ConceptReading.user_id == current_user.id)
        .order_by(ConceptReading.id.desc())
    ).scalars().all()
    return [
        {"concept_code": r.concept_code, "status": r.status}
        for r in rows
    ]


# ============ 掌握度总览 ============

@router.get("/mastery", summary="各知识点掌握度总览")
def mastery_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回 8 个一级知识点(LEVEL=1)的掌握度与作答统计。

    无作答的 KP 返回 0 掌握度、0 attempts。掌握度按 AnswerLog 聚合实时算。
    """
    from app.study.mastery import _ensure_profile, _recompute_kp_mastery
    import json

    kps = db.execute(
        select(KnowledgePoint).where(KnowledgePoint.level == 1)
        .order_by(KnowledgePoint.sort, KnowledgePoint.id)
    ).scalars().all()

    # 一次性按 kp 聚合 attempts
    # 注意：func.sum 直接作用于 Boolean 列时，SQLAlchemy 会把整数求和结果过
    # Boolean 列的结果处理器(2 → bool(2)=True → int(True)=1)，导致 2 题以上
    # 答对时 correct_attempts 永远是 1、掌握度被低估。用 cast(..., Integer)
    # 强制按整数求和。
    from sqlalchemy import Integer, cast, func
    agg = db.execute(
        select(
            AnswerLog.kp_id.label("kp_id"),
            func.count().label("total"),
            func.sum(cast(AnswerLog.is_correct, Integer)).label("correct"),
        ).where(AnswerLog.user_id == current_user.id)
        .group_by(AnswerLog.kp_id)
    ).all()
    stats = {row.kp_id: (row.total or 0, int(row.correct or 0)) for row in agg}

    # 同步刷新 profile.mastery，保证 JSON 与实时聚合一致
    profile = _ensure_profile(db, current_user.id)
    try:
        mastery_json = json.loads(profile.mastery or "{}")
        if not isinstance(mastery_json, dict):
            mastery_json = {}
    except (json.JSONDecodeError, TypeError):
        mastery_json = {}

    out = []
    for kp in kps:
        total, correct = stats.get(kp.id, (0, 0))
        if total:
            pct = round(correct / total * 100)
        else:
            # 无作答时用 profile.mastery 的旧值（0 若无）
            pct = int(mastery_json.get(kp.code, 0)) if kp.code else 0
        out.append({
            "kp_id": kp.id,
            "code": kp.code,
            "name": kp.name,
            "mastery_pct": pct,
            "total_attempts": int(total),
            "correct_attempts": int(correct),
        })
    return out
