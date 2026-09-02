#!/usr/bin/env python3
"""幂等灌入知识点前置关系（knowledge_point_prerequisites）。

X ← P 表示 P 是 X 的前置知识点（行: kp_id=X, prereq_kp_id=P）。
可重复运行：删除旧边后按规范集合重新插入，输出本次灌入的边数。
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select  # noqa: E402

from app.db.database import SessionLocal, init_db  # noqa: E402
from app.db.models import (  # noqa: E402
    KnowledgePoint,
    KnowledgePointPrerequisite,
)


# (kp_code, prereq_code) —— kp_id=X, prereq_kp_id=P
EDGES: list[tuple[str, str]] = [
    ("mid_long_term", "industry"),      # 先懂行业认知再学中长期
    ("spot", "mid_long_term"),          # 先懂中长期再学现货
    ("spot", "industry"),
    ("ancillary", "spot"),              # 辅助服务依赖现货运行
    ("retail", "wholesale"),            # 零售依赖批发
    ("retail", "mid_long_term"),
    ("green", "industry"),
    ("settlement", "mid_long_term"),
    ("settlement", "spot"),
    ("wholesale", "industry"),
]


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        # code -> KnowledgePoint
        codes = {c for edge in EDGES for c in edge}
        kps = {
            kp.code: kp
            for kp in db.execute(
                select(KnowledgePoint).where(KnowledgePoint.code.in_(codes))
            ).scalars().all()
            if kp.code
        }
        missing = codes - kps.keys()
        if missing:
            raise SystemExit(f"缺少知识点，无法灌入前置关系: {sorted(missing)}")

        # 幂等：先清空，再插入（行数小且固定，简单可靠）
        db.query(KnowledgePointPrerequisite).delete()
        db.commit()

        for kp_code, prereq_code in EDGES:
            db.add(KnowledgePointPrerequisite(
                kp_id=kps[kp_code].id,
                prereq_kp_id=kps[prereq_code].id,
            ))
        db.commit()

        count = db.execute(
            select(KnowledgePointPrerequisite)
        ).scalars().all()
        print(f"seeded {len(count)} prerequisite edges")
    finally:
        db.close()


if __name__ == "__main__":
    main()
