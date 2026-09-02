#!/usr/bin/env python3
"""从每条公告的原文页面重新核验发布日期。

发布日期只能来自原文元数据或明确的发布时间标签。无法核验时置空并标记 unverified。
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import httpx

from app.config import settings
from app.db.database import SessionLocal, init_db
from app.db.models import Policy
from app.policy.article_metadata import extract_official_publish_date

KNOWN_OFFICIAL_URLS = {
    "国务院办公厅关于完善全国统一电力市场体系的实施意见":
        "https://www.gov.cn/zhengce/content/202602/content_7057744.htm",
    "国家发改委办公厅 国家能源局综合司关于建立全国统一电力市场评价制度的通知":
        "https://www.ndrc.gov.cn/xxgk/zcfb/tz/202512/t20251217_1402475.html",
}


def fetch_evidence(url: str):
    try:
        response = httpx.get(
            url,
            timeout=25,
            follow_redirects=True,
            headers={"User-Agent": settings.CRAWLER_USER_AGENT},
        )
        response.raise_for_status()
        response.encoding = response.charset_encoding or "utf-8"
        return extract_official_publish_date(response.text), None
    except Exception as exc:
        return None, type(exc).__name__


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        rows = db.query(Policy).all()
        for row in rows:
            if row.title in KNOWN_OFFICIAL_URLS and not row.source_url:
                row.source_url = KNOWN_OFFICIAL_URLS[row.title]

        by_url = {}
        for row in rows:
            if row.source_url:
                by_url.setdefault(row.source_url, []).append(row)

        results = {}
        with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 6))) as executor:
            futures = {executor.submit(fetch_evidence, url): url for url in by_url}
            for future in as_completed(futures):
                results[futures[future]] = future.result()

        verified = 0
        unverified = 0
        fetch_errors = 0
        verified_at = datetime.now().astimezone().isoformat()
        for row in rows:
            evidence = None
            error = None
            if row.source_url:
                evidence, error = results.get(row.source_url, (None, "not_requested"))
            if evidence:
                row.publish_date = evidence.publish_date
                row.publish_date_status = "verified"
                row.publish_date_evidence = evidence.evidence
                row.publish_date_verified_at = verified_at
                verified += 1
            else:
                row.publish_date = None
                row.publish_date_status = "unverified"
                row.publish_date_evidence = "fetch_error" if error else "date_not_found"
                row.publish_date_verified_at = None
                unverified += 1
                if error:
                    fetch_errors += 1

        if args.apply:
            db.commit()
        else:
            db.rollback()
        print({
            "mode": "applied" if args.apply else "preview",
            "total": len(rows),
            "unique_source_urls": len(by_url),
            "verified": verified,
            "unverified": unverified,
            "fetch_errors": fetch_errors,
        })
    finally:
        db.close()


if __name__ == "__main__":
    main()
