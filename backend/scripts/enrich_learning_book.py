"""使用已配置的 LLM 批量重建教材学习资产。

用法：
    PYTHONPATH=backend backend/.venv/bin/python backend/scripts/enrich_learning_book.py 1
"""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.ai.credentials import get_user_runtime_config
from app.db.database import SessionLocal
from app.db.models import LearningBook, LearningBookChapter
from app.study.book_service import build_chapter_learning_assets


def enrich_one(payload: dict, runtime_config) -> dict:
    summary, assets, quiz = build_chapter_learning_assets(
        payload["title"],
        payload["content"],
        payload["concepts"],
        use_llm=True,
        runtime_config=runtime_config,
    )
    return {
        "id": payload["id"],
        "order": payload["order"],
        "summary": summary,
        "assets": assets,
        "quiz": quiz,
        "ai": assets.get("enrichment_mode") == "ai",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("book_id", type=int)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        book = db.get(LearningBook, args.book_id)
        if not book:
            raise SystemExit("教材不存在")
        runtime_config = get_user_runtime_config(db, book.user_id)
        if not runtime_config or not runtime_config.configured:
            raise SystemExit("教材所属用户尚未配置个人 AI Key，请先在个人 AI 设置中配置")
        chapters = (
            db.query(LearningBookChapter)
            .filter(LearningBookChapter.book_id == args.book_id)
            .order_by(LearningBookChapter.chapter_order)
            .all()
        )
        payloads = []
        for chapter in chapters:
            try:
                current = json.loads(chapter.key_points or "{}")
            except json.JSONDecodeError:
                current = {}
            payloads.append({
                "id": chapter.id,
                "order": chapter.chapter_order,
                "title": chapter.title,
                "content": chapter.markdown_content,
                "concepts": current.get("concepts") or [],
            })
    finally:
        db.close()

    completed = 0
    ai_count = 0
    failed_orders: list[int] = []
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 8))) as pool:
        futures = {
            pool.submit(enrich_one, payload, runtime_config): payload
            for payload in payloads
        }
        for future in as_completed(futures):
            payload = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                failed_orders.append(payload["order"])
                print(f"FAILED order={payload['order']} error={str(exc)[:120]}", flush=True)
                continue

            write_db = SessionLocal()
            try:
                chapter = write_db.get(LearningBookChapter, result["id"])
                chapter.summary = result["summary"]
                chapter.key_points = json.dumps(result["assets"], ensure_ascii=False)
                chapter.quiz_json = json.dumps(result["quiz"], ensure_ascii=False)
                write_db.commit()
            finally:
                write_db.close()

            completed += 1
            ai_count += int(result["ai"])
            print(
                f"PROGRESS {completed}/{len(payloads)} order={result['order']} "
                f"mode={'AI' if result['ai'] else 'RULES'}",
                flush=True,
            )

    final_db = SessionLocal()
    try:
        book = final_db.get(LearningBook, args.book_id)
        book.parser_message = (
            f"MinerU 解析完成；{ai_count}/{len(payloads)} 个章节已由 "
            f"{runtime_config.model} 生成大白话导读、核心结论与原文依据"
        )
        final_db.commit()
    finally:
        final_db.close()

    print(json.dumps({
        "book_id": args.book_id,
        "chapters": len(payloads),
        "completed": completed,
        "ai_enriched": ai_count,
        "failed_orders": sorted(failed_orders),
        "model": runtime_config.model,
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
