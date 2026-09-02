"""日志敏感信息脱敏。

过滤器只保留排障所需上下文，禁止 Bearer/JWT、API Key、密码和查询参数凭证
出现在终端、文件或第三方日志采集系统中。
"""
from __future__ import annotations

import logging
import re


_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(
        r"(?i)((?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|jwt)"
        r"\s*[:=]\s*)['\"]?[^\s,;&'\"]+"
    ),
    re.compile(r"(?i)([?&](?:api[_-]?key|key|token|access_token|jwt)=)[^&\s]+"),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
)


def redact_sensitive_text(value: object) -> str:
    text = str(value)
    for pattern in _PATTERNS:
        text = pattern.sub(lambda match: match.group(1) + "[REDACTED]" if match.lastindex else "[REDACTED]", text)
    return text


class SensitiveDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            rendered = record.getMessage()
            record.msg = redact_sensitive_text(rendered)
            record.args = ()
        except Exception:
            record.msg = "[日志内容无法安全格式化]"
            record.args = ()
        return True


def install_sensitive_log_filter() -> SensitiveDataFilter:
    """为当前已注册的日志处理器安装同一个脱敏过滤器。"""
    filter_instance = SensitiveDataFilter()
    loggers: list[logging.Logger] = [logging.getLogger()]
    for item in logging.root.manager.loggerDict.values():
        if isinstance(item, logging.Logger):
            loggers.append(item)
    seen: set[int] = set()
    for logger in loggers:
        for handler in logger.handlers:
            if id(handler) not in seen:
                handler.addFilter(filter_instance)
                seen.add(id(handler))
    return filter_instance
