"""In-memory task queue layer.

Provides a simple task queue abstraction for background job execution.
Since the application does not currently use Celery, RQ, or a message broker,
this uses an in-memory queue with threading for fire-and-forget tasks.

For production-scale async workloads, replace with Celery/RQ/SQS.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class TaskResult:
    """Result of a queued task."""
    task_id: str
    success: bool
    result: Any = None
    error: str | None = None


class InMemoryQueue:
    """Thread-safe in-memory task queue with fire-and-forget execution."""

    def __init__(self, max_workers: int = 4) -> None:
        self._queue: deque[tuple[str, Callable, tuple, dict]] = deque()
        self._results: dict[str, TaskResult] = {}
        self._lock = threading.Lock()
        self._max_workers = max_workers
        self._semaphore = threading.Semaphore(max_workers)

    def enqueue(self, fn: Callable, *args: Any, **kwargs: Any) -> str:
        """Queue a task for background execution. Returns task_id."""
        task_id = str(uuid4())

        def _worker() -> None:
            try:
                result = fn(*args, **kwargs)
                with self._lock:
                    self._results[task_id] = TaskResult(
                        task_id=task_id, success=True, result=result,
                    )
            except Exception as exc:
                logger.exception("Task %s failed: %s", task_id, exc)
                with self._lock:
                    self._results[task_id] = TaskResult(
                        task_id=task_id, success=False, error=str(exc),
                    )
            finally:
                self._semaphore.release()

        self._semaphore.acquire(blocking=False) or self._semaphore.acquire()
        with self._lock:
            self._queue.append((task_id, fn, args, kwargs))
        threading.Thread(target=_worker, daemon=True).start()
        return task_id

    def get_result(self, task_id: str) -> TaskResult | None:
        """Get the result of a task. Returns None if not yet completed."""
        with self._lock:
            return self._results.get(task_id)

    def pending_count(self) -> int:
        """Number of tasks waiting in the queue."""
        with self._lock:
            return len(self._queue)

    def result_count(self) -> int:
        """Number of completed tasks (including failed)."""
        with self._lock:
            return len(self._results)

    def clear_results(self) -> int:
        """Clear all stored results. Returns count cleared."""
        with self._lock:
            count = len(self._results)
            self._results.clear()
            return count


# Global queue instance
task_queue = InMemoryQueue()


def get_task_queue() -> InMemoryQueue:
    """Get the global task queue instance."""
    return task_queue


def run_background(fn: Callable, *args: Any, **kwargs: Any) -> str:
    """Convenience: enqueue a function for background execution."""
    return task_queue.enqueue(fn, *args, **kwargs)
