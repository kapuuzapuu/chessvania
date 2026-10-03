"""Sound: a data table of 8-bit blips, and a player that never raises.

`tones` holds the sound set and the synthesiser; `player` holds playback. Both
are presentation -- `core/` must not import either, and
`tests/test_architecture.py` enforces that.
"""

from .player import Audio, SilentAudio
from .tones import SOUNDS, Blip

__all__ = ["Audio", "SilentAudio", "SOUNDS", "Blip"]
