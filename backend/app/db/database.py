"""数据库引擎与会话。

SQLAlchemy 2.0 风格。SQLite 起步，ORM 抽象保证后续可平滑切到 PostgreSQL。
"""
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


# SQLite 需要 check_same_thread=False（FastAPI 多线程访问）
connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=False,  # 调试SQL可改 True
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """所有模型的基类。"""

    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：每请求一个 session，用完归还。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """建表：导入所有模型后调用。"""
    # 导入模型模块以触发注册（必须在 create_all 之前）
    from app.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_public_data_metadata()
    _migrate_policy_date_metadata()
    _migrate_crawl_source_items()
    _migrate_guided_lesson_progress()
    _migrate_wrong_answer_spaced_repetition()
    _secure_sqlite_permissions()


def _secure_sqlite_permissions() -> None:
    """SQLite 可能包含用户哈希和私有学习数据，仅允许运行账号读取。"""
    prefix = "sqlite:///"
    if not settings.DATABASE_URL.startswith(prefix):
        return
    database_path = Path(settings.DATABASE_URL[len(prefix):])
    for path in (
        database_path,
        Path(f"{database_path}-wal"),
        Path(f"{database_path}-shm"),
    ):
        if path.exists():
            try:
                path.chmod(0o600)
            except OSError:
                pass


def _migrate_public_data_metadata() -> None:
    """为已有 SQLite 开发库补充 PublicData 血缘字段。

    `create_all` 不会修改已存在的表，因此显式、幂等地执行 ADD COLUMN。
    只新增可空或有默认值的列，不重建、不删除用户数据。
    """
    inspector = inspect(engine)
    if "public_data" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("public_data")}
    additions = {
        "source_url": "VARCHAR(1000)",
        "provenance_level": "VARCHAR(30) DEFAULT 'synthetic'",
        "disclosure_scope": "VARCHAR(30) DEFAULT 'public'",
        "fetched_at": "VARCHAR(40)",
        "raw_asset_path": "VARCHAR(1000)",
        "raw_sha256": "VARCHAR(64)",
        "parser_version": "VARCHAR(50)",
        "quality_status": "VARCHAR(20) DEFAULT 'unknown'",
    }
    with engine.begin() as connection:
        for column, ddl_type in additions.items():
            if column not in existing:
                connection.execute(text(f"ALTER TABLE public_data ADD COLUMN {column} {ddl_type}"))


def _migrate_policy_date_metadata() -> None:
    """为已有政策表补充发布日期核验字段，不删除或重建数据。"""
    inspector = inspect(engine)
    if "policies" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("policies")}
    additions = {
        "publish_date_status": "VARCHAR(20) DEFAULT 'unverified'",
        "publish_date_evidence": "VARCHAR(100)",
        "publish_date_verified_at": "VARCHAR(40)",
    }
    with engine.begin() as connection:
        for column, ddl_type in additions.items():
            if column not in existing:
                connection.execute(text(f"ALTER TABLE policies ADD COLUMN {column} {ddl_type}"))


def _migrate_crawl_source_items() -> None:
    """为已创建的增量采集账本补充后续审计字段。"""
    inspector = inspect(engine)
    if "crawl_source_items" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("crawl_source_items")}
    additions = {
        "last_seen_at": "DATETIME",
    }
    with engine.begin() as connection:
        for column, ddl_type in additions.items():
            if column not in existing:
                connection.execute(text(
                    f"ALTER TABLE crawl_source_items ADD COLUMN {column} {ddl_type}"
                ))
        connection.execute(text(
            "UPDATE crawl_source_items "
            "SET last_seen_at = COALESCE(last_seen_at, first_seen_at, CURRENT_TIMESTAMP)"
        ))


def _migrate_guided_lesson_progress() -> None:
    """为已有引导课程进度补充逐题尝试记录，不影响既有完成状态。"""
    inspector = inspect(engine)
    if "guided_lesson_progress" not in inspector.get_table_names():
        return
    existing = {
        column["name"]
        for column in inspector.get_columns("guided_lesson_progress")
    }
    with engine.begin() as connection:
        if "check_attempts" not in existing:
            connection.execute(text(
                "ALTER TABLE guided_lesson_progress "
                "ADD COLUMN check_attempts TEXT DEFAULT '[]'"
            ))
        connection.execute(text(
            "UPDATE guided_lesson_progress "
            "SET check_attempts = '[]' "
            "WHERE check_attempts IS NULL OR check_attempts = ''"
        ))


def _migrate_wrong_answer_spaced_repetition() -> None:
    """为已有错题本补充间隔重复字段(next_review_at/review_interval)。

    create_all 不会给已存在的表加列，故显式幂等 ADD COLUMN。
    旧错题 next_review_at=NULL(立即到期)、review_interval 缺省 1。
    """
    inspector = inspect(engine)
    if "wrong_answers" not in inspector.get_table_names():
        return
    existing = {
        column["name"]
        for column in inspector.get_columns("wrong_answers")
    }
    with engine.begin() as connection:
        if "next_review_at" not in existing:
            connection.execute(text(
                "ALTER TABLE wrong_answers ADD COLUMN next_review_at DATETIME"
            ))
        if "review_interval" not in existing:
            connection.execute(text(
                "ALTER TABLE wrong_answers ADD COLUMN review_interval INTEGER DEFAULT 1"
            ))
