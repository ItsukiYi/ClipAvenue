"""BililiveRecorder wrapper — B站直播录制专用.

https://github.com/BililiveRecorder/BililiveRecorder

如果 BililiveRecorder 未安装，自动降级到 biliup (stream_gears) 录制。
B站直播流不能用 ffmpeg 直接录制（需要特殊协议处理）。
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional

from clipavenue.recorder.task import RecorderStatus, RecorderTask


DEFAULT_RECORDER_PATH = "BililiveRecorder.Cli"


def _find_recorder(custom_path: Optional[str] = None) -> Optional[str]:
    """Resolve the BililiveRecorder binary path. Returns None if not found."""
    candidates = []
    if custom_path:
        candidates.append(custom_path)
    env_path = os.environ.get("BILILIVE_RECORDER_PATH")
    if env_path:
        candidates.append(env_path)
    candidates.extend([
        DEFAULT_RECORDER_PATH,
        "BililiveRecorder.Cli.exe",
        "BililiveRecorder",
        "BililiveRecorder.exe",
    ])

    for name in candidates:
        try:
            result = subprocess.run(
                [name, "--version"],
                capture_output=True, timeout=5,
            )
            if result.returncode in (0, 1):
                return name
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            continue
    return None


def check_available() -> tuple[bool, str]:
    """Check if BililiveRecorder is installed."""
    binary = _find_recorder()
    if binary:
        return True, f"找到: {binary}"
    return False, (
        "BililiveRecorder 未安装，已自动降级到 biliup\n"
        "下载: https://github.com/BililiveRecorder/BililiveRecorder/releases"
    )


def start_recording(task: RecorderTask, recorder_path: Optional[str] = None) -> bool:
    """Start BililiveRecorder, or fall back to biliup if not installed."""
    task.output_dir.mkdir(parents=True, exist_ok=True)

    binary = _find_recorder(recorder_path)
    if binary is None:
        print("clipavenue: BililiveRecorder not found, falling back to biliup")
        from clipavenue.recorder.biliup import start_recording as biliup_start
        task.recorder_type = "biliup"
        return biliup_start(task)

    cmd = [binary, "record", "--url", task.url, "--output", str(task.output_dir)]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        print("clipavenue: BililiveRecorder not found, falling back to biliup")
        from clipavenue.recorder.biliup import start_recording as biliup_start
        task.recorder_type = "biliup"
        return biliup_start(task)
    except Exception as exc:
        print(f"clipavenue: BililiveRecorder error ({exc}), falling back to biliup")
        from clipavenue.recorder.biliup import start_recording as biliup_start
        task.recorder_type = "biliup"
        return biliup_start(task)

    task.start_recording(proc.pid)
    task.recorder_type = "bililive"
    task.recorder_info = f"BililiveRecorder (PID {proc.pid})"
    task.write_state()
    return True


def stop_recording(task: RecorderTask) -> bool:
    """Stop a recording process. Delegates to biliup if it fell back."""
    if task.recorder_type == "biliup":
        from clipavenue.recorder.biliup import stop_recording as biliup_stop
        return biliup_stop(task)

    if task.pid is None:
        return False

    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(task.pid), "/T"],
                capture_output=True, timeout=5,
            )
        else:
            os.kill(task.pid, 15)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        pass

    task.mark_stopped()
    task.write_state()
    return True


def check_recording(task: RecorderTask) -> RecorderStatus:
    """Check recording status. Delegates to biliup if it fell back."""
    if task.recorder_type == "biliup":
        from clipavenue.recorder.biliup import check_recording as biliup_check
        return biliup_check(task)

    if task.pid is None:
        return RecorderStatus.FAILED

    try:
        if os.name == "nt":
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {task.pid}", "/NH"],
                capture_output=True, text=True, timeout=5,
            )
            alive = str(task.pid) in result.stdout
        else:
            os.kill(task.pid, 0)
            alive = True
    except (OSError, subprocess.TimeoutExpired):
        alive = False

    if not alive and task.status == RecorderStatus.RECORDING:
        task.mark_failed("进程意外退出")
        task.write_state()
        return RecorderStatus.FAILED

    task.heartbeat()
    return task.status