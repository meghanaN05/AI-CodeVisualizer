"""Background video-generation jobs.

Rendering a full trace can take minutes, far longer than an HTTP request
should stay open, so /generate enqueues a job and the client polls
/jobs/{id}. Jobs live in memory: they are lost on restart, which is fine for
a single-process dev server but needs a shared store (Redis, a database) to
run more than one backend worker.
"""

from __future__ import annotations

import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

STAGES = ("queued", "tracing", "planning", "rendering", "done", "failed")
MAX_PARALLEL_RENDERS = 2
KEEP_FINISHED_SECONDS = 60 * 60

_executor = ThreadPoolExecutor(max_workers=MAX_PARALLEL_RENDERS, thread_name_prefix="render")
_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def submit(work: Callable[[Callable[[str], None]], dict[str, Any]]) -> dict[str, Any]:
    """Run work(report_stage) in the background; returns the new job record."""
    _prune()
    job_id = uuid.uuid4().hex[:12]
    job = {"id": job_id, "status": "queued", "created_at": time.time(), "result": None, "error": None}
    with _lock:
        _jobs[job_id] = job

    def report(stage: str) -> None:
        _update(job_id, status=stage, updated_at=time.time())

    def run() -> None:
        try:
            result = work(report)
            _update(job_id, status="done", result=result, finished_at=time.time())
        except Exception as exc:
            traceback.print_exc()
            _update(job_id, status="failed", error=str(exc), finished_at=time.time())

    _executor.submit(run)
    return dict(job)


def get(job_id: str) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def _update(job_id: str, **fields: Any) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(fields)


def _prune() -> None:
    cutoff = time.time() - KEEP_FINISHED_SECONDS
    with _lock:
        for job_id in [
            j for j, job in _jobs.items() if job.get("finished_at", float("inf")) < cutoff
        ]:
            del _jobs[job_id]
