"""End-to-end tests for the ``gacos-import`` CLI. Offline, stdlib only."""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from insar_prep.cli.main import main


def _write_product(
    directory: Path,
    day: str,
    *,
    width: int = 3,
    length: int = 2,
    ztd_bytes: int | None = None,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{day}.ztd.rsc").write_text(
        f"WIDTH {width}\nFILE_LENGTH {length}\nX_FIRST 10.0\n", encoding="utf-8"
    )
    size = ztd_bytes if ztd_bytes is not None else 4 * width * length
    (directory / f"{day}.ztd").write_bytes(b"\x00" * size)


def _ban_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*args: object, **kwargs: object) -> object:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


def test_gacos_import_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["gacos-import", "--help"])
    assert exc.value.code == 0


def test_import_directory_offline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _ban_network(monkeypatch)
    src = tmp_path / "downloads"
    _write_product(src, "20230101")
    code = main(
        [
            "gacos-import",
            "--region-name",
            "Demo Area",
            "--output-root",
            str(tmp_path),
            "--source",
            str(src),
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "GACOS import" in out
    assert "product dates: 1" in out
    ready = tmp_path / "demo_area" / "05_atmosphere" / "gacos" / "requests" / "20230101.ztd"
    assert ready.is_file()


def test_import_size_mismatch_exits_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    src = tmp_path / "downloads"
    _write_product(src, "20230101", ztd_bytes=8)
    code = main(
        [
            "gacos-import",
            "--region-name",
            "demo",
            "--output-root",
            str(tmp_path),
            "--source",
            str(src),
        ]
    )
    assert code == 2
    assert "GACOS_SIZE_MISMATCH" in capsys.readouterr().out


def test_import_with_cart_coverage(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    import insar_prep.cli.commands as commands

    src = tmp_path / "downloads"
    _write_product(src, "20230101")
    cart = tmp_path / "urls.txt"
    cart.write_text("https://example.com/scene\n", encoding="utf-8")

    class _Scene:
        from datetime import datetime as _dt

        acquisition_datetime = _dt(2023, 1, 1)

    monkeypatch.setattr(commands, "parse_asf_cart_file", lambda path: [_Scene()])
    code = main(
        [
            "gacos-import",
            "--region-name",
            "demo",
            "--output-root",
            str(tmp_path),
            "--source",
            str(src),
            "--cart",
            str(cart),
        ]
    )
    assert code == 0
    assert "expected dates: 1" in capsys.readouterr().out
