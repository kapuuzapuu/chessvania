"""Sound: the data table, the synthesiser, and the promise never to crash."""

import asyncio
import wave

import pytest

from chessvania.app import ChessvaniaApp
from chessvania.audio import Audio, SilentAudio
from chessvania.audio import player as player_module
from chessvania.audio.tones import NOISE, RATE, SOUNDS, SQUARE, TRIANGLE, render, wav_for
from chessvania.ui.layout import minimum_terminal

MIN_TERMINAL = minimum_terminal()


class FakeEngine:
    def configure(self, elo):
        pass

    def __call__(self, board):
        return next(iter(board.legal_moves))

    def close(self):
        pass


def drive(scenario):
    asyncio.run(scenario())


# -- the sound set -------------------------------------------------------


def test_every_sound_renders_to_a_playable_wav(tmp_path):
    for name in SOUNDS:
        path = tmp_path / ("%s.wav" % name)
        path.write_bytes(wav_for(name, 0.5))
        with wave.open(str(path)) as handle:
            assert handle.getnchannels() == 1
            assert handle.getsampwidth() == 2
            assert handle.getframerate() == RATE
            assert handle.getnframes() > 0, "%s is silent" % name


def test_every_sound_uses_a_waveform_the_synth_knows():
    for name, blip in SOUNDS.items():
        assert blip.wave in (SQUARE, TRIANGLE, NOISE), (
            "%s asks for an unknown waveform %r" % (name, blip.wave))


def test_sounds_stay_short_enough_to_land_on_the_action():
    """Past about a third of a second a blip arrives after the thing it describes.

    The outcome stings are exempt: nothing follows them.
    """
    for name, blip in SOUNDS.items():
        limit = 700 if name in ("win", "defeat") else 300
        assert blip.milliseconds <= limit, (
            "%s runs %dms" % (name, blip.milliseconds))


def _peak(frames: bytes) -> int:
    """Loudest sample. The frames are 16-bit little-endian, so bytes won't do."""
    import struct

    samples = struct.unpack("<%dh" % (len(frames) // 2), frames)
    return max(abs(sample) for sample in samples)


def test_volume_scales_the_waveform():
    quiet = render(SOUNDS["select"], 0.1)
    loud = render(SOUNDS["select"], 1.0)
    assert len(quiet) == len(loud), "volume must not change the duration"
    assert _peak(quiet) < _peak(loud) / 2


def test_noise_is_deterministic():
    """A capture should sound the same every time, not reroll per run."""
    assert render(SOUNDS["capture"]) == render(SOUNDS["capture"])


# -- the player ----------------------------------------------------------


def test_a_missing_backend_degrades_to_silence(monkeypatch):
    monkeypatch.setattr(player_module, "_playsound", None)
    audio = Audio(enabled=True, volume=80)
    assert audio.available is False
    assert audio.play("select") is False        # no exception


def test_a_backend_that_throws_is_swallowed(monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("no audio device")

    monkeypatch.setattr(player_module, "_playsound", explode)
    audio = Audio(enabled=True, volume=80)
    assert audio.play("select") is False, "a dead backend must not propagate"


def test_an_unknown_sound_is_ignored(monkeypatch):
    monkeypatch.setattr(player_module, "_playsound", lambda *a, **k: None)
    audio = Audio(enabled=True, volume=80)
    assert audio.play("no-such-sound") is False


def test_disabled_and_zero_volume_both_stay_quiet(monkeypatch):
    played = []
    monkeypatch.setattr(player_module, "_playsound",
                        lambda *a, **k: played.append(a))

    audio = Audio(enabled=False, volume=80)
    assert audio.play("select") is False

    audio.configure(enabled=True, volume=0)
    assert audio.play("select") is False
    assert not played


def test_changing_volume_rerenders_rather_than_reusing_the_file(monkeypatch):
    monkeypatch.setattr(player_module, "_playsound", lambda *a, **k: None)
    audio = Audio(enabled=True, volume=80)
    audio.play("select")
    first = dict(audio._cache)

    audio.configure(enabled=True, volume=20)
    audio.play("select")
    assert set(first) != set(audio._cache), "volume change reused a cached file"


def test_volume_is_clamped():
    audio = Audio()
    audio.configure(True, 900)
    assert audio.volume == 100
    audio.configure(True, -50)
    assert audio.volume == 0


def test_the_silent_player_records_without_playing():
    audio = SilentAudio()
    audio.play("capture")
    assert audio.played == ["capture"]
    assert audio.available is False


# -- wiring --------------------------------------------------------------


def test_the_app_routes_sounds_through_the_injected_player():
    async def scenario():
        audio = SilentAudio()
        app = ChessvaniaApp(engine=FakeEngine(), seed=1, audio=audio)
        async with app.run_test(size=MIN_TERMINAL) as pilot:
            await pilot.press("escape")       # skip the boot animation
            await pilot.pause()
            audio.played.clear()
            await pilot.press("down")
            await pilot.pause()
            assert "cursor" in audio.played, "menu movement made no sound"

    drive(scenario)


def test_settings_reach_the_player_at_startup():
    async def scenario():
        from chessvania.persistence import save_profile
        from chessvania.core.progress import Profile

        profile = Profile()
        profile.settings.audio = False
        profile.settings.volume = 35
        save_profile(profile)

        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=MIN_TERMINAL) as pilot:
            await pilot.pause()
            assert app.audio.enabled is False
            assert app.audio.volume == 35

    drive(scenario)
