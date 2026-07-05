"""Small helpers for stable, human-readable TXT result tables."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence


def _cell(value: object) -> str:
    text = "" if value is None else str(value)
    return text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").replace("\t", " ")


def write_table_txt(
    path: Path | str,
    columns: Sequence[str],
    rows: Sequence[Mapping[str, object]],
) -> Path:
    """Write a UTF-8 TXT table with tab-separated fixed columns."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = ["\t".join(columns)]
    for row in rows:
        lines.append("\t".join(_cell(row.get(column, "")) for column in columns))
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target
