"""RecorderManager — orchestrate live stream recording tasks.

Manages the lifecycle of multiple RecorderTask instances:
- Watch for stream availability → start recording
- Monitor recording health → restart on failure
- Write state to projects/<live-id>/recorder_state.json
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

from clipavenue.recorder.task import RecorderStatus, RecorderTask
from clipavenue.config import get as get_config
from clipavenue.logger import log


class RecorderManager:
    """Manages all active recording tasks."""

    def __init__(self, projects_dir: Optional[Path] = None) -> None:
        from clipavenue.lib_paths import PROJECTS_DIR
        self._projects_dir = projects_dir or PROJECTS_DIR
        self._tasks: dict[str, RecorderTask] = {}
        self._watch_interval: float = 60.0  # seconds between stream probes

    # ── task management ───────────────────────────────────────

    def add_task(self, task: RecorderTask) -> None:
        """Register a new recording task."""
        self._tasks[task.task_id] = task
        task.write_state()

    def remove_task(self, task_id: str) -> None:
        """Remove and stop a task."""
        if task_id in self._tasks:
            self.stop_task(task_id)
            del self._tasks[task_id]

    def get_task(self, task_id: str) -> Optional[RecorderTask]:
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[RecorderTask]:
        return list(self._tasks.values())

    def active_tasks(self) -> list[RecorderTask]:
        return [t for t in self._tasks.values() if t.alive]

    @property
    def task_count(self) -> int:
        return len(self._tasks)

    # ── lifecycle ─────────────────────────────────────────────

    def start_task(self, task_id: str) -> bool:
        """Start recording for a task. Returns True if started."""
        task = self._tasks.get(task_id)
        if not task:
            log.error("管理器", f"任务 {task_id} 不存在")
            return False

        log.info("管理器", f"启动录制: {task.streamer} @ {task.platform} ({task.url[:50]})")

        if task.recorder_type == "bililive":
            from clipavenue.recorder.bililive import start_recording as start_fn
        elif task.recorder_type == "biliup":
            from clipavenue.recorder.biliup import start_recording as start_fn
        else:
            task.mark_failed(f"Unknown recorder type: {task.recorder_type}")
            task.write_state()
            return False

        success = start_fn(task)
        task.write_state()
        if success:
            log.info("管理器", f"录制进程已启动 (PID {task.pid}) — {task.recorder_info}")
        else:
            log.error("管理器", f"录制启动失败: {task.error}")
        return success

    def stop_task(self, task_id: str) -> bool:
        """Stop a recording task."""
        task = self._tasks.get(task_id)
        if not task:
            return False

        if task.recorder_type == "bililive":
            from clipavenue.recorder.bililive import stop_recording as stop_fn
        elif task.recorder_type == "biliup":
            from clipavenue.recorder.biliup import stop_recording as stop_fn
        else:
            return False

        result = stop_fn(task)
        task.write_state()
        return result

    # ── health check loop ─────────────────────────────────────

    def tick(self) -> None:
        """One health-check tick. Call periodically from a scheduler."""
        for task in list(self._tasks.values()):
            if not task.alive:
                continue

            if task.recorder_type == "bililive":
                from clipavenue.recorder.bililive import check_recording
            else:
                from clipavenue.recorder.biliup import check_recording

            status = check_recording(task)

            if status == RecorderStatus.FAILED:
                log.warn("管理器", f"录制失败: {task.streamer} — {task.error}")
                if task.retry_count < task.max_retries:
                    log.info("管理器", f"自动重试 ({task.retry_count + 1}/{task.max_retries})")
                    self.start_task(task.task_id)
                else:
                    log.error("管理器", f"重试耗尽，放弃录制 {task.streamer}")
            elif status == RecorderStatus.COMPLETED:
                log.info("管理器", f"录制完成: {task.streamer} → {task.output_path}")
            elif status == RecorderStatus.RECORDING:
                pass  # 正常运行中，不刷日志

            task.write_state()

            task.write_state()

    # ── serialization ─────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "tasks": [t.to_dict() for t in self._tasks.values()],
            "active_count": len(self.active_tasks()),
            "total_count": len(self._tasks),
            "watch_interval": self._watch_interval,
        }

    def save_state(self) -> None:
        """Write manager state to a well-known path."""
        path = self._projects_dir / ".clipavenue_recorder_state.json"
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    def load_state(self) -> None:
        """Restore manager state from disk.
        First tries global state file, then scans projects/ for orphaned tasks.
        """
        # 1. Load from global state file
        path = self._projects_dir / ".clipavenue_recorder_state.json"
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                for tdata in data.get("tasks", []):
                    task = RecorderTask.from_dict(tdata)
                    self._tasks[task.task_id] = task
            except (OSError, json.JSONDecodeError) as exc:
                print(f"clipavenue: could not load recorder state: {exc}")

        # 2. Scan projects/ for individual recorder_state.json files
        if not self._projects_dir.is_dir():
            return
        for entry in sorted(self._projects_dir.iterdir()):
            if not entry.is_dir() or entry.name.startswith(("_", ".")):
                continue
            state_file = entry / "recorder_state.json"
            if not state_file.is_file():
                continue
            try:
                data = json.loads(state_file.read_text(encoding="utf-8"))
                task_id = data.get("task_id", entry.name)
                if task_id not in self._tasks:
                    task = RecorderTask.from_dict(data)
                    self._tasks[task.task_id] = task
            except (OSError, json.JSONDecodeError):
                continue

    def __repr__(self) -> str:
        return f"<RecorderManager {len(self._tasks)} tasks, {len(self.active_tasks())} active>"