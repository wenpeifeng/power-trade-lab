"""轻量级认证限流器。

当前项目是单进程本地/小型部署，使用进程内存避免引入额外基础设施。
多实例生产部署应将同样的键与窗口规则迁移到 Redis。
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitState:
    allowed: bool
    retry_after: int = 0


class SlidingWindowLimiter:
    """线程安全的滑动窗口计数器。"""

    def __init__(self, max_attempts: int, window_seconds: int):
        self.max_attempts = max(1, max_attempts)
        self.window_seconds = max(1, window_seconds)
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, *, now: float | None = None) -> RateLimitState:
        current = time.monotonic() if now is None else now
        cutoff = current - self.window_seconds
        with self._lock:
            events = self._events.get(key)
            if not events:
                return RateLimitState(True)
            while events and events[0] <= cutoff:
                events.popleft()
            if not events:
                self._events.pop(key, None)
                return RateLimitState(True)
            if len(events) < self.max_attempts:
                return RateLimitState(True)
            retry_after = max(1, int(events[0] + self.window_seconds - current) + 1)
            return RateLimitState(False, retry_after)

    def record(self, key: str, *, now: float | None = None) -> RateLimitState:
        current = time.monotonic() if now is None else now
        with self._lock:
            events = self._events[key]
            cutoff = current - self.window_seconds
            while events and events[0] <= cutoff:
                events.popleft()
            events.append(current)
        return self.check(key, now=current)

    def clear(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)
