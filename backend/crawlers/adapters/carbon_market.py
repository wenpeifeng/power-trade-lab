"""上海环境能源交易所全国碳市场公开日行情连接器。"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from crawlers.incremental import IncrementalTracker, official_publish_date
from crawlers.market_data_base import CrawledSeries, MarketDataCrawler

logger = logging.getLogger("crawler.carbon_market")

SOURCE_NAME = "上海环境能源交易所"
BASE_URL = "https://overview.cneeex.com"
PARSER_VERSION = "cneeex-cea-daily-v2"
RIGHTS_NOTE = "数据来源须注明上海环境能源交易所；公开转载与展示应遵守原文声明。"


def _number(value: str) -> float:
    return float(value.replace(",", ""))


def parse_carbon_daily(
    html: str,
    source_url: str,
    fetched_at: str,
) -> Optional[CrawledSeries]:
    soup = BeautifulSoup(html or "", "lxml")
    title_node = soup.select_one("h3.article-tit")
    body = soup.select_one(".article-con")
    title = " ".join(title_node.get_text(" ", strip=True).split()) if title_node else ""
    text = re.sub(r"\s+", "", body.get_text("", strip=True) if body else soup.get_text("", strip=True))
    date_match = re.search(r"(20\d{2})(\d{2})(\d{2})", title)
    prices = re.search(
        r"开盘价([\d.]+)元/吨，最高价([\d.]+)元/吨，最低价([\d.]+)元/吨，"
        r"收盘价([\d.]+)元/吨，收盘价较前一日(上涨|下降|下跌)([\d.]+)%",
        text,
    )
    total = re.search(r"总成交量([\d,]+)吨，总成交额([\d,.]+)元", text)
    if not date_match or not prices or not total:
        return None
    data_date = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"
    change_pct = float(prices.group(6)) * (-1 if prices.group(5) in {"下降", "下跌"} else 1)
    metrics = {
        "product": "CEA",
        "price": float(prices.group(4)),
        "open_price": float(prices.group(1)),
        "high_price": float(prices.group(2)),
        "low_price": float(prices.group(3)),
        "close_price": float(prices.group(4)),
        "close_change_pct": change_pct,
        "volume": _number(total.group(1)),
        "turnover_yuan": _number(total.group(2)),
        "price_unit": "元/吨",
        "volume_unit": "吨",
        "frequency": "daily",
        "attribution_required": True,
        "rights_note": RIGHTS_NOTE,
    }
    method_patterns = {
        "listed_agreement": r"挂牌协议交易成交量([\d,]+)吨，成交额([\d,.]+)元",
        "bulk_agreement": r"大宗协议交易成交量([\d,]+)吨，成交额([\d,.]+)元",
        "one_way_bidding": r"单向竞价.*?成交量([\d,]+)吨，成交额([\d,.]+)元",
    }
    for key, pattern in method_patterns.items():
        match = re.search(pattern, text)
        if match:
            metrics[f"{key}_volume"] = _number(match.group(1))
            metrics[f"{key}_turnover_yuan"] = _number(match.group(2))
    ytd = re.search(r"年1月1日至.*?成交量([\d,]+)吨，成交额([\d,.]+)元", text)
    cumulative = re.search(r"累计成交量([\d,]+)吨，累计成交额([\d,.]+)元", text)
    if ytd:
        metrics.update(ytd_volume=_number(ytd.group(1)), ytd_turnover_yuan=_number(ytd.group(2)))
    if cumulative:
        metrics.update(
            cumulative_volume=_number(cumulative.group(1)),
            cumulative_turnover_yuan=_number(cumulative.group(2)),
        )
    return CrawledSeries(
        data_type="carbon",
        province=None,
        data_date=data_date,
        metrics=metrics,
        source=SOURCE_NAME,
        source_url=source_url,
        provenance_level="observed_public",
        disclosure_scope="public",
        fetched_at=fetched_at,
        parser_version=PARSER_VERSION,
        quality_status="valid",
        update_existing=True,
        raw={
            "provider": SOURCE_NAME,
            "title": title,
            "source_url": source_url,
            "article_text": text,
            "rights_note": RIGHTS_NOTE,
        },
    )


class CarbonMarketCrawler(MarketDataCrawler):
    name = "carbon_market"
    rate_limit = 1.0

    def __init__(self, db=None, max_articles: int = 20, transport=None):
        super().__init__(db)
        self.max_articles = max_articles
        self.client = httpx.Client(
            timeout=25,
            follow_redirects=True,
            headers={"User-Agent": settings.CRAWLER_USER_AGENT},
            transport=transport,
        )

    @property
    def index_url(self) -> str:
        return f"{BASE_URL}/qgtpfqjy/mrgk/{date.today().year}n/"

    def _get_html(self, url: str) -> str:
        self._throttle()
        response = self.client.get(url)
        response.raise_for_status()
        response.encoding = response.charset_encoding or "utf-8"
        return response.text

    def _discover(self) -> list[tuple[str, str]]:
        soup = BeautifulSoup(self._get_html(self.index_url), "lxml")
        result = []
        seen = set()
        for link in soup.find_all("a", href=True):
            title = " ".join(link.get_text(" ", strip=True).split())
            if "【CEA】全国碳市场每日综合价格行情及成交信息" not in title:
                continue
            url = urljoin(BASE_URL, link["href"])
            if url in seen:
                continue
            seen.add(url)
            result.append((title, url))
        return result[:self.max_articles]

    def fetch_series(self) -> list[CrawledSeries]:
        fetched_at = datetime.now().astimezone().isoformat()
        result = []
        tracker = IncrementalTracker(self.db, self.name, PARSER_VERSION)
        bootstrapped = tracker.bootstrap_from_public_data(SOURCE_NAME)
        articles = self._discover()
        self.crawl_stats = {
            "discovered": len(articles),
            "details_fetched": 0,
            "skipped_success": 0,
            "failed_items": 0,
            "bootstrapped": bootstrapped,
        }
        if not articles:
            raise RuntimeError("上海环境能源交易所列表页未发现全国碳市场日行情")
        for title, url in articles:
            registration = tracker.register(url=url, title=title)
            if not registration.should_fetch:
                self.crawl_stats["skipped_success"] += 1
                continue
            try:
                self.crawl_stats["details_fetched"] += 1
                html = self._get_html(url)
                parsed = parse_carbon_daily(html, url, fetched_at)
                if not parsed:
                    raise ValueError("详情页未解析出全国碳市场行情")
                result.append(parsed)
                tracker.mark_success(
                    registration.state,
                    html,
                    1,
                    published_at=official_publish_date(html),
                )
            except Exception as exc:
                tracker.mark_failed(registration.state, str(exc))
                self.crawl_stats["failed_items"] += 1
                logger.warning("[carbon_market] 解析失败 %s: %s", url, exc)
        return result

    def close(self):
        self.client.close()
        super().close()
