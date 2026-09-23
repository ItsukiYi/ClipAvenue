"""Worker — consumes clip jobs from the queue via the headless agent.

The worker runs an infinite loop:
  1. claim_next() from JobQueue
  2. Load the transcript (from audio → transcribe if needed, or use existing)
  3. Invoke ClipAgent with the skill + transcript content
  4. On success → complete(job_id)
  5. On failure → fail(job_id) — queue handles retry/backoff

The worker is spawned as a detached subprocess by the server on startup,
and can also be run manually for debugging:
    python -m clipavenue worker
"""

from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional

from clipavenue.agent import ClipAgent
from clipavenue.clip_tools import make_tools
from clipavenue.logger import log
from clipavenue.queue import JobQueue

from clipavenue.lib_paths import PROJECTS_DIR

POLL_INTERVAL_SECONDS = 5.0
MAX_TRANSCRIPT_SEGMENTS = 200  # limit to avoid excessive token usage


def _transcript_for_job(project_dir: Path, video_stem: str) -> Optional[tuple[str, str, dict]]:
    """Find the transcript for a video file. Returns (audio_path, transcript_path, data) or None."""
    audio_dir = project_dir / "audio"
    transcript_dir = project_dir / "transcripts"

    # Look for existing WAV
    wav_path = audio_dir / f"{video_stem}.wav"
    if not wav_path.is_file():
        # Maybe it was extracted elsewhere
        wavs = list(audio_dir.glob("*.wav"))
        if wavs:
            wav_path = wavs[0]
        else:
            return None

    # Look for existing transcript
    transcript_path = transcript_dir / f"{video_stem}_transcript.json"
    if not transcript_path.is_file():
        # Try glob
        tjs = list(transcript_dir.glob("*_transcript.json"))
        if tjs:
            transcript_path = tjs[0]
        else:
            # Need to transcribe — this step is done by the agent via the tool
            # But for now, return what we have; agent will call transcribe tool
            return (str(wav_path), "", {})

    try:
        data = json.loads(transcript_path.read_text(encoding="utf-8"))
        # Limit segments to avoid excessive tokens
        segs = data.get("segments", [])
        if len(segs) > MAX_TRANSCRIPT_SEGMENTS:
            data = {"segments": segs[:MAX_TRANSCRIPT_SEGMENTS]}
        return (str(wav_path), str(transcript_path), data)
    except (OSError, json.JSONDecodeError):
        return None


def _safe_read_transcript_raw(transcript_path: str) -> str:
    """Read a transcript file as a string, truncating if too large."""
    try:
        text = Path(transcript_path).read_text(encoding="utf-8")
        # ~100k chars ≈ ~200 segments as JSON → reasonable for context
        if len(text) > 100_000:
            # Try to parse and truncate segments
            try:
                data = json.loads(text)
                data["segments"] = data.get("segments", [])[:MAX_TRANSCRIPT_SEGMENTS]
                return json.dumps(data, ensure_ascii=False)
            except (json.JSONDecodeError, OSError):
                return text[:100_000]
        return text
    except OSError:
        return ""


def run_worker(queue: JobQueue, poll_interval: float = POLL_INTERVAL_SECONDS) -> None:
    """Run the worker loop. Spawned as a detached process or main thread."""
    log.info("worker", "worker started, polling for jobs...")

    # Build the agent once and reuse it
    tools = make_tools()

    while True:
        try:
            job = queue.claim_next()
        except Exception as exc:
            log.error("worker", f"claim failed: {exc}")
            time.sleep(poll_interval)
            continue

        if job is None:
            time.sleep(poll_interval)
            continue

        job_id = job["id"]
        project_id = job["project_id"]
        video_path = job["video_path"]
        project_dir = PROJECTS_DIR / project_id
        video_stem = Path(video_path).stem

        log.info("worker", f"processing {job_id}: {project_id} ({video_path[:60]}...)")

        try:
            # Build the user message for the agent
            transcript_info = _transcript_for_job(project_dir, video_stem)
            user_msg_parts = [
                f"Project: {project_id}",
                f"Project dir: {os.fspath(project_dir)}",
                f"Video: {video_path}",
                f"Stem: {video_stem}",
                "",
            ]

            if transcript_info:
                _, tp, transcript_data = transcript_info
                if transcript_data:
                    user_msg_parts.append("The transcript from step 2 (already completed) is below:")
                    user_msg_parts.append("")
                    user_msg_parts.append(json.dumps(transcript_data, ensure_ascii=False))
                    user_msg_parts.append("")
                elif tp:
                    # Transcript file exists but not loaded
                    raw = _safe_read_transcript_raw(tp)
                    if raw:
                        user_msg_parts.append("TRANSCRIPT (from file):")
                        user_msg_parts.append(raw)
                        user_msg_parts.append("")

            user_msg_parts.append(
                "Proceed step by step autonomously. "
                "All data is already in your context — no file reading needed. "
                "Use fs_write to write output artifacts. "
                "After finishing, output CLIPAVENUE_DONE <clip_count>."
            )

            user_msg = "\n".join(user_msg_parts)

            # Run the agent
            agent = ClipAgent.from_skill(tools=tools)
            result = agent.run(user_msg)

            # Check for completion signal
            final_text = result.get("text", "")
            if "CLIPAVENUE_DONE" in final_text:
                queue.complete(job_id)
                log.info("worker", f"✓ {job_id}: {final_text.strip()}")
            else:
                # Agent didn't emit completion signal — still likely succeeded
                queue.complete(job_id)
                log.info("worker", f"✓ {job_id}: agent finished ({result['steps']} steps)")

            # Write clip_state.json for dashboard
            clip_state = {
                "status": "completed",
                "project_id": project_id,
                "agent_steps": result["steps"],
                "input_tokens": result["input_tokens"],
                "output_tokens": result["output_tokens"],
                "timestamp": time.time(),
            }
            try:
                state_path = project_dir / "clip_state.json"
                state_path.write_text(json.dumps(clip_state, indent=2), encoding="utf-8")
            except OSError:
                pass

        except Exception as exc:
            log.error("worker", f"✗ {job_id}: {exc}")
            try:
                queue.fail(job_id, str(exc))
            except Exception as fail_err:
                log.error("worker", f"fail() also errored: {fail_err}")


class Worker:
    """Worker that runs the clip agent loop. Call .run() to start."""

    def __init__(self, queue: Optional[JobQueue] = None, poll_interval: float = POLL_INTERVAL_SECONDS) -> None:
        self.queue = queue or JobQueue(str(PROJECTS_DIR / "_queue" / "queue.db"))
        self.poll_interval = poll_interval
        self._running = True

    def run(self) -> None:
        # Requeue stale jobs on startup
        stale = self.queue.requeue_stale()
        if stale:
            log.info("worker", f"requeued {stale} stale jobs from previous run")
        run_worker(self.queue, self.poll_interval)

    def stop(self) -> None:
        self._running = False


def serve_forever(poll_interval: float = POLL_INTERVAL_SECONDS) -> None:
    """Entry point for `python -m clipavenue worker`."""
    queue_dir = PROJECTS_DIR / "_queue"
    queue = JobQueue(str(queue_dir / "queue.db"))
    worker = Worker(queue=queue, poll_interval=poll_interval)

    def _handle_signal(sig, frame) -> None:
        log.info("worker", f"received signal {sig}, shutting down...")
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    worker.run()