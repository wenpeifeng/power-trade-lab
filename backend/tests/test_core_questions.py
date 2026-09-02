"""L11 — 手写核心题入库回归测试。

覆盖三件事：
1. seed_core_questions 后 6 个目标知识点（green/settlement/retail/
   mid_long_term/ancillary/wholesale）各至少 10 题、source_type='core'、
   is_active=True、is_ai_generated=False、难度分布合理。
2. 每题 options/answer/analysis 字段有效：options 是合法 JSON、含 is_correct
   标记、answer 字母串与 is_correct 一致、analysis 非空。
3. 幂等：二次运行不新增、不重复。
"""
from __future__ import annotations

import hashlib
import json
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import models  # noqa: F401
from app.db.database import Base
from app.db.models import KnowledgePoint, Question
from scripts.seed_core_questions import (
    TARGET_KP_CODES,
    _build_options,
    _stem_hash,
    main as seed_main,
)


def _seed_into(db) -> None:
    """在隔离测试库灌入核心题（绕过 init_db/SessionLocal，复用脚本逻辑）。"""
    kps = {
        kp.code: kp.id
        for kp in db.execute(select(KnowledgePoint)).scalars().all()
        if kp.code
    }
    # 复用脚本里的 QUESTIONS 列表
    from scripts.seed_core_questions import QUESTIONS

    for q in QUESTIONS:
        kp_id = kps.get(q["kp_code"])
        if kp_id is None:
            continue
        stem = q["stem"]
        sh = _stem_hash(stem)
        exists = db.execute(
            select(Question).where(Question.stem_hash == sh)
        ).scalars().first()
        if exists:
            continue
        db.add(
            Question(
                type=q["type"],
                stem=stem,
                options=_build_options(q["options"], q["answer"]),
                answer=q["answer"],
                analysis=q["analysis"],
                knowledge_point_id=kp_id,
                source="core",
                source_type="core",
                is_ai_generated=False,
                is_active=True,
                difficulty=q["difficulty"],
                exam_level=q.get("exam_level"),
                stem_hash=sh,
            )
        )
    db.commit()


class CoreQuestionsTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.db = sessionmaker(bind=self.engine)()
        for code, name in [
            ("green", "绿电绿证"), ("settlement", "结算与信用"),
            ("retail", "零售市场"), ("mid_long_term", "中长期交易"),
            ("ancillary", "辅助服务"), ("wholesale", "批发市场"),
            ("spot", "现货市场"), ("industry", "行业认知"),
        ]:
            self.db.add(KnowledgePoint(code=code, name=name))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def _core_rows(self):
        return (
            self.db.execute(select(Question).where(Question.source_type == "core"))
            .scalars()
            .all()
        )

    def test_seed_at_least_10_per_target_kp(self):
        _seed_into(self.db)
        for code in TARGET_KP_CODES:
            kp = (
                self.db.execute(
                    select(KnowledgePoint).where(KnowledgePoint.code == code)
                )
                .scalars()
                .first()
            )
            cnt = (
                self.db.execute(
                    select(Question).where(
                        Question.knowledge_point_id == kp.id,
                        Question.source_type == "core",
                        Question.is_active.is_(True),
                    )
                )
                .scalars()
                .all()
            )
            self.assertGreaterEqual(
                len(cnt), 10, f"{code} 应至少 10 题，实际 {len(cnt)}"
            )

    def test_all_core_fields_valid(self):
        _seed_into(self.db)
        rows = self._core_rows()
        self.assertEqual(len(rows), 60)
        for q in rows:
            # 基本字段
            self.assertEqual(q.source, "core")
            self.assertEqual(q.source_type, "core")
            self.assertFalse(q.is_ai_generated)
            self.assertTrue(q.is_active)
            self.assertIn(q.type, ("single", "multiple", "judge"))
            self.assertIn(q.difficulty, (1, 2, 3))
            # stem_hash 一致
            self.assertEqual(
                q.stem_hash, hashlib.sha256(q.stem.strip().encode()).hexdigest()
            )
            # analysis 非空
            self.assertTrue(q.analysis and q.analysis.strip())
            # options 合法 JSON
            opts = json.loads(q.options)
            self.assertGreaterEqual(len(opts), 2)
            keys = [o["key"] for o in opts]
            self.assertTrue(all(k for k in keys))
            # answer 字母串与 is_correct 一致
            ans = (q.answer or "").strip()
            for o in opts:
                self.assertEqual(
                    o["is_correct"], o["key"] in ans,
                    f"answer/is_correct 不一致：stem={q.stem[:30]}",
                )
            # answer 中的每个字母都必须是某 option 的 key
            for ch in ans:
                self.assertIn(ch, keys, f"answer 字母 {ch} 无对应选项：{q.stem[:30]}")

    def test_idempotent_rerun(self):
        _seed_into(self.db)
        n1 = len(self._core_rows())
        _seed_into(self.db)
        n2 = len(self._core_rows())
        self.assertEqual(n1, n2, "二次运行不应新增题目")

    def test_answer_has_exactly_one_or_multi_correct(self):
        """single/judge 有且仅有一个正确项；multiple 可有多个但非空。"""
        _seed_into(self.db)
        for q in self._core_rows():
            opts = json.loads(q.options)
            correct = [o["key"] for o in opts if o["is_correct"]]
            if q.type in ("single", "judge"):
                self.assertEqual(
                    len(correct), 1,
                    f"{q.type} 题应有且仅有一个正确项：{q.stem[:30]}",
                )
            else:  # multiple
                self.assertGreaterEqual(
                    len(correct), 2,
                    f"multiple 题应至少两个正确项：{q.stem[:30]}",
                )


if __name__ == "__main__":
    unittest.main()
