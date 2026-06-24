"""InSAR Data Preparation Assistant.

SARscape-oriented data preparation and quality-checking toolkit. As of v0.16.0
the offline CLI prepare workflow, the optional PySide6 GUI (with a runtime
English/中文 language switch), real ASF Sentinel-1 SLC download (CLI + GUI) with
a fast ``--download-mode verify`` network preflight, real DEM download from the
OpenTopography Global DEM API (CLI ``download-dem`` + GUI panel, each user
supplies their own free API key), a GitHub-Releases update check, real DEM
vertical-datum conversion (``convert-dem``, orthometric -> WGS84 ellipsoid via
the bundled EGM96 geoid, behind the optional ``convert`` extra), GACOS product
import (``gacos-import``: extract/organize/integrity-check manually downloaded
products), and -- new in v0.16.0 -- **real GACOS request submission and result
download** (``gacos-request`` / ``gacos-download`` + GUI panel, behind the
``download`` extra). Because GACOS has no public API, the real client automates
the two steps the service allows: submitting the web-request form and fetching
the emailed result archive (the email link itself is still pasted in by the
user).
"""

__version__ = "0.16.0"

__all__ = ["__version__"]
