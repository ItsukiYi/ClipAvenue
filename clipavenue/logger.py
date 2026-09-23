"""LiveLog — 实时日志捕获 + 环形缓冲区。

提供两个功能:
1. 全局日志记录器 (LiveLog)，后端各处调用 log() 写入
2. 日志环形缓冲区，通过 SSE 推送给前端
"""

from __future__ import annotations

import datetime
import threading
from typing import Callable


class LiveLog:
    """全局日志捕获器。线程安全。"""

    def __init__(self, max_entries: int = 500) -> None:
        self._entries: list[dict] = []
        self._max = max_entries
        self._lock = threading.Lock()
        self._listeners: list[Callable] = []

    def info(self, source: str, message: str) -> None:
        self._append("info", source, message)

    def warn(self, source: str, message: str) -> None:
        self._append("warn", source, message)

    def error(self, source: str, message: str) -> None:
        self._append("error", source, message)

    def _append(self, level: str, source: str, message: str) -> None:
        entry = {
            "ts": datetime.datetime.now().isoformat(sep=" ", timespec="milliseconds"),
            "level": level,
            "source": source[:30],
            "msg": message,
        }
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self._max:
                self._entries.pop(0)
        # 通知监听器
        for cb in self._listeners:
            try:
                cb(entry)
            except Exception:
                pass

    def get_all(self) -> list[dict]:
        with self._lock:
            return list(self._entries)

    def get_recent(self, n: int = 50) -> list[dict]:
        with self._lock:
            return list(self._entries[-n:])

    def subscribe(self, callback: Callable) -> Callable:
        """添加监听器，返回取消函数。"""
        self._listeners.append(callback)
        return lambda: self._listeners.remove(callback)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


# 全局单例
_log = LiveLog()
log = _log  # from clipavenue.logger import log; log.info("recorder", "消息")