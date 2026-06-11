"""
In-memory background run store.

Report runs execute in a small thread pool; the API returns a run_id
immediately and clients poll for status. Records live in memory only —
restart clears them. Capped at MAX_RUNS to bound memory (rendered HTML
payloads are kept on the records).
"""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable, Optional

from web.api.errors import error_detail

MAX_RUNS = 50


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunStore:
    def __init__(self, max_workers: int = 4) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, dict] = {}
        self._order: list[str] = []
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="tracebi-run"
        )

    def start(self, kind: str, name: str, fn: Callable[[], dict]) -> dict:
        """Submit ``fn`` to the pool and return the new run record."""
        run_id = uuid.uuid4().hex[:12]
        record = {
            "run_id":      run_id,
            "kind":        kind,
            "name":        name,
            "status":      "running",
            "started_at":  _now(),
            "finished_at": None,
            "result":      None,
            "error":       None,
        }
        with self._lock:
            self._runs[run_id] = record
            self._order.append(run_id)
            while len(self._order) > MAX_RUNS:
                self._runs.pop(self._order.pop(0), None)
        self._pool.submit(self._execute, run_id, fn)
        return dict(record)

    def _execute(self, run_id: str, fn: Callable[[], dict]) -> None:
        try:
            result, error, status = fn(), None, "succeeded"
        except Exception as exc:  # noqa: BLE001 — failures are the payload here
            result, status = None, "failed"
            error = error_detail("Run failed", exc)
        with self._lock:
            rec = self._runs.get(run_id)
            if rec is not None:  # may have been evicted under load
                rec.update(status=status, result=result, error=error,
                           finished_at=_now())

    def get(self, run_id: str) -> Optional[dict]:
        with self._lock:
            rec = self._runs.get(run_id)
            return dict(rec) if rec else None

    def list_for(self, kind: str, name: str, limit: int = 10) -> list[dict]:
        """Newest-first run summaries (without the result payload)."""
        with self._lock:
            out = [
                {k: v for k, v in self._runs[rid].items() if k != "result"}
                for rid in reversed(self._order)
                if self._runs[rid]["kind"] == kind
                and self._runs[rid]["name"] == name
            ]
        return out[:limit]


run_store = RunStore()
