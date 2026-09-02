"""A1 —— 后端主动学习基础设施回归测试。

覆盖 active-learning 的核心 hinge：
- _record_answer 写 AnswerLog + 更新 UserProfile.mastery JSON
- submit_answer 答题后产生 AnswerLog（对/错均记）
- mark_reviewed 间隔重复：correct=True 增长间隔(1→2)+设 next_review_at；
  correct=False 重置间隔=1+next_review_at=now+1d
- /learn/wrong-answers/due 只返回到期(NULL 或 <=now)且未复习的错题
- /learn/check?kp=<id>&count=1 按知识点抽 1 题(hide_answer)
- /study/reading upsert（read→understood 不产生重复行）
- /study/mastery 返回 8 个一级 KP 的掌握度+作答统计

用 conftest 隔离库 + auth_client_normal 夹具，遵循 test_learning_loop 风格。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.db.models import (
    AnswerLog,
    ConceptReading,
    KnowledgePoint,
    Question,
    User,
    UserProfile,
    WrongAnswer,
)
from app.common.auth import hash_password
from app.study.mastery import _record_answer, recompute_all_mastery


def _make_user(db) -> User:
    u = User(
        username="al_user",
        hashed_password=hash_password("safe-pass-2026"),
        display_name="al_user",
        role="user",
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _current_user_id(db) -> int:
    """优先找 auth_client_normal 创建的 guard_normal；找不到则现场建一个。"""
    u = db.query(User).filter_by(username="guard_normal").first()
    if u is None:
        u = _make_user(db)
    return u.id


# ---- 共用种子（镜像 test_learning_loop 的 _KP_SEED）----

_KP_SEED = [
    ("行业认知", "industry", "电力行业整体认知"),
    ("批发市场", "wholesale", "批发交易"),
    ("零售市场", "retail", "零售交易"),
    ("中长期交易", "mid_long_term", "中长期"),
    ("现货市场", "spot", "现货"),
    ("辅助服务", "ancillary", "调频备用"),
    ("绿电绿证", "green", "绿电"),
    ("结算与信用", "settlement", "结算"),
]


def _seed_kps(db) -> dict:
    kps = {}
    for name, code, desc in _KP_SEED:
        kp = KnowledgePoint(name=name, code=code, level=1, description=desc)
        db.add(kp)
    db.commit()
    for kp in db.query(KnowledgePoint).all():
        if kp.code:
            kps[kp.code] = kp
    return kps


def _make_question(*, kp_id: int, stem: str, answer: str = "A") -> Question:
    options = json.dumps(
        [{"key": "A", "text": "选项甲", "is_correct": True},
         {"key": "B", "text": "选项乙", "is_correct": False}],
        ensure_ascii=False,
    )
    return Question(
        type="single", stem=stem, options=options, answer=answer,
        analysis="解析", difficulty=2, knowledge_point_id=kp_id,
        source_type="manual", is_active=True,
    )


# ============ 1. _record_answer 写 AnswerLog + 更新 mastery ============

def test_record_answer_writes_log_and_mastery(db_session):
    kps = _seed_kps(db_session)
    q = _make_question(kp_id=kps["spot"].id, stem="现货出清机制题")
    db_session.add(q)
    db_session.commit()
    uid = _current_user_id(db_session)

    _record_answer(db_session, uid, q.id, is_correct=True)
    db_session.commit()

    logs = db_session.query(AnswerLog).filter_by(question_id=q.id).all()
    assert len(logs) == 1
    assert logs[0].is_correct is True
    assert logs[0].kp_id == kps["spot"].id

    profile = db_session.query(UserProfile).filter_by(user_id=uid).first()
    assert profile is not None
    mastery = json.loads(profile.mastery or "{}")
    assert mastery.get("spot") == 100  # 1 对 / 1 总 = 100%


def test_record_answer_mastery_partial(db_session):
    """答对1答错1 → 掌握度 50。"""
    kps = _seed_kps(db_session)
    db_session.add_all([
        _make_question(kp_id=kps["spot"].id, stem="现货题甲", answer="A"),
        _make_question(kp_id=kps["spot"].id, stem="现货题乙", answer="A"),
    ])
    db_session.commit()
    qs = db_session.query(Question).filter_by(knowledge_point_id=kps["spot"].id).all()
    uid = _current_user_id(db_session)

    _record_answer(db_session, uid, qs[0].id, True)
    _record_answer(db_session, uid, qs[1].id, False)
    db_session.commit()

    profile = db_session.query(UserProfile).filter_by(user_id=uid).first()
    mastery = json.loads(profile.mastery or "{}")
    assert mastery.get("spot") == 50  # 1/2


# ============ 2. submit_answer 产生 AnswerLog ============

def test_submit_answer_creates_answer_log(auth_client_normal, db_session):
    kps = _seed_kps(db_session)
    q = _make_question(kp_id=kps["spot"].id, stem="现货出清题")
    db_session.add(q)
    db_session.commit()

    r = auth_client_normal.post(
        "/api/learn/answer",
        json={"question_id": q.id, "user_answer": "A"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["correct"] is True

    db_session.commit()
    logs = db_session.query(AnswerLog).filter_by(question_id=q.id).all()
    assert len(logs) == 1
    assert logs[0].is_correct is True


def test_submit_answer_wrong_creates_log_and_due_review(auth_client_normal, db_session):
    """答错 → AnswerLog + WrongAnswer 带 next_review_at(未来1天)。"""
    kps = _seed_kps(db_session)
    q = _make_question(kp_id=kps["spot"].id, stem="现货题", answer="A")
    db_session.add(q)
    db_session.commit()

    r = auth_client_normal.post(
        "/api/learn/answer",
        json={"question_id": q.id, "user_answer": "B"},
    )
    assert r.status_code == 200
    assert r.json()["correct"] is False

    db_session.commit()
    assert db_session.query(AnswerLog).filter_by(question_id=q.id).count() == 1
    w = db_session.query(WrongAnswer).filter_by(question_id=q.id).first()
    assert w is not None
    assert w.review_interval == 1
    assert w.next_review_at is not None
    # 未来 1 天（不是已到期）
    assert w.next_review_at > datetime.utcnow()


# ============ 3. mark_reviewed 间隔重复 ============

def test_mark_reviewed_correct_grows_interval(auth_client_normal, db_session):
    """correct=True：间隔 1→2，next_review_at 设为 now+2d。"""
    kps = _seed_kps(db_session)
    q = _make_question(kp_id=kps["spot"].id, stem="现货题")
    db_session.add(q)
    db_session.commit()
    uid = _current_user_id(db_session)

    w = WrongAnswer(
        user_id=uid, question_id=q.id, user_answer="B",
        reviewed=False, review_interval=1,
        next_review_at=datetime.utcnow() + timedelta(days=1),
    )
    db_session.add(w)
    db_session.commit()
    wid = w.id

    r = auth_client_normal.post(
        f"/api/learn/wrong-answers/{wid}/reviewed",
        json={"correct": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reviewed"] is True
    assert body["review_interval"] == 2
    assert body["next_review_at"] is not None

    db_session.commit()
    db_session.refresh(w)
    assert w.reviewed is True
    assert w.review_interval == 2


def test_mark_reviewed_wrong_resets_interval(auth_client_normal, db_session):
    """correct=False：reviewed=False，间隔重置 1，next_review_at=now+1d。"""
    kps = _seed_kps(db_session)
    q = _make_question(kp_id=kps["spot"].id, stem="现货题")
    db_session.add(q)
    db_session.commit()
    uid = _current_user_id(db_session)

    # 模拟已复习过一次、间隔涨到 4 的错题
    w = WrongAnswer(
        user_id=uid, question_id=q.id, user_answer="B",
        reviewed=True, review_interval=4,
        next_review_at=datetime.utcnow() + timedelta(days=4),
    )
    db_session.add(w)
    db_session.commit()

    r = auth_client_normal.post(
        f"/api/learn/wrong-answers/{w.id}/reviewed",
        json={"correct": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reviewed"] is False
    assert body["review_interval"] == 1
    assert body["next_review_at"] is not None

    db_session.commit()
    db_session.refresh(w)
    assert w.reviewed is False
    assert w.review_interval == 1


def test_mark_reviewed_backward_compat_no_body(auth_client_normal, db_session):
    """不传 body → 默认 correct=True（旧标记已掌握行为）。"""
    kps = _seed_kps(db_session)
    q = _make_question(kp_id=kps["spot"].id, stem="现货题")
    db_session.add(q)
    db_session.commit()
    uid = _current_user_id(db_session)
    w = WrongAnswer(user_id=uid, question_id=q.id, user_answer="B", review_interval=1)
    db_session.add(w)
    db_session.commit()

    r = auth_client_normal.post(f"/api/learn/wrong-answers/{w.id}/reviewed")
    assert r.status_code == 200, r.text
    db_session.commit()
    db_session.refresh(w)
    assert w.reviewed is True


# ============ 4. /learn/wrong-answers/due ============

def test_due_returns_only_due_items(auth_client_normal, db_session):
    """due 端点：next_review_at=NULL 或 <=now 且未复习才返回。"""
    kps = _seed_kps(db_session)
    q1 = _make_question(kp_id=kps["spot"].id, stem="到期题")
    q2 = _make_question(kp_id=kps["spot"].id, stem="未到期题")
    q3 = _make_question(kp_id=kps["spot"].id, stem="已掌握题")
    db_session.add_all([q1, q2, q3])
    db_session.commit()
    uid = _current_user_id(db_session)
    now = datetime.utcnow()
    db_session.add_all([
        WrongAnswer(user_id=uid, question_id=q1.id, user_answer="B",
                    reviewed=False, review_interval=1, next_review_at=None),
        WrongAnswer(user_id=uid, question_id=q2.id, user_answer="B",
                    reviewed=False, review_interval=1,
                    next_review_at=now + timedelta(days=2)),
        WrongAnswer(user_id=uid, question_id=q3.id, user_answer="B",
                    reviewed=True, review_interval=2, next_review_at=None),
    ])
    db_session.commit()

    r = auth_client_normal.get("/api/learn/wrong-answers/due")
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [it["question_id"] for it in body["items"]]
    assert q1.id in ids          # NULL → 到期
    assert q2.id not in ids      # 未来 → 未到期
    assert q3.id not in ids      # reviewed=True → 不返回


# ============ 5. /learn/check ============

def test_check_returns_questions_by_kp(auth_client_normal, db_session):
    """GET /learn/check?kp=<id>&count=1 返回 1 题，hide_answer。"""
    kps = _seed_kps(db_session)
    db_session.add_all([
        _make_question(kp_id=kps["spot"].id, stem="现货甲"),
        _make_question(kp_id=kps["spot"].id, stem="现货乙"),
    ])
    db_session.commit()

    r = auth_client_normal.get(
        "/api/learn/check", params={"kp": kps["spot"].id, "count": 1}
    )
    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) == 1
    assert items[0]["knowledge_point_id"] == kps["spot"].id
    assert "answer" not in items[0]  # hide_answer=True


def test_check_404_when_no_questions(auth_client_normal, db_session):
    kps = _seed_kps(db_session)
    r = auth_client_normal.get("/api/learn/check", params={"kp": kps["spot"].id})
    assert r.status_code == 404


# ============ 6. /study/reading upsert ============

def test_reading_upsert(auth_client_normal, db_session):
    # 首次 read
    r = auth_client_normal.post(
        "/api/study/reading/321", json={"status": "read"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "read"

    # 改为 understood → upsert，不产生重复行
    r2 = auth_client_normal.post(
        "/api/study/reading/321", json={"status": "understood"}
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "understood"

    uid = _current_user_id(db_session)
    db_session.commit()
    rows = db_session.query(ConceptReading).filter_by(
        user_id=uid, concept_code="321"
    ).all()
    assert len(rows) == 1
    assert rows[0].status == "understood"

    # 列表
    r3 = auth_client_normal.get("/api/study/reading")
    assert r3.status_code == 200
    items = r3.json()
    assert any(it["concept_code"] == "321" and it["status"] == "understood" for it in items)


def test_reading_bad_status(auth_client_normal, db_session):
    r = auth_client_normal.post(
        "/api/study/reading/322", json={"status": "bogus"}
    )
    assert r.status_code == 400


# ============ 7. /study/mastery 返回 8 KP ============

def test_mastery_returns_8_kps(auth_client_normal, db_session):
    kps = _seed_kps(db_session)
    db_session.add(_make_question(kp_id=kps["spot"].id, stem="现货题"))
    db_session.commit()
    uid = _current_user_id(db_session)

    # 直接调 _record_answer 制造一答对
    q = db_session.query(Question).filter_by(knowledge_point_id=kps["spot"].id).first()
    _record_answer(db_session, uid, q.id, True)
    db_session.commit()

    r = auth_client_normal.get("/api/study/mastery")
    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) == 8
    codes = {it["code"] for it in items}
    assert codes == set(_KP_SEED[i][1] for i in range(8))
    # spot 有 1 次答对 → 100
    spot = next(it for it in items if it["code"] == "spot")
    assert spot["mastery_pct"] == 100
    assert spot["total_attempts"] == 1
    assert spot["correct_attempts"] == 1
    # 无作答的 KP → 0
    industry = next(it for it in items if it["code"] == "industry")
    assert industry["mastery_pct"] == 0
    assert industry["total_attempts"] == 0


def test_recompute_all_mastery_refreshes(db_session):
    kps = _seed_kps(db_session)
    db_session.add_all([
        _make_question(kp_id=kps["spot"].id, stem="现货甲"),
        _make_question(kp_id=kps["spot"].id, stem="现货乙"),
    ])
    db_session.commit()
    qs = db_session.query(Question).filter_by(knowledge_point_id=kps["spot"].id).all()
    uid = _current_user_id(db_session)

    _record_answer(db_session, uid, qs[0].id, True)
    _record_answer(db_session, uid, qs[1].id, False)
    db_session.commit()

    result = recompute_all_mastery(db_session, uid)
    assert result.get("spot") == 50
    profile = db_session.query(UserProfile).filter_by(user_id=uid).first()
    mastery = json.loads(profile.mastery or "{}")
    assert mastery.get("spot") == 50
