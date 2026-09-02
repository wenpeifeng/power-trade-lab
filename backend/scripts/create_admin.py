#!/usr/bin/env python3
"""交互式创建或提升管理员；不提供默认账号和默认密码。"""
from __future__ import annotations

import getpass
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select  # noqa: E402

from app.auth.router import _validate_new_password  # noqa: E402
from app.common.auth import hash_password  # noqa: E402
from app.db.database import SessionLocal, init_db  # noqa: E402
from app.db.models import TradeAccount, User, UserProfile  # noqa: E402


def main() -> None:
    init_db()
    username = input("管理员用户名: ").strip()
    if not 3 <= len(username) <= 32:
        raise SystemExit("用户名长度应为3到32个字符")

    password = getpass.getpass("管理员密码（至少8字符，不回显）: ")
    confirmation = getpass.getpass("再次输入密码: ")
    if password != confirmation:
        raise SystemExit("两次密码不一致")
    try:
        _validate_new_password(password, username)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    db = SessionLocal()
    try:
        user = db.execute(select(User).where(User.username == username)).scalars().first()
        if user:
            answer = input("用户已存在。输入 PROMOTE 确认提升为管理员并重置密码: ").strip()
            if answer != "PROMOTE":
                raise SystemExit("已取消，未修改任何数据")
            user.role = "admin"
            user.hashed_password = hash_password(password)
            user.is_active = True
        else:
            user = User(
                username=username,
                display_name=username,
                hashed_password=hash_password(password),
                role="admin",
                is_active=True,
            )
            db.add(user)
            db.flush()

        if not db.execute(
            select(TradeAccount).where(TradeAccount.user_id == user.id)
        ).scalars().first():
            db.add(TradeAccount(user_id=user.id, balance=1_000_000))
        if not db.execute(
            select(UserProfile).where(UserProfile.user_id == user.id)
        ).scalars().first():
            db.add(UserProfile(user_id=user.id, level="L1", home_province="浙江"))
        db.commit()
    finally:
        db.close()
    print(f"管理员 {username} 已配置；密码未写入日志。")


if __name__ == "__main__":
    main()
