"""biliup wrapper — 使用 biliup CLI 录制直播.

直接使用 biliup CLI (biliup download <URL>)，完全照搬其下载逻辑。
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Optional

from clipavenue.recorder.task import RecorderStatus, RecorderTask
from clipavenue.logger import log


DEFAULT_BILIUP_PATH = "biliup"


def _find_biliup() -> Optional[str]:
    """Find the biliup executable."""
    import shutil, sys as _sys

    # Check PATH
    which = shutil.which("biliup")
    if which:
        return which

    # Check venv Scripts
    scripts = Path(_sys.executable).parent
    for name in ("biliup", "biliup.exe", "biliup-cli", "biliup-cli.exe"):
        candidate = scripts / name
        if candidate.is_file():
            return str(candidate)

    return None


def check_available() -> tuple[bool, str]:
    """Check if biliup CLI is available."""
    binary = _find_biliup()
    if not binary:
        return False, "biliup not found. Install: pip install biliup"
    try:
        r = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return True, f"biliup CLI: {r.stdout.strip() or r.stderr.strip()}"
        return False, f"biliup error: {r.stderr[:100]}"
    except Exception as exc:
        return False, str(exc)[:60]


def start_recording(task: RecorderTask, biliup_path: Optional[str] = None) -> bool:
    """Start recording via biliup CLI:
        biliup download <URL> -o <output_template>

    完全照搬 biliup CLI 的下载逻辑，用子进程执行。
    """
    binary = _find_biliup()
    if not binary:
        task.mark_failed("biliup 未安装，运行: pip install biliup")
        task.write_state()
        return False

    task.output_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(task.output_dir / "{title}")

    cmd = [binary, "download", task.url, "-o", output_template]

    log.info("biliup", f"启动: {' '.join(cmd)}")

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        task.mark_failed(f"biliup 未找到: {binary}")
        task.write_state()
        return False
    except Exception as exc:
        task.mark_failed(str(exc))
        task.write_state()
        return False

    task.start_recording(pid=proc.pid)
    task.recorder_type = "biliup"
    task.recorder_info = f"biliup download (PID {proc.pid})"
    task._process = proc
    task.write_state()
    log.info("biliup", f"biliup CLI 已启动 (PID {proc.pid})")
    return True


def stop_recording(task: RecorderTask) -> bool:
    """Stop the biliup process."""
    proc = getattr(task, "_process", None)
    if proc and proc.poll() is None:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T"],
                           capture_output=True, timeout=5)
        else:
            proc.terminate()
    task.mark_stopped()
    task.write_state()
    return True


def check_recording(task: RecorderTask) -> RecorderStatus:
    """Check biliup process status."""
    proc = getattr(task, "_process", None)
    if proc is None:
        return task.status

    ret = proc.poll()

    if ret is None:
        # Still running
        task.heartbeat()
        return RecorderStatus.RECORDING

    # Process exited
    if ret != 0:
        stderr = proc.stderr.read().decode("utf-8", errors="replace")[:200] if proc.stderr else ""
        task.mark_failed(f"biliup 退出(code={ret}): {stderr}")
        task.write_state()
        return RecorderStatus.FAILED

    # Success - check for output files
    for ext in ("*.flv", "*.ts", "*.mp4"):
        for f in task.output_dir.rglob(ext):
            if f.is_file() and f.stat().st_size > 1024:
                task.mark_completed()
                task.output_path = str(f)
                task.write_state()
                return RecorderStatus.COMPLETED

    task.mark_failed("主播未开播或无录制内容")
    task.write_state()
    return RecorderStatus.FAILED