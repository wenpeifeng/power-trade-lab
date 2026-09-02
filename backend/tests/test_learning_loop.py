"""L13 —— 学习闭环回归测试。

覆盖先前各修复点的闭环关键节点（不重复单点测试的细枝末节，只钉住"闭环
 hinges"——即断一处就破坏端到端学习路径的那些衔接）：

- L4: 考试薄弱点分析 weak_points 携带 knowledge_point_id（前端据此跳针对性练习）。
- L5: 检索引擎诚实化端点 search-status 返回 embedder/semantic_available/model_name。
- L7: 知识点前置网络 prerequisites/<code> 与文档知识网络 network/<doc_id> 都返回
  前置知识点，且 spot 的前置包含 mid_long_term。
- L8: 导学课即时检查答错 → 写入 wrong_answers 并关联到入库的 guided 题目；
  再次提交不产生重复行（错题本不随练习次数膨胀）。
- L10: 文档 knowledge_point_id 回填脚本把 NULL 文档填上正确知识点。
- 组卷按 kp 过滤：/learn/quiz 只返回该知识点下的题目（闭环"练本节"入口）。

使用 conftest 的隔离库 + 已登录 TestClient 夹具，遵循 test_asset_guard 风格。
"""
from __future__ import annotations

import json

import pytest

from app.db.models import (
    ExamSession,
    KnowledgeDoc,
    KnowledgePoint,
    KnowledgePointPrerequisite,
    Question,
    WrongAnswer,
)
from app.exam.engine import analyze_weakness
from app.study.guided import GUIDED_UNITS
from scripts.backfill_doc_kp import CATEGORY_TO_KP, backfill
from scripts.seed_kp_prerequisites import EDGES
from scripts.seed_guided_questions import _difficulty_for_order, _stem_hash


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
    """种 8 个一级知识点，返回 code -> KnowledgePoint。"""
    kps = {}
    for name, code, desc in _KP_SEED:
        kp = KnowledgePoint(name=name, code=code, level=1, description=desc)
        db.add(kp)
    db.commit()
    for kp in db.query(KnowledgePoint).all():
        if kp.code:
            kps[kp.code] = kp
    return kps


def _seed_prereq_edges(db, kps: dict) -> None:
    for kp_code, prereq_code in EDGES:
        db.add(KnowledgePointPrerequisite(
            kp_id=kps[kp_code].id, prereq_kp_id=kps[prereq_code].id
        ))
    db.commit()


def _make_question(
    *, kp_id: int, stem: str, answer: str = "A", qtype: str = "single",
    source_type: str = "manual", source: str | None = None,
) -> Question:
    options = json.dumps(
        [{"key": "A", "text": "选项甲", "is_correct": True},
         {"key": "B", "text": "选项乙", "is_correct": False}],
        ensure_ascii=False,
    )
    return Question(
        type=qtype, stem=stem, options=options, answer=answer,
        analysis="解析", difficulty=2, knowledge_point_id=kp_id,
        source_type=source_type, source=source, is_active=True,
    )


def _seed_guided_questions(db, kps: dict, *, unit_code: str | None = None) -> dict:
    """灌入 guided 题目（仅指定单元或全部），返回 code -> 题目列表。"""
    out: dict[str, list[Question]] = {}
    for unit in GUIDED_UNITS:
        if unit_code and unit["code"] != unit_code:
            continue
        kp_id = kps[unit["knowledge_code"]].id if unit.get("knowledge_code") else None
        qs = []
        for check in unit.get("checks") or []:
            stem = check["question"]
            sh = _stem_hash(stem)
            answer_index = int(check["answer"])
            options_json = json.dumps(
                [
                    {"key": chr(ord("A") + i), "text": opt, "is_correct": i == answer_index}
                    for i, opt in enumerate(check["options"])
                ],
                ensure_ascii=False,
            )
            q = Question(
                type="single", stem=stem, options=options_json,
                answer=chr(ord("A") + answer_index),
                analysis=check.get("explanation"),
                knowledge_point_id=kp_id,
                source=unit["code"], source_type="guided",
                is_ai_generated=False, is_active=True,
                difficulty=_difficulty_for_order(int(unit["order"])),
                stem_hash=sh,
            )
            db.add(q)
            qs.append(q)
        out[unit["code"]] = qs
    db.commit()
    return out


# ============ L? 组卷按 kp 过滤（闭环"练本节"入口） ============

def test_quiz_filters_by_knowledge_point(client, db_session):
    """POST /api/learn/quiz?knowledge_point_id=<kp> 只返回该知识点题目。"""
    kps = _seed_kps(db_session)
    kp_a, kp_b = kps["spot"], kps["mid_long_term"]
    db_session.add_all([
        _make_question(kp_id=kp_a.id, stem="现货题-甲"),
        _make_question(kp_id=kp_a.id, stem="现货题-乙", answer="A"),
        _make_question(kp_id=kp_b.id, stem="中长期题-丙"),
    ])
    db_session.commit()

    resp = client.post(
        "/api/learn/quiz",
        json={"knowledge_point_id": kp_a.id, "count": 10},
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert items, "应至少返回一道题"
    # 闭环核心：全部归属于请求的 kp，绝不混入其它知识点
    assert all(q["knowledge_point_id"] == kp_a.id for q in items)
    assert all("现货" in q["stem"] for q in items)
    # 不超过该 kp 实有题量
    assert len(items) <= 2


def test_quiz_empty_when_kp_has_no_questions(client, db_session):
    """POST /learn/quiz 对无题的筛选返回 200 + 空列表，而非 404——前端展示空状态。"""
    kps = _seed_kps(db_session)
    db_session.add(_make_question(kp_id=kps["spot"].id, stem="现货题"))
    db_session.commit()
    # 查一个有知识点但无题的 kp
    resp = client.post(
        "/api/learn/quiz",
        json={"knowledge_point_id": kps["ancillary"].id, "count": 5},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


# ============ L4 考试薄弱点携带 knowledge_point_id ============

def test_analyze_weakness_carries_knowledge_point_id(db_session):
    """analyze_weakness 返回的 weak_points 必须带 knowledge_point_id，前端据此跳转。"""
    kps = _seed_kps(db_session)
    kp = kps["spot"]
    q = _make_question(kp_id=kp.id, stem="现货出清机制题")
    db_session.add(q)
    db_session.commit()
    # 构造一次已交卷考试会话：该题答错 → 错误率 100% → 薄弱点
    session = ExamSession(
        user_id=1, mode="exam", level="four",
        question_ids=json.dumps([q.id]),
        answers=json.dumps([
            {"question_id": q.id, "user_answer": "B", "correct": False, "time_cost": 12}
        ], ensure_ascii=False),
        score=0.0, status="finished",
    )
    db_session.add(session)
    db_session.commit()

    result = analyze_weakness(db_session, session.id)
    weak = result.get("weak_points", [])
    assert weak, "该知识点全错，应判为薄弱"
    w = weak[0]
    assert w["knowledge_point"] == kp.name
    # L4 修复点：携带 knowledge_point_id，供前端跳"练本节"
    assert w["knowledge_point_id"] == kp.id
    assert w["wrong_rate"] == 100


# ============ L7 知识点前置网络 ============

def test_prerequisites_spot_includes_mid_long_term(client, db_session):
    """GET /api/knowledge/prerequisites/spot 返回 ≥2 前置，含 mid_long_term。"""
    kps = _seed_kps(db_session)
    _seed_prereq_edges(db_session, kps)

    resp = client.get("/api/knowledge/prerequisites/spot")
    assert resp.status_code == 200
    body = resp.json()
    assert body["kp"]["code"] == "spot"
    codes = {p["code"] for p in body["prerequisites"]}
    assert "mid_long_term" in codes
    assert len(body["prerequisites"]) >= 2
    assert all("description" in p for p in body["prerequisites"])


def test_knowledge_network_includes_prerequisites(client, db_session):
    """GET /api/knowledge/network/<doc_id> 文档知识网络含 prerequisites 列表。"""
    kps = _seed_kps(db_session)
    _seed_prereq_edges(db_session, kps)
    # 一篇链接到 spot 知识点的已过审文档
    doc = KnowledgeDoc(
        title="现货市场日前出清规则", doc_type="regulation",
        review_status="approved", knowledge_point_id=kps["spot"].id,
        source="test",
    )
    db_session.add(doc)
    db_session.commit()

    resp = client.get(f"/api/knowledge/network/{doc.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["knowledge_point"]["id"] == kps["spot"].id
    assert "prerequisites" in body
    prereq_codes = {p["code"] for p in body["prerequisites"]}
    # spot 的前置应含 mid_long_term
    assert "mid_long_term" in prereq_codes


# ============ L5 检索引擎诚实化 ============

def test_search_status_honesty(client, db_session):
    """GET /api/knowledge/search-status 返回 embedder/semantic_available/model_name。"""
    resp = client.get("/api/knowledge/search-status")
    assert resp.status_code == 200
    body = resp.json()
    # 三个诚实化字段都在
    assert "embedder" in body
    assert "semantic_available" in body
    assert "model_name" in body
    # embedder 取值受控（不向后端乱报）
    assert body["embedder"] in {"uninitialized", "tfidf", "sentence-transformer"}
    # semantic_available 与 embedder 一致性：tfidf 时为 False，sentence-transformer 时为 True
    if body["embedder"] == "tfidf":
        assert body["semantic_available"] is False
    elif body["embedder"] == "sentence-transformer":
        assert body["semantic_available"] is True


# ============ L8 导学答错 → 错题本（幂等不重复） ============

def test_guided_wrong_answer_flows_to_wrong_answers(auth_client_normal, db_session):
    """导学课 check 答错 → 写入 wrong_answers 并关联入库的 guided 题目。"""
    kps = _seed_kps(db_session)
    seeded = _seed_guided_questions(db_session, kps, unit_code="power_system_map")
    unit = next(u for u in GUIDED_UNITS if u["code"] == "power_system_map")
    guided_q = seeded["power_system_map"][0]

    # answers=[0]：power_system_map 的正确答案 index=1，故 0=错
    resp = auth_client_normal.post(
        "/api/study/guided/power_system_map/progress",
        json={"action": "check", "answers": [0]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["review"]["score"] == 0
    assert body["review"]["items"][0]["is_correct"] is False

    # 提交后另起会话读取（避免事务快照看不到端点提交）
    db_session.commit()
    wrongs = db_session.query(WrongAnswer).all()
    assert len(wrongs) == 1
    assert wrongs[0].question_id == guided_q.id
    assert wrongs[0].reviewed is False
    # 关联的题目确实是入库的 guided 题
    q = db_session.get(Question, wrongs[0].question_id)
    assert q.source_type == "guided"
    assert q.source == "power_system_map"
    assert q.stem == unit["checks"][0]["question"]


def test_guided_resubmit_wrong_does_not_duplicate(auth_client_normal, db_session):
    """再次答错同一题 → 不产生重复 WrongAnswer 行。"""
    kps = _seed_kps(db_session)
    _seed_guided_questions(db_session, kps, unit_code="power_system_map")

    payload = {"action": "check", "answers": [0]}
    r1 = auth_client_normal.post(
        "/api/study/guided/power_system_map/progress", json=payload
    )
    assert r1.status_code == 200
    r2 = auth_client_normal.post(
        "/api/study/guided/power_system_map/progress", json=payload
    )
    assert r2.status_code == 200

    db_session.commit()
    wrongs = db_session.query(WrongAnswer).all()
    assert len(wrongs) == 1  # 幂等：仍是 1 行


def test_guided_wrong_answer_visible_in_wrong_book(auth_client_normal, db_session):
    """闭环：导学答错的题在错题本 GET /learn/wrong-answers 可见。"""
    kps = _seed_kps(db_session)
    seeded = _seed_guided_questions(db_session, kps, unit_code="power_system_map")
    guided_q = seeded["power_system_map"][0]

    auth_client_normal.post(
        "/api/study/guided/power_system_map/progress",
        json={"action": "check", "answers": [0]},
    )
    db_session.commit()

    resp = auth_client_normal.get("/api/learn/wrong-answers")
    assert resp.status_code == 200
    rows = resp.json()
    assert any(r["question_id"] == guided_q.id for r in rows)


# ============ L13 常规刷题答错 → 错题本（幂等不重复） ============

def test_regular_wrong_answer_creates_single_wrong_row(auth_client_normal, db_session):
    """POST /api/learn/answer 答错 → 恰好写一行 WrongAnswer。"""
    kps = _seed_kps(db_session)
    q = _make_question(kp_id=kps["spot"].id, stem="现货出清机制题")
    db_session.add(q)
    db_session.commit()

    resp = auth_client_normal.post(
        "/api/learn/answer",
        json={"question_id": q.id, "user_answer": "B"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["correct"] is False

    db_session.commit()
    wrongs = db_session.query(WrongAnswer).filter_by(question_id=q.id).all()
    assert len(wrongs) == 1
    assert wrongs[0].reviewed is False
    assert wrongs[0].user_answer == "B"


def test_regular_resubmit_wrong_does_not_duplicate(auth_client_normal, db_session):
    """再次答错同一题 → 不产生第二行，仅刷新 user_answer 并重置 reviewed=False。"""
    kps = _seed_kps(db_session)
    q = _make_question(kp_id=kps["spot"].id, stem="现货出清机制题")
    db_session.add(q)
    db_session.commit()

    for ans in ("B", "C"):
        r = auth_client_normal.post(
            "/api/learn/answer",
            json={"question_id": q.id, "user_answer": ans},
        )
        assert r.status_code == 200
        assert r.json()["correct"] is False

    db_session.commit()
    wrongs = db_session.query(WrongAnswer).filter_by(question_id=q.id).all()
    assert len(wrongs) == 1  # 幂等：仍是 1 行
    assert wrongs[0].user_answer == "C"  # 刷新为最近一次作答
    assert wrongs[0].reviewed is False


def test_regular_correct_answer_creates_no_wrong_row(auth_client_normal, db_session):
    """答对 → 不写错题本（仍是 0 行）。"""
    kps = _seed_kps(db_session)
    q = _make_question(kp_id=kps["spot"].id, stem="现货出清机制题", answer="A")
    db_session.add(q)
    db_session.commit()

    resp = auth_client_normal.post(
        "/api/learn/answer",
        json={"question_id": q.id, "user_answer": "A"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["correct"] is True

    db_session.commit()
    assert db_session.query(WrongAnswer).filter_by(question_id=q.id).count() == 0


# ============ L10 文档 KP 回填 ============

def test_backfill_fills_null_doc_kp(db_session):
    """category_code 或关键词能定位知识点的 NULL 文档被回填。"""
    kps = _seed_kps(db_session)
    # 一篇有 category_code 的 approved 文档（311 → mid_long_term）
    doc_cat = KnowledgeDoc(
        title="中长期年度月度双边协商规则",
        doc_type="regulation", source="test",
        category_code="311", review_status="approved",
        knowledge_point_id=None,
    )
    # 一篇无 category_code 但内容含"现货"关键词的 approved 文档
    doc_kw = KnowledgeDoc(
        title="关于完善现货市场日前出清的通知",
        content="现货市场日前出清 LMP 节点电价",
        doc_type="national_policy", source="test",
        category_code=None, review_status="approved",
        knowledge_point_id=None,
    )
    # 一篇 pending 不应被处理
    doc_pending = KnowledgeDoc(
        title="待审现货文档",
        content="现货", doc_type="industry_news", source="test",
        review_status="pending", knowledge_point_id=None,
    )
    db_session.add_all([doc_cat, doc_kw, doc_pending])
    db_session.commit()

    stats = backfill(db_session, apply=True)
    assert stats["filled"] == 2
    assert stats["still_orphan"] == 0

    db_session.refresh(doc_cat)
    db_session.refresh(doc_kw)
    db_session.refresh(doc_pending)
    assert doc_cat.knowledge_point_id == kps["mid_long_term"].id
    assert doc_kw.knowledge_point_id == kps["spot"].id
    assert doc_pending.knowledge_point_id is None  # pending 不动


def test_category_to_kp_mapping_covers_core_codes():
    """L10 分流映射表覆盖核心分类码且无 None 值。"""
    expected = {
        "311": "mid_long_term", "312": "spot", "32": "ancillary",
        "351": "green", "5": "settlement", "7": "wholesale", "64": "retail",
    }
    for code, want in expected.items():
        assert CATEGORY_TO_KP.get(code) == want, f"分类 {code} 应映射到 {want}"
    # 关键不变量：映射值不含 None/空串
    assert all(isinstance(v, str) and v for v in CATEGORY_TO_KP.values())
    # 8 个知识点都被映射覆盖（每个 code 至少能被某前缀命中）
    covered = set(CATEGORY_TO_KP.values())
    assert {
        "industry", "wholesale", "retail", "mid_long_term",
        "spot", "ancillary", "green", "settlement",
    }.issubset(covered)
