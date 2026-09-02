"""政策公告日期、分类、重要性与排序测试。"""
from __future__ import annotations

import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.models import Policy
from app.policy.article_metadata import (
    clean_list_title,
    extract_list_publish_date,
    extract_official_publish_date,
    extract_official_title,
)
from app.policy.ranking import (
    classify_policy,
    infer_priority,
    policy_order_by,
)


class PolicyRankingRulesTest(unittest.TestCase):
    def test_classification_distinguishes_rules_from_general_news(self):
        self.assertEqual(
            classify_policy("国家发展改革委关于电力市场信息披露的通知", "regulation"),
            "national",
        )
        self.assertEqual(
            classify_policy("山西电力现货市场日前出清结果", "market"),
            "clearing",
        )
        self.assertEqual(
            classify_policy("国家能源局负责人赴上海调研迎峰度夏能源保供", "regulation"),
            "market",
        )
        self.assertEqual(
            classify_policy("浙江电力市场结算管理办法", "market"),
            "regulation",
        )

    def test_importance_rules(self):
        self.assertEqual(infer_priority("电力市场暂停交易风险预警", "market"), 2)
        self.assertEqual(infer_priority("电力现货市场实施细则", "regulation"), 1)
        self.assertEqual(infer_priority("能源论坛在京召开", "market"), 0)


class OfficialArticleDateTest(unittest.TestCase):
    def test_extracts_meta_jsonld_time_and_labelled_dates(self):
        cases = [
            ('<meta property="article:published_time" content="2026-07-21T10:00:00+08:00">', "2026-07-21"),
            ('<script type="application/ld+json">{"datePublished":"2026-07-20"}</script>', "2026-07-20"),
            ('<time datetime="2026-07-19T08:30:00+08:00"></time>', "2026-07-19"),
            ('<div>发布时间：2026年7月18日 来源：国家能源局</div>', "2026-07-18"),
        ]
        for html, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(extract_official_publish_date(html).publish_date, expected)

    def test_rejects_title_suffix_and_unlabelled_body_date(self):
        self.assertIsNone(extract_list_publish_date("普通新闻07-21"))
        self.assertIsNone(
            extract_official_publish_date("<article>会议于2026年7月21日召开。</article>")
        )

    def test_cleans_list_date_and_reads_full_official_title(self):
        self.assertEqual(
            clean_list_title("2026世界人工智能大会“人工智能与能源双向赋能”分论坛在...07-21"),
            "2026世界人工智能大会“人工智能与能源双向赋能”分论坛在",
        )
        html = """
        <meta name="ArticleTitle"
              content="2026世界人工智能大会“人工智能与能源双向赋能”分论坛在沪举办">
        <div>发布时间：2026-07-17</div>
        """
        self.assertEqual(
            extract_official_title(html),
            "2026世界人工智能大会“人工智能与能源双向赋能”分论坛在沪举办",
        )


class PolicyOrderingTest(unittest.TestCase):
    def test_date_is_absolute_priority_then_same_day_importance_and_category(self):
        engine = create_engine("sqlite:///:memory:")
        Policy.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        rows = [
            Policy(
                title="较新普通公告", publish_date="2026-07-23", category="market",
                publish_date_status="verified", source="test", priority=0,
                dedup_key="new-market",
            ),
            Policy(
                title="较旧紧急政策", publish_date="2026-07-22", category="national",
                publish_date_status="verified", source="test", priority=2,
                dedup_key="old-urgent",
            ),
            Policy(
                title="同日市场公告", publish_date="2026-07-21", category="market",
                publish_date_status="verified", source="test", priority=0,
                dedup_key="same-market",
            ),
            Policy(
                title="同日交易规则", publish_date="2026-07-21", category="regulation",
                publish_date_status="verified", source="test", priority=0,
                dedup_key="same-regulation",
            ),
            Policy(
                title="同日国家政策", publish_date="2026-07-21", category="national",
                publish_date_status="verified", source="test", priority=0,
                dedup_key="same-national",
            ),
            Policy(
                title="未知日期", publish_date=None, category="national",
                publish_date_status="unverified", source="test", priority=2,
                dedup_key="unknown-date",
            ),
        ]
        db.add_all(rows)
        db.commit()
        ordered = db.execute(
            select(Policy).order_by(*policy_order_by())
        ).scalars().all()
        self.assertEqual(
            [item.title for item in ordered],
            [
                "较新普通公告",
                "较旧紧急政策",
                "同日国家政策",
                "同日交易规则",
                "同日市场公告",
                "未知日期",
            ],
        )
        db.close()


if __name__ == "__main__":
    unittest.main()
