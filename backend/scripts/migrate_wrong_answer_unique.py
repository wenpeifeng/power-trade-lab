#!/usr/bin/env python3
"""为 wrong_answers 表补加 (user_id, question_id) 唯一约束。

之前错题去重只靠 learn/router.py:submit_answer 的 query-before-insert，
并发提交时仍可能产生重复行。本脚本在 SQLite 上以「建新表→拷贝→删旧→改名」
的方式加上真实 UNIQUE 约束（SQLite 无法 ALTER TABLE ADD CONSTRAINT）。

步骤：
1. 幂等检查：若 uq_wrong_answer_user_question 唯一索引已存在，直接 no-op。
2. 去重：按 (user_id, question_id) 分组，保留 updated_at 最新（并列时取 id 最大）
   的一行，其余删除。
3. 重建表：create wrong_answers_new(含唯一约束) → 拷贝去重后的行 →
   drop wrong_answers → rename wrong_answers_new → wrong_answers。
4. 打印 before/after 行数。

可重复运行，对已有唯一索引的库无副作用。
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import text  # noqa: E402

from app.db.database import engine  # noqa: E402

TABLE = "wrong_answers"
NEW_TABLE = "wrong_answers_new"
INDEX_NAME = "uq_wrong_answer_user_question"

# 与 models.py WrongAnswer 完全一致的字段集（含 TimestampMixin 两列）
NEW_TABLE_DDL = f"""
CREATE TABLE {NEW_TABLE} (
    id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    question_id INTEGER NOT NULL,
    user_answer VARCHAR(200) NOT NULL,
    reviewed BOOLEAN NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (question_id) REFERENCES questions (id),
    CONSTRAINT {INDEX_NAME} UNIQUE (user_id, question_id)
)
"""


def _unique_constraint_present(conn) -> bool:
    """判断 (user_id, question_id) 上的唯一约束是否已落地。

    SQLite 的表级 CONSTRAINT name UNIQUE(...) 不会保留 name，而是生成
    一个名为 sqlite_autoindex_<table>_<n> 的自动唯一索引。所以这里不能按
    名字找，而要扫 pragma_index_list 里 origin='u' 的项，再用
    pragma_index_info 确认它覆盖的列正好是 user_id、question_id。
    """
    idx_rows = conn.execute(
        text("SELECT name, origin FROM pragma_index_list(:t)"),
        {"t": TABLE},
    ).fetchall()
    for idx_name, origin in idx_rows:
        if origin != "u":
            continue
        cols = {
            r[2]
            for r in conn.execute(
                text("SELECT * FROM pragma_index_info(:i)"), {"i": idx_name}
            ).fetchall()
        }
        if cols == {"user_id", "question_id"}:
            return True
    return False


def main() -> None:
    with engine.begin() as conn:
        before = conn.execute(text(f"SELECT COUNT(*) FROM {TABLE}")).scalar() or 0

        if _unique_constraint_present(conn):
            print(f"唯一约束 {INDEX_NAME} 已存在，跳过迁移。")
            print(f"rows(before=after): {before}")
            return

        # 1. 去重：保留每组 (user_id, question_id) 中 updated_at 最新、id 最大的一行
        dups = conn.execute(
            text(
                f"""
                SELECT user_id, question_id, COUNT(*) c
                FROM {TABLE}
                GROUP BY user_id, question_id
                HAVING c > 1
                """
            )
        ).fetchall()
        dup_groups = len(dups)
        if dup_groups:
            # 删除非「最新」行：用窗口函数挑出 keep=1 的，删 keep=0 的
            conn.execute(
                text(
                    f"""
                    DELETE FROM {TABLE}
                    WHERE id NOT IN (
                        SELECT id FROM (
                            SELECT id,
                                ROW_NUMBER() OVER (
                                    PARTITION BY user_id, question_id
                                    ORDER BY updated_at DESC, id DESC
                                ) AS rn
                            FROM {TABLE}
                        ) WHERE rn = 1
                    )
                    """
                )
            )
        after_dedup = conn.execute(text(f"SELECT COUNT(*) FROM {TABLE}")).scalar() or 0

        # 2. 建新表（带唯一约束）
        conn.execute(text(NEW_TABLE_DDL))

        # 3. 拷贝去重后的全部行
        conn.execute(
            text(
                f"""
                INSERT INTO {NEW_TABLE}
                    (id, user_id, question_id, user_answer, reviewed, created_at, updated_at)
                SELECT id, user_id, question_id, user_answer, reviewed, created_at, updated_at
                FROM {TABLE}
                """
            )
        )

        copied = conn.execute(text(f"SELECT COUNT(*) FROM {NEW_TABLE}")).scalar() or 0

        # 4. 删旧表、改名
        conn.execute(text(f"DROP TABLE {TABLE}"))
        conn.execute(
            text(
                f"ALTER TABLE {NEW_TABLE} RENAME TO {TABLE}"
            )
        )

        # 5. 重建普通索引（旧表的 ix_wrong_answers_user_id /
        #    ix_wrong_answers_question_id 随 DROP 一起没了）
        conn.execute(
            text(
                f"CREATE INDEX ix_{TABLE}_user_id ON {TABLE} (user_id)"
            )
        )
        conn.execute(
            text(
                f"CREATE INDEX ix_{TABLE}_question_id ON {TABLE} (question_id)"
            )
        )

        after = conn.execute(text(f"SELECT COUNT(*) FROM {TABLE}")).scalar() or 0

        # 校验唯一索引存在（覆盖 user_id+question_id 的 origin=u 索引）
        present = _unique_constraint_present(conn)

        print(f"迁移完成：{TABLE}")
        print(f"  before rows:          {before}")
        print(f"  dup groups found:     {dup_groups}")
        print(f"  rows after dedup:     {after_dedup}")
        print(f"  rows copied to new:   {copied}")
        print(f"  after rows:           {after}")
        print(f"  unique index present: {present} ({INDEX_NAME})")


if __name__ == "__main__":
    main()
