"""RetentionPolicy — file retention rules and cleanup planning."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class RetentionRule:
    """A retention rule for a file category.

    Files matching this rule are candidates for deletion when:
    - age > max_age_days AND
    - count > max_count (if set) AND
    - total size > max_gb (if set)
    """

    category: str                           # "raw_recordings" | "clips" | "temp"
    dir_glob: str                           # "*.flv" | "clips/*.mp4" | "*.wav"
    max_age_days: Optional[float] = None
    max_count: Optional[int] = None
    max_gb: Optional[float] = None

    @property
    def max_age_seconds(self) -> Optional[float]:
        return self.max_age_days * 86400 if self.max_age_days else None

    def qualifies(self, age_seconds: float) -> bool:
        """A file qualifies for cleanup if it exceeds the max age."""
        if self.max_age_seconds is None:
            return False
        return age_seconds > self.max_age_seconds


class RetentionPolicy:
    """Collection of retention rules for different file categories."""

    def __init__(self, rules: Optional[list[RetentionRule]] = None) -> None:
        self.rules = rules or []

    @classmethod
    def from_config(cls, cfg: dict) -> "RetentionPolicy":
        """Build policy from the config dict."""
        rules = []
        ret = cfg.get("storage", {}).get("retention", {})

        for cat, rule_cfg in ret.items():
            dir_glob_map = {
                "raw_recordings": "*.flv",
                "clips": "clips/*.mp4",
                "temp": "*.{wav,mp3,tmp}",
            }
            rules.append(RetentionRule(
                category=cat,
                dir_glob=dir_glob_map.get(cat, f"**/{cat}/*"),
                max_age_days=rule_cfg.get("max_age_days"),
                max_count=rule_cfg.get("max_count"),
                max_gb=rule_cfg.get("max_gb"),
            ))
        return cls(rules)

    def find_expired(self, projects_dir: Path, now: float) -> list[Path]:
        """Find files that exceed retention limits. Returns expired paths."""
        expired: list[Path] = []

        for rule in self.rules:
            if rule.max_age_seconds is None:
                continue
            for f in sorted(projects_dir.glob(rule.dir_glob)):
                if not f.is_file():
                    continue
                try:
                    age = now - f.stat().st_mtime
                except OSError:
                    continue
                if age > rule.max_age_seconds:
                    expired.append(f)

        return expired

    def plan_all(self, projects_dir: Path) -> dict[str, list[Path]]:
        """Build a cleanup plan per category, respecting count+size caps."""
        now = time.time()
        plan: dict[str, list[Path]] = {}
        for rule in self.rules:
            candidates = []
            total_size = 0
            for f in sorted(projects_dir.glob(rule.dir_glob)):
                if not f.is_file():
                    continue
                try:
                    age = now - f.stat().st_mtime
                    size = f.stat().st_size
                except OSError:
                    continue
                candidates.append((age, size, f))

            # Sort oldest first
            candidates.sort(key=lambda x: -x[0])

            # Remove files that don't qualify
            expired: list[Path] = []
            for age, size, path in candidates:
                if not rule.qualifies(age):
                    continue
                # Check count cap
                if rule.max_count is not None:
                    remaining = len(candidates) - len(expired)
                    if remaining <= rule.max_count:
                        break
                # Check size cap
                if rule.max_gb is not None:
                    total_size += size
                    if total_size > rule.max_gb * (1024 ** 3):
                        expired.append(path)
                        total_size += size  # accounted above
                    else:
                        expired.append(path)
                else:
                    expired.append(path)

            if expired:
                plan[rule.category] = expired

        return plan

    def estimate_freed_gb(self, plan: dict[str, list[Path]]) -> float:
        """Estimate how many GB would be freed by a cleanup plan."""
        total = 0.0
        for paths in plan.values():
            for p in paths:
                try:
                    total += p.stat().st_size
                except OSError:
                    continue
        return round(total / (1024 ** 3), 2)