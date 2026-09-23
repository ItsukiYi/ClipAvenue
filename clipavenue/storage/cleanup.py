"""CleanupJob — executes file cleanup according to retention policy."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Optional

from clipavenue.storage.policy import RetentionPolicy


class CleanupJob:
    """Execute a cleanup pass: find expired files and delete them.

    Logs all deletions to a cleanup log for audit.
    """

    def __init__(
        self,
        projects_dir: Path,
        policy: RetentionPolicy,
        dry_run: bool = False,
        log_path: Optional[Path] = None,
    ) -> None:
        self.projects_dir = projects_dir
        self.policy = policy
        self.dry_run = dry_run
        self.log_path = log_path or (projects_dir / ".clipavenue_cleanup_log.jsonl")

    def run(self) -> dict:
        """Execute one cleanup pass. Returns summary dict."""
        now = time.time()
        plan = self.policy.plan_all(self.projects_dir)

        deleted_count = 0
        deleted_gb = 0.0
        errors: list[str] = []

        for category, files in plan.items():
            for f in files:
                if f.is_file():
                    size_gb = f.stat().st_size / (1024 ** 3)
                    if self.dry_run:
                        print(f"clipavenue: would delete {f} ({size_gb:.2f} GB) [{category}]")
                    else:
                        try:
                            f.unlink()
                            deleted_count += 1
                            deleted_gb += size_gb
                            self._log(category, str(f), size_gb, now)
                        except OSError as exc:
                            errors.append(str(exc))

        # Also remove empty directories
        for f in sorted(self.projects_dir.rglob("*"), key=lambda p: len(str(p)), reverse=True):
            if f.is_dir() and not any(f.iterdir()):
                try:
                    if not self.dry_run:
                        f.rmdir()
                except OSError:
                    errors.append(f"could not rmdir {f}")

        summary = {
            "timestamp": now,
            "dry_run": self.dry_run,
            "deleted_count": deleted_count,
            "deleted_gb": round(deleted_gb, 2),
            "error_count": len(errors),
            "errors": errors[:5],
        }

        # Write summary to a well-known path
        summary_path = self.projects_dir / ".clipavenue_cleanup_summary.json"
        if not self.dry_run:
            summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        return summary

    def _log(self, category: str, path: str, size_gb: float, ts: float) -> None:
        """Append one deletion event to the audit log."""
        entry = {
            "ts": ts,
            "category": category,
            "path": path,
            "size_gb": round(size_gb, 4),
        }
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            pass