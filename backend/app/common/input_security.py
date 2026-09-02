"""外部 URL 与上传文件的统一安全边界。"""
from __future__ import annotations

import ipaddress
import io
import re
import socket
import zipfile
from pathlib import Path
from typing import Mapping, Optional
from urllib.parse import urljoin, urlsplit

import httpx
from fastapi import UploadFile

from app.config import settings


class UnsafeInputError(ValueError):
    """输入可能触达内网、危险协议或越过资源上限。"""


_BLOCKED_HEADERS = {
    "host",
    "proxy-authorization",
    "proxy-connection",
    "forwarded",
    "x-forwarded-for",
    "x-forwarded-host",
    "x-forwarded-proto",
    "x-real-ip",
    "connection",
    "transfer-encoding",
}
_REDIRECT_CODES = {301, 302, 303, 307, 308}


def _private_host_allowlist() -> set[str]:
    return {
        item.strip().lower().rstrip(".")
        for item in settings.OUTBOUND_PRIVATE_HOST_ALLOWLIST.split(",")
        if item.strip()
    }


def validate_outbound_url(url: str) -> str:
    """只允许无用户凭证、可解析到公网地址的 HTTP(S) URL。"""
    value = (url or "").strip()
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise UnsafeInputError("URL 格式无效") from exc

    if parsed.scheme.lower() not in {"http", "https"}:
        raise UnsafeInputError("仅允许 http 或 https URL")
    if not parsed.hostname:
        raise UnsafeInputError("URL 缺少主机名")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeInputError("URL 不允许携带用户名或密码")

    hostname = parsed.hostname.lower().rstrip(".")
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        raise UnsafeInputError("禁止访问本机或局域网地址")

    allow_private = hostname in _private_host_allowlist()
    try:
        addresses = {
            item[4][0].split("%")[0]
            for item in socket.getaddrinfo(hostname, parsed.port, type=socket.SOCK_STREAM)
        }
    except (socket.gaierror, OSError) as exc:
        raise UnsafeInputError("URL 主机无法解析") from exc

    if not addresses:
        raise UnsafeInputError("URL 主机没有可用地址")
    if not allow_private:
        for address in addresses:
            try:
                if not ipaddress.ip_address(address).is_global:
                    raise UnsafeInputError("禁止访问本机、内网或保留地址")
            except ValueError as exc:
                raise UnsafeInputError("URL 解析到了无效地址") from exc
    return value


def sanitize_outbound_headers(headers: Optional[Mapping]) -> dict[str, str]:
    """移除可改写目标、代理或来源身份的危险请求头。"""
    result: dict[str, str] = {}
    for raw_key, raw_value in (headers or {}).items():
        key = str(raw_key).strip()
        value = str(raw_value).strip()
        if not key or key.lower() in _BLOCKED_HEADERS:
            continue
        if "\r" in key or "\n" in key or "\r" in value or "\n" in value:
            raise UnsafeInputError("请求头中不允许换行符")
        if len(key) > 128 or len(value) > 8192:
            raise UnsafeInputError("请求头过长")
        result[key] = value
    return result


def _origin(url: str) -> tuple[str, str, Optional[int]]:
    parsed = urlsplit(url)
    return parsed.scheme.lower(), (parsed.hostname or "").lower(), parsed.port


def safe_http_request(
    method: str,
    url: str,
    *,
    headers: Optional[Mapping] = None,
    params: Optional[Mapping] = None,
    data=None,
    timeout: float = 30,
    max_redirects: int = 5,
    max_bytes: Optional[int] = None,
) -> httpx.Response:
    """逐跳校验重定向并限制响应体大小的 HTTP 请求。"""
    request_method = (method or "GET").upper()
    if request_method not in {"GET", "POST"}:
        raise UnsafeInputError("数据接入仅允许 GET 或 POST")
    current_url = validate_outbound_url(url)
    current_headers = sanitize_outbound_headers(headers)
    limit = max_bytes or max(1, settings.OUTBOUND_FETCH_MAX_MB) * 1024 * 1024

    with httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False) as client:
        for redirect_count in range(max_redirects + 1):
            with client.stream(
                request_method,
                current_url,
                headers=current_headers,
                params=params if redirect_count == 0 else None,
                content=data if request_method == "POST" else None,
            ) as upstream:
                if upstream.status_code in _REDIRECT_CODES and upstream.headers.get("location"):
                    if redirect_count >= max_redirects:
                        raise UnsafeInputError("重定向次数过多")
                    next_url = validate_outbound_url(urljoin(current_url, upstream.headers["location"]))
                    if _origin(next_url) != _origin(current_url):
                        current_headers = {
                            key: value
                            for key, value in current_headers.items()
                            if key.lower() not in {"authorization", "cookie"}
                        }
                    if upstream.status_code == 303 or (
                        upstream.status_code in {301, 302} and request_method == "POST"
                    ):
                        request_method = "GET"
                        data = None
                    current_url = next_url
                    continue

                content_length = upstream.headers.get("content-length")
                if content_length and content_length.isdigit() and int(content_length) > limit:
                    raise UnsafeInputError("远程响应体超过允许上限")
                chunks: list[bytes] = []
                total = 0
                for chunk in upstream.iter_bytes():
                    total += len(chunk)
                    if total > limit:
                        raise UnsafeInputError("远程响应体超过允许上限")
                    chunks.append(chunk)
                return httpx.Response(
                    status_code=upstream.status_code,
                    headers=upstream.headers,
                    content=b"".join(chunks),
                    request=upstream.request,
                )
    raise UnsafeInputError("请求未得到有效响应")


def safe_filename(filename: Optional[str], fallback: str = "upload") -> str:
    """删除路径与控制字符，只保留适合本地存储的短文件名。"""
    basename = Path((filename or fallback).replace("\\", "/")).name
    basename = re.sub(r"[\x00-\x1f\x7f]", "", basename).strip()
    basename = re.sub(r"[^0-9A-Za-z._\-\u4e00-\u9fff]", "_", basename)
    basename = basename.lstrip(".")[:160]
    return basename or fallback


async def read_upload_limited(upload: UploadFile, max_bytes: int) -> bytes:
    """分块读取上传，避免先把超大文件完整载入内存。"""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise UnsafeInputError("上传文件超过允许上限")
        chunks.append(chunk)
    return b"".join(chunks)


def validate_file_extension(filename: str, allowed: set[str]) -> str:
    ext = Path(filename).suffix.lower().lstrip(".")
    if not ext or ext not in allowed:
        raise UnsafeInputError(f"不支持的文件类型，仅允许：{', '.join(sorted(allowed))}")
    return ext


def validate_file_signature(filename: str, content: bytes) -> None:
    """校验常见文档真实格式，并阻断伪装文件与压缩炸弹。"""
    ext = Path(filename).suffix.lower().lstrip(".")
    if not content:
        raise UnsafeInputError("上传文件为空")
    if ext == "pdf" and not content.startswith(b"%PDF-"):
        raise UnsafeInputError("文件内容不是有效 PDF")
    if ext in {"doc", "xls"} and not content.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        raise UnsafeInputError("文件内容与旧版 Office 扩展名不匹配")
    if ext in {"docx", "xlsx"}:
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                members = archive.infolist()
                if len(members) > 5000:
                    raise UnsafeInputError("Office 文件包含过多内部文件")
                expanded_size = sum(member.file_size for member in members)
                if expanded_size > 300 * 1024 * 1024:
                    raise UnsafeInputError("Office 文件解压后体积过大")
                names = {member.filename for member in members}
                expected_prefix = "word/" if ext == "docx" else "xl/"
                if not any(name.startswith(expected_prefix) for name in names):
                    raise UnsafeInputError("文件内容与 Office 扩展名不匹配")
        except zipfile.BadZipFile as exc:
            raise UnsafeInputError("Office 文件结构无效") from exc
    if ext in {"csv", "txt", "md", "json", "xml"}:
        sample = content[:65536]
        if sample.count(b"\x00") > max(1, len(sample) // 100):
            raise UnsafeInputError("文本文件包含异常二进制内容")
