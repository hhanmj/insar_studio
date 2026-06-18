"""Quality checks for prepared InSAR inputs.

Task 007 implements scene consistency checks. Coverage/orbit/DEM/GACOS checks
are added in later tasks.
"""

from __future__ import annotations

from insar_prep.quality.scene_checks import check_scene_collection
from insar_prep.quality.types import CheckIssue, CheckSeverity, SceneCheckReport

__all__ = [
    "CheckIssue",
    "CheckSeverity",
    "SceneCheckReport",
    "check_scene_collection",
]
