"""数值型时序数据爬虫基类 —— 采集真实市场行情。

与文档型 BaseCrawler（政策/题目）并列，专门处理结构化数值时序：
- 出清价格 (clearing)
- 负荷预测 (load)
- 动力煤价格 (coal)
- 碳市场价格 (carbon)
- 新能源出力 (renewable)

入库目标：PublicData 表，供交易终端回放与数据分析页使用。

子类只需实现 fetch_series() 返回 CrawledSeries 列表。
"""
import hashlib
import json
import logging
import time
from abc import abstractmethod
from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import PublicData
from app.config import PROJECT_ROOT, settings

logger = logging.getLogger("crawler.market")


@dataclass
class CrawledSeries:
    """一条标准化时序数据点。"""
    data_type: str              # clearing/load/coal/carbon/renewable
    province: Optional[str]     # 省份，全国性数据可为 None
    data_date: str              # YYYY-MM-DD 或 YYYY-MM-DD HH:MM
    metrics: dict               # {"clearing_price": 324.5, "load": 12000, "product": "day_ahead"}
    source: str = ""            # 来源标注
    source_url: Optional[str] = None
    provenance_level: str = "synthetic"
    disclosure_scope: str = "public"
    fetched_at: Optional[str] = None
    parser_version: str = "1"
    quality_status: str = "unknown"
    update_existing: bool = False
    raw: Optional[dict] = None  # 原始响应留档


class MarketDataCrawler:
    """数值数据爬虫基类。

    与 BaseCrawler 不同：
    - fetch_items → fetch_series（返回 CrawledSeries）
    - 入库 → PublicData 表（不是 Policy/Question）
    - 去重 → (data_type + province + data_date) 组合哈希
    """

    name: str = "market_base"
    rate_limit: float = 1.0
    timeout: float = 15.0
    headers: dict = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    }

    def __init__(self, db: Optional[Session] = None):
        self.db = db or SessionLocal()
        self.rate_limit = settings.CRAWLER_RATE_LIMIT_SEC
        self._last_request_time = 0.0
        self.crawl_stats: dict[str, int] = {}

    def _throttle(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self._last_request_time = time.time()

    def _fetch_json(self, url: str, params: Optional[dict] = None) -> Optional[dict]:
        """带限速的 JSON 抓取，失败返回 None（不抛异常打断批量）。"""
        self._throttle()
        try:
            with httpx.Client(timeout=self.timeout, headers=self.headers, follow_redirects=True) as c:
                r = c.get(url, params=params)
                r.raise_for_status()
                return r.json()
        except Exception as e:
            logger.warning(f"[{self.name}] 抓取失败 {url}: {e}")
            return None

    @abstractmethod
    def fetch_series(self) -> list[CrawledSeries]:
        """子类实现：抓取并返回标准化时序数据点。"""
        ...

    def _dedup_key(self, s: CrawledSeries) -> str:
        raw = f"{s.data_type}|{s.province or 'ALL'}|{s.data_date}"
        return hashlib.md5(raw.encode()).hexdigest()[:16]

    def _save_raw_asset(self, s: CrawledSeries) -> tuple[Optional[str], Optional[str]]:
        """把原始响应保存到公开原始层，返回相对路径和 SHA-256。

        原始响应禁止包含 Authorization、API KEY 或请求头；连接器只应传业务响应。
        相同响应按内容哈希去重。
        """
        if s.raw is None:
            return None, None
        payload = json.dumps(s.raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        digest = hashlib.sha256(payload).hexdigest()
        day = (s.fetched_at or datetime.now().isoformat())[:10]
        target_dir = settings.RAW_PUBLIC_DIR / self.name / day[:4] / day[5:7] / day[8:10]
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{digest}.json"
        if not target.exists():
            target.write_bytes(payload)
        try:
            relative = str(target.relative_to(PROJECT_ROOT))
        except (ValueError, AttributeError):
            relative = str(target)
        return relative, digest

    def run(self) -> dict:
        """执行抓取并入库。"""
        logger.info(f"[{self.name}] 开始抓取数值数据...")
        stats = {"source": self.name, "new": 0, "updated": 0, "dup": 0, "errors": 0}
        try:
            series = self.fetch_series()
        except Exception as e:
            logger.error(f"[{self.name}] 抓取失败: {e}")
            stats["errors"] = 1
            stats["error_msg"] = str(e)
            return stats

        stats.update(self.crawl_stats)
        stats["errors"] += self.crawl_stats.get("failed_items", 0)

        for s in series:
            key = self._dedup_key(s)
            raw_asset_path, raw_sha256 = self._save_raw_asset(s)
            existing = self.db.query(PublicData).filter(PublicData.dedup_key == key).first()
            if existing:
                if s.update_existing:
                    existing.metrics = json.dumps(s.metrics, ensure_ascii=False)
                    existing.source = s.source or self.name
                    existing.source_url = s.source_url
                    existing.provenance_level = s.provenance_level
                    existing.disclosure_scope = s.disclosure_scope
                    existing.fetched_at = s.fetched_at or datetime.now().isoformat()
                    existing.raw_asset_path = raw_asset_path
                    existing.raw_sha256 = raw_sha256
                    existing.parser_version = s.parser_version
                    existing.quality_status = s.quality_status
                    stats["updated"] += 1
                    continue
                # 已存在：若旧数据无 curve 而新数据有，则升级覆盖（种子数据→真实分时数据）
                old_metrics = json.loads(existing.metrics) if existing.metrics else {}
                if "curve" in s.metrics and "curve" not in old_metrics:
                    existing.metrics = json.dumps(s.metrics, ensure_ascii=False)
                    existing.source = s.source or self.name
                    existing.source_url = s.source_url
                    existing.provenance_level = s.provenance_level
                    existing.disclosure_scope = s.disclosure_scope
                    existing.fetched_at = s.fetched_at or datetime.now().isoformat()
                    existing.raw_asset_path = raw_asset_path
                    existing.raw_sha256 = raw_sha256
                    existing.parser_version = s.parser_version
                    existing.quality_status = s.quality_status
                    stats["updated"] += 1
                    continue
                stats["dup"] += 1
                continue
            self.db.add(PublicData(
                data_type=s.data_type, province=s.province, data_date=s.data_date,
                metrics=json.dumps(s.metrics, ensure_ascii=False),
                source=s.source or self.name, source_url=s.source_url,
                provenance_level=s.provenance_level,
                disclosure_scope=s.disclosure_scope,
                fetched_at=s.fetched_at or datetime.now().isoformat(),
                raw_asset_path=raw_asset_path, raw_sha256=raw_sha256,
                parser_version=s.parser_version, quality_status=s.quality_status,
                dedup_key=key,
            ))
            stats["new"] += 1
        self.db.commit()
        logger.info(
            f"[{self.name}] 完成: 新增{stats['new']}条, "
            f"更新{stats['updated']}条(重复{stats['dup']})"
        )
        return stats

    def close(self):
        try:
            self.db.close()
        except Exception:
            pass
