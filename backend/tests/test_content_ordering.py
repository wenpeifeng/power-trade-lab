from __future__ import annotations

import unittest
from datetime import datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.admin.router import crawler_items
from app.db.models import CrawlSourceItem, KnowledgeDoc, PublicData
from app.knowledge.admin_router import pending_review, timeline
from app.knowledge.ordering import knowledge_doc_order_by


class ContentOrderingTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        KnowledgeDoc.__table__.create(self.engine)
        CrawlSourceItem.__table__.create(self.engine)
        PublicData.__table__.create(self.engine)
        self.db = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.db.close()

    def _doc(self, title, publish_date, doc_type, key):
        return KnowledgeDoc(
            title=title,
            publish_date=publish_date,
            doc_type=doc_type,
            source="test",
            ingest_type="crawler",
            review_status="pending",
            dedup_key=key,
        )

    def test_pending_and_all_document_lists_use_business_date(self):
        self.db.add_all([
            self._doc("较新普通新闻", "2026-07-23", "industry_news", "new"),
            self._doc("较旧国家政策", "2026-07-22", "national_policy", "old"),
            self._doc("同日普通新闻", "2026-07-21", "industry_news", "same-news"),
            self._doc("同日交易规则", "2026-07-21", "regulation", "same-rule"),
            self._doc("同日国家政策", "2026-07-21", "national_policy", "same-national"),
            self._doc("日期待核验", None, "national_policy", "unknown"),
        ])
        self.db.commit()

        ordered = self.db.execute(
            select(KnowledgeDoc).order_by(*knowledge_doc_order_by())
        ).scalars().all()
        expected = [
            "较新普通新闻",
            "较旧国家政策",
            "同日国家政策",
            "同日交易规则",
            "同日普通新闻",
            "日期待核验",
        ]
        self.assertEqual([row.title for row in ordered], expected)
        pending = pending_review(page=1, page_size=20, db=self.db)
        self.assertEqual([row["title"] for row in pending["items"]], expected)

    def test_crawler_ledger_prefers_published_date_over_seen_time(self):
        self.db.add_all([
            CrawlSourceItem(
                crawler_name="test", source_item_id="old", source_url="https://a/old",
                title="旧文章后抓到", published_at="2026-07-20",
                last_seen_at=datetime(2026, 7, 23, 12),
            ),
            CrawlSourceItem(
                crawler_name="test", source_item_id="new", source_url="https://a/new",
                title="新文章先抓到", published_at="2026-07-22",
                last_seen_at=datetime(2026, 7, 22, 12),
            ),
            CrawlSourceItem(
                crawler_name="test", source_item_id="unknown", source_url="https://a/unknown",
                title="日期未知", published_at=None,
                last_seen_at=datetime(2026, 7, 23, 13),
            ),
        ])
        self.db.commit()
        items = crawler_items(limit=10, db=self.db)["items"]
        self.assertEqual(
            [item["title"] for item in items],
            ["新文章先抓到", "旧文章后抓到", "日期未知"],
        )

    def test_asset_timeline_merges_documents_and_structured_data_by_business_date(self):
        self.db.add(self._doc("七月底政策", "2026-07-31", "national_policy", "doc-0731"))
        self.db.add_all([
            PublicData(
                data_type="clearing", province="山西", data_date="2026-08-03",
                metrics='{"curve":[300,320]}', source="公开区间重构",
                provenance_level="reconstructed", quality_status="valid",
                fetched_at="2026-08-03T10:00:00", dedup_key="clearing-0803",
            ),
            PublicData(
                data_type="weather_forecast_hourly", province="山西",
                data_date="2026-08-04 09:00", metrics='{"temp":31}',
                source="和风天气", provenance_level="observed_public",
                quality_status="valid", fetched_at="2026-08-03T10:01:00",
                dedup_key="weather-0804-09",
            ),
            PublicData(
                data_type="weather_forecast_hourly", province="山西",
                data_date="2026-08-04 10:00", metrics='{"temp":32}',
                source="和风天气", provenance_level="observed_public",
                quality_status="valid", fetched_at="2026-08-03T10:01:00",
                dedup_key="weather-0804-10",
            ),
        ])
        self.db.commit()

        result = timeline(page=1, page_size=30, db=self.db)
        self.assertEqual([group["date"] for group in result["timeline"]], [
            "2026-08-04", "2026-08-03", "2026-07-31",
        ])
        weather = result["timeline"][0]["items"][0]
        self.assertEqual(weather["asset_kind"], "structured_data")
        self.assertEqual(weather["record_count"], 2)
        self.assertEqual(weather["provenance_level"], "observed_public")

        filtered = timeline(doc_type="data:clearing", page=1, page_size=30, db=self.db)
        self.assertEqual(filtered["total"], 1)
        self.assertEqual(filtered["timeline"][0]["items"][0]["data_type"], "clearing")
