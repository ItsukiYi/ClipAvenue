"""Notifier — multi-channel notifications for pipeline events.

Supports:
- Webhook (generic JSON POST)
- Console (stdout, always-on)
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Optional


class Notifier:
    """Send notifications when pipeline events occur.

    Configured via the archive.notifications list in config.yaml.
    Each notification entry:
      type: webhook | console
      url: (webhook target URL)
      events: [completed, failed, captcha, started]
    """

    def __init__(self, config: Optional[list[dict]] = None) -> None:
        self._channels = config or []
        self._log_path: Optional[Path] = None

    def set_log_path(self, path: Path) -> None:
        self._log_path = path

    def send(
        self,
        event: str,
        title: str,
        message: str,
        data: Optional[dict] = None,
    ) -> None:
        """Send a notification through all configured channels.

        Args:
            event: Event type (completed, failed, captcha, started)
            title: Short event title
            message: Human-readable description
            data: Optional extra payload
        """
        payload = {
            "event": event,
            "title": title,
            "message": message,
            "timestamp": time.time(),
            "data": data or {},
        }

        # Always log to console
        print(f"clipavenue: [{event}] {title} — {message}")

        # Log to file if configured
        if self._log_path:
            try:
                with open(self._log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(payload, ensure_ascii=False) + "\n")
            except OSError:
                pass

        # Send through channels matching this event
        for channel in self._channels:
            if not isinstance(channel, dict):
                continue
            # Check if this channel handles this event type
            channel_events = channel.get("events", [])
            if channel_events and event not in channel_events:
                continue

            channel_type = channel.get("type", "")
            if channel_type == "webhook":
                self._send_webhook(channel.get("url", ""), payload)
            elif channel_type == "console":
                pass  # already logged above

    def _send_webhook(self, url: str, payload: dict) -> None:
        """Send JSON POST to a webhook URL."""
        if not url:
            return
        try:
            req = json.dumps(payload).encode("utf-8")
            subprocess.run(
                ["curl", "-s", "-X", "POST", url,
                 "-H", "Content-Type: application/json",
                 "-d", req],
                capture_output=True, timeout=10,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass  # webhook is best-effort

    # ── Convenience methods ───────────────────────────────────

    def on_completed(
        self, project_id: str, streamer: str, clip_count: int, bvid: str = ""
    ) -> None:
        msg = f"{streamer} 的 {clip_count} 个切片已投稿" + (f" ({bvid})" if bvid else "")
        self.send("completed", f"[OK] {project_id}", msg)

    def on_failed(self, project_id: str, stage: str, error: str) -> None:
        self.send("failed", f"[FAIL] {project_id} [{stage}]", error)

    def on_captcha(self, project_id: str, captcha_url: str) -> None:
        self.send("captcha", f"[CAPTCHA] {project_id} 需要验证码",
                  f"请解决验证码: {captcha_url}")

    def on_started(self, project_id: str, stage: str) -> None:
        self.send("started", f"[START] {project_id}", f"{stage} 阶段开始")