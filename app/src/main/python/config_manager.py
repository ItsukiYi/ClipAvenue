"""
配置持久化管理 — JSON 文件存储

存储位置: {download_dir}/biliup_config.json

存储内容:
  - rooms: [{room_id, platform, title, uname}]
  - bilibili_cookies: "SESSDATA=xxx; bili_jct=xxx; ..."
  - settings: {segment_time, auto_upload}
"""
from __future__ import annotations

import json
import os
import threading

_CONFIG = None
_LOCK = threading.Lock()
_CONFIG_DIR = ""


def init(download_dir: str):
    """初始化配置管理器"""
    global _CONFIG, _CONFIG_DIR
    _CONFIG_DIR = download_dir
    os.makedirs(download_dir, exist_ok=True)
    _CONFIG = _load()


def _config_path() -> str:
    return os.path.join(_CONFIG_DIR, "biliup_config.json")


def _load() -> dict:
    path = _config_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"rooms": [], "bilibili_cookies": "", "settings": {}}


def _save():
    path = _config_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(_CONFIG, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ─── 直播间 ──────────────────────────────────────────────

def get_rooms() -> list[dict]:
    with _LOCK:
        return list(_CONFIG.get("rooms", []))


def add_room(room_id: str, platform: str, title: str = "", uname: str = ""):
    with _LOCK:
        rooms = _CONFIG.setdefault("rooms", [])
        # 去重
        rooms = [r for r in rooms if not (r.get("room_id") == room_id and r.get("platform") == platform)]
        rooms.append({
            "room_id": room_id,
            "platform": platform,
            "title": title,
            "uname": uname,
        })
        _CONFIG["rooms"] = rooms
        _save()


def remove_room(room_id: str, platform: str):
    with _LOCK:
        rooms = _CONFIG.get("rooms", [])
        _CONFIG["rooms"] = [r for r in rooms if not (r.get("room_id") == room_id and r.get("platform") == platform)]
        _save()


def update_room_title(room_id: str, platform: str, title: str, uname: str):
    with _LOCK:
        rooms = _CONFIG.get("rooms", [])
        for r in rooms:
            if r.get("room_id") == room_id and r.get("platform") == platform:
                r["title"] = title
                r["uname"] = uname
        _CONFIG["rooms"] = rooms
        _save()


# ───登录 Cookie ────────────────────────────────────────────

def get_cookies() -> str:
    with _LOCK:
        return _CONFIG.get("bilibili_cookies", "")


def set_cookies(cookies: str):
    with _LOCK:
        _CONFIG["bilibili_cookies"] = cookies
        _save()


# ─── 设置 ──────────────────────────────────────────────────

def get_settings() -> dict:
    with _LOCK:
        return dict(_CONFIG.get("settings", {}))


def get_setting(key: str, default=None):
    return get_settings().get(key, default)


def set_setting(key: str, value):
    with _LOCK:
        _CONFIG.setdefault("settings", {})[key] = value
        _save()
