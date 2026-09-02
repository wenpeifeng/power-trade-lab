"""从原文页面提取可审计的官方发布日期。

只接受页面元数据、time 元素、JSON-LD 或带“发布时间/发布日期”标签的日期。
不从标题中的 MM-DD 猜测年份，也不使用抓取时间替代发布日期。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Optional

from bs4 import BeautifulSoup


@dataclass(frozen=True)
class PublishDateEvidence:
    publish_date: str
    evidence: str


def clean_list_title(value: str) -> str:
    """移除列表链接混入的日期尾巴，保留文章真实标题。

    政府站常把标题和 ``MM-DD`` 放在同一个 ``a`` 元素中；该日期只是列表展示，
    既不属于标题，也不能在缺少年份时用于发布日期推断。
    """
    title = " ".join((value or "").split())
    title = re.sub(r"\s*(?:\.{3}|…{1,3})?\s*\d{1,2}-\d{1,2}\s*$", "", title)
    return title.strip()


def title_needs_hydration(value: str) -> bool:
    """标题带列表日期或截断号时，需要访问原文读取完整标题。"""
    text = (value or "").strip()
    return bool(
        re.search(r"\d{1,2}-\d{1,2}\s*$", text)
        or re.search(r"(?:\.{3}|…{1,3})", text)
    )


def extract_official_title(html: str) -> Optional[str]:
    """从原文元数据或正文标题读取完整标题，不使用列表截断文本。"""
    soup = BeautifulSoup(html or "", "lxml")
    accepted_meta_keys = {
        "articletitle", "article:title", "og:title", "twitter:title",
    }
    for meta in soup.find_all("meta"):
        key = (
            meta.get("property")
            or meta.get("name")
            or meta.get("itemprop")
            or ""
        ).strip().lower()
        if key not in accepted_meta_keys:
            continue
        title = clean_list_title(meta.get("content") or "")
        title = re.sub(r"\s*[-—]{2,}\s*[^-—]+$", "", title).strip()
        if len(title) >= 8:
            return title
    for selector in (
        "h1",
        "h3.article-tit",
        "h3.title",
        ".article-title",
        ".content-title",
    ):
        node = soup.select_one(selector)
        if not node:
            continue
        title = clean_list_title(node.get_text(" ", strip=True))
        if len(title) >= 8:
            return title
    return None


def _normalize_date(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    match = re.search(
        r"(?<!\d)(20\d{2})\s*(?:年|[-/.])\s*(\d{1,2})\s*(?:月|[-/.])\s*(\d{1,2})\s*日?",
        text,
    )
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3))).isoformat()
    except ValueError:
        return None


def _json_dates(value: Any):
    if isinstance(value, dict):
        for key in ("datePublished", "dateCreated", "uploadDate"):
            if key in value:
                yield key, value[key]
        for nested in value.values():
            yield from _json_dates(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _json_dates(nested)


def extract_official_publish_date(html: str) -> Optional[PublishDateEvidence]:
    """从 HTML 中读取原文自身声明的发布日期。"""
    soup = BeautifulSoup(html or "", "lxml")

    # 1. 标准 meta / itemprop。
    accepted_meta_keys = {
        "article:published_time", "datepublished", "publishdate", "pubdate",
        "publication_date", "publish_time", "weibo:article:create_at",
    }
    for meta in soup.find_all("meta"):
        key = (
            meta.get("property")
            or meta.get("name")
            or meta.get("itemprop")
            or ""
        ).strip().lower()
        if key in accepted_meta_keys:
            parsed = _normalize_date(meta.get("content"))
            if parsed:
                return PublishDateEvidence(parsed, f"meta:{key}")

    # 2. HTML time 元素。
    for time_tag in soup.find_all("time"):
        parsed = _normalize_date(time_tag.get("datetime") or time_tag.get_text(" ", strip=True))
        if parsed:
            return PublishDateEvidence(parsed, "html:time")

    # 3. JSON-LD。
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            payload = json.loads(script.string or script.get_text())
        except (json.JSONDecodeError, TypeError):
            continue
        for key, raw_value in _json_dates(payload):
            parsed = _normalize_date(raw_value)
            if parsed:
                return PublishDateEvidence(parsed, f"jsonld:{key}")

    # 4. 页面可见的明确标签。只匹配带语义标签的日期，不扫正文里的任意日期。
    visible_text = " ".join(soup.get_text(" ", strip=True).split())
    labelled = re.search(
        r"(发布时间|发布日期|发布于|发布时间为|信息时间)"
        r"\s*[：:]?\s*"
        r"((?:20\d{2})\s*(?:年|[-/.])\s*\d{1,2}\s*(?:月|[-/.])\s*\d{1,2}\s*日?)",
        visible_text[:12000],
    )
    if labelled:
        parsed = _normalize_date(labelled.group(2))
        if parsed:
            return PublishDateEvidence(parsed, f"text:{labelled.group(1)}")

    # 5. 常见日期容器。容器属性本身必须有 date/time/publish 语义。
    for tag in soup.find_all(True):
        identity = " ".join([
            str(tag.get("id") or ""),
            " ".join(tag.get("class") or []),
        ]).lower()
        if not re.search(r"publish|pubtime|date|time", identity):
            continue
        parsed = _normalize_date(tag.get_text(" ", strip=True))
        if parsed:
            return PublishDateEvidence(parsed, f"element:{identity[:60]}")
    return None


def extract_list_publish_date(text: str) -> Optional[PublishDateEvidence]:
    """列表页只接受完整年月日；不接受缺年份的 MM-DD。"""
    parsed = _normalize_date(text)
    return PublishDateEvidence(parsed, "list:full-date") if parsed else None
