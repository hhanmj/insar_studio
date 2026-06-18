"""Tests for the task queue and state machine (Task 008)."""

from __future__ import annotations

import pytest

from insar_prep.core.enums import JobStatus, Provider, TaskStatus, TaskType
from insar_prep.core.exceptions import InputValidationError
from insar_prep.core.models import DownloadTask
from insar_prep.queue.task_queue import TaskQueue, summarize_job_status


def make_task(
    task_id: str,
    *,
    region_id: str = "r1",
    task_type: TaskType = TaskType.DOWNLOAD_SLC,
    priority: int = 0,
) -> DownloadTask:
    return DownloadTask(
        task_id=task_id,
        job_id="job1",
        region_id=region_id,
        provider=Provider.ASF,
        task_type=task_type,
        priority=priority,
    )


def test_add_single_task() -> None:
    queue = TaskQueue()
    queue.add_task(make_task("t1"))
    assert len(queue) == 1
    assert queue.get_status("t1") is TaskStatus.PENDING


def test_add_tasks_batch() -> None:
    queue = TaskQueue()
    queue.add_tasks([make_task("t1"), make_task("t2"), make_task("t3")])
    assert len(queue) == 3


def test_duplicate_task_id_raises() -> None:
    queue = TaskQueue()
    queue.add_task(make_task("t1"))
    with pytest.raises(InputValidationError):
        queue.add_task(make_task("t1"))


def test_pending_tasks_priority_order() -> None:
    queue = TaskQueue()
    queue.add_tasks(
        [make_task("low", priority=1), make_task("high", priority=9), make_task("mid", priority=5)]
    )
    assert [task.task_id for task in queue.pending_tasks()] == ["high", "mid", "low"]


def test_pending_tasks_exclude_non_pending() -> None:
    queue = TaskQueue()
    queue.add_tasks([make_task("a"), make_task("b")])
    queue.pause("b")
    assert {task.task_id for task in queue.pending_tasks()} == {"a"}


def test_pause_resume_cancel() -> None:
    queue = TaskQueue()
    queue.add_task(make_task("t1"))
    queue.pause("t1")
    assert queue.get_status("t1") is TaskStatus.PAUSED
    queue.resume("t1")
    assert queue.get_status("t1") is TaskStatus.PENDING
    queue.cancel("t1")
    assert queue.get_status("t1") is TaskStatus.CANCELLED


def test_invalid_transition_raises() -> None:
    queue = TaskQueue()
    queue.add_task(make_task("t1"))
    queue.cancel("t1")
    with pytest.raises(InputValidationError):
        queue.resume("t1")


def test_completed_cannot_retry() -> None:
    queue = TaskQueue()
    queue.add_task(make_task("t1"))
    queue.mark_running("t1")
    queue.mark_completed("t1")
    with pytest.raises(InputValidationError):
        queue.retry("t1")


def test_failed_can_retry_and_increment() -> None:
    queue = TaskQueue()
    queue.add_task(make_task("t1"))
    queue.mark_running("t1")
    queue.mark_failed("t1", error_code="DL001", error_message="boom")
    assert queue.get_status("t1") is TaskStatus.FAILED
    queue.retry("t1")
    task = queue.get("t1")
    assert task.status is TaskStatus.PENDING
    assert task.retry_count == 1
    assert task.error_code is None


def test_filter_by_region() -> None:
    queue = TaskQueue()
    queue.add_tasks([make_task("a", region_id="guangdong"), make_task("b", region_id="guangxi")])
    assert {task.task_id for task in queue.tasks_for_region("guangdong")} == {"a"}


def test_filter_by_task_type() -> None:
    queue = TaskQueue()
    queue.add_tasks(
        [
            make_task("a", task_type=TaskType.DOWNLOAD_SLC),
            make_task("b", task_type=TaskType.DOWNLOAD_DEM),
        ]
    )
    assert {task.task_id for task in queue.tasks_of_type(TaskType.DOWNLOAD_DEM)} == {"b"}


def test_unknown_task_raises() -> None:
    queue = TaskQueue()
    with pytest.raises(InputValidationError):
        queue.get_status("nope")


def _drive(queue: TaskQueue, task_id: str, final: TaskStatus) -> None:
    queue.mark_running(task_id)
    if final is TaskStatus.COMPLETED:
        queue.mark_completed(task_id)
    elif final is TaskStatus.FAILED:
        queue.mark_failed(task_id)


def test_summarize_job_status_cases() -> None:
    assert summarize_job_status([]) is JobStatus.NOT_STARTED

    pending = [make_task("a"), make_task("b")]
    assert summarize_job_status(pending) is JobStatus.NOT_STARTED

    completed = [make_task("c"), make_task("d")]
    queue_c = TaskQueue()
    queue_c.add_tasks(completed)
    for task in completed:
        _drive(queue_c, task.task_id, TaskStatus.COMPLETED)
    assert summarize_job_status(completed) is JobStatus.COMPLETED

    mixed = [make_task("e"), make_task("f")]
    queue_m = TaskQueue()
    queue_m.add_tasks(mixed)
    _drive(queue_m, "e", TaskStatus.COMPLETED)
    _drive(queue_m, "f", TaskStatus.FAILED)
    assert summarize_job_status(mixed) is JobStatus.PARTIALLY_FAILED

    failed = [make_task("g")]
    queue_f = TaskQueue()
    queue_f.add_tasks(failed)
    _drive(queue_f, "g", TaskStatus.FAILED)
    assert summarize_job_status(failed) is JobStatus.FAILED

    running = [make_task("h")]
    queue_r = TaskQueue()
    queue_r.add_tasks(running)
    queue_r.mark_running("h")
    assert summarize_job_status(running) is JobStatus.RUNNING
