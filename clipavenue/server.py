"""ClipAvenue server — FastAPI app: dashboard state, SSE, recorder control.

Architecture mirrors Backlot (backlot/server.py) but is purpose-built for
the livestream pipeline metro-map. Shares the same projects/ directory.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from clipavenue.state import load_dashboard_state, list_live_projects
from clipavenue.recorder.manager import RecorderManager
from clipavenue.recorder.task import RecorderTask
from clipavenue.storage.monitor import DiskMonitor
from clipavenue.storage.policy import RetentionPolicy
from clipavenue.storage.cleanup import CleanupJob
from clipavenue.uploader.bili_uploader import BiliUploader, UploadTask
from clipavenue.archiver.notifier import Notifier
from clipavenue.archiver.backup import BackupManager
from clipavenue.archiver.cleanup import PostUploadCleanup
from clipavenue.queue import JobQueue
from clipavenue.config import get as get_config
from clipavenue.logger import log

UI_DIR = Path(__file__).resolve().parent / "ui"
SSE_HEARTBEAT_SECONDS = 15

# ---------------------------------------------------------------------------
# ChangeHub — SSE fan-out
# ---------------------------------------------------------------------------

class ChangeHub:
    """Fan-out of change notifications to SSE subscribers."""

    def __init__(self) -> None:
        self._subscribers: dict[asyncio.Queue, Optional[str]] = {}

    def subscribe(self, project_id: Optional[str] = None) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._subscribers[q] = project_id
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.pop(q, None)

    def publish(self, project_id: str = "dashboard") -> None:
        for q, only in list(self._subscribers.items()):
            if only is not None and only != project_id:
                continue
            try:
                q.put_nowait(project_id)
            except asyncio.QueueFull:
                pass


hub = ChangeHub()

# ---------------------------------------------------------------------------
# Global singletons (initialized in create_app)
# ---------------------------------------------------------------------------

recorder_manager: Optional[RecorderManager] = None
disk_monitor: Optional[DiskMonitor] = None
notifier: Notifier = Notifier()
queue: Optional["JobQueue"] = None
_worker_process: Optional[subprocess.Popen] = None

# ---------------------------------------------------------------------------
# Watch loop
# ---------------------------------------------------------------------------

_IGNORE_PARTS = {"node_modules", ".git", "__pycache__", ".cache"}

from clipavenue.lib_paths import PROJECTS_DIR
import os as _os
_PROJECTS_ROOT_STR = _os.path.normcase(str(PROJECTS_DIR.resolve()))


def _project_of_change(path_str: str) -> Optional[str]:
    norm = _os.path.normcase(_os.path.normpath(path_str))
    if not norm.startswith(_PROJECTS_ROOT_STR):
        return None
    rel = norm[len(_PROJECTS_ROOT_STR):].lstrip("\\/")
    if not rel:
        return None
    parts = rel.replace("\\", "/").split("/")
    if _IGNORE_PARTS.intersection(parts):
        return None
    return parts[0]


async def _watch_projects() -> None:
    """Background task: watch projects/ and publish debounced changes."""
    try:
        from watchfiles import awatch
    except ImportError:
        return
    if not PROJECTS_DIR.is_dir():
        return
    async for changes in awatch(PROJECTS_DIR, recursive=True, step=400):
        touched: set[str] = set()
        for _change, path_str in changes:
            pid = _project_of_change(path_str)
            if pid:
                touched.add(pid)
        for pid in touched:
            hub.publish(pid)


async def _recorder_health_loop() -> None:
    """Periodic tick: check recorder health and storage."""
    global recorder_manager, disk_monitor
    while True:
        try:
            if recorder_manager:
                recorder_manager.tick()
            if disk_monitor:
                disk_monitor.tick()
            hub.publish("health")
        except Exception as exc:
            print(f"clipavenue: health tick error: {exc}")
        await asyncio.sleep(30)  # every 30 seconds


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _check_bilibili_cookies() -> bool:
    """Check if bilibili cookies.json exists and has valid cookies."""
    import json
    for path in (Path("cookies.json"), Path.cwd() / "cookies.json"):
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and "cookie_info" in raw:
                    cookies = raw["cookie_info"].get("cookies", [])
                    if any(c.get("name") == "SESSDATA" for c in cookies):
                        return True
                if isinstance(raw, dict) and "SESSDATA" in raw:
                    return True
            except (OSError, json.JSONDecodeError):
                continue
    return False


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    global recorder_manager, disk_monitor

    app = FastAPI(title="ClipAvenue", docs_url=None, redoc_url=None)

    cfg = get_config()

    # Initialize singletons
    recorder_manager = RecorderManager(projects_dir=PROJECTS_DIR)
    recorder_manager.load_state()

    disk_monitor = DiskMonitor(
        watch_dir=PROJECTS_DIR,
        warning_pct=cfg.get("storage", {}).get("warning_threshold_pct", 85),
        critical_pct=cfg.get("storage", {}).get("critical_threshold_pct", 95),
    )

    @app.on_event("startup")
    async def _startup() -> None:
        global queue, _worker_process
        app.state.watch_task = asyncio.create_task(_watch_projects())
        app.state.health_task = asyncio.create_task(_recorder_health_loop())

        # Initialize job queue
        queue = JobQueue(str(PROJECTS_DIR / "_queue" / "queue.db"))
        stale = queue.requeue_stale()
        if stale:
            log.info("服务器", f"恢复 {stale} 个 stale 作业")

        # Spawn worker as a detached subprocess (same pattern as __main__.py's _spawn_server)
        try:
            worker_cmd = [sys.executable, "-m", "clipavenue", "worker"]
            worker_kwargs: dict = {
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "stdin": subprocess.DEVNULL,
            }
            if _os.name == "nt":
                worker_kwargs["creationflags"] = (
                    subprocess.CREATE_NEW_PROCESS_GROUP
                    | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
                )
            else:
                worker_kwargs["start_new_session"] = True
            _worker_process = subprocess.Popen(worker_cmd, **worker_kwargs)
            log.info("服务器", f"worker 已启动 (PID {_worker_process.pid})")
        except Exception as exc:
            log.warn("服务器", f"worker 启动失败: {exc} — 队列将等待手动启动")

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        for attr in ("watch_task", "health_task"):
            task = getattr(app.state, attr, None)
            if task:
                task.cancel()

    # ==================================================================
    # API — Dashboard
    # ==================================================================

    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True, "app": "clipavenue"}

    @app.get("/api/state")
    async def dashboard_state() -> dict:
        """Full metro-map dashboard state, including recorder + storage."""
        state = await asyncio.to_thread(load_dashboard_state)

        # Inject real-time recorder data
        if recorder_manager:
            state["recorder"] = {
                "task_count": recorder_manager.task_count,
                "active_count": len(recorder_manager.active_tasks()),
                "tasks": [t.to_dict() for t in recorder_manager.list_tasks()],
            }

        # Inject real-time storage data
        if disk_monitor:
            state["storage"] = disk_monitor.stats()

        # Inject bilibili login status
        state["recorder_check"] = {
            "bilibili_logged_in": _check_bilibili_cookies(),
        }

        return state

    @app.get("/api/projects")
    async def projects() -> list:
        return await asyncio.to_thread(list_live_projects)

    @app.get("/api/events")
    async def events(request: Request) -> StreamingResponse:
        async def stream():
            q = hub.subscribe()
            try:
                yield _sse({"type": "hello"})
                while True:
                    if await request.is_disconnected():
                        return
                    try:
                        await asyncio.wait_for(q.get(), timeout=SSE_HEARTBEAT_SECONDS)
                    except asyncio.TimeoutError:
                        yield _sse({"type": "heartbeat", "ts": time.time()})
                        continue
                    while not q.empty():
                        try:
                            q.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                    yield _sse({"type": "change"})
            finally:
                hub.unsubscribe(q)

        return StreamingResponse(stream(), media_type="text/event-stream", headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        })

    # ==================================================================
    # API — Recorder Control
    # ==================================================================

    @app.post("/api/recorder/start")
    async def recorder_start(data: dict) -> dict:
        """Start a new recording task."""
        global recorder_manager
        if not recorder_manager:
            raise HTTPException(status_code=503, detail="recorder manager not available")

        platform = data.get("platform", "bilibili").lower()
        url = data.get("url", "")
        streamer = data.get("streamer", "unknown")
        task_id = data.get("task_id") or f"{streamer}-{int(time.time())}"
        output_dir = PROJECTS_DIR / task_id

        log.info("服务器", f"收到录制请求: {streamer} @ {platform} ({url[:50]}...)")

        # Determine recorder type
        recorder_type = "biliup"

        task = RecorderTask(
            task_id=task_id,
            platform=platform,
            url=url,
            streamer=streamer,
            output_dir=output_dir,
            recorder_type=recorder_type,
        )

        recorder_manager.add_task(task)
        success = recorder_manager.start_task(task_id)

        if not success:
            error_msg = task.error or "未知错误"
            log.error("服务器", f"录制启动失败: {error_msg}")
            return {"success": False, "task_id": task_id, "error": error_msg}

        log.info("服务器", f"录制已启动: {streamer} — {task.recorder_info or f'PID {task.pid}'}")

        # Write project.json marker
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "project.json").write_text(
            json.dumps({
                "project_id": task_id,
                "title": f"{streamer} 直播录制",
                "pipeline_type": "clipavenue",
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }, indent=2),
            encoding="utf-8",
        )

        hub.publish()
        info = task.recorder_info or f"PID {task.pid}"
        return {"success": True, "task_id": task_id, "pid": task.pid, "info": info}

    @app.get("/api/recorder/check")
    async def recorder_check() -> dict:
        """Check which recording tools are available on this machine."""
        results = {}

        # Check ffmpeg (always expected)
        try:
            r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
            results["ffmpeg"] = {"available": r.returncode == 0,
                                 "detail": r.stdout[:50].strip() if r.returncode == 0 else "not found"}
        except Exception as e:
            results["ffmpeg"] = {"available": False, "detail": str(e)[:60]}

        # Check biliup
        try:
            from clipavenue.recorder.biliup import check_available as check_biliup
            avail, detail = check_biliup()
            results["biliup"] = {"available": avail, "detail": detail}
        except Exception as e:
            results["biliup"] = {"available": False, "detail": str(e)[:60]}

        # Check BililiveRecorder
        try:
            from clipavenue.recorder.bililive import check_available as check_bililive
            avail, detail = check_bililive()
            results["bililive"] = {"available": avail, "detail": detail}
        except Exception as e:
            results["bililive"] = {"available": False, "detail": str(e)[:60]}

        # Check bilibili login status
        logged_in = _check_bilibili_cookies()
        results["bilibili_logged_in"] = logged_in

        return {"tools": results, "recording_possible": results.get("ffmpeg", {}).get("available", False),
                "bilibili_logged_in": logged_in}

    @app.get("/api/login/qrcode")
    async def login_qrcode() -> dict:
        """Get Bilibili QR code login URL."""
        try:
            import stream_gears
            qrcode_data = stream_gears.get_qrcode(proxy=None)
            log.info("登录", "生成B站二维码")
            return {"success": True, "qrcode": qrcode_data}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    @app.post("/api/login/check")
    async def login_check(data: dict) -> dict:
        """Check QR code login status and save cookies."""
        try:
            import stream_gears, json
            ret = data.get("ret", "")
            if not ret:
                return {"success": False, "error": "missing ret"}
            result = stream_gears.login_by_qrcode(ret, proxy=None)
            if result:
                cookie_path = Path("cookies.json")
                # result is already a JSON string — parse to dict first, then save
                try:
                    cookie_data = json.loads(result) if isinstance(result, str) else result
                except json.JSONDecodeError:
                    cookie_data = {"raw": result}
                cookie_path.write_text(json.dumps(cookie_data, indent=2, ensure_ascii=False), encoding="utf-8")
                log.info("登录", "B站扫码登录成功，cookies已保存")
                return {"success": True}
            return {"success": False, "status": "pending"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    @app.post("/api/recorder/stop/{task_id}")
    async def recorder_stop(task_id: str) -> dict:
        global recorder_manager
        if not recorder_manager:
            raise HTTPException(status_code=503, detail="recorder manager not available")
        success = recorder_manager.stop_task(task_id)
        recorder_manager.save_state()
        hub.publish()
        return {"success": success, "task_id": task_id}

    @app.get("/api/recorder/tasks")
    async def recorder_tasks() -> dict:
        global recorder_manager
        if not recorder_manager:
            return {"tasks": [], "active_count": 0}
        return {
            "tasks": [t.to_dict() for t in recorder_manager.list_tasks()],
            "active_count": len(recorder_manager.active_tasks()),
        }

    @app.delete("/api/recorder/task/{task_id}")
    async def recorder_remove(task_id: str) -> dict:
        global recorder_manager
        if not recorder_manager:
            raise HTTPException(status_code=503, detail="recorder manager not available")
        recorder_manager.remove_task(task_id)
        recorder_manager.save_state()
        hub.publish()
        return {"success": True, "task_id": task_id}

    # ==================================================================
    # API — Storage Control
    # ==================================================================

    @app.get("/api/storage/status")
    async def storage_status() -> dict:
        global disk_monitor
        if not disk_monitor:
            return {"status": "unknown"}
        return disk_monitor.stats()

    @app.post("/api/storage/cleanup")
    async def storage_cleanup(data: dict) -> dict:
        """Run cleanup pass. Body: {"dry_run": true} (default) or {"dry_run": false}."""
        dry_run = data.get("dry_run", True)
        cfg = get_config()
        policy = RetentionPolicy.from_config(cfg)
        job = CleanupJob(
            projects_dir=PROJECTS_DIR,
            policy=policy,
            dry_run=dry_run,
        )
        result = job.run()
        hub.publish()
        return result

    @app.get("/api/storage/plan")
    async def storage_plan() -> dict:
        """Preview what would be cleaned up (dry-run plan)."""
        cfg = get_config()
        policy = RetentionPolicy.from_config(cfg)
        plan = policy.plan_all(PROJECTS_DIR)
        freed_gb = policy.estimate_freed_gb(plan)
        return {
            "plan": {k: [str(p) for p in v] for k, v in plan.items()},
            "estimated_freed_gb": freed_gb,
        }

    # ==================================================================
    # API — Clip Pipeline
    # ==================================================================

    @app.post("/api/clip/start")
    async def clip_start(data: dict) -> dict:
        """Enqueue a clip pipeline job to be processed by the agent worker.
        Returns immediately with the job_id.
        Body: {"project_id": "...", "video_path": "..."}
        """
        global queue
        project_id = data.get("project_id", "")
        video_path_str = data.get("video_path", "")

        if not project_id or not video_path_str:
            raise HTTPException(status_code=400, detail="project_id and video_path required")

        video_path = Path(video_path_str)
        if video_path.is_dir():
            for ext in ("*.flv", "*.mp4", "*.ts", "*.mkv", "*.mov"):
                files = list(video_path.rglob(ext))
                if files:
                    video_path = max(files, key=lambda p: p.stat().st_size)
                    log.info("剪辑", f"自动检测到视频: {video_path.name}")
                    break
        if not video_path.is_file():
            raise HTTPException(status_code=404, detail=f"video not found: {video_path_str}")

        project_dir = PROJECTS_DIR / project_id
        project_dir.mkdir(parents=True, exist_ok=True)

        # Write "in_progress" state for the dashboard
        clip_state = {"status": "queued", "project_id": project_id, "video_path": str(video_path)}
        clip_state_path = project_dir / "clip_state.json"
        clip_state_path.write_text(json.dumps(clip_state, indent=2), encoding="utf-8")

        if queue is None:
            queue = JobQueue(str(PROJECTS_DIR / "_queue" / "queue.db"))

        job_id = queue.enqueue(project_id=project_id, video_path=str(video_path))
        hub.publish()

        log.info("剪辑", f"已入队: {job_id} ({video_path.name})")
        return {"success": True, "status": "queued", "job_id": job_id, "project_id": project_id, "video": video_path.name}

    @app.get("/api/clip/status/{project_id}")
    async def clip_status(project_id: str) -> dict:
        """Get clip pipeline status for a project."""
        project_dir = PROJECTS_DIR / project_id
        state_path = project_dir / "clip_state.json"
        if not state_path.is_file():
            return {"status": "not_started", "project_id": project_id}
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            return data
        except (OSError, json.JSONDecodeError):
            return {"status": "error", "project_id": project_id}

    @app.get("/api/clip/queue")
    async def clip_queue() -> dict:
        """List all clip pipeline jobs and their statuses."""
        global queue
        if queue is None:
            return {"jobs": []}
        try:
            return {"jobs": queue.list_jobs()}
        except Exception as exc:
            return {"error": str(exc), "jobs": []}

    @app.get("/api/clip/analysis/{project_id}")
    async def clip_analysis(project_id: str) -> dict:
        """Get transcript analysis for a project."""
        project_dir = PROJECTS_DIR / project_id
        analysis_path = project_dir / "clip_analysis.json"
        if not analysis_path.is_file():
            return {"status": "not_analyzed"}
        try:
            data = json.loads(analysis_path.read_text(encoding="utf-8"))
            return data
        except (OSError, json.JSONDecodeError):
            return {"status": "error"}

    @app.get("/api/project/{project_id}/files")
    async def project_files(project_id: str) -> dict:
        """List video files in a project directory."""
        project_dir = PROJECTS_DIR / project_id
        if not project_dir.is_dir():
            return {"files": []}
        video_files = []
        for ext in ("*.flv", "*.flv.part", "*.mp4", "*.ts", "*.mkv", "*.mov"):
            for f in project_dir.rglob(ext):
                if f.is_file():
                    video_files.append({
                        "name": f.name,
                        "path": str(f.relative_to(project_dir)),
                        "size_mb": round(f.stat().st_size / (1024 * 1024), 1),
                    })
        video_files.sort(key=lambda x: -x["size_mb"])
        return {"files": video_files, "project_id": project_id}

    # ==================================================================
    # API — Upload Control
    # ==================================================================

    @app.post("/api/upload/start")
    async def upload_start(data: dict) -> dict:
        """Upload a clip to Bilibili.

        Body: {"project_id": "...", "file_path": "...", "title": "...", "tags": []}
        """
        global notifier  # defined below
        file_path = Path(data.get("file_path", ""))
        title = data.get("title", "")

        if not file_path.is_file():
            raise HTTPException(status_code=400, detail=f"file not found: {file_path}")

        task = UploadTask(
            task_id=f"up-{int(time.time())}",
            file_path=file_path,
            title=title or file_path.stem,
            tags=data.get("tags", []),
        )

        uploader = BiliUploader()
        uploader.upload(task)

        # Write upload state for dashboard
        project_id = data.get("project_id", "default")
        project_dir = PROJECTS_DIR / project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / "upload_state.json").write_text(
            json.dumps(task.to_dict(), indent=2), encoding="utf-8")

        hub.publish()
        return task.to_dict()

    @app.post("/api/upload/captcha")
    async def upload_captcha(data: dict) -> dict:
        """Submit captcha code for a pending upload."""
        project_id = data.get("project_id", "")
        captcha_code = data.get("code", "")
        if not captcha_code:
            raise HTTPException(status_code=400, detail="captcha code required")

        project_dir = PROJECTS_DIR / project_id
        state_path = project_dir / "upload_state.json"
        if not state_path.is_file():
            raise HTTPException(status_code=404, detail="no upload state found")

        try:
            task_data = json.loads(state_path.read_text(encoding="utf-8"))
            task = UploadTask(
                task_id=task_data["task_id"],
                file_path=Path(task_data["file_path"]),
                title=task_data.get("title", ""),
                tags=task_data.get("tags", []),
            )
            for k, v in task_data.items():
                if hasattr(task, k):
                    setattr(task, k, v)
        except (OSError, KeyError) as exc:
            raise HTTPException(status_code=500, detail=str(exc))

        uploader = BiliUploader()
        uploader.solve_captcha(task, captcha_code)

        state_path.write_text(json.dumps(task.to_dict(), indent=2), encoding="utf-8")
        hub.publish()
        return task.to_dict()

    @app.get("/api/upload/status/{project_id}")
    async def upload_status(project_id: str) -> dict:
        """Get upload status for a project."""
        project_dir = PROJECTS_DIR / project_id
        state_path = project_dir / "upload_state.json"
        if not state_path.is_file():
            return {"status": "not_uploaded"}
        try:
            return json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"status": "error"}

    # ==================================================================
    # API — Archive Control
    # ==================================================================

    @app.post("/api/archive/backup")
    async def archive_backup(data: dict) -> dict:
        """Backup a project directory.

        Body: {"project_id": "...", "dest_dir": "...", "compress": false}
        """
        project_id = data.get("project_id", "")
        dest_str = data.get("dest_dir", "")
        compress = data.get("compress", False)

        project_dir = PROJECTS_DIR / project_id
        if not project_dir.is_dir():
            raise HTTPException(status_code=404, detail=f"project not found: {project_id}")

        dest_dir = Path(dest_str) if dest_str else PROJECTS_DIR.parent / "backups"
        bm = BackupManager(dest_dir=dest_dir, compress=compress)
        result = bm.backup_project(project_dir)
        hub.publish()
        return result

    @app.post("/api/archive/cleanup")
    async def archive_cleanup(data: dict) -> dict:
        """Clean up project files after upload.

        Body: {"project_id": "...", "level": "clips_only|all_except_raw|full|none", "dry_run": true}
        """
        project_id = data.get("project_id", "")
        level = data.get("level", "clips_only")
        dry_run = data.get("dry_run", True)

        project_dir = PROJECTS_DIR / project_id
        if not project_dir.is_dir():
            raise HTTPException(status_code=404, detail=f"project not found: {project_id}")

        cleaner = PostUploadCleanup(level=level, dry_run=dry_run)
        result = cleaner.run(project_dir)
        if not dry_run:
            hub.publish()
        return result

    @app.post("/api/archive/notify")
    async def archive_notify(data: dict) -> dict:
        """Send a notification.

        Body: {"event": "...", "title": "...", "message": "...", "project_id": "..."}
        """
        notifier.send(
            event=data.get("event", "info"),
            title=data.get("title", ""),
            message=data.get("message", ""),
            data={"project_id": data.get("project_id")},
        )
        return {"success": True}

    # ==================================================================
    # API — Live Logs (SSE)
    # ==================================================================

    @app.get("/api/logs")
    async def get_logs(n: int = 50) -> list[dict]:
        """Get recent log entries."""
        return log.get_recent(n)

    @app.get("/api/logs/stream")
    async def logs_stream(request: Request) -> StreamingResponse:
        """SSE stream of live log entries."""
        from clipavenue.logger import LiveLog

        q: asyncio.Queue = asyncio.Queue(maxsize=128)

        def on_entry(entry: dict) -> None:
            try:
                q.put_nowait(entry)
            except asyncio.QueueFull:
                pass

        cancel = log.subscribe(on_entry)

        async def stream():
            try:
                yield _sse({"type": "hello", "msg": "日志连接已建立"})
                # Send recent entries on connection
                for entry in log.get_recent(20):
                    yield _sse({"type": "log", **entry})
                while True:
                    if await request.is_disconnected():
                        return
                    try:
                        entry = await asyncio.wait_for(q.get(), timeout=SSE_HEARTBEAT_SECONDS)
                        yield _sse({"type": "log", **entry})
                    except asyncio.TimeoutError:
                        yield _sse({"type": "heartbeat"})
            finally:
                cancel()

        return StreamingResponse(stream(), media_type="text/event-stream", headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        })

    # ==================================================================
    # UI
    # ==================================================================

    @app.get("/")
    async def dashboard_page() -> FileResponse:
        return FileResponse(UI_DIR / "board.html")

    if UI_DIR.is_dir():
        app.mount("/ui", StaticFiles(directory=UI_DIR), name="ui")

    return app


app = create_app()