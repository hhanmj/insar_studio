"""Tests for core enumerations (Task 002)."""

from __future__ import annotations

from insar_prep.core import enums


def test_task_status_members() -> None:
    assert {s.value for s in enums.TaskStatus} == {
        "PENDING",
        "RUNNING",
        "PAUSED",
        "COMPLETED",
        "FAILED",
        "CANCELLED",
        "SKIPPED",
        "WAITING_FOR_USER",
    }


def test_job_status_members() -> None:
    assert {s.value for s in enums.JobStatus} == {
        "NOT_STARTED",
        "RUNNING",
        "COMPLETED",
        "COMPLETED_WITH_WARNINGS",
        "FAILED",
        "PARTIALLY_FAILED",
        "CANCELLED",
    }


def test_coverage_status_members() -> None:
    assert {s.value for s in enums.CoverageStatus} == {
        "COVERED",
        "PARTIALLY_COVERED",
        "NOT_COVERED",
        "UNKNOWN",
    }


def test_polarization_members() -> None:
    assert {s.value for s in enums.Polarization} == {"VV", "VH", "VV_VH", "HH", "HV"}


def test_enum_values_are_strings() -> None:
    assert isinstance(enums.TaskStatus.PENDING, str)
    assert enums.TaskStatus.PENDING == "PENDING"
    assert enums.TargetSoftware.SARSCAPE == "SARSCAPE"
