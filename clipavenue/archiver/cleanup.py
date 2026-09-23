"""PostUploadCleanup — remove local files after successful upload.

Manages the "after publishing, delete local clip files" workflow,
with configurable retention for raw recordings vs clips vs temp.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any, Optional


class PostUploadCleanup:
    """Clean up project files after upload is complete.

    Cleanup levels:
      - clips_only: delete clips/ and renders/ (keep raw recording + transcript)
      - all_except_raw: delete clips, renders, transcripts (keep raw flv/mp4)
      - full: delete the entire project directory
      - none: no cleanup (manual)
    """

    def __init__(
        self,
        level: str = "clips_only",
        dry_run: bool = False,
    ) -> None:
        self.level = level
        self.dry_run = dry_run

    def run(self, project_dir: Path) -> dict[str, Any]:
        """Execute cleanup for a project.

        Returns summary of what was deleted.
        """
        if not project_dir.is_dir():
            return {"success": False, "error": "project dir not found"}

        summary: dict[str, Any] = {
            "project": project_dir.name,
            "level": self.level,
            "dry_run": self.dry_run,
            "deleted_dirs": [],
            "deleted_files": 0,
            "freed_mb": 0.0,
            "errors": [],
        }

        actions = self._plan(project_dir)

        for action in actions:
            path = action["path"]
            label = action["label"]
            if action["type"] == "dir":
                if path.is_dir():
                    size = self._dir_size(path)
                    file_count = sum(1 for _ in path.rglob("*")) if path.is_dir() else 0
                    if self.dry_run:
                        print(f"clipavenue: would delete {label} ({size:.1f} MB)")
                    else:
                        try:
                            shutil.rmtree(path)
                            summary["deleted_dirs"].append(label)
                            summary["freed_mb"] += size
                        except OSError as exc:
                            summary["errors"].append(f"{label}: {exc}")
                    summary["deleted_files"] += file_count
            elif action["type"] == "file":
                if path.is_file():
                    size = path.stat().st_size / (1024 * 1024)
                    if self.dry_run:
                        print(f"clipavenue: would delete {label} ({size:.1f} MB)")
                    else:
                        try:
                            path.unlink()
                            summary["deleted_files"] += 1
                            summary["freed_mb"] += size
                        except OSError as exc:
                            summary["errors"].append(f"{label}: {exc}")

        summary["freed_mb"] = round(summary["freed_mb"], 2)
        return summary

    def _plan(self, project_dir: Path) -> list[dict]:
        """Build a list of deletion actions based on cleanup level."""
        actions: list[dict] = []

        # Common to all levels except "none"
        if self.level == "none":
            return actions

        # Always clean temp audio files
        audio_dir = project_dir / "audio"
        if audio_dir.is_dir():
            actions.append({"type": "dir", "path": audio_dir, "label": "audio/"})

        # clips_only or higher: clean clips and renders
        if self.level in ("clips_only", "all_except_raw", "full"):
            clips_dir = project_dir / "clips"
            if clips_dir.is_dir():
                actions.append({"type": "dir", "path": clips_dir, "label": "clips/"})
            renders_dir = project_dir / "renders"
            if renders_dir.is_dir():
                actions.append({"type": "dir", "path": renders_dir, "label": "renders/"})

        # all_except_raw or higher: clean transcripts too
        if self.level in ("all_except_raw", "full"):
            transcripts_dir = project_dir / "transcripts"
            if transcripts_dir.is_dir():
                actions.append({"type": "dir", "path": transcripts_dir, "label": "transcripts/"})
            # State files
            for fname in ("clip_state.json", "clip_analysis.json", "recorder_state.json"):
                f = project_dir / fname
                if f.is_file():
                    actions.append({"type": "file", "path": f, "label": fname})

        # full: remove entire project
        if self.level == "full":
            actions.append({"type": "dir", "path": project_dir, "label": project_dir.name})

        return actions

    @staticmethod
    def _dir_size(path: Path) -> float:
        total = 0.0
        try:
            for f in path.rglob("*"):
                if f.is_file():
                    total += f.stat().st_size
        except OSError:
            pass
        return total / (1024 * 1024)