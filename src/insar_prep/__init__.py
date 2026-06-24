"""InSAR Data Preparation Assistant.

SARscape-oriented data preparation and quality-checking toolkit. As of v0.14.0
the offline CLI prepare workflow, the optional PySide6 GUI Beta, real ASF
Sentinel-1 SLC download (CLI + GUI) with a fast ``--download-mode verify``
network preflight, real DEM download from the OpenTopography Global DEM API
(CLI ``download-dem`` + GUI panel, each user supplies their own free API key),
and a GitHub-Releases update check are implemented. Real DEM vertical-datum
conversion remains intentionally deferred.
"""

__version__ = "0.14.0"

__all__ = ["__version__"]
