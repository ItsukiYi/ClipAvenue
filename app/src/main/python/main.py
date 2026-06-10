"""
biliup-android Python 入口 — 完整录制工作流

架构:
  start_recording() 是自包含的完整工作流:
    1. 获取直播流URL
    2. 在数据库创建 live_session
    3. 启动下载线程
    4. 每段完成 → 写recording_files表 → 发事件给Kotlin
    5. 录制结束(手动停/断线/下播) → 关session → 发事件

  Kotlin侧通过 register_callback 接收事件，只负责UI更新+前台保活
"""
from __future__ import annotations

import json
import os
import time
from typing import Optional, Callable

import traceback

import file_logger as flog
from bilibili_api import BilibiliAPI
from recorder import FFmpegRecorder

try:
    from database import init as db_init
    from database import (
        add_room, get_rooms, update_room_info, remove_room,
        start_session, end_session,
        add_recording_file, get_recording_files,
        set_setting, get_setting, get_all_settings, get_stats,
    )
except Exception as e:
    db_init = None
    _import_error = traceback.format_exc()

_bilibili: Optional[BilibiliAPI] = None
_recorder: Optional[FFmpegRecorder] = None
_callbacks: list[Callable] = []  # Kotlin 事件回调
_task_sessions: dict[str, int] = {}  # task_id → session_id


def _emit(event: str, data: dict):
    """发送事件给 Kotlin — 调用 Java 对象的 onPythonEvent 方法"""
    payload = json.dumps(data, ensure_ascii=False)
    for cb in _callbacks:
        try:
            cb.onPythonEvent(event, payload)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
# 初始化
# ═══════════════════════════════════════════════════════════════

def init_app(download_dir: str = None):
    global _bilibili, _recorder

    dl = download_dir or "/sdcard/biliup"
    try:
        os.makedirs(dl, exist_ok=True)
        testf = os.path.join(dl, ".testinit")
        with open(testf, "w") as f: f.write("ok")
        os.remove(testf)
    except Exception as e:
        return json.dumps({"success": False, "error": "目录不可写 %s: %s" % (dl, str(e))})

    # 文件日志
    flog.init(dl)
    flog.info("init_app download_dir=%s" % dl)

    if db_init is None:
        return json.dumps({"success": False, "error": "导入database失败: %s" % _import_error})

    try:
        db_init(dl)
        from database import get_logs
        dblogs = get_logs()
    except Exception as e:
        return json.dumps({"success": False, "error": "数据库初始化失败 %s: %s" % (dl, str(e))})

    cookies = get_setting("bilibili_cookies", "")
    _bilibili = BilibiliAPI()
    if cookies:
        _bilibili.load_cookies(cookies)
        flog.info("已恢复B站登录: uid=%s, uname=%s" % (_bilibili.login.uid, _bilibili.login.uname))
    else:
        flog.info("未登录B站 (扫码登录后可获更高画质)")

    _recorder = FFmpegRecorder(download_dir=dl)
    # 断连时自动刷新流地址
    def _refresh_url(room_id: int):
        if _bilibili:
            urls = _bilibili.get_stream_urls(room_id)
            return urls[0] if urls else None
        return None
    _recorder.set_url_refresher(_refresh_url)

    s = get_stats()
    return json.dumps({
        "success": True, "download_dir": dl,
        "rooms": len(get_rooms()), "cookies_loaded": bool(cookies),
        "total_sessions": s.get("total_sessions", 0),
        "db_logs": dblogs,
    })


def register_callback(cb):
    _callbacks.append(cb)


# ═══════════════════════════════════════════════════════════════
# 数据库操作
# ═══════════════════════════════════════════════════════════════

def db_get_rooms_json() -> str:
    return json.dumps(get_rooms(), ensure_ascii=False)

def db_add_room(room_id: str, platform: str):
    add_room(room_id, platform)

def db_update_room(room_id: str, platform: str, title: str = "",
                   uname: str = "", is_live: int = 0):
    update_room_info(room_id, platform, title, uname, is_live)

def db_remove_room(room_id: str, platform: str):
    remove_room(room_id, platform)

def db_get_sessions_json(room_id: str = "", platform: str = "",
                         limit: int = 50) -> str:
    from database import get_sessions
    return json.dumps(get_sessions(room_id, platform, limit) if room_id
                      else get_sessions(limit=limit), ensure_ascii=False)

def db_get_files_json(session_id: int = 0) -> str:
    return json.dumps(get_recording_files(session_id if session_id > 0 else None),
                      ensure_ascii=False)

def db_get_settings_json() -> str:
    return json.dumps(get_all_settings(), ensure_ascii=False)

def db_set_setting(key: str, value: str):
    set_setting(key, value)

def db_get_setting(key: str, default: str = "") -> str:
    return get_setting(key, default)

def db_get_stats_json() -> str:
    return json.dumps(get_stats(), ensure_ascii=False)


def get_file_log(lines: int = 100) -> str:
    """返回 biliup.log 最后 N 行"""
    try:
        log_path = os.path.join(_recorder.download_dir if _recorder else "/sdcard/biliup", "biliup.log")
        if not os.path.exists(log_path):
            return "日志文件不存在: %s" % log_path
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
            return "".join(all_lines[-lines:])
    except Exception as e:
        return "读取日志失败: %s" % str(e)


# ═══════════════════════════════════════════════════════════════
# B站 API
# ═══════════════════════════════════════════════════════════════

def bilibili_get_room_info(room_id: str, qn: int = 10000) -> str:
    data = _bilibili.get_room_info(int(room_id), int(qn))
    return json.dumps(data.__dict__, ensure_ascii=False, default=str)

def bilibili_check_live(room_id: str) -> bool:
    return _bilibili.check_live(int(room_id))

def bilibili_get_stream_url(room_id: str, qn: int = 10000) -> str:
    urls = _bilibili.get_stream_urls(int(room_id), int(qn))
    return json.dumps({"success": len(urls) > 0, "urls": urls})


# ═══════════════════════════════════════════════════════════════
# B站登录
# ═══════════════════════════════════════════════════════════════

def bilibili_login_qr_generate() -> str:
    _bilibili.clear_cookies()
    result = _bilibili.generate_qr()
    flog.info("QR生成: %s" % ("成功" if result.get("success") else result.get("message")))
    return json.dumps(result, ensure_ascii=False)

def bilibili_login_qr_poll() -> str:
    r = _bilibili.poll_qr()
    flog.info("QR轮询: status=%s, msg=%s" % (r.get("status"), r.get("message", "")))
    if r.get("status") == "success":
        cookie_str = _bilibili.get_cookies_str()
        if cookie_str:
            set_setting("bilibili_cookies", cookie_str)
            flog.info("B站登录成功, cookies已保存: %s..." % cookie_str[:50])
    return json.dumps(r, ensure_ascii=False)

def bilibili_set_cookies(c: str):
    _bilibili.load_cookies(c)
    set_setting("bilibili_cookies", c)

def bilibili_get_cookies() -> str:
    return _bilibili.get_cookies_str()

def bilibili_is_logged_in() -> bool:
    return _bilibili.login.logged_in

def bilibili_get_user_info() -> str:
    return json.dumps({"uid": _bilibili.login.uid, "uname": _bilibili.login.uname})


# ═══════════════════════════════════════════════════════════════
# 录制工作流 (完整自包含)
# ═══════════════════════════════════════════════════════════════

def start_recording(room_id: str, platform: str = "bilibili",
                    title: str = "", uname: str = "",
                    segment_time: int = 3600, qn: int = 10000) -> str:
    """完整的录制工作流，返回 {task_id, session_id, stream_url}"""
    rid = int(room_id)

    # 1. 获取流地址（用指定画质）
    urls = _bilibili.get_stream_urls(rid, int(qn))
    if not urls:
        return json.dumps({"success": False, "error": "获取直播流失败，可能未开播"})
    stream_url = urls[0]

    # 2. 数据库创建直播场次
    sid = start_session(room_id, platform, title, uname)
    update_room_info(room_id, platform, title, uname, is_live=1)

    # 3. 创建录制任务
    task_id = "%s_%s_%d" % (platform, room_id, int(time.time()))
    # 构建 CDN 流请求 headers (含 cookie 保持长连接)
    stream_headers = {}
    if _bilibili and _bilibili.login.cookies:
        cookies = _bilibili.get_cookies_str()
        if cookies:
            stream_headers["Cookie"] = cookies

    task = _recorder.create_task(
        task_id=task_id, room_id=rid, platform=platform,
        stream_url=stream_url, title=title or "room_%s" % room_id,
        uname=uname, segment_seconds=segment_time,
    )
    task.stream_headers = stream_headers
    _task_sessions[task_id] = sid

    # 4. 设置录制事件回调 (Python → Kotlin + DB写入)
    def _on_recorder_event(tid, event, data):
        d = dict(data) if data else {}
        if event == "recording_start":
            _emit("record", {"type": "start", "task_id": tid,
                   "file": d.get("file", ""), "title": task.title,
                   "session_id": sid})
        elif event == "segment_complete":
            fp = d.get("file", "")
            sz = d.get("size", 0)
            dur = d.get("duration", 0)
            if fp:
                add_recording_file(sid, fp, os.path.basename(fp), sz, dur)
            _emit("record", {"type": "segment", "task_id": tid,
                   "file": fp, "size": sz, "duration": dur})
        elif event == "reconnecting":
            _emit("record", {"type": "reconnecting", "task_id": tid,
                   "retry": d.get("retry", 0)})
        elif event == "stopped" or event == "error":
            s = _task_sessions.pop(tid, None)
            if s:
                end_session(s)
                update_room_info(str(task.room_id), platform, is_live=0)
            _emit("record", {"type": "stopped", "task_id": tid,
                   "file": task.current_file, "error": d.get("error", "")})

    _recorder.on_event(task_id, _on_recorder_event)

    # 5. 启动下载
    ok = _recorder.start_recording(task_id)

    if not ok:
        end_session(sid)
        update_room_info(room_id, platform, is_live=0)
        return json.dumps({"success": False, "error": "启动下载失败"})

    _emit("record", {"type": "started", "task_id": task_id,
           "room_id": room_id, "session_id": sid})

    return json.dumps({
        "success": True, "task_id": task_id,
        "session_id": sid, "output_dir": task.output_dir,
    })


def stop_recording(task_id: str) -> str:
    _recorder.stop_recording(task_id)
    return json.dumps({"success": True})


def stop_all_recordings() -> str:
    _recorder.stop_all()
    return json.dumps({"success": True})


def get_recording_status(task_id: str = "") -> str:
    if task_id:
        return json.dumps(_recorder.get_task_status(task_id), ensure_ascii=False)
    return json.dumps(_recorder.get_all_status(), ensure_ascii=False, default=str)


# ═══════════════════════════════════════════════════════════════
# 上传
# ═══════════════════════════════════════════════════════════════

def upload_video(file_path: str, title: str, platform: str = "bilibili",
                 desc: str = "", tags: str = "") -> str:
    from uploader import BilibiliUploader, UploadTask
    cookies = _bilibili.login.cookies if _bilibili else {}
    u = BilibiliUploader(cookies)
    t = UploadTask(task_id="up_%d" % int(time.time()), file_path=file_path,
                   platform=platform, title=title, desc=desc,
                   tags=[x.strip() for x in tags.split(",") if x.strip()] if tags else [])

    def _cb(tid, p, sp, st):
        _emit("upload", {"task_id": tid, "progress": p, "speed": sp, "status": st})
    u.on_progress(t.task_id, _cb)

    r = u.upload(t)
    if r.get("success"):
        from database import add_upload, update_upload
        fid = add_recording_file(0, file_path, os.path.basename(file_path))
        uid = add_upload(fid, platform)
        update_upload(uid, status="completed", bvid=r.get("bvid", ""), aid=r.get("aid", 0))
    return json.dumps(r, ensure_ascii=False)


def set_download_dir(d: str):
    if _recorder:
        _recorder.download_dir = d; os.makedirs(d, exist_ok=True)
    set_setting("download_dir", d)


def cleanup():
    if _recorder:
        _recorder.stop_all()
    for sid in _task_sessions.values():
        try: end_session(sid)
        except Exception: pass
    _task_sessions.clear()
