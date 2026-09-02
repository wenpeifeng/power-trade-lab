#!/usr/bin/env python3
"""交互式配置和风天气，密钥不回显。

运行：
    backend/.venv/bin/python backend/scripts/configure_qweather.py

脚本只修改 backend/.env 中 QWEATHER_* 配置，并将文件权限设为 600。
"""
from __future__ import annotations

import getpass
import os
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = BACKEND_ROOT / ".env"

QWEATHER_KEYS = {
    "QWEATHER_ENABLED",
    "QWEATHER_API_HOST",
    "QWEATHER_AUTH_TYPE",
    "QWEATHER_API_KEY",
    "QWEATHER_PROJECT_ID",
    "QWEATHER_CREDENTIAL_ID",
    "QWEATHER_PRIVATE_KEY_PATH",
    "QWEATHER_FORECAST_HOURS",
}


def normalize_host(value: str) -> str:
    host = value.strip().replace("https://", "").replace("http://", "").strip("/")
    if not host or "/" in host or "." not in host:
        raise ValueError("API Host 应是控制台分配的域名，不含 https:// 和路径")
    if host in {"api.qweather.com", "devapi.qweather.com", "geoapi.qweather.com"}:
        raise ValueError("请使用控制台分配的专属 API Host，不要使用旧公共域名")
    return host


def read_existing() -> tuple[list[str], dict[str, str]]:
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    values: dict[str, str] = {}
    kept: list[str] = []
    for line in lines:
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith("#"):
            key, value = stripped.split("=", 1)
            if key in QWEATHER_KEYS:
                values[key] = value
                continue
        kept.append(line)
    return kept, values


def prompt(label: str, default: str = "", secret: bool = False) -> str:
    if secret and default:
        suffix = " [已配置，回车保留]"
    else:
        suffix = f" [{default}]" if default else ""
    reader = getpass.getpass if secret else input
    value = reader(f"{label}{suffix}: ").strip()
    return value or default


def main() -> None:
    kept, existing = read_existing()
    print("配置和风天气。真实密钥不会显示，也不会写入日志。")

    host = normalize_host(prompt("API Host", existing.get("QWEATHER_API_HOST", "")))
    auth_type = prompt(
        "认证方式 api_key/jwt",
        existing.get("QWEATHER_AUTH_TYPE", "api_key"),
    ).lower()
    if auth_type not in {"api_key", "jwt"}:
        raise SystemExit("认证方式只能是 api_key 或 jwt")

    values = {
        "QWEATHER_ENABLED": "true",
        "QWEATHER_API_HOST": host,
        "QWEATHER_AUTH_TYPE": auth_type,
        "QWEATHER_API_KEY": "",
        "QWEATHER_PROJECT_ID": "",
        "QWEATHER_CREDENTIAL_ID": "",
        "QWEATHER_PRIVATE_KEY_PATH": "",
        "QWEATHER_FORECAST_HOURS": prompt(
            "逐小时预报范围 24h/72h/168h",
            existing.get("QWEATHER_FORECAST_HOURS", "24h"),
        ),
    }
    if values["QWEATHER_FORECAST_HOURS"] not in {"24h", "72h", "168h"}:
        raise SystemExit("逐小时预报范围只能是 24h、72h 或 168h")

    if auth_type == "api_key":
        values["QWEATHER_API_KEY"] = prompt(
            "API KEY（输入不回显）",
            existing.get("QWEATHER_API_KEY", ""),
            secret=True,
        )
        if not values["QWEATHER_API_KEY"]:
            raise SystemExit("API KEY 不能为空")
    else:
        values["QWEATHER_PROJECT_ID"] = prompt(
            "项目ID",
            existing.get("QWEATHER_PROJECT_ID", ""),
        )
        values["QWEATHER_CREDENTIAL_ID"] = prompt(
            "凭据ID",
            existing.get("QWEATHER_CREDENTIAL_ID", ""),
        )
        private_path = Path(prompt(
            "Ed25519 私钥文件路径",
            existing.get("QWEATHER_PRIVATE_KEY_PATH", ""),
        )).expanduser().resolve()
        if not private_path.is_file():
            raise SystemExit("私钥文件不存在")
        values["QWEATHER_PRIVATE_KEY_PATH"] = str(private_path)
        if not values["QWEATHER_PROJECT_ID"] or not values["QWEATHER_CREDENTIAL_ID"]:
            raise SystemExit("项目ID和凭据ID不能为空")

    content = list(kept)
    if content and content[-1] != "":
        content.append("")
    content.extend([
        "# QWeather connector (managed by scripts/configure_qweather.py)",
        *[f"{key}={values[key]}" for key in (
            "QWEATHER_ENABLED",
            "QWEATHER_API_HOST",
            "QWEATHER_AUTH_TYPE",
            "QWEATHER_API_KEY",
            "QWEATHER_PROJECT_ID",
            "QWEATHER_CREDENTIAL_ID",
            "QWEATHER_PRIVATE_KEY_PATH",
            "QWEATHER_FORECAST_HOURS",
        )],
    ])
    ENV_FILE.write_text("\n".join(content).rstrip() + "\n", encoding="utf-8")
    os.chmod(ENV_FILE, 0o600)
    print(f"配置已安全写入 {ENV_FILE}")
    print("连接器已显式开启。请重启后端，再在数据资产中心点击“测试连接”。")


if __name__ == "__main__":
    main()
