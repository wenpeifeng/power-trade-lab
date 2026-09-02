"""A8 Part1 —— 主动学习 phase-2 增量回归测试。

聚焦 phase-2 新增能力（A1 已有 14 例覆盖 1→2 一档间隔、due 基本过滤、
reading upsert 基本面、mastery 返回 8 KP），本文件补齐：
- 间隔重复完整阶梯 1→2→4（两次正确复习）与 correct=False 重置回 1；
- due 端点对「未来未到期 / 已复习」的排除双保险；
- D2 /knowledge/by-concept 概念级原文召回（top-3 + 空结果 200）；
- reading：read→understood 升级且 GET /study/reading 列出条目；
- mastery 端到端：经 submit_answer 混合作答后 GET /study/mastery 返回正确
  百分比，且 UserProfile.mastery JSON 含该 KP 条目；
- 导学答题（A1 的 wire）：guided check 既写 AnswerLog 又更新 mastery。

沿用 conftest 的 auth_client_normal + db_session 隔离库夹具，测试自洽
（自带 KP/题目/文档种子），不依赖开发数据。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.db.models import (
    AnswerLog,
    ConceptReading,
    KnowledgeDoc,
    KnowledgePoint,
    Question,
    UserProfile,
    WrongAnswer,
)


# ---- 共用种子 ----

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
        db.add(KnowledgePoint(name=name, code=code, level=1, description=desc))
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


def _make_guided_question(*, kp_id: int, unit_code: str, stem: str,
                          options: list[str], answer_index: int) -> Question:
    """镜像 _record_guided_wrong_answers 的查题条件：
    source_type='guided', source=unit_code, stem=check.question。
    options 存成 guided check 形式（前端不发 key，后端按 index 判分）。
    """
    opts = json.dumps(
        [{"key": chr(65 + i), "text": t, "is_correct": i == answer_index}
         for i, t in enumerate(options)],
        ensure_ascii=False,
    )
    return Question(
        type="single", stem=stem, options=opts,
        answer=chr(65 + answer_index), analysis="导学解析",
        difficulty=2, knowledge_point_id=kp_id,
        source_type="guided", source=unit_code, is_active=True,
    )


def _current_user_id(db) -> int:
    u = db.query(__import__("app.db.models", fromlist=["User"]).User).filter_by(
        username="guard_normal"
    ).first()
    assert u is not None, "auth_client_normal 应已建好 guard_normal"
    return u.id


# ============ 1. 间隔重复完整阶梯 1→2→4 ============

def test_mark_reviewed_correct_grows_1_to_2_to_4(auth_client_normal, db_session):
    """两次正确复习：间隔 1→2→4，每次 next_review_at 都被刷新到未来。"""
    kps = _seed_kps(db_session)
    q = _make_question(kp_id=kps["spot"].id, stem="现货出清题")
    db_session.add(q)
    db_session.commit()
    uid = _current_user_id(db_session)

    w = WrongAnswer(
        user_id=uid, question_id=q.id, user_answer="B",
        reviewed=False, review_interval=1,
        next_review_at=None,  # NULL → 到期，可复习
    )
    db_session.add(w)
    db_session.commit()

    # 第一次正确复习：1 → 2
    r1 = auth_client_normal.post(
        f"/api/learn/wrong-answers/{w.id}/reviewed", json={"correct": True}
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["review_interval"] == 2
    db_session.commit()
    db_session.refresh(w)
    assert w.reviewed is True
    assert w.review_interval == 2

    # 第二次正确复习：2 → 4
    r2 = auth_client_normal.post(
        f"/api/learn/wrong-answers/{w.id}/reviewed", json={"correct": True}
    )
    assert r2.status_code == 200
    assert r2.json()["review_interval"] == 4
    db_session.commit()
    db_session.refresh(w)
    assert w.review_interval == 4
    # next_review_at 始终是未来（间隔天）
    assert w.next_review_at is not None
    assert w.next_review_at > datetime.utcnow()


def test_mark_reviewed_wrong_after_progress_resets_to_1(auth_client_normal, db_session):
    """已涨到 4 的错题答错 → 重置 1，reviewed=False，next_review_at=now+1d。"""
    kps = _seed_kps(db_session)
    q = _make_question(kp_id=kps["spot"].id, stem="现货题")
    db_session.add(q)
    db_session.commit()
    uid = _current_user_id(db_session)

    w = WrongAnswer(
        user_id=uid, question_id=q.id, user_answer="B",
        reviewed=True, review_interval=4,
        next_review_at=datetime.utcnow() + timedelta(days=4),
    )
    db_session.add(w)
    db_session.commit()

    r = auth_client_normal.post(
        f"/api/learn/wrong-answers/{w.id}/reviewed", json={"correct": False}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reviewed"] is False
    assert body["review_interval"] == 1
    db_session.commit()
    db_session.refresh(w)
    assert w.reviewed is False
    assert w.review_interval == 1


# ============ 2. due 端点排除双保险 ============

def test_due_excludes_future_and_reviewed(auth_client_normal, db_session):
    """due 只返回 (next_review_at IS NULL 或 <=now) 且 reviewed=False 的条目。

    4 条种子：
    - q1: NULL + 未复习 → 命中
    - q2: 未来(2d) + 未复习 → 排除
    - q3: 过去(已到期) + 未复习 → 命中
    - q4: NULL + 已复习 → 排除
    """
    kps = _seed_kps(db_session)
    qs = [_make_question(kp_id=kps["spot"].id, stem=f"due题{i}") for i in range(4)]
    db_session.add_all(qs)
    db_session.commit()
    uid = _current_user_id(db_session)
    now = datetime.utcnow()
    db_session.add_all([
        WrongAnswer(user_id=uid, question_id=qs[0].id, user_answer="B",
                    reviewed=False, review_interval=1, next_review_at=None),
        WrongAnswer(user_id=uid, question_id=qs[1].id, user_answer="B",
                    reviewed=False, review_interval=1,
                    next_review_at=now + timedelta(days=2)),
        WrongAnswer(user_id=uid, question_id=qs[2].id, user_answer="B",
                    reviewed=False, review_interval=1,
                    next_review_at=now - timedelta(days=1)),
        WrongAnswer(user_id=uid, question_id=qs[3].id, user_answer="B",
                    reviewed=True, review_interval=2, next_review_at=None),
    ])
    db_session.commit()

    r = auth_client_normal.get("/api/learn/wrong-answers/due")
    assert r.status_code == 200, r.text
    ids = [it["question_id"] for it in r.json()["items"]]
    assert qs[0].id in ids      # NULL
    assert qs[2].id in ids      # 过去
    assert qs[1].id not in ids   # 未来
    assert qs[3].id not in ids   # 已复习


# ============ 3. D2 /knowledge/by-concept 概念级原文召回 ============

def _seed_doc(db, title, *, kp_id=None, content="", ai_summary="",
              source_url=None, publish_date="2026-07-01",
              doc_type="regulation", source="发改委",
              review_status="approved"):
    doc = KnowledgeDoc(
        title=title, doc_type=doc_type, source=source, source_url=source_url,
        content=content, ai_summary=ai_summary, knowledge_point_id=kp_id,
        publish_date=publish_date, review_status=review_status,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def test_by_concept_returns_top3_approved_docs(auth_client_normal, db_session):
    """title=双边协商 召回 approved 文档，limit=3 截断。"""
    for i in range(4):
        _seed_doc(db_session, f"双边协商案例第{i}篇",
                  ai_summary="双边协商流程", publish_date=f"2026-0{i+1}-01")
    # pending 文档不应出现
    _seed_doc(db_session, "双边协商待审稿", review_status="pending")

    r = auth_client_normal.get("/api/knowledge/by-concept",
                               params={"title": "双边协商", "limit": 3})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 3
    for it in body["items"]:
        assert "双边协商" in it["title"]
        assert "source_url" in it  # _doc_brief 之外补的字段


def test_by_concept_returns_empty_200_when_no_match(auth_client_normal, db_session):
    """无命中时返回 200 + 空列表（前端据此隐藏区块，不报错）。"""
    _seed_doc(db_session, "完全无关的标题")
    r = auth_client_normal.get("/api/knowledge/by-concept",
                               params={"title": "双边协商"})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 0
    assert body["items"] == []


# ============ 4. reading：read→understood 升级 + 列表 ============

def test_reading_read_then_understood_upserts_and_lists(auth_client_normal, db_session):
    code = "321"
    # 首次 read
    r1 = auth_client_normal.post(f"/api/study/reading/{code}",
                                 json={"status": "read"})
    assert r1.status_code == 200, r1.text
    assert r1.json()["status"] == "read"

    # 升级 understood —— upsert，不产生重复行
    r2 = auth_client_normal.post(f"/api/study/reading/{code}",
                                 json={"status": "understood"})
    assert r2.status_code == 200
    assert r2.json()["status"] == "understood"

    uid = _current_user_id(db_session)
    db_session.commit()
    rows = db_session.query(ConceptReading).filter_by(
        user_id=uid, concept_code=code
    ).all()
    assert len(rows) == 1
    assert rows[0].status == "understood"

    # GET /study/reading 列出该条目
    r3 = auth_client_normal.get("/api/study/reading")
    assert r3.status_code == 200
    items = r3.json()
    assert any(it["concept_code"] == code and it["status"] == "understood"
               for it in items)


# ============ 5. mastery 端到端：submit_answer 混合作答 ============

def test_mastery_end_to_end_via_submit_answer(auth_client_normal, db_session):
    """答 3 题（2 对 1 错）→ /study/mastery 返回 67%，且 profile.mastery 含 spot。"""
    kps = _seed_kps(db_session)
    qs = [
        _make_question(kp_id=kps["spot"].id, stem="现货甲", answer="A"),
        _make_question(kp_id=kps["spot"].id, stem="现货乙", answer="A"),
        _make_question(kp_id=kps["spot"].id, stem="现货丙", answer="A"),
    ]
    db_session.add_all(qs)
    db_session.commit()
    uid = _current_user_id(db_session)

    # 2 对 1 错
    for q, ua in [(qs[0], "A"), (qs[1], "A"), (qs[2], "B")]:
        r = auth_client_normal.post("/api/learn/answer",
                                    json={"question_id": q.id, "user_answer": ua})
        assert r.status_code == 200, r.text

    # GET /study/mastery
    r = auth_client_normal.get("/api/study/mastery")
    assert r.status_code == 200, r.text
    items = r.json()
    spot = next(it for it in items if it["code"] == "spot")
    assert spot["mastery_pct"] == 67  # round(2/3*100)
    assert spot["total_attempts"] == 3
    assert spot["correct_attempts"] == 2

    # UserProfile.mastery JSON 含 spot 条目
    db_session.commit()
    profile = db_session.query(UserProfile).filter_by(user_id=uid).first()
    assert profile is not None
    mastery = json.loads(profile.mastery or "{}")
    assert mastery.get("spot") == 67

    # AnswerLog 落了 3 行
    logs = db_session.query(AnswerLog).filter(
        AnswerLog.user_id == uid,
        AnswerLog.kp_id == kps["spot"].id,
    ).all()
    assert len(logs) == 3


# ============ 6. 导学答题写 answer_log + 更新 mastery（A1 wire）============

def test_guided_check_writes_answer_log_and_mastery(auth_client_normal, db_session):
    """guided check：答错一道 → AnswerLog 落行 + mastery 更新该 KP。

    _record_guided_wrong_answers 按 source_type='guided'+source=unit_code+stem
    定位题目，再调 _record_answer(db, uid, q.id, is_correct)。
    本测试镜像 power_system_map 单元的唯一 check：
      stem = "电力交易成交后，物理送电是否可以脱离电网调度独立完成？"
      options = ["可以","不可以"], answer=1（index）
    """
    kps = _seed_kps(db_session)
    # 单元 knowledge_code=industry → KP industry
    kp = kps["industry"]
    unit_code = "power_system_map"
    stem = "电力交易成交后，物理送电是否可以脱离电网调度独立完成？"
    q = _make_guided_question(
        kp_id=kp.id, unit_code=unit_code, stem=stem,
        options=["可以", "不可以"], answer_index=1,
    )
    db_session.add(q)
    db_session.commit()
    uid = _current_user_id(db_session)

    # action=check，答 index 0（"可以"，错；正确是 1 "不可以"）
    r = auth_client_normal.post(
        f"/api/study/guided/{unit_code}/progress",
        json={"action": "check", "answers": [0]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    review = body["review"]
    assert review["score"] == 0  # 0/1
    assert review["wrong_count"] == 1

    # AnswerLog 落了一行（答错也记）
    db_session.commit()
    logs = db_session.query(AnswerLog).filter(
        AnswerLog.user_id == uid, AnswerLog.question_id == q.id,
    ).all()
    assert len(logs) == 1
    assert logs[0].is_correct is False
    assert logs[0].kp_id == kp.id

    # mastery JSON 已更新：industry = 0（1 题 0 对）
    profile = db_session.query(UserProfile).filter_by(user_id=uid).first()
    assert profile is not None
    mastery = json.loads(profile.mastery or "{}")
    assert "industry" in mastery
    assert mastery["industry"] == 0

    # /study/mastery 也能看到这条统计
    r2 = auth_client_normal.get("/api/study/mastery")
    industry = next(it for it in r2.json() if it["code"] == "industry")
    assert industry["total_attempts"] == 1
    assert industry["correct_attempts"] == 0
    assert industry["mastery_pct"] == 0
