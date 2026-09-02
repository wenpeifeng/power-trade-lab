"""政府政策站爬虫 —— 国家发改委、能源局等官方政策源。

这些是纯静态政府站，爬取稳定、合规、权威。
是政策数据和考点预测输入流的主要来源。
"""
import logging
import re
from datetime import datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.policy.article_metadata import (
    clean_list_title,
    extract_list_publish_date,
    extract_official_publish_date,
    extract_official_title,
    title_needs_hydration,
)
from app.policy.ranking import classify_policy, infer_priority
from crawlers.base import BaseCrawler, CrawledPolicy

logger = logging.getLogger("crawler.gov")

# 官方数据源配置。list_selector 为可选的精准列表选择器（命中率远高于泛泛抓链接）；
# 无 selector 的源走通用兜底。交易中心为动态站，交由 Playwright 适配器处理（见 exchange_center.py）。
GOV_SOURCES = [
    # ---- 国家发改委（ul.u-list 结构已验证，精准抓取）----
    {"name": "国家发改委-通知公告", "url": "https://www.ndrc.gov.cn/xxgk/zcfb/tz/", "base": "https://www.ndrc.gov.cn", "category": "national", "list_selector": "ul.u-list li"},
    {"name": "国家发改委-规范性文件", "url": "https://www.ndrc.gov.cn/xxgk/zcfb/ghxwj/", "base": "https://www.ndrc.gov.cn", "category": "national", "list_selector": "ul.u-list li"},
    # ---- 国家能源局（新闻栏目通用可抓；旧政策 URL 已 404，移除）----
    {"name": "国家能源局-新闻发布", "url": "https://www.nea.gov.cn/xwzx/", "base": "https://www.nea.gov.cn", "category": "national"},
    # ---- 各区域能源监管局（西北/东北通用已抓到；华北华东南方保留兜底）----
    {"name": "西北能源监管局", "url": "http://xbj.nea.gov.cn/", "base": "http://xbj.nea.gov.cn", "category": "regulation"},
    {"name": "东北能源监管局", "url": "http://dbj.nea.gov.cn/", "base": "http://dbj.nea.gov.cn", "category": "regulation"},
    {"name": "华北能源监管局", "url": "http://hbj.nea.gov.cn/", "base": "http://hbj.nea.gov.cn", "category": "regulation"},
    {"name": "华东能源监管局", "url": "http://hdj.nea.gov.cn/", "base": "http://hdj.nea.gov.cn", "category": "regulation"},
    {"name": "南方能源监管局", "url": "http://nfj.nea.gov.cn/", "base": "http://nfj.nea.gov.cn", "category": "regulation"},
    # ---- 行业组织 ----
    {"name": "中国电力企业联合会", "url": "https://www.cec.org.cn/", "base": "https://www.cec.org.cn", "category": "market"},
]


class GovPolicyCrawler(BaseCrawler):
    """政府政策站爬虫。

    策略：用 httpx 抓取列表页HTML，解析标题/日期/链接，
    再抓详情页正文。限速1req/s。
    """
    name = "gov_policy"
    rate_limit = 1.5  # 政府站更保守

    def __init__(self, db=None, max_items: int = 40):
        super().__init__(db)
        self.max_items = max_items
        self.client = httpx.Client(
            timeout=20,
            headers={"User-Agent": settings.CRAWLER_USER_AGENT},
            follow_redirects=True,
        )

    def fetch_items(self) -> tuple[list[CrawledPolicy], list]:
        policies = []
        for src in GOV_SOURCES:
            try:
                items = self._crawl_incremental(src)
                policies.extend(items)
                logger.info(f"[gov_policy] {src['name']}: 新增候选 {len(items)} 条")
            except Exception as e:
                logger.warning(f"[gov_policy] 抓取 {src['name']} 失败: {e}")
        return policies[:self.max_items], []

    def _crawl_incremental(self, src: dict) -> list[CrawledPolicy]:
        """翻页增量抓取 + 早停：只收库里没有的；连续遇到已入库的就停止翻页
        （列表按日期倒序，遇到老的说明后面全是老的）。首次爬会翻到底，之后只增量。"""
        new_items = []
        consecutive_dup = 0
        max_pages = src.get("max_pages", 1)
        for page in range(max_pages):
            self._throttle()
            page_items = self._crawl_source({**src, "url": self._page_url(src, page)})
            if not page_items:
                break  # 该页无内容(或翻页URL失效)，停止
            for it in page_items:
                if self._policy_exists(it):
                    consecutive_dup += 1
                    if consecutive_dup >= 6:  # 连续6条已入库 → 后面都是老的，停止翻页
                        return new_items
                else:
                    consecutive_dup = 0
                    self._hydrate_official_metadata(it)
                    new_items.append(it)
        return new_items

    def _page_url(self, src: dict, page: int) -> str:
        """翻页 URL：page=0 首页；配了 page_pattern 的源支持翻页(如 index_{n}.html)。"""
        if page == 0:
            return src["url"]
        pat = src.get("page_pattern")
        if pat:
            # 翻页页在栏目目录下：<栏目URL>/index_{n}.html
            return src["url"].rstrip("/") + "/" + pat.format(n=page)
        return src["url"]

    KEYWORDS = ["电力", "市场", "能源", "电价", "交易", "现货", "绿电", "绿证",
                "辅助服务", "输配电", "碳", "需求响应", "储能", "煤电", "新能源", "价格", "购售电"]

    def _crawl_source(self, src: dict) -> list[CrawledPolicy]:
        """抓取单个政策源列表页。优先用配置的 list_selector 精准定位列表项，
        没有则走通用兜底（含关键词的链接）。"""
        resp = self.client.get(src["url"])
        resp.encoding = resp.charset_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "lxml")

        results = []
        selector = src.get("list_selector")
        items = soup.select(selector) if selector else None
        if items:
            for it in items[:15]:
                a = it.find("a", href=True)
                if a:
                    title = a.get("title") or a.get_text(" ", strip=True)
                    r = self._make_policy(title, a.get("href"), src, near=it)
                    if r:
                        results.append(r)
        else:
            for link in soup.find_all("a", href=True)[:60]:
                title = link.get("title") or link.get_text(" ", strip=True)
                r = self._make_policy(title, link.get("href"), src, near=link)
                if r:
                    results.append(r)
        return results

    NOISE_WORDS = ("更多", "首页", "下一页", "上一页", "尾页", "返回", "查看全部",
                   "点击", "详见", "登录", "注册", "index", "list", "网站地图")

    def _make_policy(self, title, href, src, near) -> Optional[CrawledPolicy]:
        """标题过滤（关键词命中 + 排除导航/栏目噪音）+ URL 规整 + 构造。"""
        title = clean_list_title(title)
        if not title or len(title) < 10 or not href:
            return None
        if any(n in title for n in self.NOISE_WORDS):
            return None
        if not any(k in title for k in self.KEYWORDS):
            return None
        if href.startswith("/"):
            href = src["base"] + href
        elif not href.startswith("http"):
            return None
        category = classify_policy(title, src["category"])
        date_evidence = self._extract_date_near(near)
        return CrawledPolicy(
            title=title, category=category, source=src["name"],
            source_url=href,
            publish_date=date_evidence.publish_date if date_evidence else None,
            publish_date_status="verified" if date_evidence else "unverified",
            publish_date_evidence=date_evidence.evidence if date_evidence else None,
            priority=infer_priority(title, category),
        )

    def _extract_date_near(self, element):
        """列表页只接受完整年月日，不根据 MM-DD 猜年份。"""
        for _ in range(3):
            parent = element.parent
            if not parent:
                break
            text = parent.get_text()
            parsed = extract_list_publish_date(text)
            if parsed:
                return parsed
            element = parent
        return None

    def _hydrate_official_metadata(self, policy: CrawledPolicy) -> None:
        """访问原文补齐严格发布日期及未截断标题。"""
        needs_date = policy.publish_date_status != "verified"
        needs_title = title_needs_hydration(policy.title)
        if not policy.source_url or not (needs_date or needs_title):
            return
        try:
            self._throttle()
            response = self.client.get(policy.source_url)
            response.raise_for_status()
            response.encoding = response.charset_encoding or "utf-8"
            official_title = extract_official_title(response.text)
            if official_title:
                policy.title = official_title
            evidence = extract_official_publish_date(response.text) if needs_date else None
            if evidence is not None:
                policy.publish_date = evidence.publish_date
                policy.publish_date_status = "verified"
                policy.publish_date_evidence = evidence.evidence
        except Exception as exc:
            logger.warning("[gov_policy] 原文日期核验失败 %s: %s", policy.source_url, exc)

    def close(self):
        self.client.close()
