"""Tests for task executors and the queue scheduler (Task 008)."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from insar_prep.core.enums import Provider, TaskStatus, TaskType
from insar_prep.core.models import DownloadTask
from insar_prep.queue.executor import DryRunExecutor, FailingExecutor
from insar_prep.queue.task_queue import TaskQueue
from insar_prep.queue.types import ExecutionResult, QueueRunConfig


def make_task(task_id: str, *, priority: int = 0) -> DownloadTask:
    return DownloadTask(
        task_id=task_id,
        job_id="job1",
        region_id="r1",
        provider=Provider.ASF,
        task_type=TaskType.DOWNLOAD_SLC,
        priority=priority,
    )


class RaisingExecutor:
    def execute(self, task: DownloadTask) -> ExecutionResult:
        raise RuntimeError("kaboom")


class SkippingExecutor:
    def execute(self, task: DownloadTask) -> ExecutionResult:
        return ExecutionResult(success=True, skipped=True, message="already present")


def test_dry_run_completes_all() -> None:
    queue = TaskQueue()
    queue.add_tasks([make_task("a"), make_task("b")])
    result = queue.run(DryRunExecutor())
    assert result.completed == 2
    assert result.failed == 0
    assert queue.get_status("a") is TaskStatus.COMPLETED


def test_dry_run_via_config_flag() -> None:
    queue = TaskQueue()
    queue.add_task(make_task("a"))
    result = queue.run(config=QueueRunConfig(dry_run=True))
    assert result.completed == 1


def test_failing_executor_marks_failed() -> None:
    queue = TaskQueue()
    queue.add_task(make_task("a"))
    result = queue.run(FailingExecutor(message="net down", error_code="DL001"))
    assert result.failed == 1
    task = queue.get("a")
    assert task.status is TaskStatus.FAILED
    assert task.error_code == "DL001"
    assert any("net down" in issue for issue in result.issues)


def test_stop_on_error_true_stops() -> None:
    queue = TaskQueue()
    queue.add_tasks(
        [make_task("a", priority=3), make_task("b", priority=2), make_task("c", priority=1)]
    )
    result = queue.run(FailingExecutor(), config=QueueRunConfig(stop_on_error=True))
    assert result.failed == 1
    assert queue.get_status("b") is TaskStatus.PENDING
    assert queue.get_status("c") is TaskStatus.PENDING


def test_stop_on_error_false_continues() -> None:
    queue = TaskQueue()
    queue.add_tasks([make_task("a"), make_task("b"), make_task("c")])
    result = queue.run(FailingExecutor(), config=QueueRunConfig(stop_on_error=False))
    assert result.failed == 3


def test_waiting_for_user_not_executed() -> None:
    queue = TaskQueue()
    queue.add_task(make_task("a"))
    queue.mark_waiting_for_user("a")
    result = queue.run(DryRunExecutor())
    assert queue.get_status("a") is TaskStatus.WAITING_FOR_USER
    assert result.completed == 0


def test_paused_not_executed() -> None:
    queue = TaskQueue()
    queue.add_task(make_task("a"))
    queue.pause("a")
    queue.run(DryRunExecutor())
    assert queue.get_status("a") is TaskStatus.PAUSED


def test_executor_exception_becomes_failure() -> None:
    queue = TaskQueue()
    queue.add_task(make_task("a"))
    result = queue.run(RaisingExecutor())
    assert queue.get_status("a") is TaskStatus.FAILED
    assert result.failed == 1
    assert result.issues


def test_retry_then_rerun_completes() -> None:
    queue = TaskQueue()
    queue.add_task(make_task("a"))
    queue.run(FailingExecutor())
    assert queue.get_status("a") is TaskStatus.FAILED
    queue.retry("a")
    queue.run(DryRunExecutor())
    assert queue.get_status("a") is TaskStatus.COMPLETED
    assert queue.get("a").retry_count == 1


def test_skipped_outcome() -> None:
    queue = TaskQueue()
    queue.add_task(make_task("a"))
    result = queue.run(SkippingExecutor())
    assert queue.get_status("a") is TaskStatus.SKIPPED
    assert result.skipped == 1


def test_result_is_json_serializable() -> None:
    queue = TaskQueue()
    queue.add_tasks([make_task("a"), make_task("b")])
    result = queue.run(DryRunExecutor())
    assert isinstance(json.dumps(result.to_dict()), str)


def test_max_concurrent_validation() -> None:
    with pytest.raises(ValidationError):
        QueueRunConfig(max_concurrent_tasks=0)
