"""polish3 —— ExamResult 去练习 e2e 验证。

回归 drillWeak 链路：ExamResult 的"去练习"按钮把 weak_points[i]
的 knowledge_point_id 作为 ?kp=<id> 带到 Quiz 页；Quiz 页用该 id
组卷应只返回该 KP 下的题目。

此前该路径仅 code-review（测试用户无考试历史），本测试用真实 API
会话跑通：建考 → 答错 → 交卷判分 → 取结果(weak_points) → 用
weak kp 调 /learn/quiz 验证题目归属。沿用 conftest 的
auth_client_normal + db_session 隔离库夹具。
"""
from __future__ import annotations

import json

import pytest

from app.db.models import KnowledgePoint, Question


# ---- 共用种子（镜像 test_active_learning_phase2 的 _KP_SEED 子集）----

_KP_SEED = [
    ("现货市场", "spot", "现货"),
    ("中长期交易", "mid_long_term", "中长期"),
    ("辅助服务", "ancillary", "调频备用"),
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


def _make_question(*, kp_id: int, qtype: str, stem: str, answer: str = "A") -> Question:
    options = json.dumps(
        [
            {"key": "A", "text": "选项甲", "is_correct": True},
            {"key": "B", "text": "选项乙", "is_correct": False},
        ],
        ensure_ascii=False,
    )
    return Question(
        type=qtype, stem=stem, options=options, answer=answer,
        analysis="解析", difficulty=2, knowledge_point_id=kp_id,
        source_type="manual", is_active=True,
    )


def _current_user_id(db) -> int:
    from app.db.models import User

    u = db.query(User).filter_by(username="guard_normal").first()
    assert u is not None, "auth_client_normal 应已建好 guard_normal"
    return u.id


def _start_and_submit_wrong_exam(client, count: int = 10) -> dict:
    """开考 → 全部答错 → 交卷，返回 submit 响应 JSON。"""
    start = client.post("/api/exam/start", json={"mode": "exam", "count": count})
    assert start.status_code == 200, start.text
    paper = start.json()
    session_id = paper["session_id"]
    questions = paper["questions"]

    # 全部答错：user_answer 故意取一个不可能匹配的值
    answers = [
        {"question_id": q["id"], "user_answer": "__WRONG__", "time_cost": 5}
        for q in questions
    ]
    submit = client.post(
        "/api/exam/submit", json={"session_id": session_id, "answers": answers}
    )
    assert submit.status_code == 200, submit.text
    return submit.json()


def test_drill_weak_carries_correct_kp_id(auth_client_normal, db_session):
    """考后 weak_points 含 knowledge_point_id，且以该 id 组卷只返回该 KP 题。"""
    kps = _seed_kps(db_session)
    target = kps["spot"]

    # 在目标 KP 下铺足够多、覆盖三种题型的题，让组卷引擎抽到的几乎都是该 KP
    for qtype in ("single", "multiple", "judge"):
        for i in range(4):
            db_session.add(_make_question(
                kp_id=target.id, qtype=qtype, stem=f"{qtype}-{i}",
            ))
    # 其他 KP 也放少量题，避免组卷引擎在补齐时混入（target 池足够大）
    db_session.add(_make_question(kp_id=kps["mid_long_term"].id, qtype="single", stem="mlt-0"))
    db_session.add(_make_question(kp_id=kps["ancillary"].id, qtype="single", stem="anc-0"))
    db_session.commit()

    result = _start_and_submit_wrong_exam(auth_client_normal, count=10)

    # 交卷响应必含 weak_points，且至少一个带 knowledge_point_id
    assert result["weak_points"], "答错全部题后应产生薄弱知识点"
    with_id = [w for w in result["weak_points"] if w.get("knowledge_point_id")]
    assert with_id, "weak_points 应携带 knowledge_point_id 以驱动去练习跳转"

    # 目标 KP 错误率应最高（其题被全答错），取其 id 作为 drill 目标
    drill_weak = next(
        (w for w in with_id if w["knowledge_point_id"] == target.id),
        None,
    )
    assert drill_weak is not None, "目标 KP 应出现在 weak_points 中"
    kp_id = drill_weak["knowledge_point_id"]

    # 用 /exam/result/{session_id} 重取（ExamResult 页真实加载路径），
    # 验证 weak_points 在结果详情端点同样携带 knowledge_point_id
    session_id = result["session_id"]
    detail = auth_client_normal.get(f"/api/exam/result/{session_id}")
    assert detail.status_code == 200, detail.text
    detail_json = detail.json()
    detail_with_id = [
        w for w in detail_json["weak_points"] if w.get("knowledge_point_id")
    ]
    assert any(w["knowledge_point_id"] == kp_id for w in detail_with_id), (
        "/exam/result 端点的 weak_points 须携带 kp id 才能驱动去练习按钮"
    )

    # drill 落点：以该 kp 组卷，返回的题必须全部属于该 KP
    quiz = auth_client_normal.post(
        "/api/learn/quiz",
        json={"knowledge_point_id": kp_id, "count": 5},
    )
    assert quiz.status_code == 200, quiz.text
    picked = quiz.json()
    assert picked, "该 KP 下应有可抽题目"
    assert all(q["knowledge_point_id"] == kp_id for q in picked), (
        "drillWeak 跳转后 Quiz 用该 kp 组卷，结果必须全部属于该知识点"
    )
