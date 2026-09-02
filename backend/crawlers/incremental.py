"""通用增量采集账本。

唯一性优先级：
1. 官方 URL 中的稳定文章 ID；
2. URL 最后一个非通用路径段；
3. 规范化 URL 的 SHA-256。

连接器应先 register()，只有 should_fetch=True 时才请求详情页。成功、失败状态
与业务数据使用同一个 SQLAlchemy Session 提交，避免“账本成功但数据未落库”。
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.db.models import CrawlSourceItem, PublicData, now_utc


TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {"spm", "from", "source", "eqid"}


def canonicalize_url(url: str) -> str:
    """移除 fragment 和常见跟踪参数，保留影响资源定位的业务参数。"""
    parts = urlsplit((url or "").strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_KEYS
        and not key.lower().startswith(TRACKING_QUERY_PREFIXES)
    ]
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    return urlunsplit((
        parts.scheme.lower(),
        parts.netloc.lower(),
        path,
        urlencode(sorted(query)),
        "",
    ))


def source_item_id(url: str) -> str:
    """提取可审计的官方文章 ID；找不到时退回 URL 内容哈希。"""
    canonical = canonicalize_url(url)
    path = urlsplit(canonical).path
    for pattern in (
        r"/([0-9a-f]{24,64})/c\.html$",  # 国家能源局 UUID
        r"/(t20\d{6,}_\d+)\.html?$",     # 统计局/政府站
        r"/(\d{5,})\.(?:s?html?)$",      # 交易所数值文章 ID
    ):
        match = re.search(pattern, path, re.IGNORECASE)
        if match:
            return match.group(1).lower()
    stem = path.rstrip("/").rsplit("/", 1)[-1]
    stem = re.sub(r"\.(?:s?html?)$", "", stem, flags=re.IGNORECASE)
    if stem and stem.lower() not in {"c", "index", "default"} and len(stem) >= 6:
        return stem[:200]
    return "url:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def official_publish_date(html: str) -> Optional[str]:
    """只读取原文明确披露的发布日期；不从 URL、标题或抓取时间猜日期。"""
    soup = BeautifulSoup(html or "", "lxml")
    for meta_name in ("PubDate", "publishdate", "PublishDate", "ArticleDate"):
        meta = soup.find("meta", attrs={"name": re.compile(f"^{meta_name}$", re.I)})
        if meta and meta.get("content"):
            match = re.search(r"(20\d{2})[-年/.](\d{1,2})[-月/.](\d{1,2})", meta["content"])
            if match:
                return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    text = " ".join(soup.get_text(" ", strip=True).split())
    match = re.search(
        r"(?:发布时间|发布日期|发布于|时间)\s*[:：]?\s*"
        r"(20\d{2})[-年/.](\d{1,2})[-月/.](\d{1,2})日?",
        text,
    )
    if match:
        return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    return None


@dataclass
class Registration:
    state: CrawlSourceItem
    should_fetch: bool
    reason: str


class IncrementalTracker:
    def __init__(self, db: Session, crawler_name: str, parser_version: str):
        self.db = db
        self.crawler_name = crawler_name
        self.parser_version = parser_version

    def bootstrap_from_public_data(self, source_name: str) -> int:
        """把已有真实数据回填到账本，升级部署后不会把历史原文再下载一遍。"""
        rows = (
            self.db.query(PublicData)
            .filter(
                PublicData.source == source_name,
                PublicData.source_url.isnot(None),
                PublicData.provenance_level.in_(("observed_public", "observed_authorized")),
            )
            .all()
        )
        grouped: dict[str, list[PublicData]] = {}
        for row in rows:
            if row.source_url:
                grouped.setdefault(canonicalize_url(row.source_url), []).append(row)
        created = 0
        for url, source_rows in grouped.items():
            item_id = source_item_id(url)
            existing = self._get(item_id)
            if existing:
                continue
            latest = max(source_rows, key=lambda row: row.fetched_at or "")
            success_at = _parse_datetime(latest.fetched_at) or now_utc()
            self.db.add(CrawlSourceItem(
                crawler_name=self.crawler_name,
                source_item_id=item_id,
                source_url=url,
                status="success",
                content_sha256=latest.raw_sha256,
                # 保留业务表中真实使用过的版本；若当前解析器已升级，
                # register() 会判定 parser_upgraded 并重新处理原文。
                parser_version=latest.parser_version or self.parser_version,
                data_count=len(source_rows),
                first_seen_at=success_at,
                last_seen_at=success_at,
                last_attempt_at=success_at,
                last_success_at=success_at,
            ))
            created += 1
        if created:
            self.db.flush()
        return created

    def register(
        self,
        *,
        url: str,
        title: Optional[str] = None,
        published_at: Optional[str] = None,
        item_id: Optional[str] = None,
    ) -> Registration:
        canonical = canonicalize_url(url)
        official_id = item_id or source_item_id(canonical)
        state = self._get(official_id)
        if state is None:
            state = CrawlSourceItem(
                crawler_name=self.crawler_name,
                source_item_id=official_id,
                source_url=canonical,
                title=title,
                published_at=published_at,
                status="discovered",
                first_seen_at=now_utc(),
                last_seen_at=now_utc(),
            )
            self.db.add(state)
            self.db.flush()
            return Registration(state, True, "new")

        state.source_url = canonical
        state.last_seen_at = now_utc()
        if title:
            state.title = title
        if published_at:
            state.published_at = published_at
        if state.status == "success" and state.parser_version == self.parser_version:
            return Registration(state, False, "already_successful")
        if state.status == "failed":
            return Registration(state, True, "retry_failed")
        return Registration(state, True, "parser_upgraded")

    def mark_success(
        self,
        state: CrawlSourceItem,
        content: str | bytes,
        data_count: int,
        published_at: Optional[str] = None,
    ) -> None:
        payload = content.encode("utf-8") if isinstance(content, str) else content
        now = now_utc()
        state.status = "success"
        state.content_sha256 = hashlib.sha256(payload).hexdigest()
        state.parser_version = self.parser_version
        state.data_count = data_count
        if published_at:
            state.published_at = published_at
        state.last_attempt_at = now
        state.last_success_at = now
        state.error_message = None

    def mark_failed(self, state: CrawlSourceItem, error: str) -> None:
        state.status = "failed"
        state.parser_version = self.parser_version
        state.last_attempt_at = now_utc()
        state.error_message = str(error)[:1000]

    def _get(self, item_id: str) -> Optional[CrawlSourceItem]:
        return (
            self.db.query(CrawlSourceItem)
            .filter(
                CrawlSourceItem.crawler_name == self.crawler_name,
                CrawlSourceItem.source_item_id == item_id,
            )
            .first()
        )


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
    except (TypeError, ValueError):
        return None
