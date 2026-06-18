"""JSON serialization helpers for core data models (Task 002).

Scope is JSON only. YAML support is intentionally not implemented here; when it
is added (for ``project.yaml`` / ``region.yaml`` config loading) it must use
``yaml.safe_load`` / ``yaml.safe_dump`` and never the unsafe ``yaml.load``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

ModelT = TypeVar("ModelT", bound=BaseModel)


def model_to_json(model: BaseModel, *, indent: int | None = 2) -> str:
    """Serialize a model to a JSON string."""
    return model.model_dump_json(indent=indent)


def model_from_json(model_type: type[ModelT], data: str | bytes) -> ModelT:
    """Parse and validate a model from a JSON string or bytes."""
    return model_type.model_validate_json(data)


def save_json(model: BaseModel, path: str | Path, *, indent: int | None = 2) -> Path:
    """Write a model to ``path`` as JSON, creating parent directories."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(model.model_dump_json(indent=indent), encoding="utf-8")
    return target


def load_json(model_type: type[ModelT], path: str | Path) -> ModelT:
    """Read and validate a model from a JSON file at ``path``."""
    return model_type.model_validate_json(Path(path).read_text(encoding="utf-8"))
