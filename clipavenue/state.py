"""ClipAvenue dashboard state — disk-derived metro-map station data.

Derives the current state of each pipeline station from on-disk checkpoints,
task files, and config. Never writes to disk (read-only, observation model).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

from clipavenue.lib_paths import PROJECTS_DIR

# ---------------------------------------------------------------------------
# Station definition — the canonical ClipAvenue pipeline stages
# ---------------------------------------------------------------------------

STATIONS = [
    {"id": "recording",    "label": "直播录制",  "icon": "mic",     "gated": False},
    {"id": "storage",      "label": "存储管理",  "icon": "disk",    "gated": False},
    {"id": "transcribe",   "label": "语音转写",  "icon": "text",    "gated": False},
    {"id": "analyze",      "label": "语义分析",  "icon": "brain",   "gated": True},
    {"id": "clip",         "label": "自动剪辑",  "icon": "scissors","gated": False},
    {"id": "subtitle",     "label": "字幕压制",  "icon": "sub",     "gated": False},
    {"id": "upload",       "label": "自动投稿",  "icon": "upload",  "gated": False},
    {"id": "archive",      "label": "自动归档",  "icon": "archive", "gated": False},
]

STATION_ORDER = [s["id"] for s in STATIONS]

# How long (seconds) without activity before a station reads "idle".
LIVE_WINDOW_SECONDS = 5 * 60

# An in_progress stage with no activity for this long is flagged stalled.
STALL_WINDOW_SECONDS = 10 * 60

# Files we look for per live project.
RECORDER_STATE_FILE = "recorder_state.json"
CLIP_STATE_FILE = "clip_state.json"
UPLOAD_STATE_FILE = "upload_state.json"


def _read_json(path: Path) -> Optional[dict]:
    """Read a JSON file, returning None on any failure."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None


def _find_live_projects() -> list[Path]:
    """Discover live-recording projects under projects/."""
    if not PROJECTS_DIR.is_dir():
        return []
    lives = []
    for entry in sorted(PROJECTS_DIR.iterdir()):
        if not entry.is_dir() or entry.name.startswith(("_", ".")):
            continue
        # A project is a "live" if it has a marker or a recorder state file.
        marker = _read_json(entry / "project.json")
        rec_state = _read_json(entry / RECORDER_STATE_FILE)
        if marker or rec_state:
            lives.append(entry)
    return lives


def _last_activity(project_dir: Path) -> float:
    """Most recent mtime among state-bearing files."""
    latest = 0.0
    try:
        for pattern in ("*.json", "*.jsonl"):
            for p in project_dir.glob(pattern):
                try:
                    latest = max(latest, p.stat().st_mtime)
                except OSError:
                    continue
    except OSError:
        pass
    return latest


# ---------------------------------------------------------------------------
# Per-station state derivation
# ---------------------------------------------------------------------------


def _station_recording(project_dir: Path) -> dict[str, Any]:
    """Derive recording station state."""
    state_file = project_dir / RECORDER_STATE_FILE
    data = _read_json(state_file)
    if data is None:
        return {"status": "pending", "detail": "等待录制"}
    status = data.get("status", "unknown")
    detail = data.get("detail", "")
    # Use error as detail if failed
    if status == "failed":
        error = data.get("error", "")
        detail = error[:60] if error else "录制失败"
    elif status == "recording":
        info = data.get("recorder_info") or (f"PID {data.get('pid')}" if data.get('pid') else "")
        detail = info or "录制中"
    eta = data.get("eta")
    return {
        "status": status,
        "detail": detail,
        "eta": eta,
        "pid": data.get("pid"),
        "platform": data.get("platform"),
        "streamer": data.get("streamer"),
        "started_at": data.get("started_at"),
        "duration_seconds": data.get("duration_seconds"),
        "recorder_info": data.get("recorder_info"),
    }


def _station_storage(project_dir: Path) -> dict[str, Any]:
    """Derive storage station state."""
    # Check disk usage of the projects directory
    try:
        import shutil
        usage = shutil.disk_usage(PROJECTS_DIR)
        pct = usage.used / usage.total * 100
        free_gb = usage.free / (1024 ** 3)
        total_gb = usage.total / (1024 ** 3)
    except Exception:
        return {"status": "unknown", "detail": "无法检测", "usage_pct": 0}

    status = "ok"
    detail = f"已用 {pct:.0f}%"
    if pct > 95:
        status = "critical"
        detail = f"磁盘告警！仅剩 {free_gb:.1f} GB"
    elif pct > 85:
        status = "warning"

    return {
        "status": status,
        "detail": detail,
        "usage_pct": round(pct, 1),
        "free_gb": round(free_gb, 1),
        "total_gb": round(total_gb, 1),
    }


def _station_transcribe(project_dir: Path) -> dict[str, Any]:
    """Derive transcribe station state from transcript files."""
    transcripts = list(project_dir.glob("**/*transcript*.json"))
    if not transcripts:
        return {"status": "pending", "detail": "等待转写"}

    # Check the most recent transcript
    latest = max(transcripts, key=lambda p: p.stat().st_mtime)
    data = _read_json(latest)
    if data is None:
        return {"status": "failed", "detail": "转写文件损坏"}

    segments = data.get("segments", [])
    duration = data.get("duration_seconds", 0)
    return {
        "status": "completed",
        "detail": f"已转写 {len(segments)} 段，共 {duration:.0f}s",
        "segments": len(segments),
        "duration_seconds": duration,
        "language": data.get("language"),
        "model": data.get("model_size"),
    }


def _station_analyze(project_dir: Path) -> dict[str, Any]:
    """Derive analyze station state from analysis artifacts."""
    clip_state = _read_json(project_dir / CLIP_STATE_FILE)
    if clip_state:
        status = clip_state.get("status", "pending")
        clips = clip_state.get("clips", [])
        detail = f"检测到 {len(clips)} 个切片" if clips else "分析中"
        # Show agent path info if available
        agent_info = _agent_path_info(clip_state)
        if agent_info:
            detail += f" ({agent_info})"
        return {
            "status": status,
            "detail": detail,
            "clip_count": len(clips),
            "clips": clips,
        }
    # Fall back to checking clip_analysis.json for agent output
    analysis = _read_json(project_dir / "clip_analysis.json")
    if analysis:
        cc = analysis.get("clip_count", 0)
        tc = analysis.get("topic_count", 0)
        return {
            "status": "completed",
            "detail": f"分析完成 ({tc} 话题, {cc} 切片推荐)",
            "topic_count": tc,
            "clip_count": cc,
        }
    return {"status": "pending", "detail": "等待分析"}


def _station_clip(project_dir: Path) -> dict[str, Any]:
    """Derive clip station state."""
    clips_dir = project_dir / "clips"
    if not clips_dir.is_dir():
        return {"status": "pending", "detail": "等待剪辑"}

    clip_files = sorted(clips_dir.glob("*.mp4"))
    if not clip_files:
        return {"status": "pending", "detail": "等待剪辑"}

    total_size = sum(f.stat().st_size for f in clip_files) / (1024 ** 2)
    detail = f"已生成 {len(clip_files)} 个切片 ({total_size:.0f} MB)"

    # Show agent path info from clip_state.json
    clip_state = _read_json(project_dir / CLIP_STATE_FILE)
    agent_info = _agent_path_info(clip_state) if clip_state else ""
    if agent_info:
        detail += f" | {agent_info}"

    return {
        "status": "completed",
        "detail": detail,
        "clip_count": len(clip_files),
        "total_size_mb": round(total_size, 1),
    }


def _agent_path_info(clip_state: dict) -> str:
    """Extract agent path info from clip_state.json for display."""
    parts = []
    steps = clip_state.get("agent_steps")
    if steps is not None:
        parts.append(f"agent {steps}轮")
    inp = clip_state.get("input_tokens")
    if inp is not None:
        parts.append(f"{inp//1000}k输入")
    if clip_state.get("status") == "in_progress" or clip_state.get("status") == "queued":
        parts.append("agent")
    return " ".join(parts) if parts else ""


def _station_subtitle(project_dir: Path) -> dict[str, Any]:
    """Derive subtitle station state."""
    ass_files = list(project_dir.glob("**/*.ass"))
    srt_files = list(project_dir.glob("**/*.srt"))
    all_sub = ass_files + srt_files
    if not all_sub:
        return {"status": "pending", "detail": "等待字幕"}
    return {
        "status": "completed",
        "detail": f"已生成 {len(all_sub)} 个字幕文件",
        "count": len(all_sub),
    }


def _station_upload(project_dir: Path) -> dict[str, Any]:
    """Derive upload station state."""
    upload_state = _read_json(project_dir / UPLOAD_STATE_FILE)
    if upload_state is None:
        return {"status": "pending", "detail": "等待上传"}

    status = upload_state.get("status", "pending")
    detail = upload_state.get("detail", "")
    captcha_needed = upload_state.get("captcha_needed", False)

    if captcha_needed:
        return {"status": "verifying", "detail": "需要验证码", "captcha_url": upload_state.get("captcha_url")}
    if status == "failed":
        error = upload_state.get("error", "")
        return {"status": "failed", "detail": f"上传失败: {error[:50]}", "error": error}
    if status == "completed":
        bvid = upload_state.get("bvid", "")
        return {"status": "completed", "detail": f"已投稿 {bvid}", "bvid": bvid}
    return {"status": status, "detail": detail}


def _station_archive(project_dir: Path) -> dict[str, Any]:
    """Derive archive station state."""
    upload_done = _read_json(project_dir / UPLOAD_STATE_FILE)
    if upload_done and upload_done.get("status") == "completed":
        return {"status": "completed", "detail": "归档完成"}
    return {"status": "pending", "detail": "等待归档"}


# Map station id → derivation function
_STATION_DERIVERS = {
    "recording": _station_recording,
    "storage": _station_storage,
    "transcribe": _station_transcribe,
    "analyze": _station_analyze,
    "clip": _station_clip,
    "subtitle": _station_subtitle,
    "upload": _station_upload,
    "archive": _station_archive,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_dashboard_state() -> dict[str, Any]:
    """Full dashboard state — never raises, degrades gracefully."""
    import time
    now = time.time()

    projects = _find_live_projects()
    all_stations: list[dict] = []

    for station_def in STATIONS:
        sid = station_def["id"]
        station: dict[str, Any] = {
            "id": sid,
            "label": station_def["label"],
            "icon": station_def["icon"],
            "gated": station_def["gated"],
            "status": "pending",
            "detail": "",
        }
        # If there are live projects, derive from the most active one.
        if projects:
            # Pick the project with the most recent activity for this station
            active_project = max(projects, key=lambda p: _last_activity(p))
            deriver = _STATION_DERIVERS.get(sid)
            if deriver:
                try:
                    derived = deriver(active_project)
                    station.update(derived)
                except Exception:
                    station["status"] = "unknown"

        all_stations.append(station)

    # Compute overall pipeline status
    active_count = sum(1 for s in all_stations if s["status"] in ("in_progress", "recording", "transcribing"))
    completed_count = sum(1 for s in all_stations if s["status"] == "completed")
    failed_count = sum(1 for s in all_stations if s["status"] in ("failed", "critical"))
    verifying_count = sum(1 for s in all_stations if s["status"] == "verifying")

    return {
        "stations": all_stations,
        "project_count": len(projects),
        "active_count": active_count,
        "completed_count": completed_count,
        "failed_count": failed_count,
        "verifying_count": verifying_count,
        "live": any(s["status"] in ("in_progress", "recording", "transcribing", "verifying") for s in all_stations),
        "timestamp": now,
    }


def list_live_projects() -> list[dict[str, Any]]:
    """Summary cards for the library view."""
    projects = _find_live_projects()
    results = []
    for proj_dir in projects:
        marker = _read_json(proj_dir / "project.json") or {}
        rec_state = _read_json(proj_dir / RECORDER_STATE_FILE) or {}
        results.append({
            "project_id": proj_dir.name,
            "title": marker.get("title") or rec_state.get("streamer") or proj_dir.name,
            "streamer": rec_state.get("streamer"),
            "platform": rec_state.get("platform"),
            "recording_status": rec_state.get("status"),
            "last_activity": _last_activity(proj_dir),
            "has_checkpoints": bool(list(proj_dir.glob("checkpoint_*.json"))),
            "clip_count": len(list(proj_dir.glob("clips/*.mp4"))) if (proj_dir / "clips").is_dir() else 0,
        })
    results.sort(key=lambda r: -(r["last_activity"] or 0))
    return results