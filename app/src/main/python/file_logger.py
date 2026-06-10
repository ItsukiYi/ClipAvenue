"""
文件日志 — 持久化到 {download_dir}/biliup.log
"""
from __future__ import annotations

import os
import threading
import time

_LOCK = threading.Lock()
_LOG_FILE = ""


def init(download_dir: str):
    global _LOG_FILE
    _LOG_FILE = os.path.join(download_dir, "biliup.log")
    os.makedirs(download_dir, exist_ok=True)


def log(level: str, msg: str):
    global _LOG_FILE
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = "[%s] [%s] %s\n" % (ts, level, msg)
    try:
        with _LOCK:
            with open(_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception:
        pass


def info(msg: str): log("INFO", msg)
def warn(msg: str): log("WARN", msg)
def error(msg: str): log("ERROR", msg)
def debug(msg: str): log("DEBUG", msg)
