"""能力诊断分级回归测试 —— 守护 diagnosis.py 的 tier/difficulty 派生与 L1/L2/L3 判定。

背景：诊断分级曾被标记为脆弱。实际上 build_diagnosis_paper 已正确从
Question.difficulty 派生 tier（1→basic / 2→intermediate / 3→advanced），
无需 questions.tier 列。本测试用隔离库种子数据守护这一行为，防止静默回归：
  - 出卷：8 题 = 3 basic + 3 intermediate + 2 advanced，tier 与 difficulty 对齐
  - 评估：basic<50%→L1；basic OK + intermediate<50%→L2；intermediate OK→L3
"""
from __future__ import annotations

import json

import pytest

from app.db.models import Question
from app.study.diagnosis import build_diagnosis_paper, evaluate_diagnosis


# ---- 种子数据 ----
# 每个 difficulty 恰好放 count 个题，使 random.sample 必取全集，行为确定。
def _make_question(qid: int, difficulty: int, answer: str = "A") -> Question:
    return Question(
        id=qid,
        type="single",
        stem=f"诊断题-{qid}-d{difficulty}",
        options=json.dumps([
            {"key": "A", "text": "选项A"},
            {"key": "B", "text": "选项B"},
        ]),
        answer=answer,
        analysis="解析",
        difficulty=difficulty,
        is_active=True,
    )


def _seed(db) -> dict:
    """灌入 3 basic + 3 intermediate + 2 advanced，返回 id→tier 映射。"""
    qs = (
        [_make_question(1, 1), _make_question(2, 1), _make_question(3, 1)]
        + [_make_question(4, 2), _make_question(5, 2), _make_question(6, 2)]
        + [_make_question(7, 3), _make_question(8, 3)]
    )
    for q in qs:
        db.add(q)
    db.commit()
    return {
        1: "basic", 2: "basic", 3: "basic",
        4: "intermediate", 5: "intermediate", 6: "intermediate",
        7: "advanced", 8: "advanced",
    }


# ============ 出卷 ============

def test_build_diagnosis_paper_returns_8_with_correct_tiers(db_session):
    """出 8 题，tier 分布 3/3/2，且 tier 与 difficulty 对齐（核心不变量）。"""
    _seed(db_session)

    paper = build_diagnosis_paper(db_session)

    # 1) 总数 = 8
    assert len(paper) == 8, f"期望 8 题，实得 {len(paper)}"

    # 2) tier 分布
    from collections import Counter
    tier_counts = Counter(q["tier"] for q in paper)
    assert tier_counts == {"basic": 3, "intermediate": 3, "advanced": 2}

    # 3) 每题 tier 与 difficulty 派生关系一致（核心守护点）
    diff_to_tier = {1: "basic", 2: "intermediate", 3: "advanced"}
    for q in paper:
        assert q["tier"] == diff_to_tier[q["difficulty"]], (
            f"题 {q['id']} difficulty={q['difficulty']} 但 tier={q['tier']}"
        )

    # 4) 出卷字段完备，前端依赖
    for q in paper:
        assert set(q.keys()) >= {"id", "tier", "type", "stem", "options", "difficulty"}


def test_build_diagnosis_paper_empty_when_no_questions(db_session, caplog):
    """空题库不出卷（返回 []），不抛异常；且对每个缺档记录警告。"""
    import logging

    with caplog.at_level(logging.WARNING, logger="app.study.diagnosis"):
        paper = build_diagnosis_paper(db_session)
    assert paper == []
    # 三个难度档都缺题，应各告警一次
    assert len(caplog.records) == 3


def test_build_diagnosis_paper_short_tier_returns_partial(db_session, caplog):
    """某档题量不足仍返回现有全部，不崩溃，并告警该档缺量。"""
    import logging

    # 只放 1 道 basic 题、3 intermediate、2 advanced —— basic 档不足
    db_session.add(_make_question(1, 1))
    db_session.add(_make_question(2, 2))
    db_session.add(_make_question(3, 2))
    db_session.add(_make_question(4, 2))
    db_session.add(_make_question(5, 3))
    db_session.add(_make_question(6, 3))
    db_session.commit()

    with caplog.at_level(logging.WARNING, logger="app.study.diagnosis"):
        paper = build_diagnosis_paper(db_session)

    # basic 1 + intermediate 3 + advanced 2 = 6（不足 8，但不崩溃）
    assert len(paper) == 6
    assert any("basic" in r.getMessage() for r in caplog.records)


# ============ 评估 L1/L2/L3 ============

def _answers_for(qids: list[int], correct_ids: set[int], tier_map: dict) -> list[dict]:
    """对 qids 中每个题构造答案：在 correct_ids 中答 A（对），否则答 B（错）。"""
    return [
        {
            "question_id": qid,
            "user_answer": "A" if qid in correct_ids else "B",
            "tier": tier_map[qid],
        }
        for qid in qids
    ]


@pytest.mark.parametrize(
    "label, basic_correct, inter_correct, expect_level, expect_rates",
    [
        # L1：basic 1/3=33% < 50%，intermediate 全错
        ("L1", [1], [], "L1", {"basic": 33, "intermediate": 0, "advanced": 0}),
        # L2：basic 3/3 OK，intermediate 1/3=33% < 50%
        ("L2", [1, 2, 3], [4], "L2", {"basic": 100, "intermediate": 33, "advanced": 0}),
        # L3：basic 3/3 OK，intermediate 3/3 OK
        ("L3", [1, 2, 3], [4, 5, 6], "L3",
         {"basic": 100, "intermediate": 100, "advanced": 0}),
    ],
)
def test_evaluate_diagnosis_level(
    db_session, label, basic_correct, inter_correct, expect_level, expect_rates
):
    tier_map = _seed(db_session)
    # advanced 全答错，不影响 L1/L2/L3 主判定（advanced 只参与得分/老手题率）
    basic_ids, inter_ids, advanced_ids = [1, 2, 3], [4, 5, 6], [7, 8]
    correct_set = set(basic_correct) | set(inter_correct)

    answers = (
        _answers_for(basic_ids, correct_set, tier_map)
        + _answers_for(inter_ids, correct_set, tier_map)
        + _answers_for(advanced_ids, correct_set, tier_map)
    )

    result = evaluate_diagnosis(db_session, answers, user_id=1)

    assert result["level"] == expect_level, (
        f"{label}: 期望 {expect_level}，实得 {result['level']}（rates={result['tier_rates']}）"
    )
    assert result["tier_rates"] == expect_rates, (
        f"{label}: tier_rates 期望 {expect_rates}，实得 {result['tier_rates']}"
    )
