"""L9 — 教材章节 quiz_json 入库回归测试。

覆盖三件事：
1. seed_book_questions 后 questions 表存在 source_type='book' 行，含正确的
   options/answer/analysis/source/is_ai_generated/stem_hash/is_active/difficulty 映射。
2. judge 题答案归一化（对/错 → option key）与 is_correct 标记正确。
3. 重复运行幂等：题数不变、不新增重复行。
"""
from __future__ import annotations

import hashlib
import json
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import models  # noqa: F401
from app.db.database import Base
from app.db.models import KnowledgePoint, LearningBookChapter, Question
from scripts.seed_book_questions import (
    _build_options,
    _normalize_judge_answer,
    _stem_hash,
    seed_book_questions,
)


def _make_chapter(db, cid, book_id, order, title, quiz_json):
    db.add(
        LearningBookChapter(
            id=cid,
            book_id=book_id,
            chapter_order=order,
            title=title,
            markdown_content="",
            quiz_json=json.dumps(quiz_json, ensure_ascii=False),
        )
    )


class BookIngestTest(unittest.TestCase):
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

    def tearDown(self):
        self.db.close()

    def test_seeded_book_questions_exist_with_correct_mapping(self):
        quiz = [
            {
                "type": "single",
                "stem": "下列关于现货市场的说法，正确的是？",
                "options": [
                    {"key": "A", "text": "选项甲"},
                    {"key": "B", "text": "选项乙"},
                    {"key": "C", "text": "选项丙"},
                    {"key": "D", "text": "选项丁"},
                ],
                "answer": "B",
                "analysis": "现货市场是发现价格的机制。",
            },
            {
                "type": "judge",
                "stem": "电力现货市场的价格会随时间波动。",
                "options": [
                    {"key": "A", "text": "正确"},
                    {"key": "B", "text": "错误"},
                ],
                "answer": "A",
                "analysis": "现货价格随供需实时变化。",
            },
        ]
        _make_chapter(self.db, 1, 1, 1, "现货市场基础", quiz)
        self.db.commit()

        result = seed_book_questions(self.db)
        self.assertEqual(result["seeded"], 2)
        self.assertEqual(result["skipped"], 0)

        rows = self.db.execute(
            select(Question).where(Question.source_type == "book")
        ).scalars().all()
        self.assertEqual(len(rows), 2)

        by_type = {q.type: q for q in rows}
        # ---- single ----
        sq = by_type["single"]
        self.assertTrue(sq.is_active)
        self.assertTrue(sq.is_ai_generated)
        self.assertEqual(sq.difficulty, 2)
        self.assertEqual(sq.source, "book:1:1")
        self.assertEqual(sq.answer, "B")
        self.assertEqual(sq.analysis, "现货市场是发现价格的机制。")
        self.assertEqual(sq.stem_hash, _stem_hash("下列关于现货市场的说法，正确的是？"))
        # 现货 → spot KP 应被推断
        self.assertIsNotNone(sq.knowledge_point_id, "现货题应推断出知识点")
        # options 格式：[{key,text,is_correct}]
        opts = json.loads(sq.options)
        self.assertEqual(len(opts), 4)
        self.assertEqual(opts[0]["key"], "A")
        self.assertEqual(opts[1]["text"], "选项乙")
        self.assertTrue(opts[1]["is_correct"])   # B 正确
        self.assertFalse(opts[0]["is_correct"])
        self.assertFalse(opts[2]["is_correct"])
        self.assertFalse(opts[3]["is_correct"])

        # ---- judge ----
        jq = by_type["judge"]
        self.assertEqual(jq.answer, "A")
        jopts = json.loads(jq.options)
        self.assertEqual(jopts[0]["key"], "A")
        self.assertTrue(jopts[0]["is_correct"])   # A 正确
        self.assertFalse(jopts[1]["is_correct"])

    def test_judge_answer_normalization(self):
        # answer="对" 且 options text 含"对"/"正确" → 映射到对应 key
        opts = [{"key": "A", "text": "正确"}, {"key": "B", "text": "错误"}]
        self.assertEqual(_normalize_judge_answer("对", opts), "A")
        self.assertEqual(_normalize_judge_answer("错", opts), "B")
        self.assertEqual(_normalize_judge_answer("A", opts), "A")  # 已是字母
        built = json.loads(_build_options(
            {"type": "judge", "options": opts, "answer": "对"},
            _normalize_judge_answer("对", opts),
        ))
        self.assertTrue(built[0]["is_correct"])
        self.assertFalse(built[1]["is_correct"])

    def test_multiple_answer_is_correct_marks_each_letter(self):
        item = {
            "type": "multiple",
            "stem": "以下哪些属于辅助服务？",
            "options": [
                {"key": "A", "text": "调频"}, {"key": "B", "text": "调峰"},
                {"key": "C", "text": "用电"}, {"key": "D", "text": "黑启动"},
            ],
            "answer": "ABD",
            "analysis": "调频/调峰/黑启动属辅助服务。",
        }
        norm = _normalize_judge_answer("ABD", item["options"])  # 非judge原样返回
        self.assertEqual(norm, "ABD")
        built = json.loads(_build_options(item, norm))
        self.assertTrue(built[0]["is_correct"])   # A
        self.assertTrue(built[1]["is_correct"])   # B
        self.assertFalse(built[2]["is_correct"])  # C
        self.assertTrue(built[3]["is_correct"])   # D

    def test_re_run_is_idempotent(self):
        quiz = [
            {"type": "single", "stem": "重复运行不应新增题。", "options": [
                {"key": "A", "text": "甲"}, {"key": "B", "text": "乙"}],
             "answer": "A", "analysis": "幂等。"},
        ]
        _make_chapter(self.db, 2, 1, 2, "中长期交易", quiz)
        self.db.commit()

        first = seed_book_questions(self.db)
        self.assertEqual(first["seeded"], 1)
        count_after_first = self.db.execute(
            select(Question).where(Question.source_type == "book")
        ).scalars().all()
        self.assertEqual(len(count_after_first), 1)

        second = seed_book_questions(self.db)
        self.assertEqual(second["seeded"], 0)
        self.assertEqual(second["skipped"], 1)
        count_after_second = self.db.execute(
            select(Question).where(Question.source_type == "book")
        ).scalars().all()
        self.assertEqual(len(count_after_second), 1, "二次运行题数不变")

    def test_malformed_quiz_json_skipped_not_crash(self):
        # 直接写非法 JSON 串到 quiz_json
        db = self.db
        db.add(LearningBookChapter(
            id=3, book_id=1, chapter_order=3, title="坏章节",
            markdown_content="", quiz_json="not-json{",
        ))
        db.add(LearningBookChapter(
            id=4, book_id=1, chapter_order=4, title="空章节",
            markdown_content="", quiz_json="[]",
        ))
        db.commit()
        result = seed_book_questions(self.db)
        self.assertEqual(result["seeded"], 0)
        self.assertGreaterEqual(result["parse_errors"], 1)


if __name__ == "__main__":
    unittest.main()
