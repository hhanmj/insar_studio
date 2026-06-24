"""InSAR Data Preparation Assistant.

SARscape-oriented data preparation and quality-checking toolkit. As of v0.15.0
the offline CLI prepare workflow, the optional PySide6 GUI Beta, real ASF
Sentinel-1 SLC download (CLI + GUI) with a fast ``--download-mode verify``
network preflight, real DEM download from the OpenTopography Global DEM API
(CLI ``download-dem`` + GUI panel, each user supplies their own free API key),
a GitHub-Releases update check, real DEM vertical-datum conversion
(``convert-dem``, orthometric -> WGS84 ellipsoid via the bundled EGM96 geoid,
behind the optional ``convert`` extra), and GACOS product import
(``gacos-import``: extract/organize/integrity-check manually downloaded
products) are implemented. Real GACOS *download* remains impossible (the
service has no public API); GACOS products are still requested and downloaded
manually.
"""

__version__ = "0.15.0"

__all__ = ["__version__"]
