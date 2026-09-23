"""BackupManager — archive recordings and clips to backup location.

Supports:
- Copy/move to another directory (local or network mounted)
- Optional compression before backup
- Retention: keep N latest backups per project
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Optional


class BackupManager:
    """Backup project files to a destination directory.

    Backup modes:
      - copy: duplicate files (default)
      - move: relocate files (frees local space)
      - compress: tar.gz the project first, then copy
    """

    def __init__(
        self,
        dest_dir: Path,
        mode: str = "copy",
        max_backups: int = 10,
        compress: bool = False,
    ) -> None:
        self.dest_dir = dest_dir
        self.mode = mode
        self.max_backups = max_backups
        self.compress = compress

    # ── backup a project ──────────────────────────────────────

    def backup_project(self, project_dir: Path) -> dict[str, Any]:
        """Backup an entire project directory.

        Returns backup result metadata.
        """
        if not project_dir.is_dir():
            return {"success": False, "error": f"directory not found: {project_dir}"}

        project_name = project_dir.name
        timestamp = int(time.time())
        backup_name = f"{project_name}_{timestamp}"
        self.dest_dir.mkdir(parents=True, exist_ok=True)

        if self.compress:
            return self._backup_compress(project_dir, backup_name)
        else:
            return self._backup_copy(project_dir, backup_name)

    def _backup_copy(self, project_dir: Path, backup_name: str) -> dict[str, Any]:
        """Copy project to backup destination."""
        dest = self.dest_dir / backup_name
        project_name = project_dir.name
        start = time.time()

        try:
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(project_dir, dest, ignore=shutil.ignore_patterns(
                "__pycache__", "node_modules", ".cache",
            ))
        except OSError as exc:
            return {"success": False, "error": str(exc)}

        elapsed = time.time() - start
        size_mb = self._dir_size(dest) / (1024 * 1024)

        self._prune_old(project_name)
        self._write_manifest(backup_name, project_dir, dest, size_mb, "copy")

        return {
            "success": True,
            "backup_name": backup_name,
            "backup_path": str(dest),
            "size_mb": round(size_mb, 1),
            "duration_seconds": round(elapsed, 1),
        }

    def _backup_compress(self, project_dir: Path, backup_name: str) -> dict[str, Any]:
        """Create a compressed archive of the project."""
        archive_path = self.dest_dir / f"{backup_name}.tar.gz"
        start = time.time()

        try:
            subprocess.run(
                ["tar", "-czf", str(archive_path),
                 "-C", str(project_dir.parent), project_dir.name],
                capture_output=True, timeout=1800,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            return {"success": False, "error": str(exc)}

        elapsed = time.time() - start
        size_mb = archive_path.stat().st_size / (1024 * 1024) if archive_path.is_file() else 0

        return {
            "success": True,
            "backup_name": f"{backup_name}.tar.gz",
            "backup_path": str(archive_path),
            "size_mb": round(size_mb, 1),
            "duration_seconds": round(elapsed, 1),
        }

    # ── cleanup old backups ───────────────────────────────────

    def _prune_old(self, project_name: str) -> None:
        """Remove oldest backups for a project if over max_backups."""
        backups = sorted(self.dest_dir.glob(f"{project_name}_*"))
        if self.compress:
            backups = [p for p in backups if p.suffix == ".gz"]

        while len(backups) > self.max_backups:
            oldest = backups.pop(0)
            try:
                if oldest.is_dir():
                    shutil.rmtree(oldest)
                else:
                    oldest.unlink()
                print(f"clipavenue: pruned old backup {oldest.name}")
            except OSError as exc:
                print(f"clipavenue: could not prune {oldest}: {exc}")

    # ── helpers ───────────────────────────────────────────────

    @staticmethod
    def _dir_size(path: Path) -> int:
        total = 0
        try:
            for f in path.rglob("*"):
                if f.is_file():
                    total += f.stat().st_size
        except OSError:
            pass
        return total

    def _write_manifest(
        self, backup_name: str, src: Path, dest: Path,
        size_mb: float, mode: str,
    ) -> None:
        manifest = {
            "backup_name": backup_name,
            "source": str(src),
            "destination": str(dest),
            "size_mb": round(size_mb, 1),
            "mode": mode,
            "timestamp": time.time(),
        }
        try:
            (dest / ".backup_manifest.json").write_text(
                json.dumps(manifest, indent=2), encoding="utf-8",
            )
        except OSError:
            pass