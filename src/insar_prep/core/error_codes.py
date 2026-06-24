"""Error codes for user-visible failures (manual section 18.2).

Each user-visible error in the application is identified by a stable code from
``ErrorCode``. ``ERROR_CODE_MESSAGES`` provides a default human-readable message
for every code.
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    """Stable identifiers for user-visible errors."""

    CFG001 = "CFG001"
    CFG002 = "CFG002"
    AUTH001 = "AUTH001"
    AUTH002 = "AUTH002"
    ASF001 = "ASF001"
    ASF002 = "ASF002"
    ASF003 = "ASF003"
    AOI001 = "AOI001"
    AOI002 = "AOI002"
    AOI003 = "AOI003"
    DL001 = "DL001"
    DL002 = "DL002"
    DL003 = "DL003"
    DL004 = "DL004"
    DL005 = "DL005"
    ORB001 = "ORB001"
    DEM001 = "DEM001"
    DEM002 = "DEM002"
    DEM003 = "DEM003"
    DEM004 = "DEM004"
    DEM005 = "DEM005"
    GAC001 = "GAC001"
    GAC002 = "GAC002"
    REP001 = "REP001"
    GUI001 = "GUI001"
    GUI002 = "GUI002"
    GUI003 = "GUI003"


ERROR_CODE_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.CFG001: "Project configuration file is missing.",
    ErrorCode.CFG002: "Project configuration field is invalid.",
    ErrorCode.AUTH001: "Account credential is missing.",
    ErrorCode.AUTH002: "Account authentication failed.",
    ErrorCode.ASF001: "ASF cart file cannot be parsed.",
    ErrorCode.ASF002: "ASF search failed.",
    ErrorCode.ASF003: "ASF download link is invalid.",
    ErrorCode.AOI001: "AOI input is invalid.",
    ErrorCode.AOI002: "AOI multi-feature processing failed.",
    ErrorCode.AOI003: "China administrative boundary is missing review-number metadata.",
    ErrorCode.DL001: "Download was interrupted.",
    ErrorCode.DL002: "Downloaded file size does not match.",
    ErrorCode.DL003: "Zip integrity check failed.",
    ErrorCode.DL004: "ASF/Earthdata download credentials are missing or were rejected.",
    ErrorCode.DL005: "ASF download network/transport error.",
    ErrorCode.ORB001: "No matching orbit file was found.",
    ErrorCode.DEM001: "DEM download failed.",
    ErrorCode.DEM002: "DEM vertical datum is unknown.",
    ErrorCode.DEM003: "DEM ellipsoid-height conversion failed.",
    ErrorCode.DEM004: "SARscape DEM naming is invalid.",
    ErrorCode.DEM005: "OpenTopography DEM API key is missing or was rejected.",
    ErrorCode.GAC001: "GACOS date list generation failed.",
    ErrorCode.GAC002: "GACOS product dates are incomplete.",
    ErrorCode.REP001: "Report generation failed.",
    ErrorCode.GUI001: "GUI dependency (PySide6) is not installed.",
    ErrorCode.GUI002: "GUI workflow step prerequisite is missing.",
    ErrorCode.GUI003: "GUI input value is invalid.",
}
