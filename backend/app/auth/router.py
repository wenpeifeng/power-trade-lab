"""认证路由 —— 注册/登录/获取用户信息。

/api/auth/register  注册
/api/auth/login     登录（返回JWT）
/api/auth/me        获取当前用户
"""
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.common.rate_limit import SlidingWindowLimiter
from app.config import settings
from app.db.database import get_db
from app.db.models import TradeAccount, User, UserProfile, now_utc

router = APIRouter(prefix="/auth", tags=["用户认证"])

_login_limiter = SlidingWindowLimiter(
    settings.LOGIN_MAX_FAILURES,
    settings.LOGIN_FAILURE_WINDOW_MINUTES * 60,
)
_register_limiter = SlidingWindowLimiter(
    settings.REGISTER_MAX_ATTEMPTS,
    settings.REGISTER_WINDOW_MINUTES * 60,
)
_common_passwords = {
    "123456", "12345678", "123456789", "password", "password123",
    "admin", "admin123", "qwerty", "qwerty123", "11111111",
}


def _client_ip(request: Request) -> str:
    """只信任直连地址，避免攻击者伪造 X-Forwarded-For 绕过限流。"""
    return request.client.host if request.client else "unknown"


def _validate_new_password(password: str, username: str = "") -> str:
    if len(password) < 8:
        raise ValueError("密码至少8个字符")
    if len(password.encode("utf-8")) > 72:
        raise ValueError("密码不能超过72个字节")
    lowered = password.casefold()
    if lowered in _common_passwords or (username and lowered == username.casefold()):
        raise ValueError("密码过于简单，请更换更安全的密码")
    return password


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.AUTH_COOKIE_NAME,
        value=token,
        max_age=max(1, settings.JWT_ACCESS_TOKEN_HOURS) * 3600,
        httponly=True,
        secure=settings.is_production,
        samesite="strict",
        path="/api",
    )


class RegisterReq(BaseModel):
    username: str
    password: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    home_province: Optional[str] = None
    target_level: Optional[str] = None

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        value = value.strip()
        if not 3 <= len(value) <= 32:
            raise ValueError("用户名长度应为3到32个字符")
        if not re.fullmatch(r"[\w\-\u4e00-\u9fff]+", value, flags=re.UNICODE):
            raise ValueError("用户名只能包含中英文、数字、下划线和短横线")
        return value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validate_new_password(value)

    @field_validator("display_name", "email", "home_province", "target_level")
    @classmethod
    def trim_optional(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None


class LoginReq(BaseModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def trim_username(cls, value: str) -> str:
        return value.strip()[:64]

    @field_validator("password")
    @classmethod
    def bound_password(cls, value: str) -> str:
        if not value or len(value.encode("utf-8")) > 72:
            raise ValueError("用户名或密码错误")
        return value


class ChangePasswordReq(BaseModel):
    current_password: str
    new_password: str

    @field_validator("current_password")
    @classmethod
    def validate_current(cls, value: str) -> str:
        if not value or len(value.encode("utf-8")) > 72:
            raise ValueError("当前密码不正确")
        return value


@router.post("/register", summary="注册")
def register(
    req: RegisterReq,
    request: Request,
    response: Response,
    include_token: bool = False,
    db: Session = Depends(get_db),
):
    """注册新用户。注册成功自动创建模拟交易账户和学习档案。"""
    rate_key = f"register:{_client_ip(request)}"
    state = _register_limiter.check(rate_key)
    if not state.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="注册请求过于频繁，请稍后再试",
            headers={"Retry-After": str(state.retry_after)},
        )
    _register_limiter.record(rate_key)

    try:
        _validate_new_password(req.password, req.username)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # 查重
    exists = db.execute(select(User).where(User.username == req.username)).scalars().first()
    if exists:
        raise HTTPException(status_code=400, detail="用户名已存在")

    # 创建用户
    user = User(
        username=req.username,
        hashed_password=hash_password(req.password),
        display_name=req.display_name or req.username,
        email=req.email,
        home_province=req.home_province,
        target_level=req.target_level,
        role="user",
    )
    db.add(user)
    db.flush()

    # 自动初始化：交易账户（模拟资金100万）
    db.add(TradeAccount(user_id=user.id, balance=1000000))
    # 自动初始化：学习档案
    db.add(UserProfile(user_id=user.id, level="L1", home_province=req.home_province or "浙江"))

    db.commit()
    db.refresh(user)

    # 签发令牌
    token = create_access_token(user.id, user.username, user.role)
    _set_session_cookie(response, token)
    result = {
        "ok": True,
        "user": _user_info(user),
    }
    if include_token:
        result["token"] = token
    return result


@router.post("/login", summary="登录")
def login(
    req: LoginReq,
    request: Request,
    response: Response,
    include_token: bool = False,
    db: Session = Depends(get_db),
):
    """登录，返回 JWT 令牌。"""
    rate_key = f"login:{_client_ip(request)}:{req.username.casefold()}"
    state = _login_limiter.check(rate_key)
    if not state.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="登录失败次数过多，请稍后再试",
            headers={"Retry-After": str(state.retry_after)},
        )

    user = db.execute(select(User).where(User.username == req.username)).scalars().first()
    if not user or not verify_password(req.password, user.hashed_password):
        _login_limiter.record(rate_key)
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not user.is_active:
        _login_limiter.record(rate_key)
        raise HTTPException(status_code=403, detail="账号已被禁用")

    _login_limiter.clear(rate_key)

    # 更新最后登录
    user.last_login_at = now_utc()
    db.commit()

    token = create_access_token(user.id, user.username, user.role)
    _set_session_cookie(response, token)
    result = {
        "ok": True,
        "user": _user_info(user),
    }
    if include_token:
        result["token"] = token
    return result


@router.get("/me", summary="获取当前用户")
def get_me(current_user: User = Depends(get_current_user)):
    """获取当前登录用户信息（需携带JWT）。"""
    return _user_info(current_user)


@router.post("/logout", summary="退出当前浏览器会话")
def logout(response: Response):
    response.delete_cookie(
        key=settings.AUTH_COOKIE_NAME,
        path="/api",
        httponly=True,
        secure=settings.is_production,
        samesite="strict",
    )
    return {"ok": True}


@router.post("/change-password", summary="修改当前账号密码")
def change_password(
    req: ChangePasswordReq,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(req.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="当前密码不正确")
    try:
        _validate_new_password(req.new_password, current_user.username)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if verify_password(req.new_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="新密码不能与当前密码相同")
    current_user.hashed_password = hash_password(req.new_password)
    db.commit()
    return {"ok": True, "message": "密码修改成功，请妥善保管新密码"}


def _user_info(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "role": user.role,
        "home_province": user.home_province,
        "target_level": user.target_level,
        "avatar": user.avatar,
    }
