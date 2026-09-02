#!/usr/bin/env python3
"""修复历史政策/知识资产的列表标题污染和错误发布日期。

只接受原文明确标题和官方发布日期；请求失败时仅移除 ``MM-DD`` 尾巴，
不会使用抓取时间、入库时间或 URL 日期推测发布日期。
"""
from __future__ import annotations

import argparse
import time
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.config import settings
from app.db.database import SessionLocal, init_db
from app.db.models import KnowledgeDoc, Policy
from app.policy.article_metadata import (
    clean_list_title,
    extract_official_publish_date,
    extract_official_title,
    title_needs_hydration,
)


def canonical_url(value: str) -> str:
    parts = urlsplit((value or "").strip())
    return urlunsplit(("", parts.netloc.lower(), parts.path, parts.query, ""))


def repair(fetch_official: bool = False, rate_limit: float = 0.3) -> dict:
    init_db()
    db = SessionLocal()
    stats = {
        "policies_updated": 0,
        "assets_updated": 0,
        "official_pages_fetched": 0,
        "fetch_errors": 0,
        "test_assets_rejected": 0,
    }
    try:
        policies = db.query(Policy).filter(Policy.source_url.isnot(None)).all()
        by_url: dict[str, list[Policy]] = {}
        for policy in policies:
            by_url.setdefault(canonical_url(policy.source_url or ""), []).append(policy)

        client = httpx.Client(
            timeout=25,
            follow_redirects=True,
            headers={"User-Agent": settings.CRAWLER_USER_AGENT},
        )
        try:
            for url_key, rows in by_url.items():
                if not url_key:
                    continue
                representative = max(rows, key=lambda row: row.id)
                official_title = None
                evidence = None
                should_fetch = fetch_official and (
                    any(title_needs_hydration(row.title) for row in rows)
                    or representative.publish_date_status != "verified"
                )
                if should_fetch:
                    try:
                        response = client.get(representative.source_url)
                        response.raise_for_status()
                        response.encoding = response.charset_encoding or "utf-8"
                        official_title = extract_official_title(response.text)
                        evidence = extract_official_publish_date(response.text)
                        stats["official_pages_fetched"] += 1
                        time.sleep(max(rate_limit, 0))
                    except Exception:
                        stats["fetch_errors"] += 1

                for policy in rows:
                    changed = False
                    repaired_title = official_title or clean_list_title(policy.title)
                    if repaired_title and policy.title != repaired_title:
                        policy.title = repaired_title
                        changed = True
                    if evidence and (
                        policy.publish_date != evidence.publish_date
                        or policy.publish_date_status != "verified"
                    ):
                        policy.publish_date = evidence.publish_date
                        policy.publish_date_status = "verified"
                        policy.publish_date_evidence = evidence.evidence
                        changed = True
                    if changed:
                        stats["policies_updated"] += 1

            assets = db.query(KnowledgeDoc).filter(
                KnowledgeDoc.ingest_type == "crawler",
                KnowledgeDoc.source_url.isnot(None),
            ).all()
            for asset in assets:
                if asset.title.startswith("[测试]"):
                    if asset.review_status != "rejected":
                        asset.review_status = "rejected"
                        stats["test_assets_rejected"] += 1
                    continue
                candidates = by_url.get(canonical_url(asset.source_url or ""), [])
                verified = next(
                    (
                        row for row in sorted(candidates, key=lambda row: row.id, reverse=True)
                        if row.publish_date_status == "verified" and row.publish_date
                    ),
                    None,
                )
                title_source = next(
                    (row for row in sorted(candidates, key=lambda row: row.id, reverse=True) if row.title),
                    None,
                )
                changed = False
                repaired_title = (
                    title_source.title if title_source else clean_list_title(asset.title)
                )
                if repaired_title and asset.title != repaired_title:
                    asset.title = repaired_title
                    changed = True
                correct_date = verified.publish_date if verified else None
                if asset.publish_date != correct_date:
                    asset.publish_date = correct_date
                    changed = True
                if changed:
                    stats["assets_updated"] += 1

            db.commit()
            return stats
        finally:
            client.close()
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch-official", action="store_true")
    parser.add_argument("--rate-limit", type=float, default=0.3)
    args = parser.parse_args()
    print(repair(fetch_official=args.fetch_official, rate_limit=args.rate_limit))
