"""认证授权模块 —— JWT 令牌 + bcrypt 密码哈希 + 依赖注入。

核心能力：
1. 密码哈希/校验（passlib[bcrypt]）
2. JWT 令牌签发/验证（PyJWT）
3. FastAPI 依赖注入 get_current_user（从 Authorization header 解 JWT）

用法：
    from app.common.auth import get_current_user, require_admin

    @router.get("/me")
    def me(current_user: User = Depends(get_current_user)):
        return current_user
"""
import os
import secrets
from datetime import timedelta
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from jwt import InvalidTokenError
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import get_db
from app.db.models import User, now_utc

# ============ 配置 ============

def _resolve_jwt_secret(
    configured: Optional[str] = None,
    environment: Optional[str] = None,
    secret_file=None,
) -> str:
    """解析 JWT 签名密钥，不允许回退到代码仓库中的固定默认值。"""
    configured = settings.JWT_SECRET_KEY if configured is None else configured
    environment = settings.ENVIRONMENT if environment is None else environment
    secret_file = settings.JWT_SECRET_FILE if secret_file is None else secret_file

    configured = (configured or "").strip()
    if configured:
        if len(configured) < 32:
            raise RuntimeError("JWT_SECRET_KEY 至少需要 32 个字符")
        return configured

    if (environment or "").strip().lower() in {"production", "prod"}:
        raise RuntimeError("生产环境必须配置 JWT_SECRET_KEY，禁止使用默认密钥")

    secret_file.parent.mkdir(parents=True, exist_ok=True)
    if secret_file.is_file():
        existing = secret_file.read_text(encoding="utf-8").strip()
        if len(existing) >= 32:
            try:
                secret_file.chmod(0o600)
            except OSError:
                pass
            return existing

    generated = secrets.token_urlsafe(48)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    descriptor = os.open(str(secret_file), flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(generated)
    try:
        secret_file.chmod(0o600)
    except OSError:
        pass
    return generated


SECRET_KEY = _resolve_jwt_secret()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = max(1, settings.JWT_ACCESS_TOKEN_HOURS)

# 密码哈希
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 Bearer（从 Authorization: Bearer <token> 取令牌）
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


# ============ 密码工具 ============

def hash_password(password: str) -> str:
    """密码哈希。"""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """校验密码。"""
    return pwd_context.verify(plain, hashed)


# ============ JWT 工具 ============

def create_access_token(user_id: int, username: str, role: str = "user") -> str:
    """签发 JWT 令牌。"""
    expire = now_utc() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """解码 JWT，失败返回 None。"""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except InvalidTokenError:
        return None


# ============ FastAPI 依赖 ============

def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """从 JWT 解出当前登录用户。

    所有需要登录的路由加 current_user = Depends(get_current_user)。
    未登录或令牌无效返回 401。
    """
    # 兜底：如果没传 token，查是否有本地单用户模式（兼容旧前端）
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="未登录或令牌已过期",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = token or request.cookies.get(settings.AUTH_COOKIE_NAME)
    if not token:
        raise credentials_exception

    payload = decode_token(token)
    if payload is None:
        raise credentials_exception

    user_id = int(payload.get("sub", 0))
    if not user_id:
        raise credentials_exception

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise credentials_exception

    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """要求管理员权限。"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return current_user


def get_current_user_optional(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """可选登录：已登录返回 User，未登录返回 None（用于公开页面个性化）。"""
    token = token or request.cookies.get(settings.AUTH_COOKIE_NAME)
    if not token:
        return None
    payload = decode_token(token)
    if payload is None:
        return None
    user_id = int(payload.get("sub", 0))
    return db.get(User, user_id) if user_id else None
