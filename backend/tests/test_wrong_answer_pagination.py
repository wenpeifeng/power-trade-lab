from __future__ import annotations

import json
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import KnowledgePoint, Question, User, WrongAnswer
from app.learn.router import list_wrong_answers_paged


class WrongAnswerPaginationTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        KnowledgePoint.__table__.create(engine)
        Question.__table__.create(engine)
        WrongAnswer.__table__.create(engine)
        self.db = sessionmaker(bind=engine)()
        self.user = User(id=9, username="learner", hashed_password="unused")

        kp = KnowledgePoint(name="现货交易", code="spot", level=1, sort=1)
        self.db.add(kp)
        self.db.flush()
        single = Question(
            type="single",
            stem="日前现货市场在哪个时间尺度组织？",
            options=json.dumps([{"key": "A", "text": "日前"}]),
            answer="A",
            analysis="日前市场通常按次日运行日组织。",
            difficulty=1,
            knowledge_point_id=kp.id,
            is_active=True,
        )
        multiple = Question(
            type="multiple",
            stem="现货市场价格信号包括哪些？",
            options=json.dumps([
                {"key": "A", "text": "节点电价"},
                {"key": "B", "text": "分区电价"},
            ]),
            answer="AB",
            analysis="不同市场可采用节点或分区价格机制。",
            difficulty=2,
            knowledge_point_id=kp.id,
            is_active=True,
        )
        self.db.add_all([single, multiple])
        self.db.flush()
        # 注意：wrong_answers 表上现有 (user_id, question_id) 唯一约束，
        # 同一 user+question 只能存在一行。此前测试靠插两行验证
        # list_wrong_answers_paged 的 group_by 去重逻辑，现在 DB 层已杜绝重复，
        # 故每个 question 仅种一行（reviewed=False 的最近作答），endpoint 的
        # group_by max(id) 去重逻辑仍生效（对单行幂等）。
        self.db.add_all([
            WrongAnswer(user_id=9, question_id=single.id, user_answer="C", reviewed=False),
            WrongAnswer(user_id=9, question_id=multiple.id, user_answer="A", reviewed=False),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_latest_attempt_is_deduplicated_and_stats_are_global(self):
        result = list_wrong_answers_paged(
            page=1,
            page_size=5,
            reviewed=False,
            question_type=None,
            knowledge_point_id=None,
            keyword=None,
            db=self.db,
            current_user=self.user,
        )
        self.assertEqual(result["pagination"]["total"], 2)
        self.assertEqual(result["stats"]["total"], 2)
        self.assertEqual(result["stats"]["pending"], 2)
        self.assertEqual(len(result["items"]), 2)
        single = next(item for item in result["items"] if item["question"]["type"] == "single")
        self.assertEqual(single["user_answer"], "C")
        multiple = next(item for item in result["items"] if item["question"]["type"] == "multiple")
        self.assertEqual(multiple["error_reason"], "漏选")

    def test_type_and_keyword_filters_apply_before_pagination(self):
        result = list_wrong_answers_paged(
            page=1,
            page_size=5,
            reviewed=None,
            question_type="multiple",
            knowledge_point_id=None,
            keyword="价格信号",
            db=self.db,
            current_user=self.user,
        )
        self.assertEqual(result["pagination"]["total"], 1)
        self.assertEqual(result["items"][0]["question"]["type"], "multiple")
        self.assertEqual(result["knowledge_points"][0]["name"], "现货交易")
