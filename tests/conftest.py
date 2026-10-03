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
def silent_audio(monkeypatch):
    """No test ever makes a sound.

    Autouse and unconditional for the same reason as the save directory: a
    suite that chirps on every simulated keypress is unusable, and a CI box has
    no audio device to chirp with anyway. Removing the backend exercises the
    same path a machine without one takes, so the degrade-to-silence promise is
    under test on every run rather than only on the machines that lack sound.
    """
    from chessvania.audio import player

    monkeypatch.setattr(player, "_playsound", None)
