# InSAR Data Preparation Assistant (`insar-prep`)

A SARscape-oriented InSAR **data preparation and quality-checking assistant** for
Sentinel-1 / InSAR beginners. It is **not** a full InSAR processing engine and does
not replace SARscape, ISCE, MintPy, SNAP, or ASF Vertex.

The tool helps organize and validate Sentinel-1 SLC lists, precise orbits, DEMs
(with vertical-datum conversion), GACOS atmospheric products, and produces
SARscape-ready directories, manifests, logs, and reports.

> Status: **v0.1.0 — project skeleton only.** No business features are implemented yet.

## Requirements

- Python 3.11
- [uv](https://docs.astral.sh/uv/)

## Quick start

```bash
uv sync
uv run insar-prep --help
uv run insar-prep --version
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## Project layout

```text
src/insar_prep/      # core package (importable as insar_prep)
  cli/               # command-line interface
tests/               # pytest test suite
.github/workflows/   # CI
```

See `DEVELOPMENT_MANUAL.md`, `CURSOR_OPUS_GUIDE.md`, and
`insar_prep_project_rules.mdc` for design, hard constraints, and the task roadmap.

## License

MIT — see [LICENSE](LICENSE).
