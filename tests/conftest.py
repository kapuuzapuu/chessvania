"""Shared test setup."""

import pytest


@pytest.fixture(autouse=True)
def isolated_saves(tmp_path, monkeypatch):
    """Point every test at a throwaway save directory.

    Autouse and unconditional: without it a test run would read and overwrite
    the player's real profile and run-in-progress.
    """
    monkeypatch.setenv("CHESSVANIA_DATA_DIR", str(tmp_path / "saves"))
