"""DiskMonitor — periodic disk usage tracking."""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Callable, Optional


class DiskMonitor:
    """Monitor disk space for a given path.

    Calls the warning_callback and critical_callback when thresholds
    are crossed, but only fires once per crossing (not every tick).
    """

    def __init__(
        self,
        watch_dir: Path,
        warning_pct: float = 85.0,
        critical_pct: float = 95.0,
        warning_callback: Optional[Callable] = None,
        critical_callback: Optional[Callable] = None,
    ) -> None:
        self.watch_dir = watch_dir
        self.warning_pct = warning_pct
        self.critical_pct = critical_pct
        self.warning_callback = warning_callback
        self.critical_callback = critical_callback

        self._was_warning: bool = False
        self._was_critical: bool = False
        self._last_checked: float = 0.0
        self._check_interval: float = 300.0  # 5 min between checks

    # ── properties ────────────────────────────────────────────

    @property
    def usage_pct(self) -> float:
        """Current disk usage percentage for the watch directory."""
        try:
            usage = shutil.disk_usage(self.watch_dir)
            return usage.used / usage.total * 100
        except OSError:
            return 0.0

    @property
    def free_gb(self) -> float:
        try:
            usage = shutil.disk_usage(self.watch_dir)
            return usage.free / (1024 ** 3)
        except OSError:
            return 0.0

    @property
    def total_gb(self) -> float:
        try:
            usage = shutil.disk_usage(self.watch_dir)
            return usage.total / (1024 ** 3)
        except OSError:
            return 0.0

    @property
    def status(self) -> str:
        """Status label: 'ok', 'warning', or 'critical'."""
        pct = self.usage_pct
        if pct >= self.critical_pct:
            return "critical"
        if pct >= self.warning_pct:
            return "warning"
        return "ok"

    # ── tick ──────────────────────────────────────────────────

    def tick(self) -> dict:
        """Run one monitoring tick. Returns current stats dict.

        Fires callbacks when thresholds cross (once per crossing).
        """
        now = time.time()
        if now - self._last_checked < self._check_interval:
            return self.stats()

        self._last_checked = now
        pct = self.usage_pct
        stats = self.stats()

        if pct >= self.critical_pct and not self._was_critical:
            self._was_critical = True
            if self.critical_callback:
                self.critical_callback(stats)
        elif pct < self.critical_pct:
            self._was_critical = False

        if pct >= self.warning_pct and not self._was_warning:
            self._was_warning = True
            if self.warning_callback:
                self.warning_callback(stats)
        elif pct < self.warning_pct:
            self._was_warning = False

        return stats

    def stats(self) -> dict:
        """Current storage stats snapshot."""
        return {
            "usage_pct": round(self.usage_pct, 1),
            "free_gb": round(self.free_gb, 1),
            "total_gb": round(self.total_gb, 1),
            "status": self.status,
            "watch_dir": str(self.watch_dir),
        }

    def reset_alerts(self) -> None:
        """Reset alert state (e.g., after thresholds change)."""
        self._was_warning = False
        self._was_critical = False