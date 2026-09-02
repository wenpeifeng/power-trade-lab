"""国家能源局公开统计数据连接器。

抓取国家能源局公开页面中的月度真实统计，不登录、不绕过访问控制：
- 全社会用电量
- 全国电力市场交易电量
- 绿证核发与交易

每条数据同时保留来源 URL、抓取时间、原文快照和 SHA-256。
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Callable, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from crawlers.incremental import IncrementalTracker, official_publish_date
from crawlers.market_data_base import CrawledSeries, MarketDataCrawler

logger = logging.getLogger("crawler.nea_statistics")

SOURCE_NAME = "国家能源局"
INDEX_URLS = (
    "https://www.nea.gov.cn/xwfb/index.htm",
    "https://www.nea.gov.cn/sjzz/jgs/",
)
PARSER_VERSION = "nea-public-statistics-v5"

# 保底入口用于首次运行；动态发现到更新文章后会自动优先解析新页面。
SEED_ARTICLES = [
    (
        "国家能源局发布2026年1-6月份全国电力统计数据",
        "https://www.nea.gov.cn/20260722/3b678308556b4df0a574537b59a28731/c.html",
    ),
    (
        "2026年1-6月份全社会用电量同比增长5.3%",
        "https://www.nea.gov.cn/20260715/ca1da417932c4fbfa26c0006f272d691/c.html",
    ),
    (
        "2026年1-5月全国电力市场交易电量同比增长24.8%",
        "https://www.nea.gov.cn/20260629/77ccaff0f2934369a7b94078165ceb54/c.html",
    ),
    (
        "国家能源局发布2026年5月全国可再生能源绿色电力证书核发及交易数据",
        "https://www.nea.gov.cn/20260630/4d2258229b144a4a8634e3de78f7385a/c.html",
    ),
    (
        "关于2026年6月全国新增建档立卡新能源发电（不含户用光伏）项目情况的公告",
        "https://www.nea.gov.cn/20260720/f978dbe5fcbc4d8085a3909410b9366e/c.html",
    ),
]


def _number(pattern: str, text: str) -> Optional[float]:
    match = re.search(pattern, text)
    return float(match.group(1)) if match else None


def _month_from_text(text: str, pattern: str) -> Optional[str]:
    match = re.search(pattern, text)
    if not match:
        return None
    return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}"


def parse_power_consumption(title: str, text: str, source_url: str, fetched_at: str) -> Optional[CrawledSeries]:
    month = _month_from_text(title, r"(\d{4})年1[-～—至](\d{1,2})月")
    current = re.search(
        r"(\d{1,2})月份?[，,]\s*全社会用电量\s*([\d.]+)\s*亿千瓦时[，,]\s*"
        r"同比(增长|下降)\s*([\d.]+)%",
        text,
    )
    if not month or not current:
        return None
    yoy = float(current.group(4)) * (-1 if current.group(3) == "下降" else 1)
    monthly_block = text[current.start():]
    cumulative_marker = re.search(r"\d+\s*[～—-]\s*\d+月", monthly_block[1:])
    if cumulative_marker:
        monthly_block = monthly_block[:cumulative_marker.start() + 1]

    metrics = {
        "period": month,
        "total_consumption_100m_kwh": float(current.group(2)),
        "yoy_pct": yoy,
        "primary_industry_100m_kwh": _number(r"第一产业用电量\s*([\d.]+)\s*亿千瓦时", monthly_block),
        "secondary_industry_100m_kwh": _number(r"第二产业用电量\s*([\d.]+)\s*亿千瓦时", monthly_block),
        "industrial_100m_kwh": _number(r"工业用电量\s*([\d.]+)\s*亿千瓦时", monthly_block),
        "tertiary_industry_100m_kwh": _number(r"第三产业用电量\s*([\d.]+)\s*亿千瓦时", monthly_block),
        "residential_100m_kwh": _number(r"城乡居民生活用电量\s*([\d.]+)\s*亿千瓦时", monthly_block),
        "unit": "亿千瓦时",
    }
    return _series(
        "national_power_consumption",
        month,
        title,
        text,
        source_url,
        fetched_at,
        metrics,
    )


def parse_market_transaction(title: str, text: str, source_url: str, fetched_at: str) -> Optional[CrawledSeries]:
    current = re.search(
        r"(\d{4})年(\d{1,2})月[，,]\s*全国完成电力市场交易电量\s*([\d.]+)\s*亿千瓦时"
        r"[，,]\s*同比(增长|下降)\s*([\d.]+)%",
        text,
    )
    if not current:
        cumulative = re.search(
            r"(\d{4})年1[-～—至](\d{1,2})月[，,]\s*全国累计完成电力市场交易电量"
            r"\s*([\d.]+)\s*亿千瓦时[，,]\s*同比(增长|下降)\s*([\d.]+)%",
            text,
        )
        if not cumulative:
            return None
        month = f"{int(cumulative.group(1)):04d}-{int(cumulative.group(2)):02d}"
        yoy = float(cumulative.group(5)) * (-1 if cumulative.group(4) == "下降" else 1)
        metrics = {
            "period": month,
            "period_scope": "year_to_date",
            "market_transaction_100m_kwh": float(cumulative.group(3)),
            "yoy_pct": yoy,
            "intra_province_100m_kwh": _number(r"省内交易电量\s*([\d.]+)\s*亿千瓦时", text),
            "inter_province_100m_kwh": _number(r"跨省跨区交易电量\s*([\d.]+)\s*亿千瓦时", text),
            "mid_long_term_100m_kwh": _number(r"中长期交易电量\s*([\d.]+)\s*亿千瓦时", text),
            "spot_100m_kwh": _number(r"现货交易电量\s*([\d.]+)\s*亿千瓦时", text),
            "green_power_100m_kwh": _number(r"绿电交易电量\s*([\d.]+)\s*亿千瓦时", text),
            "unit": "亿千瓦时",
        }
        return _series(
            "national_market_transaction_ytd",
            month,
            title,
            text,
            source_url,
            fetched_at,
            metrics,
        )
    month = f"{int(current.group(1)):04d}-{int(current.group(2)):02d}"
    yoy = float(current.group(5)) * (-1 if current.group(4) == "下降" else 1)
    monthly_block = text[current.start():]
    cumulative_marker = re.search(r"\d{4}年1[-～—至]\d{1,2}月", monthly_block[1:])
    if cumulative_marker:
        monthly_block = monthly_block[:cumulative_marker.start() + 1]
    metrics = {
        "period": month,
        "period_scope": "monthly",
        "market_transaction_100m_kwh": float(current.group(3)),
        "yoy_pct": yoy,
        "intra_province_100m_kwh": _number(r"省内交易电量\s*([\d.]+)\s*亿千瓦时", monthly_block),
        "inter_province_100m_kwh": _number(r"跨省跨区交易电量\s*([\d.]+)\s*亿千瓦时", monthly_block),
        "mid_long_term_100m_kwh": _number(r"中长期交易电量\s*([\d.]+)\s*亿千瓦时", monthly_block),
        "spot_100m_kwh": _number(r"现货交易电量\s*([\d.]+)\s*亿千瓦时", monthly_block),
        "green_power_100m_kwh": _number(r"绿电交易电量\s*([\d.]+)\s*亿千瓦时", monthly_block),
        "grid_agent_purchase_100m_kwh": _number(
            r"电网企业市场化代理购电电量\s*([\d.]+)\s*亿千瓦时",
            monthly_block,
        ),
        "unit": "亿千瓦时",
    }
    return _series(
        "national_market_transaction",
        month,
        title,
        text,
        source_url,
        fetched_at,
        metrics,
    )


def parse_green_certificate(title: str, text: str, source_url: str, fetched_at: str) -> Optional[CrawledSeries]:
    month = _month_from_text(title, r"(\d{4})年(\d{1,2})月.*绿色电力证书")
    if not month:
        return None
    metrics = {
        "period": month,
        "issued_100m": _number(r"核发绿证\s*([\d.]+)\s*亿个", text),
        "tradable_100m": _number(r"可交易绿证\s*([\d.]+)\s*亿个", text),
        "traded_10k": _number(r"全国交易绿证\s*([\d.]+)\s*万个", text),
        "green_power_traded_10k": _number(r"绿色电力交易绿证\s*([\d.]+)\s*万个", text),
        "standalone_traded_10k": _number(r"全国单独交易绿证\s*([\d.]+)\s*万个", text),
        "unit_note": "核发量为亿个，交易量为万个",
    }
    if metrics["issued_100m"] is None or metrics["traded_10k"] is None:
        return None
    vintage_rows = re.findall(
        r"电量生产年为(20\d{2})年的绿证交易([\d.]+)万个，平均价格([\d.]+)元/个",
        text,
    )
    if vintage_rows:
        metrics["standalone_price_by_vintage"] = [
            {
                "production_year": int(year),
                "traded_10k": float(volume),
                "average_price_yuan_each": float(price),
            }
            for year, volume, price in vintage_rows
        ]
    return _series(
        "national_green_certificate",
        month,
        title,
        text,
        source_url,
        fetched_at,
        metrics,
    )


def _series(
    data_type: str,
    month: str,
    title: str,
    text: str,
    source_url: str,
    fetched_at: str,
    metrics: dict,
) -> CrawledSeries:
    return CrawledSeries(
        data_type=data_type,
        province=None,
        data_date=month,
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


def parse_power_statistics(
    title: str,
    text: str,
    source_url: str,
    fetched_at: str,
) -> Optional[CrawledSeries]:
    """全国电力统计：装机容量、风光装机及设备利用小时。"""
    month = _month_from_text(title, r"(\d{4})年1[-～—至](\d{1,2})月份?全国电力统计数据")
    capacity = re.search(
        r"全国累计发电装机容量([\d.]+)亿千瓦，同比增长([\d.]+)%.*?"
        r"太阳能发电装机容量([\d.]+)亿千瓦，同比增长([\d.]+)%.*?"
        r"风电装机容量([\d.]+)亿千瓦，同比增长([\d.]+)%",
        text,
    )
    if not month or not capacity:
        return None
    utilization = re.search(
        r"全国发电设备累计平均利用(\d+)小时，比上年同期(增加|降低)(\d+)小时",
        text,
    )
    metrics = {
        "period": month,
        "total_installed_capacity_100m_kw": float(capacity.group(1)),
        "total_installed_capacity_yoy_pct": float(capacity.group(2)),
        "solar_installed_capacity_100m_kw": float(capacity.group(3)),
        "solar_installed_capacity_yoy_pct": float(capacity.group(4)),
        "wind_installed_capacity_100m_kw": float(capacity.group(5)),
        "wind_installed_capacity_yoy_pct": float(capacity.group(6)),
        "capacity_unit": "亿千瓦",
    }
    if utilization:
        metrics["average_utilization_hours"] = int(utilization.group(1))
        delta = int(utilization.group(3))
        metrics["average_utilization_hours_yoy_change"] = (
            -delta if utilization.group(2) == "降低" else delta
        )
    return _series(
        "national_power_statistics",
        month,
        title,
        text,
        source_url,
        fetched_at,
        metrics,
    )


def parse_new_energy_projects(
    title: str,
    text: str,
    source_url: str,
    fetched_at: str,
) -> Optional[CrawledSeries]:
    """全国新能源项目建档增量，反映未来新增供给结构。"""
    month = _month_from_text(title, r"(\d{4})年(\d{1,2})月全国新增建档立卡新能源发电")
    counts = re.search(
        r"项目共(\d+)个，其中风电项目(\d+)个，光伏发电项目(\d+)个"
        r"（集中式光伏发电项目(\d+)个，工商业分布式光伏发电项目(\d+)个）"
        r"，生物质发电项目(\d+)个",
        text,
    )
    if not month or not counts:
        return None
    metrics = {
        "period": month,
        "total_projects": int(counts.group(1)),
        "wind_projects": int(counts.group(2)),
        "solar_projects": int(counts.group(3)),
        "utility_solar_projects": int(counts.group(4)),
        "commercial_distributed_solar_projects": int(counts.group(5)),
        "biomass_projects": int(counts.group(6)),
        "scope_note": "全国新增建档立卡新能源发电项目，不含户用光伏",
        "unit": "个",
    }
    return _series(
        "national_new_energy_projects",
        month,
        title,
        text,
        source_url,
        fetched_at,
        metrics,
    )


def parse_new_energy_project_provinces(
    html: str,
    *,
    data_date: str,
    title: str,
    source_url: str,
    fetched_at: str,
) -> list[CrawledSeries]:
    """解析公告内分省项目表；列为风电/集中式光伏/工商业分布式/生物质/合计。"""
    soup = BeautifulSoup(html or "", "lxml")
    rows: list[CrawledSeries] = []
    article_text = re.sub(r"\s+", "", soup.get_text("", strip=True))
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = [
                " ".join(cell.get_text(" ", strip=True).split())
                for cell in tr.find_all(["th", "td"])
            ]
            if len(cells) < 6:
                continue
            province = cells[0].replace(" ", "")
            if province in {"地区", "全国", ""}:
                continue
            try:
                values = [int(value.replace(",", "").strip()) for value in cells[1:6]]
            except ValueError:
                continue
            wind, utility_solar, commercial_solar, biomass, total = values
            if wind + utility_solar + commercial_solar + biomass != total:
                continue
            rows.append(CrawledSeries(
                data_type="national_new_energy_projects",
                province=province,
                data_date=data_date,
                metrics={
                    "period": data_date,
                    "wind_projects": wind,
                    "utility_solar_projects": utility_solar,
                    "commercial_distributed_solar_projects": commercial_solar,
                    "solar_projects": utility_solar + commercial_solar,
                    "biomass_projects": biomass,
                    "total_projects": total,
                    "scope_note": "分省新增建档立卡新能源发电项目，不含户用光伏",
                    "unit": "个",
                },
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
                    "article_text": article_text,
                },
            ))
    return rows


PARSERS: list[tuple[str, Callable[[str, str, str, str], Optional[CrawledSeries]]]] = [
    ("全国电力统计数据", parse_power_statistics),
    ("全社会用电量", parse_power_consumption),
    ("全国电力市场交易电量", parse_market_transaction),
    ("绿色电力证书核发及交易数据", parse_green_certificate),
    ("全国新增建档立卡新能源发电", parse_new_energy_projects),
]


class NEAStatisticsCrawler(MarketDataCrawler):
    name = "nea_statistics"
    rate_limit = 1.0

    def __init__(self, db=None, max_articles: int = 18, transport=None):
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

    def _discover_articles(self) -> list[tuple[str, str]]:
        candidates = []
        for index_url in INDEX_URLS:
            try:
                soup = BeautifulSoup(self._get_html(index_url), "lxml")
                for link in soup.find_all("a", href=True):
                    title = " ".join(link.get_text(" ", strip=True).split())
                    if any(keyword in title for keyword, _ in PARSERS):
                        candidates.append((title, urljoin(index_url, link["href"])))
            except Exception as exc:
                logger.warning(
                    "[nea_statistics] 动态发现失败 %s，继续使用其他入口: %s",
                    index_url,
                    exc,
                )
        candidates.extend(SEED_ARTICLES)
        seen = set()
        result = []
        for title, url in candidates:
            if url in seen:
                continue
            seen.add(url)
            result.append((title, url))
        return result[:self.max_articles]

    def fetch_series(self) -> list[CrawledSeries]:
        fetched_at = datetime.now().astimezone().isoformat()
        result = []
        seen_periods = set()
        tracker = IncrementalTracker(self.db, self.name, PARSER_VERSION)
        bootstrapped = tracker.bootstrap_from_public_data(SOURCE_NAME)
        articles = self._discover_articles()
        self.crawl_stats = {
            "discovered": len(articles),
            "details_fetched": 0,
            "skipped_success": 0,
            "failed_items": 0,
            "bootstrapped": bootstrapped,
        }
        if not articles:
            raise RuntimeError("国家能源局列表页未发现目标统计文章")
        for title, url in articles:
            parser = next((func for keyword, func in PARSERS if keyword in title), None)
            if parser is None:
                continue
            registration = tracker.register(url=url, title=title)
            if not registration.should_fetch:
                self.crawl_stats["skipped_success"] += 1
                continue
            try:
                self.crawl_stats["details_fetched"] += 1
                html = self._get_html(url)
                soup = BeautifulSoup(html, "lxml")
                text = " ".join(soup.get_text(" ", strip=True).split())
                parsed = parser(title, text, url, fetched_at)
                if not parsed:
                    raise ValueError("详情页未解析出结构化统计数据")
                parsed_rows = [parsed]
                if parsed.data_type == "national_new_energy_projects":
                    parsed_rows.extend(parse_new_energy_project_provinces(
                        html,
                        data_date=parsed.data_date,
                        title=title,
                        source_url=url,
                        fetched_at=fetched_at,
                    ))
                appended = 0
                for row in parsed_rows:
                    unique_period = (row.data_type, row.province, row.data_date)
                    if unique_period in seen_periods:
                        continue
                    seen_periods.add(unique_period)
                    result.append(row)
                    appended += 1
                tracker.mark_success(
                    registration.state,
                    html,
                    appended,
                    published_at=official_publish_date(html),
                )
            except Exception as exc:
                tracker.mark_failed(registration.state, str(exc))
                self.crawl_stats["failed_items"] += 1
                logger.warning("[nea_statistics] 解析失败 %s: %s", url, exc)
        return result

    def close(self):
        self.client.close()
        super().close()
