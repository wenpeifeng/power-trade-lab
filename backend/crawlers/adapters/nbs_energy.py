"""国家统计局月度能源生产数据连接器。"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from crawlers.incremental import IncrementalTracker, official_publish_date
from crawlers.market_data_base import CrawledSeries, MarketDataCrawler

logger = logging.getLogger("crawler.nbs_energy")

SOURCE_NAME = "国家统计局"
INDEX_URL = "https://www.stats.gov.cn/sj/zxfb/"
PARSER_VERSION = "nbs-monthly-energy-v2"


def _signed(direction: str, value: str) -> float:
    return float(value) * (-1 if direction == "下降" else 1)


def _monthly_metric(text: str, label_pattern: str) -> Optional[tuple[float, str, float]]:
    match = re.search(
        rf"\d{{1,2}}月份，规上工业(?:{label_pattern})([\d.]+)(亿吨|万吨|亿立方米|亿千瓦时)，"
        rf"同比(增长|下降)([\d.]+)%",
        text,
    )
    if not match:
        return None
    return float(match.group(1)), match.group(2), _signed(match.group(3), match.group(4))


def parse_nbs_energy_monthly(
    html: str,
    source_url: str,
    fetched_at: str,
) -> Optional[CrawledSeries]:
    soup = BeautifulSoup(html or "", "lxml")
    meta = soup.find("meta", attrs={"name": "ArticleTitle"})
    title = (meta.get("content") if meta else "") or (soup.title.get_text(strip=True) if soup.title else "")
    period_match = re.search(r"(20\d{2})年(\d{1,2})月份能源生产情况", title)
    if not period_match:
        return None
    text = re.sub(r"\s+", "", soup.get_text("", strip=True))
    data_date = f"{int(period_match.group(1)):04d}-{int(period_match.group(2)):02d}"
    fields = {
        "coal": _monthly_metric(text, r"原煤产量"),
        "crude_oil": _monthly_metric(text, r"原油产量"),
        "crude_processing": (
            _monthly_metric(text, r"原油加工量")
            or _monthly_metric(text, r"加工原油")
        ),
        "natural_gas": _monthly_metric(text, r"天然气产量"),
        "power_generation": _monthly_metric(text, r"发电量"),
    }
    if fields["power_generation"] is None or sum(value is not None for value in fields.values()) < 4:
        return None
    metrics = {
        "period": data_date,
        "frequency": "monthly",
        "statistical_scope": "规模以上工业企业",
        "scope_note": "年主营业务收入2000万元及以上工业企业；不同年份企业范围可能变化",
    }
    for key, value in fields.items():
        if value is None:
            continue
        amount, unit, yoy = value
        metrics[f"{key}_amount"] = amount
        metrics[f"{key}_unit"] = unit
        metrics[f"{key}_yoy_pct"] = yoy

    generation_patterns = {
        "thermal_power_yoy_pct": r"规上工业火电(?:同比)?(增长|下降)([\d.]+)%",
        "hydropower_yoy_pct": r"规上工业水电(?:同比)?(增长|下降)([\d.]+)%",
        "nuclear_power_yoy_pct": r"规上工业核电(?:同比)?(增长|下降)([\d.]+)%",
        "wind_power_yoy_pct": r"规上工业风电(?:同比)?(增长|下降)([\d.]+)%",
        "solar_power_yoy_pct": r"规上工业太阳能发电(?:同比)?(增长|下降)([\d.]+)%",
    }
    for key, pattern in generation_patterns.items():
        match = re.search(pattern, text)
        if match:
            metrics[key] = _signed(match.group(1), match.group(2))
    return CrawledSeries(
        data_type="nbs_energy_production",
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
        },
    )


class NBSEnergyCrawler(MarketDataCrawler):
    name = "nbs_energy"
    rate_limit = 1.0

    def __init__(self, db=None, max_articles: int = 6, transport=None):
        super().__init__(db)
        self.max_articles = max_articles
        self.client = httpx.Client(
            timeout=25,
            follow_redirects=True,
            headers={"User-Agent": settings.CRAWLER_USER_AGENT},
            transport=transport,
        )

    def _get_html(self, url: str) -> str:
        self._throttle()
        response = self.client.get(url)
        response.raise_for_status()
        response.encoding = response.charset_encoding or "utf-8"
        return response.text

    def _discover(self) -> list[tuple[str, str]]:
        soup = BeautifulSoup(self._get_html(INDEX_URL), "lxml")
        result = []
        seen = set()
        for link in soup.find_all("a", href=True):
            title = " ".join(link.get_text(" ", strip=True).split())
            if not re.fullmatch(r"20\d{2}年\d{1,2}月份能源生产情况", title):
                continue
            url = urljoin(INDEX_URL, link["href"])
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
            raise RuntimeError("国家统计局列表页未发现月度能源生产文章")
        for title, url in articles:
            registration = tracker.register(url=url, title=title)
            if not registration.should_fetch:
                self.crawl_stats["skipped_success"] += 1
                continue
            try:
                self.crawl_stats["details_fetched"] += 1
                html = self._get_html(url)
                parsed = parse_nbs_energy_monthly(html, url, fetched_at)
                if not parsed:
                    raise ValueError("详情页未解析出月度能源生产数据")
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
                logger.warning("[nbs_energy] 解析失败 %s: %s", url, exc)
        return result

    def close(self):
        self.client.close()
        super().close()
