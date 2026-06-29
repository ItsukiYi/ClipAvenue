"""
SQLite 数据库 — 录播信息持久化
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time
import traceback

_LOCK = threading.Lock()
_DB_PATH = ""
_LOG = []  # 数据库日志

def _db_log(msg: str):
    _LOG.append("[DB] %s" % msg)
    if len(_LOG) > 50: _LOG.pop(0)

def get_logs() -> list[str]:
    return list(_LOG)

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id TEXT NOT NULL,
    platform TEXT NOT NULL DEFAULT 'bilibili',
    title TEXT DEFAULT '',
    uname TEXT DEFAULT '',
    face_url TEXT DEFAULT '',
    cover_url TEXT DEFAULT '',
    last_checked INTEGER DEFAULT 0,
    is_live INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime')),
    updated_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime')),
    UNIQUE(room_id, platform)
);

CREATE TABLE IF NOT EXISTS live_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id TEXT NOT NULL,
    platform TEXT NOT NULL DEFAULT 'bilibili',
    title TEXT DEFAULT '',
    uname TEXT DEFAULT '',
    start_time INTEGER NOT NULL,
    end_time INTEGER DEFAULT 0,
    duration INTEGER DEFAULT 0,
    status TEXT DEFAULT 'recording'
);

CREATE TABLE IF NOT EXISTS recording_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER REFERENCES live_sessions(id),
    file_path TEXT NOT NULL,
    file_name TEXT DEFAULT '',
    file_size INTEGER DEFAULT 0,
    duration REAL DEFAULT 0,
    bitrate INTEGER DEFAULT 0,
    resolution TEXT DEFAULT '',
    codec TEXT DEFAULT '',
    created_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime'))
);

CREATE TABLE IF NOT EXISTS uploads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER REFERENCES recording_files(id),
    platform TEXT DEFAULT 'bilibili',
    status TEXT DEFAULT 'pending',
    bvid TEXT DEFAULT '',
    aid INTEGER DEFAULT 0,
    error_msg TEXT DEFAULT '',
    created_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime'))
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_sessions_room ON live_sessions(room_id, platform);
CREATE INDEX IF NOT EXISTS idx_files_session ON recording_files(session_id);
"""


def init(db_dir: str):
    """初始化数据库"""
    global _DB_PATH
    os.makedirs(db_dir, exist_ok=True)
    db_file = os.path.join(db_dir, "biliup.db")

    # 如果旧文件存在但有损坏，删除重建
    if os.path.exists(db_file) and os.path.getsize(db_file) < 100:
        try: os.remove(db_file)
        except Exception: pass

    _DB_PATH = db_file
    _db_log("db file: %s" % db_file)

    with _LOCK:
        try:
            conn = sqlite3.connect(_DB_PATH)
            conn.executescript(CREATE_SQL)
            conn.commit()
            # 验证表存在
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cursor.fetchall()]
            conn.close()
            _db_log("tables: %s" % ", ".join(tables))
            if "rooms" not in tables:
                raise Exception("rooms 表创建失败")
        except Exception as e:
            _db_log("INIT ERROR: %s" % traceback.format_exc())
            # 最后一次尝试：删除文件重建
            try:
                if os.path.exists(db_file): os.remove(db_file)
                conn = sqlite3.connect(db_file)
                conn.executescript(CREATE_SQL)
                conn.commit()
                conn.close()
                _db_log("重建成功")
            except Exception as e2:
                _db_log("重建也失败: %s" % str(e2))
                raise


def _conn():
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ─── 直播间 ──────────────────────────────────────────────

def add_room(room_id: str, platform: str, title: str = "", uname: str = ""):
    with _LOCK:
        conn = _conn()
        try:
            conn.execute("""
                INSERT OR REPLACE INTO rooms (room_id, platform, title, uname, updated_at)
                VALUES (?, ?, ?, ?, strftime('%Y-%m-%d %H:%M:%S','now','localtime'))
            """, (room_id, platform, title, uname))
            conn.commit()
        except Exception as e:
            _db_log("add_room error: %s" % str(e))
        finally:
            conn.close()


def get_rooms() -> list[dict]:
    with _LOCK:
        conn = _conn()
        try:
            rows = conn.execute("SELECT * FROM rooms ORDER BY updated_at DESC").fetchall()
            result = [dict(r) for r in rows]
        except Exception as e:
            _db_log("get_rooms error: %s" % str(e))
            result = []
        finally:
            conn.close()
        return result


def update_room_info(room_id: str, platform: str, title: str = "",
                     uname: str = "", is_live: int = 0):
    with _LOCK:
        conn = _conn()
        try:
            conn.execute("""
                UPDATE rooms SET title=?, uname=?, is_live=?, last_checked=strftime('%s','now'),
                updated_at=strftime('%Y-%m-%d %H:%M:%S','now','localtime') WHERE room_id=? AND platform=?
            """, (title, uname, is_live, room_id, platform))
            conn.commit()
        except Exception as e:
            _db_log("update_room error: %s" % str(e))
        finally:
            conn.close()


def remove_room(room_id: str, platform: str):
    with _LOCK:
        conn = _conn()
        try:
            conn.execute("DELETE FROM rooms WHERE room_id=? AND platform=?", (room_id, platform))
            conn.commit()
        except Exception as e:
            _db_log("remove_room error: %s" % str(e))
        finally:
            conn.close()


# ─── 直播场次 ────────────────────────────────────────────

def start_session(room_id: str, platform: str, title: str = "",
                  uname: str = "") -> int:
    with _LOCK:
        conn = _conn()
        try:
            cur = conn.execute("""
                INSERT INTO live_sessions (room_id, platform, title, uname, start_time, status)
                VALUES (?, ?, ?, ?, ?, 'recording')
            """, (room_id, platform, title, uname, int(time.time())))
            conn.commit()
            sid = cur.lastrowid
        except Exception as e:
            _db_log("start_session error: %s" % str(e))
            sid = -1
        finally:
            conn.close()
        return sid


def end_session(session_id: int):
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute(
                "SELECT start_time FROM live_sessions WHERE id=?", (session_id,)
            ).fetchone()
            if row:
                now = int(time.time())
                duration = now - row["start_time"]
                conn.execute(
                    "UPDATE live_sessions SET end_time=?, duration=?, status='completed' WHERE id=?",
                    (now, duration, session_id),
                )
                conn.commit()
        except Exception as e:
            _db_log("end_session error: %s" % str(e))
        finally:
            conn.close()


def get_sessions(room_id: str = None, platform: str = None, limit: int = 50) -> list[dict]:
    with _LOCK:
        conn = _conn()
        try:
            if room_id and platform:
                rows = conn.execute(
                    "SELECT * FROM live_sessions WHERE room_id=? AND platform=? ORDER BY start_time DESC LIMIT ?",
                    (room_id, platform, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM live_sessions ORDER BY start_time DESC LIMIT ?", (limit,)
                ).fetchall()
            result = [dict(r) for r in rows]
        except Exception:
            result = []
        finally:
            conn.close()
        return result


# ─── 录制文件 ────────────────────────────────────────────

def add_recording_file(session_id: int, file_path: str, file_name: str = "",
                       file_size: int = 0, duration: float = 0) -> int:
    with _LOCK:
        conn = _conn()
        try:
            cur = conn.execute("""
                INSERT INTO recording_files (session_id, file_path, file_name, file_size, duration)
                VALUES (?, ?, ?, ?, ?)
            """, (session_id, file_path, file_name, file_size, duration))
            conn.commit()
            fid = cur.lastrowid
        except Exception:
            fid = -1
        finally:
            conn.close()
        return fid


def get_recording_files(session_id: int = None) -> list[dict]:
    with _LOCK:
        conn = _conn()
        try:
            if session_id:
                rows = conn.execute(
                    "SELECT * FROM recording_files WHERE session_id=? ORDER BY created_at DESC",
                    (session_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM recording_files ORDER BY created_at DESC"
                ).fetchall()
            result = [dict(r) for r in rows]
        except Exception:
            result = []
        finally:
            conn.close()
        return result


# ─── 设置 ────────────────────────────────────────────────

def set_setting(key: str, value: str):
    with _LOCK:
        conn = _conn()
        try:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()


def get_setting(key: str, default: str = "") -> str:
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            result = row["value"] if row else default
        except Exception:
            result = default
        finally:
            conn.close()
        return result


def get_all_settings() -> dict[str, str]:
    with _LOCK:
        conn = _conn()
        try:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
            result = {r["key"]: r["value"] for r in rows}
        except Exception:
            result = {}
        finally:
            conn.close()
        return result


# ─── 统计 ────────────────────────────────────────────────

def get_stats() -> dict:
    with _LOCK:
        conn = _conn()
        try:
            n_sessions = conn.execute("SELECT COUNT(*) as c FROM live_sessions").fetchone()["c"]
            n_files = conn.execute("SELECT COUNT(*) as c FROM recording_files").fetchone()["c"]
            total_size = conn.execute("SELECT COALESCE(SUM(file_size),0) as s FROM recording_files").fetchone()["s"]
            total_dur = conn.execute("SELECT COALESCE(SUM(duration),0) as d FROM recording_files").fetchone()["d"]
            total_up = conn.execute("SELECT COUNT(*) as c FROM uploads WHERE status='completed'").fetchone()["c"]
            result = {
                "total_sessions": n_sessions,
                "total_files": n_files,
                "total_size_mb": round(total_size / 1048576, 1),
                "total_duration_h": round(total_dur / 3600, 1),
                "total_uploads": total_up,
            }
        except Exception:
            result = {}
        finally:
            conn.close()
        return result


# ─── 上传 ────────────────────────────────────────────────

def add_upload(file_id: int, platform: str = "bilibili") -> int:
    with _LOCK:
        conn = _conn()
        try:
            cur = conn.execute(
                "INSERT INTO uploads (file_id, platform, status) VALUES (?, ?, 'pending')",
                (file_id, platform),
            )
            conn.commit()
            uid = cur.lastrowid
        except Exception:
            uid = -1
        finally:
            conn.close()
        return uid


def update_upload(upload_id: int, status: str = None, bvid: str = None,
                  aid: int = None, error_msg: str = None):
    fields = {}
    if status is not None: fields["status"] = status
    if bvid is not None: fields["bvid"] = bvid
    if aid is not None: fields["aid"] = aid
    if error_msg is not None: fields["error_msg"] = error_msg
    if not fields:
        return
    with _LOCK:
        conn = _conn()
        try:
            sets = ", ".join("%s=?" % k for k in fields)
            vals = list(fields.values()) + [upload_id]
            conn.execute("UPDATE uploads SET %s WHERE id=?" % sets, vals)
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()
