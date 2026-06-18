"""Offline task queue and scheduling framework (Task 008).

Implements an in-memory task queue, a task state machine, and a sequential
scheduler that drives a :class:`TaskExecutor`. No network, no real downloads,
no GUI. This is the shared scheduling base for later ASF/orbit/DEM/GACOS tasks.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence

from insar_prep.core.enums import JobStatus, TaskStatus, TaskType
from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.events import EventType
from insar_prep.core.exceptions import InputValidationError
from insar_prep.core.logging import get_logger, log_event
from insar_prep.core.models import DownloadTask
from insar_prep.queue.executor import DryRunExecutor, TaskExecutor
from insar_prep.queue.types import QueueRunConfig, QueueRunResult

logger = get_logger("queue.task_queue")

# Allowed task state transitions.
_ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {
        TaskStatus.RUNNING,
        TaskStatus.PAUSED,
        TaskStatus.CANCELLED,
        TaskStatus.WAITING_FOR_USER,
    },
    TaskStatus.RUNNING: {
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
        TaskStatus.SKIPPED,
        TaskStatus.WAITING_FOR_USER,
    },
    TaskStatus.PAUSED: {TaskStatus.PENDING, TaskStatus.CANCELLED},
    TaskStatus.FAILED: {TaskStatus.PENDING, TaskStatus.CANCELLED},
    TaskStatus.WAITING_FOR_USER: {TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.CANCELLED},
    TaskStatus.COMPLETED: set(),
    TaskStatus.CANCELLED: set(),
    TaskStatus.SKIPPED: set(),
}


def summarize_job_status(tasks: Sequence[DownloadTask]) -> JobStatus:
    """Summarize a job's status from its tasks' statuses."""
    if not tasks:
        return JobStatus.NOT_STARTED
    statuses = [task.status for task in tasks]
    if any(status is TaskStatus.RUNNING for status in statuses):
        return JobStatus.RUNNING
    if all(status is TaskStatus.PENDING for status in statuses):
        return JobStatus.NOT_STARTED
    completed = sum(1 for status in statuses if status is TaskStatus.COMPLETED)
    failed = sum(1 for status in statuses if status is TaskStatus.FAILED)
    if failed and completed:
        return JobStatus.PARTIALLY_FAILED
    if failed:
        return JobStatus.FAILED
    if all(status is TaskStatus.COMPLETED for status in statuses):
        return JobStatus.COMPLETED
    if completed and any(
        status in {TaskStatus.SKIPPED, TaskStatus.CANCELLED} for status in statuses
    ):
        return JobStatus.COMPLETED_WITH_WARNINGS
    return JobStatus.RUNNING


class TaskQueue:
    """An in-memory queue of :class:`DownloadTask` objects."""

    def __init__(self) -> None:
        self._tasks: dict[str, DownloadTask] = {}

    def __len__(self) -> int:
        return len(self._tasks)

    def add_task(self, task: DownloadTask) -> None:
        if task.task_id in self._tasks:
            raise InputValidationError(f"duplicate task_id {task.task_id!r}", code=ErrorCode.ASF001)
        self._tasks[task.task_id] = task

    def add_tasks(self, tasks: Iterable[DownloadTask]) -> None:
        for task in tasks:
            self.add_task(task)

    def all_tasks(self) -> list[DownloadTask]:
        return list(self._tasks.values())

    def get(self, task_id: str) -> DownloadTask:
        try:
            return self._tasks[task_id]
        except KeyError:
            raise InputValidationError(
                f"unknown task_id {task_id!r}", code=ErrorCode.ASF001
            ) from None

    def get_status(self, task_id: str) -> TaskStatus:
        return self.get(task_id).status

    def pending_tasks(self) -> list[DownloadTask]:
        """Return PENDING tasks ordered by priority (desc) then creation time."""
        pending = [task for task in self._tasks.values() if task.status is TaskStatus.PENDING]
        pending.sort(key=lambda task: (-task.priority, task.created_at))
        return pending

    def tasks_for_region(self, region_id: str) -> list[DownloadTask]:
        return [task for task in self._tasks.values() if task.region_id == region_id]

    def tasks_of_type(self, task_type: TaskType) -> list[DownloadTask]:
        return [task for task in self._tasks.values() if task.task_type == task_type]

    def _transition(self, task: DownloadTask, target: TaskStatus) -> None:
        if target not in _ALLOWED_TRANSITIONS[task.status]:
            raise InputValidationError(
                f"cannot move task {task.task_id!r} from {task.status.value} to {target.value}",
                code=ErrorCode.ASF001,
            )
        task.status = target

    def pause(self, task_id: str) -> None:
        self._transition(self.get(task_id), TaskStatus.PAUSED)

    def resume(self, task_id: str) -> None:
        self._transition(self.get(task_id), TaskStatus.PENDING)

    def cancel(self, task_id: str) -> None:
        self._transition(self.get(task_id), TaskStatus.CANCELLED)

    def mark_running(self, task_id: str) -> None:
        self._transition(self.get(task_id), TaskStatus.RUNNING)

    def mark_completed(self, task_id: str) -> None:
        self._transition(self.get(task_id), TaskStatus.COMPLETED)

    def mark_waiting_for_user(self, task_id: str) -> None:
        self._transition(self.get(task_id), TaskStatus.WAITING_FOR_USER)

    def mark_failed(
        self, task_id: str, *, error_code: str | None = None, error_message: str | None = None
    ) -> None:
        task = self.get(task_id)
        self._transition(task, TaskStatus.FAILED)
        if error_code is not None:
            task.error_code = error_code
        if error_message is not None:
            task.error_message = error_message

    def retry(self, task_id: str) -> None:
        task = self.get(task_id)
        self._transition(task, TaskStatus.PENDING)
        task.retry_count += 1
        task.error_code = None
        task.error_message = None

    def run(
        self,
        executor: TaskExecutor | None = None,
        config: QueueRunConfig | None = None,
    ) -> QueueRunResult:
        """Run all pending tasks (by priority) through ``executor``."""
        run_config = config or QueueRunConfig()
        active = DryRunExecutor() if executor is None or run_config.dry_run else executor
        issues: list[str] = []
        for task in self.pending_tasks():
            issue = self._execute_one(task, active)
            if issue is not None:
                issues.append(issue)
            if run_config.stop_on_error and task.status is TaskStatus.FAILED:
                break
        return self._summarize_run(issues)

    def _execute_one(self, task: DownloadTask, executor: TaskExecutor) -> str | None:
        self._transition(task, TaskStatus.RUNNING)
        log_event(
            logger,
            EventType.DOWNLOAD_STARTED,
            f"task {task.task_id} started",
            module="queue",
            payload={"task_id": task.task_id},
        )
        try:
            outcome = executor.execute(task)
        except Exception as exc:  # convert any executor error into a task failure
            self._transition(task, TaskStatus.FAILED)
            task.error_message = str(exc)
            log_event(
                logger,
                EventType.DOWNLOAD_FAILED,
                f"task {task.task_id} raised an exception",
                level="ERROR",
                module="queue",
                payload={"task_id": task.task_id},
            )
            return f"{task.task_id}: {exc}"
        if outcome.skipped:
            self._transition(task, TaskStatus.SKIPPED)
            return None
        if outcome.success:
            self._transition(task, TaskStatus.COMPLETED)
            log_event(
                logger,
                EventType.DOWNLOAD_FINISHED,
                f"task {task.task_id} finished",
                module="queue",
                payload={"task_id": task.task_id},
            )
            return None
        self._transition(task, TaskStatus.FAILED)
        task.error_code = outcome.error_code
        task.error_message = outcome.message
        log_event(
            logger,
            EventType.DOWNLOAD_FAILED,
            f"task {task.task_id} failed",
            level="ERROR",
            module="queue",
            payload={"task_id": task.task_id},
        )
        return f"{task.task_id}: {outcome.message}"

    def _summarize_run(self, issues: list[str]) -> QueueRunResult:
        counts = Counter(task.status for task in self._tasks.values())
        return QueueRunResult(
            total=len(self._tasks),
            completed=counts.get(TaskStatus.COMPLETED, 0),
            failed=counts.get(TaskStatus.FAILED, 0),
            cancelled=counts.get(TaskStatus.CANCELLED, 0),
            skipped=counts.get(TaskStatus.SKIPPED, 0),
            issues=issues,
        )
