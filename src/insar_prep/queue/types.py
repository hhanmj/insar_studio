"""Data structures for the task queue framework (Task 008).

All models are JSON-serializable via the shared pydantic base model.
"""

from __future__ import annotations

from pydantic import Field

from insar_prep.core.models import InsarBaseModel


class ExecutionResult(InsarBaseModel):
    """The outcome of executing a single task."""

    success: bool
    skipped: bool = False
    message: str = ""
    error_code: str | None = None


class QueueRunConfig(InsarBaseModel):
    """Configuration for a single queue run."""

    max_concurrent_tasks: int = Field(default=1, ge=1)
    stop_on_error: bool = False
    dry_run: bool = False


class QueueRunResult(InsarBaseModel):
    """A summary of a queue run (final status distribution + issues)."""

    total: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0
    skipped: int = 0
    issues: list[str] = Field(default_factory=list)
