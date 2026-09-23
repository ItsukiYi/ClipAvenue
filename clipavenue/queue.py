"""JobQueue — persistent SQLite-backed queue for clip pipeline jobs.

The queue lives at `projects/_queue/queue.db`. The worker claims jobs
atomically, retries on failure with exponential backoff, and requeues
stale "running" jobs on startup (so server+worker restarts don't lose work).
"""

from __future__ import annotations

import json
import math
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Optional

from clipavenue.logger import log

# Default retry window: backoff capped at 30 minutes
MAX_BACKOFF_SECONDS = 1800.0
BASE_BACKOFF_SECONDS = 10.0


class JobQueue:
    """Persistent job queue backed by SQLite.

    Thread-safe as long as each thread uses its own connection.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS clip_jobs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    video_path TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued'
                        CHECK(status IN ('queued','running','done','failed')),
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    next_retry_at REAL,          -- unix ts; NULL = ready now
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    error TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_clip_jobs_status
                ON clip_jobs(status)
            """)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    # ------------------------------------------------------------------
    # Enqueue
    # ------------------------------------------------------------------

    def enqueue(self, project_id: str, video_path: str, max_attempts: int = 3) -> str:
        """Add a job to the queue. Returns the job_id."""
        job_id = f"clip-{uuid.uuid4().hex[:12]}"
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO clip_jobs
                   (id, project_id, video_path, status, attempts, max_attempts,
                    created_at, updated_at)
                   VALUES (?, ?, ?, 'queued', 0, ?, ?, ?)""",
                (job_id, project_id, video_path, max_attempts, now, now),
            )
            conn.commit()
        log.info("queue", f"enqueued {job_id}: {project_id} ({video_path[:60]}...)")
        return job_id

    # ------------------------------------------------------------------
    # Claim next job
    # ------------------------------------------------------------------

    def claim_next(self) -> Optional[dict]:
        """Atomically claim the next ready job and mark it running.

        Returns the job dict, or None if no job is ready.
        """
        now = time.time()
        with self._connect() as conn:
            # Find a job that is queued and ready (next_retry_at is NULL or <= now)
            row = conn.execute(
                """SELECT * FROM clip_jobs
                   WHERE status = 'queued'
                     AND (next_retry_at IS NULL OR next_retry_at <= ?)
                   ORDER BY created_at ASC
                   LIMIT 1""",
                (now,),
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE clip_jobs SET status='running', updated_at=? WHERE id=?",
                (now, row["id"]),
            )
            conn.commit()
            return dict(row)

    # ------------------------------------------------------------------
    # Mark job complete / fail
    # ------------------------------------------------------------------

    def complete(self, job_id: str) -> None:
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "UPDATE clip_jobs SET status='done', updated_at=? WHERE id=?",
                (now, job_id),
            )
            conn.commit()
        log.info("queue", f"completed {job_id}")

    def fail(self, job_id: str, error: str = "") -> None:
        now = time.time()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT attempts, max_attempts FROM clip_jobs WHERE id=?",
                (job_id,),
            ).fetchone()
            if row is None:
                return
            attempts = row["attempts"] + 1
            max_attempts = row["max_attempts"]

            if attempts < max_attempts:
                # Requeue with backoff
                backoff = min(
                    BASE_BACKOFF_SECONDS * (2 ** (attempts - 1)),
                    MAX_BACKOFF_SECONDS,
                )
                retry_at = now + backoff
                conn.execute(
                    """UPDATE clip_jobs
                       SET status='queued', attempts=?, next_retry_at=?,
                           updated_at=?, error=?
                       WHERE id=?""",
                    (attempts, retry_at, now, error[:500], job_id),
                )
                conn.commit()
                log.info("queue", f"retry {job_id} (attempt {attempts}/{max_attempts}, +{backoff:.0f}s)")
            else:
                # Out of retries → permanent failure
                conn.execute(
                    """UPDATE clip_jobs
                       SET status='failed', attempts=?, updated_at=?, error=?
                       WHERE id=?""",
                    (attempts, now, error[:500], job_id),
                )
                conn.commit()
                log.info("queue", f"failed {job_id} after {attempts} attempts")

    # ------------------------------------------------------------------
    # Stale job recovery (called on worker startup)
    # ------------------------------------------------------------------

    def requeue_stale(self) -> int:
        """Requeue jobs that were 'running' when the worker died.

        Returns the count of requeued jobs.
        """
        now = time.time()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id FROM clip_jobs WHERE status='running'"
            ).fetchall()
            for row in rows:
                conn.execute(
                    """UPDATE clip_jobs
                       SET status='queued', attempts=attempts+1,
                           updated_at=?, error='stale (worker restarted)'
                       WHERE id=?""",
                    (now, row["id"]),
                )
            conn.commit()
        if rows:
            log.info("queue", f"requeued {len(rows)} stale job(s)")
        return len(rows)

    # ------------------------------------------------------------------
    # List / inspect
    # ------------------------------------------------------------------

    def list_jobs(self, limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM clip_jobs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_job(self, job_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM clip_jobs WHERE id=?", (job_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_jobs_for_project(self, project_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM clip_jobs WHERE project_id=? ORDER BY created_at DESC",
                (project_id,),
            ).fetchall()
            return [dict(r) for r in rows]