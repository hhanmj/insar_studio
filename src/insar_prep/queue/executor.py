"""Task executors for the queue framework (Task 008).

Executors turn a :class:`DownloadTask` into an :class:`ExecutionResult`. The
provided executors are offline only: they never perform real network downloads.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.logging import get_logger
from insar_prep.core.models import DownloadTask
from insar_prep.queue.types import ExecutionResult

logger = get_logger("queue.executor")


@runtime_checkable
class TaskExecutor(Protocol):
    """Protocol implemented by anything that can execute a task."""

    def execute(self, task: DownloadTask) -> ExecutionResult: ...


class DryRunExecutor:
    """Executor that completes every task without doing any real work."""

    def execute(self, task: DownloadTask) -> ExecutionResult:
        logger.debug("dry-run executing task %s", task.task_id)
        return ExecutionResult(success=True, message="dry run")


class FailingExecutor:
    """Executor that always fails; used for retry/error-handling tests."""

    def __init__(self, message: str = "simulated failure", error_code: str | None = None) -> None:
        self.message = message
        self.error_code = error_code or ErrorCode.DL001.value

    def execute(self, task: DownloadTask) -> ExecutionResult:
        logger.debug("failing executor for task %s", task.task_id)
        return ExecutionResult(success=False, message=self.message, error_code=self.error_code)
