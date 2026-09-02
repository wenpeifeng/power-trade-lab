"""爬虫定时调度器 —— APScheduler 驱动所有数据源定时抓取。

调度策略：
- 政府政策站：每日1次（早8点）
- 知乎/B站：每日1次（晚8点）
- 标准PDF：每周1次（周一早6点，标准偶尔更新）
"""
import logging
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings

logger = logging.getLogger("crawler.scheduler")

_scheduler: Optional[BackgroundScheduler] = None


def run_all_crawlers() -> dict:
    """手动触发：运行所有爬虫（文档型+数值型），返回汇总统计。"""
    if not settings.CRAWLER_ENABLED:
        logger.info("CRAWLER_ENABLED=false，跳过手动触发")
        return {"ran_at": datetime.now().isoformat(), "skipped": True,
                "reason": "CRAWLER_ENABLED=false"}
    from crawlers.adapters.gov_policy import GovPolicyCrawler
    from crawlers.adapters.standard_pdf import StandardPdfCrawler
    from crawlers.adapters.zhihu_bilibili import ZhihuBilibiliCrawler
    from crawlers.adapters.exchange_center import ExchangeCenterCrawler
    from crawlers.adapters.market_data import MARKET_CRAWLERS

    results = []
    # 文档型爬虫（政策/题目/交易公告）
    for CrawlerClass in [GovPolicyCrawler, ZhihuBilibiliCrawler, StandardPdfCrawler, ExchangeCenterCrawler]:
        try:
            crawler = CrawlerClass()
            stats = crawler.run()
            results.append(stats)
            try:
                crawler.close()
            except Exception:
                pass
        except Exception as e:
            logger.error(f"爬虫 {CrawlerClass.__name__} 失败: {e}")
            results.append({"source": CrawlerClass.name, "errors": 1, "error_msg": str(e)})

    # 数值型爬虫（出清价/负荷/煤价/碳价）
    for name, CrawlerClass in MARKET_CRAWLERS.items():
        try:
            crawler = CrawlerClass()
            stats = crawler.run()
            results.append(stats)
            try:
                crawler.close()
            except Exception:
                pass
        except Exception as e:
            logger.error(f"数值爬虫 {name} 失败: {e}")
            results.append({"source": name, "errors": 1, "error_msg": str(e)})

    return {"ran_at": datetime.now().isoformat(), "results": results}


def run_single_crawler(name: str) -> dict:
    """运行单个爬虫（文档型或数值型统一入口）。"""
    from crawlers.adapters.gov_policy import GovPolicyCrawler
    from crawlers.adapters.standard_pdf import StandardPdfCrawler
    from crawlers.adapters.zhihu_bilibili import ZhihuBilibiliCrawler
    from crawlers.adapters.exchange_center import ExchangeCenterCrawler
    from crawlers.adapters.market_data import MARKET_CRAWLERS

    mapping = {
        "gov_policy": GovPolicyCrawler,
        "zhihu_bilibili": ZhihuBilibiliCrawler,
        "standard_pdf": StandardPdfCrawler,
        "exchange_center": ExchangeCenterCrawler,
    }
    cls = mapping.get(name) or MARKET_CRAWLERS.get(name)
    if not cls:
        return {"error": f"未知爬虫: {name}"}
    crawler = cls()
    stats = crawler.run()
    try:
        crawler.close()
    except Exception:
        pass
    return stats


def init_scheduler():
    """初始化后台调度器（随应用启动）。"""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    if not settings.CRAWLER_ENABLED:
        logger.info("CRAWLER_ENABLED=false，不注册任何爬虫定时任务")
        return None

    _scheduler = BackgroundScheduler(timezone="Asia/Shanghai")

    # 政府政策站：每日早8点
    _scheduler.add_job(
        lambda: run_single_crawler("gov_policy"),
        CronTrigger(hour=8, minute=0),
        id="gov_policy_daily",
        replace_existing=True,
    )
    # 知乎/B站：每日晚8点
    _scheduler.add_job(
        lambda: run_single_crawler("zhihu_bilibili"),
        CronTrigger(hour=20, minute=0),
        id="zhihu_daily",
        replace_existing=True,
    )
    # 标准PDF：每周一早6点
    _scheduler.add_job(
        lambda: run_single_crawler("standard_pdf"),
        CronTrigger(day_of_week="mon", hour=6, minute=0),
        id="standard_pdf_weekly",
        replace_existing=True,
    )
    # 出清价格：每日9:00（交易中心发布后）
    _scheduler.add_job(
        lambda: run_single_crawler("clearing_price"),
        CronTrigger(hour=9, minute=0),
        id="clearing_price_daily",
        replace_existing=True,
    )
    # 负荷预测：每日6:00
    _scheduler.add_job(
        lambda: run_single_crawler("load_forecast"),
        CronTrigger(hour=6, minute=0),
        id="load_forecast_daily",
        replace_existing=True,
    )
    # 煤价/碳价：每日10:00
    _scheduler.add_job(
        lambda: [run_single_crawler(n) for n in ("coal_price", "carbon_price")],
        CronTrigger(hour=10, minute=0),
        id="commodity_price_daily",
        replace_existing=True,
    )
    # 国家能源局公开统计：每日 12:20 检查增量，按月份去重。
    _scheduler.add_job(
        lambda: run_single_crawler("nea_statistics"),
        CronTrigger(hour=12, minute=20),
        id="nea_statistics_daily",
        replace_existing=True,
    )
    # 广州电力交易中心每周现货/绿证公开行情：每日检查增量。
    _scheduler.add_job(
        lambda: run_single_crawler("gzpec_market"),
        CronTrigger(hour=13, minute=0),
        id="gzpec_market_daily",
        replace_existing=True,
    )
    # 全国碳市场日行情：交易日收盘后同步；节假日无新增时由去重保证幂等。
    _scheduler.add_job(
        lambda: run_single_crawler("carbon_market"),
        CronTrigger(hour=18, minute=20),
        id="carbon_market_daily",
        replace_existing=True,
    )
    # 国家统计局月度能源生产：每日检查最新月报。
    _scheduler.add_job(
        lambda: run_single_crawler("nbs_energy"),
        CronTrigger(hour=12, minute=40),
        id="nbs_energy_daily",
        replace_existing=True,
    )

    # 交易中心（Playwright 渲染动态站）：每日 11:30
    _scheduler.add_job(
        lambda: run_single_crawler("exchange_center"),
        CronTrigger(hour=11, minute=30),
        id="exchange_center_daily",
        replace_existing=True,
    )

    # 和风天气：配置完成后每小时第5分钟同步近实时观测和逐小时预报。
    if settings.qweather_configured:
        _scheduler.add_job(
            lambda: run_single_crawler("qweather"),
            CronTrigger(minute=5),
            id="qweather_hourly",
            replace_existing=True,
        )

    # 启动补爬：后端启动 30 秒后自动跑一次政策爬虫。
    # 开发环境后端非常驻，容易错过每日 8:00 定时；有去重，重复不会入库。
    from apscheduler.triggers.date import DateTrigger
    from datetime import datetime, timedelta
    _scheduler.add_job(
        lambda: run_single_crawler("gov_policy"),
        DateTrigger(run_date=datetime.now() + timedelta(seconds=30)),
        id="gov_policy_startup",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info(
        "爬虫调度器已启动: "
        "政策(8:00) 知乎B站(20:00) 标准PDF(周一6:00) "
        "出清价(9:00) 负荷(6:00) 煤价碳价(10:00) 国家能源局统计(12:20) "
        "国家统计局能源(12:40) 广州公开行情(13:00) 全国碳市场(18:20) "
        f"和风天气({'每小时' if settings.qweather_configured else '未配置'})"
    )
    return _scheduler


def get_scheduler_info() -> dict:
    """获取调度器状态。"""
    if not _scheduler:
        return {"running": False}
    jobs = []
    for job in _scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "next_run": str(job.next_run_time) if job.next_run_time else None,
        })
    return {"running": _scheduler.running, "jobs": jobs}
