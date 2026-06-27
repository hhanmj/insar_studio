"""Shared pytest fixtures and global test guards.

Disables the automatic GitHub update check for the whole suite so that running
the CLI ``main()`` in tests never attempts a network request (several tests ban
sockets and assert no network is opened). Tests that exercise the update-check
feature itself inject their own ``fetch`` / cache and do not rely on the network.
"""

from __future__ import annotations

import pytest

from insar_prep.core.update_check import UPDATE_CHECK_OPT_OUT_ENV


@pytest.fixture(autouse=True)
def _disable_auto_update_check(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(UPDATE_CHECK_OPT_OUT_ENV, "1")


@pytest.fixture(autouse=True)
def _default_language() -> None:
    """Reset the GUI language to English before each test for determinism.

    Tests that exercise the language switch set their own language inside the
    test; this guard keeps that state from leaking into later tests.
    """
    from insar_prep import i18n

    i18n.set_language("en")
