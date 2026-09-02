"""按登录用户隔离并加密保存的大模型 BYOK 配置。"""
from __future__ import annotations

import ipaddress
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import UserLLMConfig


ALLOWED_PROVIDERS = {"zhipu", "openai", "deepseek", "ollama", "none"}
PROVIDER_DEFAULTS = {
    "zhipu": ("https://open.bigmodel.cn/api/paas/v4", "glm-4-flash"),
    "deepseek": ("https://api.deepseek.com", "deepseek-chat"),
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
    "ollama": ("http://127.0.0.1:11434", "qwen2.5:7b"),
    "none": ("", ""),
}


@dataclass(frozen=True)
class LLMRuntimeConfig:
    provider: str
    base_url: str
    model: str
    api_key: str = ""
    enabled: bool = True

    @property
    def configured(self) -> bool:
        if not self.enabled or self.provider == "none":
            return False
        return self.provider == "ollama" or bool(self.api_key)


def _resolve_master_key(
    configured: Optional[str] = None,
    environment: Optional[str] = None,
    key_file: Optional[Path] = None,
) -> bytes:
    configured = settings.LLM_CONFIG_MASTER_KEY if configured is None else configured
    environment = settings.ENVIRONMENT if environment is None else environment
    key_file = settings.LLM_CONFIG_MASTER_KEY_FILE if key_file is None else key_file
    value = (configured or "").strip().encode()
    if value:
        try:
            Fernet(value)
        except (ValueError, TypeError) as exc:
            raise RuntimeError("LLM_CONFIG_MASTER_KEY 不是有效的 Fernet Key") from exc
        return value
    if (environment or "").strip().lower() in {"production", "prod"}:
        raise RuntimeError("生产环境必须配置 LLM_CONFIG_MASTER_KEY")

    key_file.parent.mkdir(parents=True, exist_ok=True)
    if key_file.is_file():
        existing = key_file.read_bytes().strip()
        try:
            Fernet(existing)
            key_file.chmod(0o600)
            return existing
        except (ValueError, TypeError):
            raise RuntimeError("本机 LLM 主密钥文件已损坏")
    generated = Fernet.generate_key()
    descriptor = os.open(str(key_file), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(generated)
    key_file.chmod(0o600)
    return generated


def _fernet() -> Fernet:
    return Fernet(_resolve_master_key())


def encrypt_api_key(api_key: str) -> str:
    return _fernet().encrypt(api_key.encode("utf-8")).decode("ascii")


def decrypt_api_key(ciphertext: Optional[str]) -> str:
    if not ciphertext:
        return ""
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeError) as exc:
        raise RuntimeError("当前用户的 AI Key 无法解密，请重新配置") from exc


def normalize_llm_config(provider: str, base_url: str, model: str) -> tuple[str, str, str]:
    provider = (provider or "none").strip().lower()
    if provider not in ALLOWED_PROVIDERS:
        raise ValueError("不支持的模型供应商")
    default_url, default_model = PROVIDER_DEFAULTS[provider]
    base_url = (base_url or default_url).strip().rstrip("/")
    model = (model or default_model).strip()
    if provider == "none":
        return provider, "", ""
    if not model or len(model) > 150 or not re.fullmatch(r"[\w./:\-]+", model):
        raise ValueError("模型名称无效")

    parsed = urlsplit(base_url)
    if parsed.username is not None or parsed.password is not None or not parsed.hostname:
        raise ValueError("模型接口地址无效")
    hostname = parsed.hostname.lower().rstrip(".")
    if provider == "ollama":
        if (
            parsed.scheme != "http"
            or hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.port not in {None, 11434}
        ):
            raise ValueError("本地 Ollama 只允许 127.0.0.1:11434")
    else:
        if parsed.scheme != "https":
            raise ValueError("云模型接口必须使用 HTTPS")
        if hostname == "localhost" or hostname.endswith(".local"):
            raise ValueError("云模型接口不能指向本机或内网")
        try:
            address = ipaddress.ip_address(hostname)
            if not address.is_global:
                raise ValueError("云模型接口不能指向本机或内网")
        except ValueError as exc:
            if "不能指向" in str(exc):
                raise
    clean_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))
    return provider, clean_url, model


def get_user_llm_row(db: Session, user_id: int) -> Optional[UserLLMConfig]:
    return db.query(UserLLMConfig).filter(UserLLMConfig.user_id == user_id).first()


def get_user_runtime_config(db: Session, user_id: int) -> Optional[LLMRuntimeConfig]:
    row = get_user_llm_row(db, user_id)
    if not row or not row.is_enabled:
        return None
    return LLMRuntimeConfig(
        provider=row.provider,
        base_url=row.base_url,
        model=row.model,
        api_key=decrypt_api_key(row.encrypted_api_key),
        enabled=row.is_enabled,
    )


def save_user_llm_config(
    db: Session,
    user_id: int,
    *,
    provider: str,
    base_url: str,
    model: str,
    api_key: str = "",
) -> UserLLMConfig:
    provider, base_url, model = normalize_llm_config(provider, base_url, model)
    row = get_user_llm_row(db, user_id) or UserLLMConfig(user_id=user_id)
    if api_key:
        if len(api_key) > 4096 or any(ch in api_key for ch in "\r\n"):
            raise ValueError("API Key 格式无效")
        row.encrypted_api_key = encrypt_api_key(api_key.strip())
        row.api_key_hint = api_key.strip()[-4:]
    if provider not in {"ollama", "none"} and not row.encrypted_api_key:
        raise ValueError("云模型必须配置当前用户自己的 API Key")
    row.provider = provider
    row.base_url = base_url
    row.model = model
    row.is_enabled = provider != "none"
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delete_user_llm_config(db: Session, user_id: int) -> None:
    row = get_user_llm_row(db, user_id)
    if row:
        db.delete(row)
        db.commit()


def config_status(row: Optional[UserLLMConfig]) -> dict:
    return {
        "provider": row.provider if row else "none",
        "base_url": row.base_url if row else "",
        "model": row.model if row else "",
        "api_key_masked": f"***{row.api_key_hint}" if row and row.api_key_hint else "",
        "api_key_set": bool(row and row.encrypted_api_key),
        "enabled": bool(row and row.is_enabled),
        "scope": "current_user",
    }
