from __future__ import annotations

import tomllib
from pathlib import Path


def test_full_desktop_selftest_dependencies_are_declared_in_convert_extra() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    convert_deps = {
        dep.split(";", 1)[0].split("[", 1)[0].split(">", 1)[0].split("<", 1)[0].split("=", 1)[0].strip().lower()
        for dep in project["project"]["optional-dependencies"]["convert"]
    }

    assert {"numpy", "pyproj", "rasterio"} <= convert_deps
