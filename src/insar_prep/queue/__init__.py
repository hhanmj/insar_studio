"""Offline task queue and scheduling framework.

Task 008 implements the queue, task state machine, executors, and a sequential
scheduler. Real network downloads are provided by later provider tasks.
"""

from __future__ import annotations

from insar_prep.queue.executor import (
    DryRunExecutor,
    FailingExecutor,
    TaskExecutor,
)
from insar_prep.queue.task_queue import TaskQueue, summarize_job_status
from insar_prep.queue.types import ExecutionResult, QueueRunConfig, QueueRunResult

__all__ = [
    "DryRunExecutor",
    "ExecutionResult",
    "FailingExecutor",
    "QueueRunConfig",
    "QueueRunResult",
    "TaskExecutor",
    "TaskQueue",
    "summarize_job_status",
]
