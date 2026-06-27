# ASF / GeoDownloader-Style Upgrade Plan

## Current Scope

- Keep the main workspace map-first: left panel for resources, right panel for map, top bar for product mode.
- Sentinel-1 supports ASF metadata search, ASF official cart files (`.py`, `.metalink`, `.metadata`, `.csv`, `.geojson`, `.json`, `.txt`), and local SAR image directories.
- Map results draw per-scene footprints. Clicking a footprint should show acquisition time, product type, orbit direction, path, frame, orbit number, file size, and URL availability.
- Download center keeps active, paused, completed, failed, cancelled, and deleted task states.
- DEM keeps raw GeoTIFF, ellipsoidal GeoTIFF, and SARscape-ready `_dem.tif`.
- Orbit downloads write to `Sentinel_Orbit\AUX_POEORB` and explain unavailable precise orbits, especially for very recent scenes.

## Near-Term Upgrades

- Expand ASF search filters:
  - platform, processing level, beam mode, polarization, flight direction, relative orbit/path, frame, temporal range, intersects AOI, and max results.
  - preserve filters per task so switching panels does not clear results.
- Add scene cart behavior:
  - map click selects/unselects scenes.
  - table supports sort/filter by date, orbit, path/frame, size, and product type.
  - selected scenes can be exported to ASF-style `.py`, `.metalink`, CSV, and GeoJSON.
- Add footprint layer controls:
  - all scenes, selected scenes, downloaded scenes, failed scenes.
  - color by orbit direction, product type, or path.
- Improve cache:
  - cache search responses by query hash.
  - cache tile provider metadata and user-selected map source.
  - cache download manifests for resume and task history rebuild.

## ASF Website-Like Long-Term Scope

- Broaden products beyond the first Sentinel-1 SLC/GRD workflow:
  - Sentinel-1 RAW / OCN.
  - Sentinel-1 RTC or other ASF-hosted derived products where credentials and licensing allow.
  - Future SAR missions can reuse the same result table, footprint layer, cart, and download queue.
- Add InSAR-specific helpers on top of generic ASF search:
  - master/slave candidate grouping.
  - temporal baseline and perpendicular baseline columns when available.
  - burst/subswath helpers for TOPS workflows.
  - warning rules for mixed beam mode, polarization, orbit direction, path/frame, and incomplete AOI coverage.
- Add reusable resource providers:
  - Sentinel-2, Landsat, DEM, GACOS, orbit, and vector AOI layers should share the same task model.
  - each provider contributes search filters, result footprints, download actions, and output parameters.

## UI Direction

- Use an iOS-style transparent theme: rounded controls, frosted panels, restrained shadows, and map-first interaction.
- Keep region/AOI selection in the top workflow context, but render details in the left panel so the map remains interactive.
- Do not force project or region names; auto-name when blank.
- Ask for output/cache directories only when a task starts or when the user edits output parameters.
