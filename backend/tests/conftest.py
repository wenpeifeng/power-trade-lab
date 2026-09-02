"""测试共享夹具 —— 隔离数据库 + 已登录 TestClient。

本项目此前无 conftest.py，所有测试均为单元式。本文件为 /asset 权限边界
测试新建，遵循项目既有风格（自建指向隔离 SQLite 文件测试引擎，通过依赖
注入覆盖 get_db 把请求会话指向测试引擎，不污染开发库，也不修改全局环境变量）。

关键点：早期实现曾在模块导入时 `os.environ["DATABASE_URL"] = ...`，这会让
测试库 URL 泄漏到整个 pytest 会话的所有测试。现改为直接构造测试引擎，
不触碰 os.environ / settings / app.db.database 的模块级 engine。
"""
import os

os.environ.setdefault("ENVIRONMENT", "development")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.common.auth import create_access_token, hash_password
from app.config import settings
from app.db import models  # noqa: F401  注册所有模型
from app.db.database import Base, get_db
from app.db.models import User
from app.main import app

# ---- 隔离测试库 ----
# 直接用测试库路径构造引擎，不依赖 os.environ.DATABASE_URL，
# 因此 app.db.database.engine 仍绑开发库、settings 不被污染、env 不外泄。
_TEST_DB_PATH = "/tmp/asset_guard_test.db"
_TEST_DB_URL = f"sqlite:///{_TEST_DB_PATH}"

if os.path.exists(_TEST_DB_PATH):
    os.remove(_TEST_DB_PATH)

_test_engine = create_engine(
    _TEST_DB_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)
Base.metadata.create_all(bind=_test_engine)

_TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=_test_engine
)


def _override_get_db():
    db = _TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture()
def db_session():
    """每用例一个会话，用完归还。

    用例间清空所有表，避免上轮 fixture 写入的用户名触发 UNIQUE 冲突
    （隔离库在进程内复用同一文件）。
    """
    db = _TestingSessionLocal()
    for tbl in reversed(Base.metadata.sorted_tables):
        db.execute(tbl.delete())
    db.commit()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client():
    """未登录的匿名 TestClient。

    不用 ``with TestClient(app)`` 以避免触发 lifespan（会跑种子灌入、爬虫
    调度器、embedding 预热），表结构已由上方 create_all 建好。
    """
    yield TestClient(app)


def _make_user(db, username: str, role: str) -> User:
    user = User(
        username=username,
        hashed_password=hash_password("safe-pass-2026"),
        display_name=username,
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def auth_client_normal(db_session):
    """已登录的普通用户 TestClient（role=user）。"""
    user = _make_user(db_session, "guard_normal", "user")
    token = create_access_token(user.id, user.username, user.role)
    c = TestClient(app)
    c.cookies.set(settings.AUTH_COOKIE_NAME, token)
    yield c


@pytest.fixture()
def auth_client_admin(db_session):
    """已登录的管理员 TestClient（role=admin）。"""
    user = _make_user(db_session, "guard_admin", "admin")
    token = create_access_token(user.id, user.username, user.role)
    c = TestClient(app)
    c.cookies.set(settings.AUTH_COOKIE_NAME, token)
    yield c
