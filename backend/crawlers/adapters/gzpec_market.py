"""广州电力交易中心公开行情连接器。

采集无需登录即可访问的市场研究栏目：
- 南方区域电力现货市场每周行情（区域及粤桂云贵琼日前/实时均价、成交量）
- 绿证交易每周行情（平台成交量、均价及分项信息）

广州交易中心官网当前 HTTPS 证书与 www 域名不匹配，公开 HTTP 入口可正常访问，
因此抓取入口使用 HTTP；每条数据仍保留官方原文 URL、抓取时间和原文快照。
"""
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

logger = logging.getLogger("crawler.gzpec_market")

SOURCE_NAME = "广州电力交易中心"
INDEX_URL = "http://www.gzpec.cn/news/scyj/"
PARSER_VERSION = "gzpec-public-market-v2"
PROVINCES = ("广东", "广西", "云南", "贵州", "海南")


def _numbers(value: str) -> list[float]:
    return [float(item.replace(",", "")) for item in re.findall(r"[\d,.]+", value)]


def _article_text(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html or "", "lxml")
    title_node = soup.select_one("h3.title")
    body = soup.select_one(".txt") or soup.select_one(".content") or soup
    title = " ".join(title_node.get_text(" ", strip=True).split()) if title_node else ""
    text = re.sub(r"\s+", "", body.get_text("", strip=True))
    return title, text


def _period(title: str, text: str) -> Optional[tuple[str, str]]:
    year_match = re.search(r"(20\d{2})年", title + text[:120])
    range_match = re.search(
        r"(\d{1,2})月(\d{1,2})日[-—至](?:(\d{1,2})月)?(\d{1,2})日",
        text[:180] + title,
    )
    if not year_match or not range_match:
        return None
    year = int(year_match.group(1))
    start_month = int(range_match.group(1))
    start_day = int(range_match.group(2))
    end_month = int(range_match.group(3) or start_month)
    end_day = int(range_match.group(4))
    try:
        start = date(year, start_month, start_day).isoformat()
        end = date(year, end_month, end_day).isoformat()
    except ValueError:
        return None
    return start, end


def _market_block(text: str, market: str, subjects: str) -> Optional[tuple[list[float], list[float]]]:
    match = re.search(
        rf"{market}市场，{subjects}日均成交电量分别为(.+?)亿千瓦时，"
        rf"加权均价分别为(.+?)元/兆瓦时",
        text,
    )
    if not match:
        return None
    volumes = _numbers(match.group(1))
    prices = _numbers(match.group(2))
    return (volumes, prices) if volumes and len(volumes) == len(prices) else None


def parse_spot_weekly(html: str, source_url: str, fetched_at: str) -> list[CrawledSeries]:
    """解析南方区域周行情；周数据不伪装成 96 点出清曲线。"""
    title, text = _article_text(html)
    if "南方区域电力现货市场每周行情一览" not in title:
        return []
    period = _period(title, text)
    aggregate = re.search(
        r"日前市场日均成交电量([\d.]+)亿千瓦时.*?加权均价为([\d.]+)元/兆瓦时.*?"
        r"实时市场日均成交电量([\d.]+)亿千瓦时.*?加权均价为([\d.]+)元/兆瓦时",
        text,
    )
    day_ahead = _market_block(text, "日前", "广东、广西、云南、贵州、海南")
    real_time = _market_block(text, "实时", "广东、广西、云南、贵州、海南")
    if not period or not aggregate or not day_ahead or not real_time:
        return []

    start_date, end_date = period
    common = {
        "period_start": start_date,
        "period_end": end_date,
        "frequency": "weekly",
        "price_unit": "元/MWh",
        "energy_unit": "亿千瓦时",
        "market_scope": "南方区域",
        "data_note": "发电侧快报数据，非最终结算数据",
    }
    raw = {
        "provider": SOURCE_NAME,
        "title": title,
        "source_url": source_url,
        "article_text": text,
    }
    series = [
        CrawledSeries(
            data_type="southern_spot_weekly",
            province="南方区域",
            data_date=end_date,
            metrics={
                **common,
                "day_ahead_avg_volume_100m_kwh": float(aggregate.group(1)),
                "day_ahead_avg_price_yuan_mwh": float(aggregate.group(2)),
                "real_time_avg_volume_100m_kwh": float(aggregate.group(3)),
                "real_time_avg_price_yuan_mwh": float(aggregate.group(4)),
            },
            source=SOURCE_NAME,
            source_url=source_url,
            provenance_level="observed_public",
            disclosure_scope="public",
            fetched_at=fetched_at,
            parser_version=PARSER_VERSION,
            quality_status="valid",
            update_existing=True,
            raw=raw,
        )
    ]
    da_volumes, da_prices = day_ahead
    rt_volumes, rt_prices = real_time
    if not all(len(values) == len(PROVINCES) for values in (da_volumes, da_prices, rt_volumes, rt_prices)):
        return series
    for index, province in enumerate(PROVINCES):
        series.append(CrawledSeries(
            data_type="southern_spot_weekly",
            province=province,
            data_date=end_date,
            metrics={
                **common,
                "day_ahead_avg_volume_100m_kwh": da_volumes[index],
                "day_ahead_avg_price_yuan_mwh": da_prices[index],
                "real_time_avg_volume_100m_kwh": rt_volumes[index],
                "real_time_avg_price_yuan_mwh": rt_prices[index],
            },
            source=SOURCE_NAME,
            source_url=source_url,
            provenance_level="observed_public",
            disclosure_scope="public",
            fetched_at=fetched_at,
            parser_version=PARSER_VERSION,
            quality_status="valid",
            update_existing=True,
            raw=raw,
        ))
    return series


def parse_green_certificate_weekly(
    html: str,
    source_url: str,
    fetched_at: str,
) -> Optional[CrawledSeries]:
    title, text = _article_text(html)
    if "绿证交易每周行情一览" not in title:
        return None
    period = _period(title, text)
    core = re.search(
        r"平台绿证交易([\d.]+)万个.*?交易均价([\d.]+)元/个.*?"
        r"年累计交易量([\d.]+)(亿|万)个，交易均价([\d.]+)元/个",
        text,
    )
    if not period or not core:
        return None
    start_date, end_date = period
    cumulative_10k = round(
        float(core.group(3)) * (10000 if core.group(4) == "亿" else 1),
        4,
    )
    metrics = {
        "period_start": start_date,
        "period_end": end_date,
        "frequency": "weekly",
        "traded_volume_10k": float(core.group(1)),
        "average_price_yuan_each": float(core.group(2)),
        "ytd_traded_volume_10k": cumulative_10k,
        "ytd_average_price_yuan_each": float(core.group(5)),
        "volume_unit": "万个",
        "price_unit": "元/个",
        "market_scope": "广州电力交易中心绿证交易平台",
    }
    ranking = re.search(
        r"购入省份排名前五(?:的省份)?为(.+?)，绿证交易售出省份排名前五(?:的省份)?为(.+?)[。.]",
        text,
    )
    if ranking:
        metrics["top_buying_provinces"] = re.split(r"[、,，]", ranking.group(1))
        metrics["top_selling_provinces"] = re.split(r"[、,，]", ranking.group(2))
    solar = re.search(r"光伏项目.*?交易规模为([\d.]+)万个.*?占交易总量(?:的)?([\d.]+)%", text)
    wind = re.search(r"风电项目.*?交易规模为([\d.]+)万个.*?占交易总量(?:的)?([\d.]+)%", text)
    if solar:
        metrics.update(solar_volume_10k=float(solar.group(1)), solar_share_pct=float(solar.group(2)))
    if wind:
        metrics.update(wind_volume_10k=float(wind.group(1)), wind_share_pct=float(wind.group(2)))
    return CrawledSeries(
        data_type="green_certificate_weekly",
        province=None,
        data_date=end_date,
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


class GZPECMarketCrawler(MarketDataCrawler):
    name = "gzpec_market"
    rate_limit = 1.0

    def __init__(self, db=None, max_articles: int = 12, transport=None):
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
            if not (
                "南方区域电力现货市场每周行情一览" in title
                or "绿证交易每周行情一览" in title
            ):
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
            raise RuntimeError("广州电力交易中心列表页未发现目标行情文章")
        for title, url in articles:
            registration = tracker.register(url=url, title=title)
            if not registration.should_fetch:
                self.crawl_stats["skipped_success"] += 1
                continue
            try:
                self.crawl_stats["details_fetched"] += 1
                html = self._get_html(url)
                parsed_rows = []
                if "现货市场每周行情" in title:
                    parsed_rows = parse_spot_weekly(html, url, fetched_at)
                elif "绿证交易每周行情" in title:
                    parsed = parse_green_certificate_weekly(html, url, fetched_at)
                    if parsed:
                        parsed_rows = [parsed]
                if not parsed_rows:
                    raise ValueError("详情页未解析出结构化行情")
                result.extend(parsed_rows)
                tracker.mark_success(
                    registration.state,
                    html,
                    len(parsed_rows),
                    published_at=official_publish_date(html),
                )
            except Exception as exc:
                tracker.mark_failed(registration.state, str(exc))
                self.crawl_stats["failed_items"] += 1
                logger.warning("[gzpec_market] 解析失败 %s: %s", url, exc)
        return result

    def close(self):
        self.client.close()
        super().close()
