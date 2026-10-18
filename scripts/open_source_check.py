#!/usr/bin/env python3
"""不输出秘密值的开源发布前静态检查。"""
from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {
    ".git", ".idea", ".zcode", ".superpowers", "node_modules", "venv", ".venv", "dist",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
}
LOCAL_ONLY_FILES = {
    ".env", "llm_config.json", "power_trade.db", "jwt-secret.key",
    "llm-master.key", ".npmrc", ".pypirc", ".netrc",
}
LOCAL_ONLY_PREFIXES = (
    "data/credentials/", "data/learning_books/", "data/attachments/",
    "data/history/", "data/raw/", "data/uploads/", "data/private/",
    ".zcode/", ".run/", "logs/", "backend/logs/",
)
REQUIRED_GITIGNORE_RULES = {
    ".env", "*.pem", "*.key", "data/credentials/", "data/learning_books/",
    "data/attachments/", "data/raw/", "*.db", "*.bak-*",
    "frontend/node_modules/", "backend/.venv/", ".zcode/", ".superpowers/",
    "/logs/", "/.run/",
}
TEXT_SUFFIXES = {
    ".py", ".js", ".ts", ".vue", ".json", ".toml", ".yaml", ".yml",
    ".md", ".txt", ".ini", ".cfg", ".sh", ".html", ".css",
}
HIGH_CONFIDENCE_PATTERNS = {
    "私钥正文": re.compile(r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"),
    "个人绝对路径": re.compile(r"/(?:Users|home)/[^/\s]+/(?:job|Desktop|Documents|Downloads|project|workspace)/"),
    "疑似智谱 API Key": re.compile(r"\b[a-fA-F0-9]{24,64}\.[A-Za-z0-9_-]{12,}\b"),
    "疑似 OpenAI 风格 Key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "硬编码 Bearer Token": re.compile(r"Bearer\s+[A-Za-z0-9._~-]{24,}"),
}


def iter_source_files():
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in SKIP_DIRS for part in path.parts):
            continue
        relative = path.relative_to(ROOT)
        if relative.parts and relative.parts[0] == "data":
            continue
        if path.name in LOCAL_ONLY_FILES:
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or path.name in {"Dockerfile", "Makefile"}:
            yield path


def git_tracked_files() -> set[str] | None:
    if not (ROOT / ".git").exists():
        return None
    result = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        return None
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def is_local_only_path(name: str) -> bool:
    path = Path(name)
    if path.name in LOCAL_ONLY_FILES:
        return True
    if path.name.startswith(".env") and path.name != ".env.example":
        return True
    if path.suffix.lower() in {
        ".pem", ".key", ".p12", ".pfx", ".sqlite", ".sqlite3", ".db",
    }:
        return True
    normalized = path.as_posix()
    return any(normalized.startswith(prefix) for prefix in LOCAL_ONLY_PREFIXES)


def main() -> int:
    findings: list[str] = []
    warnings: list[str] = []
    tracked = git_tracked_files()

    if tracked is None:
        warnings.append("尚未初始化 Git，无法审计暂存区和提交历史")
    else:
        for tracked_name in sorted(tracked):
            if is_local_only_path(tracked_name):
                findings.append(f"敏感文件已被 Git 跟踪: {tracked_name}")

    gitignore_path = ROOT / ".gitignore"
    if not gitignore_path.is_file():
        findings.append("缺少 .gitignore")
    else:
        gitignore_lines = {
            line.strip() for line in gitignore_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        for rule in sorted(REQUIRED_GITIGNORE_RULES - gitignore_lines):
            findings.append(f".gitignore 缺少必要规则: {rule}")

    for path in iter_source_files():
        try:
            if path.stat().st_size > 10 * 1024 * 1024:
                findings.append(f"源码区存在超过 10MB 的文件: {path.relative_to(ROOT)}")
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for label, pattern in HIGH_CONFIDENCE_PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{label}: {path.relative_to(ROOT)}（值未输出）")

    for path in ROOT.rglob("*"):
        if not path.is_file() or path.name not in LOCAL_ONLY_FILES:
            continue
        try:
            mode = stat.S_IMODE(path.stat().st_mode)
        except OSError:
            continue
        if mode & 0o077:
            findings.append(
                f"本机凭证文件权限过宽: {path.relative_to(ROOT)} mode={oct(mode)}"
            )

    if not any((ROOT / name).is_file() for name in ("LICENSE", "LICENSE.md", "LICENSE.txt")):
        warnings.append("尚未选择开源 LICENSE；首次公开前必须由维护者确认")

    print("开源发布安全检查")
    print(f"- 已扫描源码文件: {sum(1 for _ in iter_source_files())}")
    for warning in warnings:
        print(f"- 警告: {warning}")
    for finding in findings:
        print(f"- 失败: {finding}")
    if findings:
        print(f"结果: 未通过（{len(findings)} 项）")
        return 1
    print("结果: 通过（警告项仍需在首次公开前确认）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
