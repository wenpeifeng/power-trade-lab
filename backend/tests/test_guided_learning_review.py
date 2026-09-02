from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import GuidedLessonProgress, KnowledgeDoc, Question, User, WrongAnswer
from app.study.router import (
    GuidedProgressReq,
    guided_detail,
    update_guided_progress,
)


class GuidedLearningReviewTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        GuidedLessonProgress.__table__.create(engine)
        KnowledgeDoc.__table__.create(engine)
        # L8 起 check 流程会查询 questions/wrong_answers，同步建表
        Question.__table__.create(engine)
        WrongAnswer.__table__.create(engine)
        self.db = sessionmaker(bind=engine)()
        self.user = User(id=7, username="learner", hashed_password="unused")

    def tearDown(self):
        self.db.close()

    def test_answers_are_hidden_before_submit_and_attempts_are_reviewable(self):
        initial = guided_detail("power_system_map", self.db, self.user)
        self.assertNotIn("answer", initial["checks"][0])
        wrong = update_guided_progress(
            "power_system_map",
            GuidedProgressReq(action="check", answers=[0]),
            self.db,
            self.user,
        )
        self.assertEqual(wrong["review"]["score"], 0)
        self.assertFalse(wrong["review"]["items"][0]["is_correct"])
        self.assertEqual(wrong["review"]["items"][0]["correct_answer_index"], 1)
        self.assertTrue(wrong["review"]["items"][0]["review_action"])

        correct = update_guided_progress(
            "power_system_map",
            GuidedProgressReq(action="check", answers=[1]),
            self.db,
            self.user,
        )
        self.assertEqual(correct["review"]["score"], 100)
        completed = update_guided_progress(
            "power_system_map",
            GuidedProgressReq(
                action="complete",
                deliverable_text="发电企业形成申报，交易机构组织出清，调度执行并由计量结算。",
            ),
            self.db,
            self.user,
        )
        self.assertEqual(completed["progress"]["status"], "completed")

        detail = guided_detail("power_system_map", self.db, self.user)
        self.assertEqual(len(detail["attempts"]), 2)
        self.assertEqual(detail["review"]["score"], 100)
        self.assertEqual(detail["attempts"][0]["wrong_count"], 1)

    def test_legacy_completion_shows_correct_answer_with_clear_warning(self):
        self.db.add(GuidedLessonProgress(
            user_id=self.user.id,
            unit_code="power_system_map",
            status="completed",
            progress_pct=100,
            check_score=100,
            check_attempts="[]",
            completed_at="2026-07-23T12:00:00+08:00",
        ))
        self.db.commit()
        detail = guided_detail("power_system_map", self.db, self.user)
        self.assertFalse(detail["review"]["record_available"])
        self.assertTrue(detail["review"]["legacy"])
        self.assertEqual(detail["review"]["items"][0]["correct_answer_index"], 1)
        self.assertEqual(
            detail["review"]["items"][0]["user_answer_text"],
            "历史版本未保存逐题选择",
        )
