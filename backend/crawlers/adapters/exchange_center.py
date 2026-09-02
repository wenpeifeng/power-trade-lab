"""电力交易中心爬虫 —— Playwright 渲染抓取动态站的交易公告/规则/出清结果。

交易中心网站多为 JS 动态渲染，httpx 抓不到内容，必须用浏览器渲染。

依赖：playwright + chromium 浏览器内核。
首次在服务器上使用前需执行一次：
    ./venv/bin/playwright install chromium

注意：交易中心域名/公告栏目 URL 需按实际网站确认（各交易中心改版频繁）。
本适配器用通用提取（渲染后抓含交易关键词的链接），具体栏目可在 EXCHANGE_SOURCES 精调。
"""
import logging
from bs4 import BeautifulSoup

from app.config import settings
from app.policy.article_metadata import extract_list_publish_date, extract_official_publish_date
from app.policy.ranking import classify_policy, infer_priority
from crawlers.base import BaseCrawler, CrawledPolicy

logger = logging.getLogger("crawler.exchange")

# 电力交易中心源。url 建议填「公告/信息披露」栏目页而非首页。
EXCHANGE_SOURCES = [
    {"name": "广州电力交易中心", "url": "https://www.gzpec.cn/", "base": "https://www.gzpec.cn", "category": "market"},
    {"name": "北京电力交易中心", "url": "https://www.bjpx.com.cn/", "base": "https://www.bjpx.com.cn", "category": "market"},
]

KEYWORDS = ["交易", "公告", "出清", "规则", "结算", "市场", "电价", "现货",
            "中长期", "绿电", "绿证", "辅助服务", "结果", "通知", "价格", "披露"]


class ExchangeCenterCrawler(BaseCrawler):
    """交易中心动态站爬虫（Playwright 浏览器渲染）。"""
    name = "exchange_center"
    rate_limit = 2.0

    def __init__(self, db=None, max_items: int = 30):
        super().__init__(db)
        self.max_items = max_items

    def fetch_items(self) -> tuple[list[CrawledPolicy], list]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("[exchange] playwright 包缺失，跳过")
            return [], []

        policies = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=settings.CRAWLER_USER_AGENT,
                    ignore_https_errors=True,  # 部分交易中心 SSL 证书不规范
                )
                page = context.new_page()
                for ex in EXCHANGE_SOURCES:
                    try:
                        page.goto(ex["url"], timeout=30000, wait_until="domcontentloaded")
                        page.wait_for_timeout(2500)  # 等 JS 渲染出列表
                        items = self._extract(page.content(), ex)
                        self._hydrate_official_dates(page, items)
                        policies.extend(items)
                        logger.info(f"[exchange] {ex['name']}: 抓到 {len(items)} 条")
                    except Exception as e:
                        logger.warning(f"[exchange] 渲染 {ex['name']} 失败: {str(e)[:80]}")
                browser.close()
        except Exception as e:
            logger.error(
                f"[exchange] Playwright 启动失败（是否已执行 playwright install chromium?）: {e}"
            )
        return policies[:self.max_items], []

    def _extract(self, html: str, ex: dict) -> list[CrawledPolicy]:
        soup = BeautifulSoup(html, "lxml")
        results, seen = [], set()
        for a in soup.find_all("a", href=True):
            title = a.get_text(strip=True)
            href = a["href"]
            if not title or len(title) < 8 or title in seen:
                continue
            if not any(k in title for k in KEYWORDS):
                continue
            if href.startswith("/"):
                href = ex["base"] + href
            elif not href.startswith("http"):
                continue
            seen.add(title)
            near = a.parent.get_text() if a.parent else ""
            date_evidence = extract_list_publish_date(near)
            category = classify_policy(title, ex["category"])
            results.append(CrawledPolicy(
                title=title, category=category, source=ex["name"], source_url=href,
                publish_date=date_evidence.publish_date if date_evidence else None,
                publish_date_status="verified" if date_evidence else "unverified",
                publish_date_evidence=date_evidence.evidence if date_evidence else None,
                priority=infer_priority(title, category),
            ))
        return results

    def _hydrate_official_dates(self, page, policies: list[CrawledPolicy]) -> None:
        for item in policies:
            # 列表页仍需扫描以发现增量；已入库 URL 不再重复访问详情页。
            if (
                item.publish_date_status == "verified"
                or not item.source_url
                or self._policy_exists(item)
            ):
                continue
            try:
                page.goto(item.source_url, timeout=20000, wait_until="domcontentloaded")
                evidence = extract_official_publish_date(page.content())
                if evidence:
                    item.publish_date = evidence.publish_date
                    item.publish_date_status = "verified"
                    item.publish_date_evidence = evidence.evidence
            except Exception as exc:
                logger.warning("[exchange] 原文日期核验失败 %s: %s", item.source_url, exc)

    def close(self):
        pass
