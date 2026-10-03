"""Playback. Injected like the engine is, and silent by construction in tests.

THIS LAYER NEVER RAISES. A missing backend, a read-only temp directory, a
machine with no sound card, an SSH session -- all of it degrades to silence,
because a game must not die for want of a blip. `available` says whether
anything will actually be heard, for the settings screen to report.

Rendered sounds are cached to temp files per (sound, volume). They are a few
kilobytes each and the whole set is under 100 KB, so the cache is built lazily
and thrown away with the process.
"""

from __future__ import annotations

import atexit
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Optional, Tuple

from .tones import SOUNDS, wav_for

try:  # pragma: no cover - import guard, exercised by not having the package
    from playsound3 import playsound as _playsound
except Exception:  # noqa: BLE001 - any import failure means no audio, not a crash
    _playsound = None


class Audio:
    """Plays the sound set. Construct one per app; the UI calls `play`."""

    def __init__(self, enabled: bool = True, volume: int = 70) -> None:
        self.enabled = enabled
        self.volume = volume
        self._cache: Dict[Tuple[str, int], Path] = {}
        self._directory: Optional[Path] = None

    # -- state -----------------------------------------------------------

    @property
    def available(self) -> bool:
        """Whether a backend exists at all, regardless of the user's setting."""
        return _playsound is not None

    def configure(self, enabled: bool, volume: int) -> None:
        if volume != self.volume:
            # Amplitude is baked in at render time, so a volume change
            # invalidates every cached file rather than being applied at play.
            self._cache.clear()
        self.enabled = enabled
        self.volume = max(0, min(100, volume))

    # -- playback --------------------------------------------------------

    def play(self, name: str) -> bool:
        """Fire and forget. Returns whether a sound was actually started."""
        if not self.enabled or not self.available or self.volume <= 0:
            return False
        if name not in SOUNDS:
            return False
        try:
            path = self._file_for(name)
            _playsound(str(path), block=False)
            return True
        except Exception:  # noqa: BLE001 - see the module docstring
            return False

    def _file_for(self, name: str) -> Path:
        key = (name, self.volume)
        cached = self._cache.get(key)
        if cached is not None and cached.exists():
            return cached

        if self._directory is None:
            self._directory = Path(tempfile.mkdtemp(prefix="chessvania-audio-"))
            atexit.register(shutil.rmtree, self._directory, True)

        path = self._directory / ("%s-%d.wav" % (name, self.volume))
        path.write_bytes(wav_for(name, self.volume / 100.0))
        self._cache[key] = path
        return path


class SilentAudio(Audio):
    """A no-op player. Tests use it so a suite run never makes a sound."""

    def __init__(self) -> None:
        super().__init__(enabled=False, volume=0)
        self.played: list = []
        """Every name passed to `play`, so tests can assert on intent."""

    @property
    def available(self) -> bool:
        return False

    def play(self, name: str) -> bool:
        self.played.append(name)
        return False
