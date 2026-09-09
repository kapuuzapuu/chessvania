"""Shared test setup."""

import pytest


@pytest.fixture(autouse=True)
def isolated_saves(tmp_path, monkeypatch):
    """Point every test at a throwaway save directory.

    Autouse and unconditional: without it a test run would read and overwrite
    the player's real profile and run-in-progress.
    """
    monkeypatch.setenv("CHESSVANIA_DATA_DIR", str(tmp_path / "saves"))


@pytest.fixture(autouse=True)
def default_piece_fill():
    """Reset the glyph fill around every test.

    `theme` holds the fill as module state, which is the right call for a
    display mode that applies to the whole app but does mean one test could
    otherwise leak its preference into the next one.
    """
    from chessvania.ui import theme

    theme.set_piece_fill(False)
    yield
    theme.set_piece_fill(False)
