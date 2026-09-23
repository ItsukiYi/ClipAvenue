"""Recording task data model — state machine, serialization."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class RecorderStatus(str, Enum):
    IDLE = "idle"
    WATCHING = "watching"          # monitoring for stream start
    RECORDING = "recording"        # actively capturing
    COMPLETED = "completed"        # recording finished normally
    FAILED = "failed"              # error / crash
    STOPPED = "stopped"            # manually stopped


class RecorderTask:
    """A single live-stream recording task.

    State machine::

        IDLE → WATCHING → RECORDING → COMPLETED
                          → RECORDING → FAILED (auto-restart → RECORDING)
        IDLE → STOPPED (manual)
    """

    def __init__(
        self,
        task_id: str,
        platform: str,
        url: str,
        streamer: str,
        output_dir: Path,
        recorder_type: str = "bililive",
    ) -> None:
        self.task_id = task_id
        self.platform = platform          # "bilibili" | "douyin"
        self.url = url
        self.streamer = streamer
        self.output_dir = output_dir
        self.recorder_type = recorder_type
        self.status = RecorderStatus.IDLE
        self.pid: Optional[int] = None     # subprocess PID
        self.started_at: Optional[float] = None
        self.duration_seconds: float = 0.0
        self.error: Optional[str] = None
        self.retry_count: int = 0
        self.max_retries: int = 3
        self.eta: Optional[str] = None
        self.output_path: Optional[str] = None  # ffmpeg fallback output path
        self.recorder_info: Optional[str] = None  # human-readable recorder info
        self._heartbeat_ts: float = 0.0

    # ── transitions ──────────────────────────────────────────

    def start_watch(self) -> None:
        self.status = RecorderStatus.WATCHING
        self._heartbeat_ts = time.time()

    def start_recording(self, pid: int) -> None:
        self.status = RecorderStatus.RECORDING
        self.pid = pid
        self.started_at = time.time()
        self._heartbeat_ts = time.time()

    def mark_completed(self) -> None:
        self.status = RecorderStatus.COMPLETED
        if self.started_at:
            self.duration_seconds = time.time() - self.started_at

    def mark_failed(self, error: str) -> None:
        self.status = RecorderStatus.FAILED
        self.error = error
        self.retry_count += 1

    def mark_stopped(self) -> None:
        self.status = RecorderStatus.STOPPED
        if self.started_at:
            self.duration_seconds = time.time() - self.started_at

    def heartbeat(self) -> None:
        self._heartbeat_ts = time.time()

    @property
    def alive(self) -> bool:
        """True if the task is in a running state."""
        return self.status in (RecorderStatus.WATCHING, RecorderStatus.RECORDING)

    @property
    def stale_seconds(self) -> float:
        """Seconds since last heartbeat. 0 if never heartbeated."""
        if not self._heartbeat_ts:
            return 0.0
        return time.time() - self._heartbeat_ts

    # ── serialization ────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "platform": self.platform,
            "url": self.url,
            "streamer": self.streamer,
            "output_dir": str(self.output_dir),
            "recorder_type": self.recorder_type,
            "status": self.status.value,
            "pid": self.pid,
            "started_at": self.started_at,
            "duration_seconds": round(self.duration_seconds, 1),
            "error": self.error,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "eta": self.eta,
            "output_path": self.output_path,
            "recorder_info": self.recorder_info,
            "heartbeat_ts": self._heartbeat_ts,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RecorderTask":
        task = cls(
            task_id=data["task_id"],
            platform=data["platform"],
            url=data["url"],
            streamer=data["streamer"],
            output_dir=Path(data["output_dir"]),
            recorder_type=data.get("recorder_type", "bililive"),
        )
        task.status = RecorderStatus(data.get("status", "idle"))
        task.pid = data.get("pid")
        task.started_at = data.get("started_at")
        task.duration_seconds = data.get("duration_seconds", 0.0)
        task.error = data.get("error")
        task.retry_count = data.get("retry_count", 0)
        task.max_retries = data.get("max_retries", 3)
        task.eta = data.get("eta")
        task.output_path = data.get("output_path")
        task.recorder_info = data.get("recorder_info")
        task._heartbeat_ts = data.get("heartbeat_ts", 0.0)
        return task

    def write_state(self) -> None:
        """Write task state to project dir as recorder_state.json."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / "recorder_state.json"
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    def __repr__(self) -> str:
        return (
            f"<RecorderTask {self.task_id} [{self.platform}] "
            f"{self.streamer} → {self.status.value}>"
        )