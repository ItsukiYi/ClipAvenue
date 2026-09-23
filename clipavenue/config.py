"""ClipAvenue configuration management.

Loads from clipavenue/config.yaml by default. All fields have safe defaults
so the dashboard works with zero configuration.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_CONFIG: dict[str, Any] = {
    "recording": {
        "bilibili": {
            "enabled": True,
            "monitor_interval_seconds": 60,
            "recorder_path": "BililiveRecorder",
        },
        "douyin": {
            "enabled": False,
            "monitor_interval_seconds": 120,
        },
    },
    "storage": {
        "watch_dirs": ["projects"],
        "warning_threshold_pct": 85,
        "critical_threshold_pct": 95,
        "cleanup_interval_hours": 6,
        "retention": {
            "raw_recordings": {"max_age_days": 14, "max_count": 50, "max_gb": 200},
            "clips": {"max_age_days": 30},
            "temp": {"max_age_hours": 24},
        },
    },
    "clipping": {
        "whisper_model": "tiny",
        "max_chars_per_line": 17,
        "format": "vertical_1080x1920",
        "output_dir": "projects/{live_id}/clips/",
    },
    "upload": {
        "platform": "bilibili",
        "biliup_path": "biliup",
        "max_retries": 3,
        "retry_delay_seconds": 300,
    },
    "archive": {
        "backup_enabled": False,
        "notifications": [],
        "cleanup_on_success": False,
    },
    "dashboard": {
        "title": "ClipAvenue",
        "refresh_interval_ms": 2000,
    },
}

_CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"
_ENV_CONFIG_PATH = Path(os.environ.get("CLIPAVENUE_CONFIG", ""))


def _merge(base: dict, overrides: dict) -> dict:
    """Deep-merge overrides into base (mutates base)."""
    for key, val in overrides.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            _merge(base[key], val)
        else:
            base[key] = val
    return base


def load(config_path: Optional[Path] = None) -> dict[str, Any]:
    """Load configuration, merging defaults with user config file."""
    cfg = dict(DEFAULT_CONFIG)  # shallow copy top level
    for key, val in DEFAULT_CONFIG.items():
        if isinstance(val, dict):
            cfg[key] = dict(val)

    sources = []
    if config_path:
        sources.append(config_path)
    if _ENV_CONFIG_PATH.is_file():
        sources.append(_ENV_CONFIG_PATH)
    if _CONFIG_PATH.is_file():
        sources.append(_CONFIG_PATH)

    for path in sources:
        try:
            with open(path, encoding="utf-8") as f:
                user_cfg = yaml.safe_load(f) or {}
            _merge(cfg, user_cfg)
        except (OSError, yaml.YAMLError) as exc:
            print(f"clipavenue: warning — could not load config {path}: {exc}")

    return cfg


# Module-level singleton (lazy-loaded).
_config: Optional[dict[str, Any]] = None


def get() -> dict[str, Any]:
    global _config
    if _config is None:
        _config = load()
    return _config


def reload() -> dict[str, Any]:
    global _config
    _config = load()
    return _config