"""Build the bundled EGM96 geoid grid (``egm96_15.npz``) from a GeographicLib PGM.

The real DEM vertical-datum conversion (``providers/dem/converter.py``) needs a
geoid-undulation grid to turn orthometric (EGM96/EGM2008) DEM heights into WGS84
ellipsoidal heights. We bundle the small EGM96 15-arc-minute grid published for
the ``GeographicLib::Geoid`` class (public domain, derived from NGA's EGM96).

This is a *maintenance* script, run once to regenerate the committed data file;
it is not imported at runtime and adds no runtime dependency. Provenance:

    https://sourceforge.net/projects/geographiclib/files/geoids-distrib/
    egm96-15.tar.bz2  (contains geoids/egm96-15.pgm)

Usage::

    uv run --no-sync python scripts/build_geoid_npz.py PATH_TO_egm96-15.tar.bz2
    uv run --no-sync python scripts/build_geoid_npz.py PATH_TO_egm96-15.pgm

The output is written to ``src/insar_prep/data/egm96_15.npz`` with arrays:

* ``undulation`` -- float32 (height, width) geoid undulation N in metres, where
  ``N = ellipsoidal_height - orthometric_height``.
* scalar metadata: ``lat0``, ``lon0``, ``dlat``, ``dlon`` (degrees), plus the
  string ``model`` and ``source``.

The grid runs north->south (row 0 = +90 deg lat) and west->east over
``lon = 0 .. 360`` (the final column duplicates ``lon = 0``).
"""

from __future__ import annotations

import sys
import tarfile
from pathlib import Path

import numpy as np

_OUT = Path(__file__).resolve().parent.parent / "src" / "insar_prep" / "data" / "egm96_15.npz"
_SOURCE = "GeographicLib egm96-15.pgm (public domain, NGA EGM96)"


def _read_pgm_bytes(path: Path) -> bytes:
    if path.suffixes[-2:] == [".tar", ".bz2"] or path.suffix == ".bz2":
        with tarfile.open(path, "r:bz2") as tar:
            member = next(m for m in tar.getmembers() if m.name.endswith(".pgm"))
            extracted = tar.extractfile(member)
            if extracted is None:  # pragma: no cover - defensive
                raise ValueError(f"could not extract {member.name}")
            return extracted.read()
    return path.read_bytes()


def _next_token(data: bytes, pos: int, comments: list[bytes]) -> tuple[bytes, int]:
    """Return the next whitespace-delimited token, recording comment lines."""
    while True:
        while pos < len(data) and data[pos] in b" \t\r\n":
            pos += 1
        if pos < len(data) and data[pos : pos + 1] == b"#":
            eol = data.find(b"\n", pos)
            eol = len(data) if eol == -1 else eol
            comments.append(data[pos:eol])
            pos = eol + 1
            continue
        break
    start = pos
    while pos < len(data) and data[pos] not in b" \t\r\n":
        pos += 1
    return data[start:pos], pos


def parse_geographiclib_pgm(data: bytes) -> tuple[np.ndarray, float, float]:
    """Parse a GeographicLib geoid PGM -> (undulation[h, w], offset, scale)."""
    if data[:2] != b"P5":
        raise ValueError("not a binary PGM (missing P5 magic)")
    pos = 2
    comments: list[bytes] = []
    width_b, pos = _next_token(data, pos, comments)
    height_b, pos = _next_token(data, pos, comments)
    maxval_b, pos = _next_token(data, pos, comments)
    width, height, maxval = int(width_b), int(height_b), int(maxval_b)
    if maxval < 256:
        raise ValueError(f"expected 16-bit PGM, got maxval={maxval}")
    # Exactly one whitespace byte separates the header from the raster.
    binary_start = pos + 1
    raw = np.frombuffer(data, dtype=">u2", count=width * height, offset=binary_start)
    raw = raw.astype(np.float64).reshape(height, width)

    offset = scale = None
    for line in comments:
        text = line.decode("ascii", "ignore")
        if text.startswith("# Offset"):
            offset = float(text.split()[-1])
        elif text.startswith("# Scale"):
            scale = float(text.split()[-1])
    if offset is None or scale is None:
        raise ValueError("PGM header is missing the Offset/Scale comments")
    undulation = (offset + scale * raw).astype(np.float32)
    return undulation, offset, scale


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    src = Path(argv[1])
    if not src.exists():
        print(f"input not found: {src}")
        return 2
    undulation, offset, scale = parse_geographiclib_pgm(_read_pgm_bytes(src))
    height, width = undulation.shape
    # GeographicLib layout: latitude spans -90..+90 inclusive (height-1 steps),
    # longitude spans 0..360 with the wrap column omitted (width steps), so the
    # final stored column is at 360 - dlon and column ``width`` wraps to column 0.
    dlon = 360.0 / width
    dlat = -180.0 / (height - 1)
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        _OUT,
        undulation=undulation,
        lat0=np.float64(90.0),
        lon0=np.float64(0.0),
        dlat=np.float64(dlat),
        dlon=np.float64(dlon),
        model=np.str_("EGM96"),
        source=np.str_(_SOURCE),
    )
    print(
        f"wrote {_OUT} ({_OUT.stat().st_size} bytes); grid {height}x{width}, "
        f"dlat={dlat}, dlon={dlon}, offset={offset}, scale={scale}, "
        f"N range [{float(undulation.min()):.2f}, {float(undulation.max()):.2f}] m"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
