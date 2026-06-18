# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-06-18

### Added

- Initial project skeleton (Task 001).
- `pyproject.toml` with uv, hatchling build backend, ruff, and pytest configuration.
- `insar-prep` CLI entry point supporting `--help` and `--version` only.
- `src/insar_prep` package (src-layout) with a `cli` subpackage.
- Smoke tests in `tests/test_import.py`.
- GitHub Actions CI running ruff and pytest.
