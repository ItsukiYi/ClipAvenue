"""clip_tools — mechanical tools for the ClipAvenue agent.

Each tool is a standalone function callable by the agent loop. The agent
calls these for the mechanical steps; the intelligence steps (ASR correction,
segmentation, clip selection, metadata) are handled by the agent itself.

Every tool accepts a `project_dir` (str) and returns a JSON-serializable dict.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from clipavenue.logger import log

# ---------------------------------------------------------------------------
# Tool 1: extract_audio
# ---------------------------------------------------------------------------


def extract_audio(video_path: str, project_dir: str) -> dict:
    """Extract 16kHz mono WAV from video via ffmpeg."""
    vp = Path(video_path)
    pd = Path(project_dir)
    audio_dir = pd / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    output_path = audio_dir / f"{vp.stem}.wav"

    if output_path.is_file():
        return {"success": True, "path": str(output_path), "cached": True}

    log.info("agent-tool", f"extract_audio: {vp.name}")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error",
             "-i", str(vp),
             "-vn", "-acodec", "pcm_s16le",
             "-ar", "16000", "-ac", "1",
             str(output_path)],
            capture_output=True, timeout=3600,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return {"success": False, "error": str(exc)}

    if not output_path.is_file():
        return {"success": False, "error": "output not produced"}
    size_mb = output_path.stat().st_size / 1024 / 1024
    return {"success": True, "path": str(output_path), "size_mb": round(size_mb, 1)}


# ---------------------------------------------------------------------------
# Tool 2: transcribe
# ---------------------------------------------------------------------------


def transcribe(audio_path: str, project_dir: str) -> dict:
    """Run faster-whisper transcription via OpenMontage's Transcriber tool."""
    pd = Path(project_dir)
    transcript_dir = pd / "transcripts"
    transcript_dir.mkdir(parents=True, exist_ok=True)

    audio_p = Path(audio_path)
    output_path = transcript_dir / f"{audio_p.stem}_transcript.json"

    if output_path.is_file():
        try:
            data = json.loads(output_path.read_text(encoding="utf-8"))
            return {"success": True, "path": str(output_path), "segments": len(data.get("segments", [])), "cached": True}
        except (OSError, json.JSONDecodeError):
            pass

    log.info("agent-tool", f"transcribe: {audio_p.name}")
    try:
        from clipavenue.clipper.asr import Transcriber
        t = Transcriber()
        result = t.execute({
            "input_path": str(audio_p),
            "model_size": "tiny",
            "language": "zh",
            "output_dir": str(transcript_dir),
        })
        if not result.success:
            return {"success": False, "error": result.error}
        if output_path.is_file():
            return {"success": True, "path": str(output_path), "segments": len(result.data.get("segments", []))}
        # Transcriber may write to a different path; find the json
        jsons = list(transcript_dir.glob("*_transcript.json"))
        if jsons:
            return {"success": True, "path": str(jsons[0]), "segments": len(result.data.get("segments", []))}
        return {"success": True, "path": "", "segments": len(result.data.get("segments", []))}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Tool 3: trim_clips
# ---------------------------------------------------------------------------


def trim_clips(video_path: str, clips: list[dict], project_dir: str) -> dict:
    """Trim video segments into individual clip MP4s."""
    vp = Path(video_path)
    pd = Path(project_dir)
    clips_dir = pd / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    output_paths = []
    total = len(clips)
    log.info("agent-tool", f"trim_clips: {total} clips from {vp.name}")

    for i, clip in enumerate(clips):
        label = clip.get("label", f"clip{i + 1:02d}")
        start = clip.get("start", 0)
        end = clip.get("end", 0)
        output_path = clips_dir / f"{label}.mp4"

        if output_path.is_file():
            output_paths.append(str(output_path))
            continue

        try:
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error",
                 "-ss", str(start), "-to", str(end),
                 "-i", str(vp),
                 "-c:v", "libx264", "-crf", "23", "-preset", "fast",
                 "-c:a", "aac", "-b:a", "128k",
                 str(output_path)],
                capture_output=True, timeout=3600,
            )
            if output_path.is_file():
                output_paths.append(str(output_path))
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            log.warn("agent-tool", f"trim failed for {label}: {exc}")

    return {"success": True, "total": total, "clips": output_paths}


# ---------------------------------------------------------------------------
# Tool 4: generate_subs
# ---------------------------------------------------------------------------


def generate_subs(project_dir: str, clips: list[dict]) -> dict:
    """Generate ASS subtitle files for each clip.

    Reads corrected_transcript.json (with segmented_lines) from project_dir.
    """
    pd = Path(project_dir)
    renders_dir = pd / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)

    # Read the corrected transcript
    transcript_path = pd / "corrected_transcript.json"
    if not transcript_path.is_file():
        return {"success": False, "error": "corrected_transcript.json not found"}
    try:
        transcript_data = json.loads(transcript_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"success": False, "error": f"corrupted transcript: {exc}"}

    # ASS header
    ass_header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes
WrapStyle: 1

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,微软雅黑,80,&H00FFFFFF,&H000000FF,&H00E98D8F,&H80000000,1,0,0,0,100,100,0,0,1,6,1,2,100,100,400,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def _fmt_ts(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        return f"{h}:{m:02d}:{s:05.2f}"

    sub_paths = []
    all_segments = transcript_data.get("segments", [])

    for i, clip in enumerate(clips):
        clip_start = clip.get("start", 0)
        clip_end = clip.get("end", 0)
        label = clip.get("label", f"clip{i + 1:02d}")
        ass_path = renders_dir / f"{label}.ass"

        if ass_path.is_file():
            sub_paths.append(str(ass_path))
            continue

        # Find overlapping segments
        overlapping = [
            s for s in all_segments
            if s.get("start", 0) < clip_end and s.get("end", 0) > clip_start
        ]

        ass_lines = [ass_header]
        for seg in overlapping:
            lines = seg.get("segmented_lines") or [seg.get("text", "")]
            total_lines = len([l for l in lines if l.strip()])
            if total_lines == 0:
                continue
            seg_start = seg["start"]
            seg_end = seg["end"]
            seg_duration = max(seg_end - seg_start, 0.8)
            # Distribute lines evenly across the segment duration
            chunk_duration = seg_duration / total_lines
            line_idx = 0
            for line in lines:
                if not line.strip():
                    continue
                rel_start = max(0, seg_start + line_idx * chunk_duration - clip_start)
                rel_end = max(rel_start + 0.8,
                              seg_start + (line_idx + 1) * chunk_duration - clip_start)
                ass_lines.append(
                    f"Dialogue: 0,{_fmt_ts(rel_start)},{_fmt_ts(rel_end)},"
                    f"Default,,0,0,0,,{line.strip()}\n"
                )
                line_idx += 1

        ass_path.write_text("".join(ass_lines), encoding="utf-8")
        sub_paths.append(str(ass_path))

    return {"success": True, "subs": sub_paths}


# ---------------------------------------------------------------------------
# Tool 5: burn_subs
# ---------------------------------------------------------------------------


def burn_subs(project_dir: str, clips: list[dict]) -> dict:
    """Burn ASS subtitles into clip videos.

    Matches clip -> ass by label.  ASS must be in renders/ ; clip in clips/ .
    Outputs to renders/{label}_subbed.mp4.
    """
    pd = Path(project_dir)
    clips_dir = pd / "clips"
    renders_dir = pd / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)

    output_paths = []
    total = len(clips)

    for i, clip in enumerate(clips):
        label = clip.get("label", f"clip{i + 1:02d}")
        clip_path = clips_dir / f"{label}.mp4"
        ass_path = renders_dir / f"{label}.ass"
        output_path = renders_dir / f"{label}_subbed.mp4"

        if not clip_path.is_file():
            continue
        if not ass_path.is_file():
            log.warn("agent-tool", f"burn_subs: no ASS for {label}, skipping")
            continue
        if output_path.is_file():
            output_paths.append(str(output_path))
            continue

        # Copy ASS to clip dir (ffmpeg needs relative path for subtitles filter)
        local_ass = clip_path.parent / "_subs_temp.ass"
        try:
            shutil.copy2(ass_path, local_ass)
        except OSError:
            local_ass = ass_path

        try:
            r = subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error",
                 "-i", clip_path.name,
                 "-vf", f"subtitles={local_ass.name}:original_size=1080x1920",
                 "-c:v", "libx264", "-crf", "23", "-preset", "fast",
                 "-c:a", "copy",
                 output_path.name],
                capture_output=True, timeout=3600,
                cwd=clip_path.parent,
            )
            if r.returncode != 0:
                log.warn("agent-tool", f"burn_subs: ffmpeg error for {label}: {r.stderr.decode('utf-8', 'replace')[:100]}")
            if output_path.is_file():
                output_paths.append(str(output_path))
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            log.warn("agent-tool", f"burn_subs: exception for {label}: {exc}")

    # Cleanup temp ASS files
    for f in clips_dir.glob("_subs_temp.ass"):
        try:
            f.unlink()
        except OSError:
            pass

    return {"success": True, "rendered": output_paths}


# ---------------------------------------------------------------------------
# Tool 6: generate_cover
# ---------------------------------------------------------------------------


def generate_cover(video_path: str, start_time: float, title: str, output_path: str) -> dict:
    """Extract a frame from the video and overlay title text."""
    temp = Path(output_path).with_suffix(".raw.jpg")
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    seek = max(0.5, start_time + 3.0)  # 3 seconds into the clip

    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error",
             "-ss", str(seek), "-i", str(video_path),
             "-frames:v", "1", "-q:v", "2", str(temp)],
            capture_output=True, timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return {"success": False, "error": str(exc)}

    if not temp.is_file():
        return {"success": False, "error": "no frame extracted"}

    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error",
             "-i", str(temp),
             "-vf", f"drawtext=text={title}:fontsize=42:fontcolor=white:box=1:boxcolor=black@0.5:x=(w-text_w)/2:y=h-text_h-40",
             "-q:v", "2", str(out)],
            capture_output=True, timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return {"success": False, "error": str(exc)}

    temp.unlink(missing_ok=True)
    if out.is_file():
        return {"success": True, "path": str(out)}
    if temp.is_file():
        temp.rename(out)
        return {"success": True, "path": str(out)}
    return {"success": False, "error": "cover not produced"}


# ---------------------------------------------------------------------------
# Tool 7: fs_write  — agent writes any JSON artifact to project dir
# ---------------------------------------------------------------------------


def fs_write(path: str, data: Any) -> dict:
    """Write JSON-serializable data to a file. Creates parent dirs."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        p.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return {"success": True, "path": str(p.absolute())}
    except (OSError, TypeError) as exc:
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Build the tool list for the agent loop
# ---------------------------------------------------------------------------


def make_tools() -> list:
    """Return the Tool list expected by agent.py's ClipAgent.

    Each entry: Tool(name, description, input_schema, fn)
    """
    # Import Tool here to avoid circular imports at module level
    from clipavenue.agent import Tool

    return [
        Tool(
            "extract_audio",
            "Extract 16kHz mono WAV audio from a video file. Returns path to the WAV.",
            {
                "type": "object",
                "properties": {
                    "video_path": {"type": "string", "description": "Full path to the video file"},
                    "project_dir": {"type": "string", "description": "Project directory path"},
                },
                "required": ["video_path", "project_dir"],
            },
            lambda p: extract_audio(p["video_path"], p["project_dir"]),
        ),
        Tool(
            "transcribe",
            "Run faster-whisper transcription on a WAV file. Returns path + segment count.",
            {
                "type": "object",
                "properties": {
                    "audio_path": {"type": "string", "description": "Path to the WAV file"},
                    "project_dir": {"type": "string", "description": "Project directory path"},
                },
                "required": ["audio_path", "project_dir"],
            },
            lambda p: transcribe(p["audio_path"], p["project_dir"]),
        ),
        Tool(
            "trim_clips",
            "Trim video segments into individual clip MP4 files.",
            {
                "type": "object",
                "properties": {
                    "video_path": {"type": "string", "description": "Full path to the source video"},
                    "clips": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "start": {"type": "number"},
                                "end": {"type": "number"},
                            },
                        },
                        "description": "Clip definitions from clip_analysis.json suggested_clips",
                    },
                    "project_dir": {"type": "string", "description": "Project directory path"},
                },
                "required": ["video_path", "clips", "project_dir"],
            },
            lambda p: trim_clips(p["video_path"], p["clips"], p["project_dir"]),
        ),
        Tool(
            "generate_subs",
            "Generate ASS subtitle files for each clip. Reads corrected_transcript.json from the project dir.",
            {
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string", "description": "Project directory path"},
                    "clips": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "start": {"type": "number"},
                                "end": {"type": "number"},
                            },
                        },
                        "description": "Clip definitions from clip_analysis.json suggested_clips",
                    },
                },
                "required": ["project_dir", "clips"],
            },
            lambda p: generate_subs(p["project_dir"], p["clips"]),
        ),
        Tool(
            "burn_subs",
            "Burn ASS subtitles into clip videos. Outputs to renders/{label}_subbed.mp4.",
            {
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string", "description": "Project directory path"},
                    "clips": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "start": {"type": "number"},
                                "end": {"type": "number"},
                            },
                        },
                        "description": "Clip definitions from clip_analysis.json suggested_clips",
                    },
                },
                "required": ["project_dir", "clips"],
            },
            lambda p: burn_subs(p["project_dir"], p["clips"]),
        ),
        Tool(
            "generate_cover",
            "Extract a frame from a video and overlay title text for a thumbnail.",
            {
                "type": "object",
                "properties": {
                    "video_path": {"type": "string", "description": "Full path to the source video"},
                    "start_time": {"type": "number", "description": "Seek time in seconds (use clip start + 3s)"},
                    "title": {"type": "string", "description": "Title text to overlay on the thumbnail"},
                    "output_path": {"type": "string", "description": "Full output path for the cover JPG"},
                },
                "required": ["video_path", "start_time", "title", "output_path"],
            },
            lambda p: generate_cover(p["video_path"], p["start_time"], p["title"], p["output_path"]),
        ),
        Tool(
            "fs_write",
            "Write JSON-serializable data to a file. Creates parent directories.",
            {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Full path to write to"},
                    "data": {
                        "description": "JSON-serializable data to write",
                        "oneOf": [
                            {"type": "string"},
                            {"type": "object"},
                            {"type": "array"},
                        ],
                    },
                },
                "required": ["path", "data"],
            },
            lambda p: fs_write(p["path"], p["data"]),
        ),
    ]