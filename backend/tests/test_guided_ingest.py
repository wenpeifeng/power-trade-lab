"""L8 — 导学题入库 + 答错回流错题本回归测试。

覆盖三件事：
1. seed_guided_questions 后 questions 表每课一题、source_type=guided、is_active、
   难度按 unit order 映射（1-3→1, 4-6→2, 7-8→3）。
2. 引导课 check 流程答错 → 同 user+question 写入一行 WrongAnswer，且不破坏
   既有返回结构（items 仍带 is_correct/explanation）。
3. 再次答错同一题 → 不产生重复 WrongAnswer 行。
"""
from __future__ import annotations

import hashlib
import json
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import models  # noqa: F401
from app.db.database import Base
from app.db.models import (
    GuidedLessonProgress,
    KnowledgePoint,
    Question,
    User,
    WrongAnswer,
)
from scripts.seed_guided_questions import _difficulty_for_order, _stem_hash, main as seed_main
from app.study.guided import GUIDED_UNITS


def _seed_questions(db) -> None:
    """在测试库灌入 guided 题目（复用 seed 脚本的核心逻辑但绕过 init_db/SessionLocal）。"""
    kps = {kp.code: kp.id for kp in db.execute(select(KnowledgePoint)).scalars().all() if kp.code}
    for unit in GUIDED_UNITS:
        kp_id = kps.get(unit.get("knowledge_code"))
        if kp_id is None:
            continue
        for check in unit.get("checks") or []:
            stem = check["question"]
            sh = _stem_hash(stem)
            exists = db.execute(select(Question).where(Question.stem_hash == sh)).scalars().first()
            if exists:
                continue
            answer_index = int(check["answer"])
            options_json = json.dumps(
                [
                    {"key": chr(ord("A") + i), "text": opt, "is_correct": i == answer_index}
                    for i, opt in enumerate(check["options"])
                ],
                ensure_ascii=False,
            )
            db.add(
                Question(
                    type="single",
                    stem=stem,
                    options=options_json,
                    answer=chr(ord("A") + answer_index),
                    analysis=check.get("explanation"),
                    knowledge_point_id=kp_id,
                    source=unit["code"],
                    source_type="guided",
                    is_ai_generated=False,
                    is_active=True,
                    difficulty=_difficulty_for_order(int(unit["order"])),
                    stem_hash=sh,
                )
            )
    db.commit()


class GuidedIngestTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.db = sessionmaker(bind=self.engine)()
        # 种 8 个知识点
        for code, name in [
            ("industry", "行业认知"), ("wholesale", "批发市场"), ("retail", "零售市场"),
            ("mid_long_term", "中长期交易"), ("spot", "现货市场"), ("ancillary", "辅助服务"),
            ("green", "绿电绿证"), ("settlement", "结算与信用"),
        ]:
            self.db.add(KnowledgePoint(code=code, name=name))
        self.db.commit()
        self.user = User(id=7, username="learner", hashed_password="unused")
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_seeded_questions_per_unit_with_difficulty_mapping(self):
        _seed_questions(self.db)
        rows = self.db.execute(
            select(Question).where(Question.source_type == "guided")
        ).scalars().all()
        # 8 单元各 1 题
        self.assertEqual(len(rows), 8)
        for q in rows:
            self.assertTrue(q.is_active)
            self.assertEqual(q.type, "single")
            self.assertFalse(q.is_ai_generated)
            self.assertIsNotNone(q.knowledge_point_id)
            self.assertEqual(q.stem_hash, hashlib.sha256(q.stem.strip().encode()).hexdigest())
            # source=unit code
            self.assertIn(q.source, [u["code"] for u in GUIDED_UNITS])
        # 难度映射：unit1-3→1, 4-6→2, 7-8→3
        by_source = {q.source: q for q in rows}
        unit_by_code = {u["code"]: u for u in GUIDED_UNITS}
        for code, q in by_source.items():
            self.assertEqual(q.difficulty, _difficulty_for_order(unit_by_code[code]["order"]))

    def test_wrong_answer_creates_row_on_wrong_check(self):
        from app.study.router import GuidedProgressReq, update_guided_progress

        _seed_questions(self.db)
        unit = GUIDED_UNITS[0]  # power_system_map, answer index=1, 故 0=错
        req = GuidedProgressReq(action="check", answers=[0])
        result = update_guided_progress(unit["code"], req, self.db, self.user)
        # 返回结构未被破坏
        self.assertEqual(result["review"]["score"], 0)
        self.assertFalse(result["review"]["items"][0]["is_correct"])
        self.assertTrue(result["review"]["items"][0]["explanation"])
        # 错题本应有一行
        wrongs = self.db.execute(
            select(WrongAnswer).where(WrongAnswer.user_id == self.user.id)
        ).scalars().all()
        self.assertEqual(len(wrongs), 1)
        self.assertFalse(wrongs[0].reviewed)
        # 关联到正确的 question
        q = self.db.get(Question, wrongs[0].question_id)
        self.assertEqual(q.stem, unit["checks"][0]["question"])

    def test_resubmit_wrong_does_not_duplicate(self):
        from app.study.router import GuidedProgressReq, update_guided_progress

        _seed_questions(self.db)
        unit = GUIDED_UNITS[0]
        # 第一次答错
        update_guided_progress(unit["code"], GuidedProgressReq(action="check", answers=[0]), self.db, self.user)
        # 第二次仍答错
        update_guided_progress(unit["code"], GuidedProgressReq(action="check", answers=[0]), self.db, self.user)
        wrongs = self.db.execute(
            select(WrongAnswer).where(WrongAnswer.user_id == self.user.id)
        ).scalars().all()
        self.assertEqual(len(wrongs), 1)

    def test_correct_answer_marks_existing_wrong_as_reviewed(self):
        from app.study.router import GuidedProgressReq, update_guided_progress

        _seed_questions(self.db)
        unit = GUIDED_UNITS[0]  # 正确答案 index=1
        # 先答错
        update_guided_progress(unit["code"], GuidedProgressReq(action="check", answers=[0]), self.db, self.user)
        # 再答对
        update_guided_progress(unit["code"], GuidedProgressReq(action="check", answers=[1]), self.db, self.user)
        wrongs = self.db.execute(
            select(WrongAnswer).where(WrongAnswer.user_id == self.user.id)
        ).scalars().all()
        self.assertEqual(len(wrongs), 1)  # 不新增
        self.assertTrue(wrongs[0].reviewed)  # 旧的标记已掌握


if __name__ == "__main__":
    unittest.main()
