#!/usr/bin/env python3
"""幂等灌入主动引导课即时检查题到 questions 表（source_type='guided'）。

把 GUIDED_UNITS 里每课的 checks 灌入真实题库，使其：
- 进入共享组卷池（/learn/quiz 自动可选）
- 答错时进错题本（WrongAnswer，由 study/router 的 check 流程写入）

幂等：按 stem_hash 判重，已存在则跳过。
难度映射（按 unit order）：1-3→1(易)，4-6→2(中)，7-8→3(难)。

调用：python -m scripts.seed_guided_questions
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select  # noqa: E402

from app.db.database import SessionLocal, init_db  # noqa: E402
from app.db.models import KnowledgePoint, Question  # noqa: E402
from app.study.guided import GUIDED_UNITS  # noqa: E402


def _stem_hash(stem: str) -> str:
    return hashlib.sha256(stem.strip().encode("utf-8")).hexdigest()


def _difficulty_for_order(order: int) -> int:
    """按 unit order 映射难度：1-3→1, 4-6→2, 7-8→3。"""
    if order <= 3:
        return 1
    if order <= 6:
        return 2
    return 3


def _letter_for_index(index: int) -> str:
    """0→A, 1→B ..."""
    return chr(ord("A") + index)


def main() -> None:
    init_db()
    db = SessionLocal()
    seeded = 0
    skipped = 0
    kp_missing: list[str] = []
    try:
        # 预取全部知识点 code→id，避免逐题查询
        kps = {
            kp.code: kp.id
            for kp in db.execute(select(KnowledgePoint)).scalars().all()
            if kp.code
        }
        for unit in GUIDED_UNITS:
            kp_code = unit.get("knowledge_code")
            kp_id = kps.get(kp_code) if kp_code else None
            if kp_id is None:
                kp_missing.append(f"{unit['code']}→{kp_code!r}")
                continue
            unit_code = unit["code"]
            difficulty = _difficulty_for_order(int(unit["order"]))
            for check in unit.get("checks") or []:
                stem = check["question"]
                options = check["options"]
                answer_index = int(check["answer"])
                sh = _stem_hash(stem)
                exists = db.execute(
                    select(Question).where(Question.stem_hash == sh)
                ).scalars().first()
                if exists:
                    skipped += 1
                    continue
                options_json = json.dumps(
                    [
                        {
                            "key": _letter_for_index(i),
                            "text": opt,
                            "is_correct": i == answer_index,
                        }
                        for i, opt in enumerate(options)
                    ],
                    ensure_ascii=False,
                )
                db.add(
                    Question(
                        type="single",
                        stem=stem,
                        options=options_json,
                        answer=_letter_for_index(answer_index),
                        analysis=check.get("explanation"),
                        knowledge_point_id=kp_id,
                        source=unit_code,
                        source_type="guided",
                        is_ai_generated=False,
                        is_active=True,
                        difficulty=difficulty,
                        stem_hash=sh,
                    )
                )
                seeded += 1
        db.commit()
        total = db.execute(
            select(Question).where(Question.source_type == "guided")
        ).scalars().all()
        print(f"seeded {seeded} guided questions, skipped {skipped} (already present)")
        if kp_missing:
            print(f"WARNING: missing knowledge points, skipped units: {kp_missing}")
        print(f"total guided questions in DB: {len(total)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
