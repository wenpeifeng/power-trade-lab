"""增量采集账本与“第二轮不再请求详情页”测试。"""
from __future__ import annotations

import unittest

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.models import CrawlSourceItem
from crawlers.adapters.carbon_market import CarbonMarketCrawler
from crawlers.incremental import (
    IncrementalTracker,
    canonicalize_url,
    official_publish_date,
    source_item_id,
)


DETAIL_HTML = """
<h3 class="article-tit">【CEA】全国碳市场每日综合价格行情及成交信息20260722</h3>
<div class="article-con">
开盘价90.40元/吨，最高价91.50元/吨，最低价90.40元/吨，
收盘价91.03元/吨，收盘价较前一日上涨0.54%。
全国碳排放配额总成交量826,425吨，总成交额74,525,790.00元。
</div>
"""


class IncrementalTrackerTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self):
        self.engine.dispose()

    def test_canonical_url_and_official_id(self):
        url = "HTTPS://WWW.NEA.GOV.CN/20260715/abc123def456abc123def456/c.html?utm_source=x#top"
        self.assertNotIn("utm_source", canonicalize_url(url))
        self.assertEqual(source_item_id(url), "abc123def456abc123def456")

    def test_publish_date_must_come_from_explicit_original_label(self):
        self.assertEqual(
            official_publish_date("<div>发布时间：2026-07-22 来源：国家能源局</div>"),
            "2026-07-22",
        )
        self.assertIsNone(official_publish_date("<h1>2026年7月市场行情</h1>"))

    def test_success_is_skipped_until_parser_upgrade(self):
        db = self.Session()
        tracker = IncrementalTracker(db, "demo", "v1")
        first = tracker.register(url="https://example.cn/article/123456.shtml", title="文章")
        self.assertTrue(first.should_fetch)
        tracker.mark_success(first.state, "body", 2)
        db.commit()

        same = tracker.register(url="https://example.cn/article/123456.shtml", title="文章")
        self.assertFalse(same.should_fetch)
        upgraded = IncrementalTracker(db, "demo", "v2").register(
            url="https://example.cn/article/123456.shtml",
            title="文章",
        )
        self.assertTrue(upgraded.should_fetch)
        self.assertEqual(upgraded.reason, "parser_upgraded")
        db.close()

    def test_second_carbon_run_only_scans_index(self):
        calls = {"index": 0, "detail": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("123456.shtml"):
                calls["detail"] += 1
                return httpx.Response(200, text=DETAIL_HTML, request=request)
            calls["index"] += 1
            return httpx.Response(
                200,
                text=(
                    '<a href="/qgtpfqjy/mrgk/2026n/123456.shtml">'
                    "【CEA】全国碳市场每日综合价格行情及成交信息20260722</a>"
                ),
                request=request,
            )

        db = self.Session()
        first = CarbonMarketCrawler(
            db=db,
            max_articles=5,
            transport=httpx.MockTransport(handler),
        )
        first.rate_limit = 0
        first_stats = first.run()
        first.close()
        self.assertEqual(first_stats["details_fetched"], 1)
        self.assertEqual(calls["detail"], 1)

        second = CarbonMarketCrawler(
            db=db,
            max_articles=5,
            transport=httpx.MockTransport(handler),
        )
        second.rate_limit = 0
        second_stats = second.run()
        second.close()
        self.assertEqual(second_stats["details_fetched"], 0)
        self.assertEqual(second_stats["skipped_success"], 1)
        self.assertEqual(calls["detail"], 1)
        self.assertEqual(db.query(CrawlSourceItem).count(), 1)
        db.close()


if __name__ == "__main__":
    unittest.main()
