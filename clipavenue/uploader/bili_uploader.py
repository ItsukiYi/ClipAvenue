"""BiliUploader — upload clips to Bilibili via biliup-rs CLI.

biliup-rs (https://github.com/biliup/biliup-rs) is a Rust CLI tool for
Bilibili upload. This wrapper manages the upload lifecycle:

    PENDING → UPLOADING → CAPTCHA (if needed) → VERIFIED → SUCCESS
                                                          → FAILED (retry)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class UploadStatus(str, Enum):
    PENDING = "pending"
    UPLOADING = "uploading"
    CAPTCHA = "captcha"        # needs human to solve captcha
    VERIFIED = "verified"      # captcha solved, retrying
    SUCCESS = "completed"
    FAILED = "failed"


class UploadTask:
    """A single upload task for one clip."""

    def __init__(
        self,
        task_id: str,
        file_path: Path,
        title: str = "",
        description: str = "",
        tags: Optional[list[str]] = None,
    ) -> None:
        self.task_id = task_id
        self.file_path = file_path
        self.title = title or file_path.stem
        self.description = description
        self.tags = tags or []
        self.status = UploadStatus.PENDING
        self.bvid: Optional[str] = None          # B站 video ID on success
        self.error: Optional[str] = None
        self.captcha_url: Optional[str] = None    # captcha image URL if needed
        self.captcha_solved: bool = False
        self.retry_count: int = 0
        self.max_retries: int = 3
        self.started_at: Optional[float] = None
        self.completed_at: Optional[float] = None
        self.duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "file_path": str(self.file_path),
            "title": self.title,
            "description": self.description,
            "tags": self.tags,
            "status": self.status.value,
            "bvid": self.bvid,
            "error": self.error,
            "captcha_url": self.captcha_url,
            "captcha_needed": self.captcha_url is not None,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": round(self.duration_seconds, 1),
        }


class BiliUploader:
    """Manages Bilibili upload via biliup-rs CLI.

    Flow:
    1. upload(task) → spawns biliup upload process
    2. If captcha needed → sets task.status = CAPTCHA, stores captcha_url
    3. solve_captcha(task, code) → retries upload with captcha code
    4. On success → stores bvid
    5. On failure → retries up to max_retries
    """

    def __init__(
        self,
        biliup_path: str = "biliup",
        max_retries: int = 3,
        upload_timeout: int = 600,
    ) -> None:
        self._biliup_path = os.environ.get("BILIUP_PATH") or biliup_path
        self.max_retries = max_retries
        self.upload_timeout = upload_timeout

    # ── upload ────────────────────────────────────────────────

    def upload(self, task: UploadTask) -> UploadTask:
        """Execute one upload attempt.

        Returns the updated task (in-place modification).
        """
        file_path = task.file_path
        if not file_path.is_file():
            task.status = UploadStatus.FAILED
            task.error = f"file not found: {file_path}"
            return task

        task.status = UploadStatus.UPLOADING
        task.started_at = time.time()
        print(f"clipavenue: uploading {file_path.name}...")

        # Build biliup upload command
        # biliup-rs: biliup upload --title "..." --desc "..." --tag tag1,tag2 file.mp4
        cmd = [self._biliup_path, "upload"]
        if task.title:
            cmd.extend(["--title", task.title])
        if task.description:
            cmd.extend(["--desc", task.description])
        if task.tags:
            cmd.extend(["--tag", ",".join(task.tags)])
        cmd.append(str(file_path))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True, text=True,
                timeout=self.upload_timeout,
            )
        except subprocess.TimeoutExpired:
            task.status = UploadStatus.FAILED
            task.error = "upload timed out"
            return task
        except FileNotFoundError:
            task.status = UploadStatus.FAILED
            task.error = f"biliup not found: {self._biliup_path}"
            return task
        except Exception as exc:
            task.status = UploadStatus.FAILED
            task.error = str(exc)
            return task

        stdout = result.stdout or ""
        stderr = result.stderr or ""

        # Check for captcha
        if self._detect_captcha(stdout, stderr):
            task.status = UploadStatus.CAPTCHA
            task.captcha_url = self._extract_captcha_url(stdout, stderr)
            print(f"clipavenue: captcha required for {file_path.name}")
            return task

        # Check for success
        bvid = self._extract_bvid(stdout, stderr)
        if bvid:
            task.status = UploadStatus.SUCCESS
            task.bvid = bvid
            task.completed_at = time.time()
            task.duration_seconds = task.completed_at - (task.started_at or task.completed_at)
            print(f"clipavenue: upload success — {bvid}")
            return task

        # Failure
        error_msg = self._extract_error(stdout, stderr)
        task.status = UploadStatus.FAILED
        task.error = error_msg or "unknown upload error"
        task.retry_count += 1
        print(f"clipavenue: upload failed — {task.error}")

        return task

    # ── captcha handling ──────────────────────────────────────

    def solve_captcha(self, task: UploadTask, captcha_code: str) -> UploadTask:
        """Re-upload after solving a captcha.

        biliup typically reads the captcha code from a file or env var.
        We write it to a well-known path and re-run.
        """
        # Write captcha code to a temp file that biliup can read
        captcha_file = task.file_path.parent / ".biliup_captcha.txt"
        try:
            captcha_file.write_text(captcha_code.strip(), encoding="utf-8")
        except OSError as exc:
            task.status = UploadStatus.FAILED
            task.error = f"could not write captcha file: {exc}"
            return task

        # Set env for biliup and retry
        old_env = os.environ.get("BILIUP_CAPTCHA_CODE")
        os.environ["BILIUP_CAPTCHA_CODE"] = captcha_code.strip()

        try:
            return self.upload(task)
        finally:
            if old_env is None:
                os.environ.pop("BILIUP_CAPTCHA_CODE", None)
            else:
                os.environ["BILIUP_CAPTCHA_CODE"] = old_env

    # ── result parsing ────────────────────────────────────────

    @staticmethod
    def _detect_captcha(stdout: str, stderr: str) -> bool:
        combined = (stdout + stderr).lower()
        return any(kw in combined for kw in ["captcha", "验证码", "verification"])

    @staticmethod
    def _extract_captcha_url(stdout: str, stderr: str) -> Optional[str]:
        # Look for URL patterns in output
        combined = stdout + stderr
        url_match = re.search(r'https?://[^\s]+(?:captcha|verify|qrcode)[^\s]*', combined, re.IGNORECASE)
        if url_match:
            return url_match.group(0)
        # Look for image file paths
        img_match = re.search(r'([^\s]+\.(?:png|jpg|jpeg|gif))', combined)
        if img_match:
            return img_match.group(1)
        return None

    @staticmethod
    def _extract_bvid(stdout: str, stderr: str) -> Optional[str]:
        combined = stdout + stderr
        match = re.search(r'(BV[a-zA-Z0-9]{10,})', combined)
        if match:
            return match.group(1)
        match = re.search(r'"bvid"\s*:\s*"([^"]+)"', combined)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def _extract_error(stdout: str, stderr: str) -> Optional[str]:
        # Take the last non-empty error-like line
        combined = (stdout + "\n" + stderr).strip()
        lines = [l.strip() for l in combined.split("\n") if l.strip()]
        for line in reversed(lines):
            if any(kw in line.lower() for kw in ["error", "fail", "err:", "错误", "失败"]):
                return line[:200]
        # Return the last line as fallback
        return lines[-1] if lines else None

    # ── batch upload ──────────────────────────────────────────

    def upload_batch(self, file_paths: list[Path], **kwargs) -> list[UploadTask]:
        """Upload multiple files, returning a list of UploadTasks."""
        tasks = []
        for i, file_path in enumerate(file_paths):
            task = UploadTask(
                task_id=f"upload-{int(time.time())}-{i}",
                file_path=file_path,
                **kwargs,
            )
            self.upload(task)
            tasks.append(task)
        return tasks