"""The sound set, as data, plus the synthesiser that renders it.

NOTHING IS SHIPPED AS AN AUDIO FILE. Every sound is built from square, triangle
and noise waves at 22.05 kHz, which is both why it sounds like a 1986 console
and why there is no third-party sample in the repository to license. A sound is
a short tuple of (pitch, duration) steps -- editing one means editing a line of
`SOUNDS`, and adding one means adding a key.

To retune a sound, change its steps. To add one, add an entry and call
`audio.play("your_key")` from wherever it belongs. To silence one without
deleting it, give it empty steps.
"""

from __future__ import annotations

import io
import math
import struct
import wave
from dataclasses import dataclass
from typing import Dict, Tuple

RATE = 22050
"""Sample rate. Deliberately low -- period-correct and inaudibly different at
these frequencies, at a quarter the bytes of CD audio."""

SQUARE = "square"
TRIANGLE = "triangle"
NOISE = "noise"

Step = Tuple[int, int]
"""(frequency in Hz, duration in milliseconds). A frequency of 0 is a rest."""


@dataclass(frozen=True)
class Blip:
    """One sound: a run of steps played back to back on a single waveform."""

    steps: Tuple[Step, ...]
    wave: str = SQUARE
    decay: float = 0.3
    """How much the tail fades, 0 to 1. Without it every step ends on a click."""

    @property
    def milliseconds(self) -> int:
        return sum(ms for _, ms in self.steps)


# --------------------------------------------------------------------------
# The sound set
# --------------------------------------------------------------------------
#
# Rising intervals read as success, falling as loss, noise as impact. Keep them
# SHORT: these fire on keypresses, and anything past ~150ms starts arriving
# after the thing it is describing.

SOUNDS: Dict[str, Blip] = {
    # -- menus and navigation ------------------------------------------
    "cursor": Blip(((660, 18),), decay=0.6),
    "select": Blip(((880, 30), (1320, 45))),
    "back": Blip(((660, 30), (440, 45))),
    "deny": Blip(((220, 70), (165, 90)), wave=TRIANGLE),

    # -- the fight ------------------------------------------------------
    "pickup": Blip(((990, 22),), decay=0.5),
    "move": Blip(((523, 26), (784, 34))),
    "capture": Blip(((400, 45), (200, 70)), wave=NOISE, decay=0.8),
    "lost": Blip(((330, 60), (247, 70), (165, 110)), wave=TRIANGLE),
    "check": Blip(((988, 55), (988, 55)), wave=TRIANGLE),

    # -- the economy ----------------------------------------------------
    "buy": Blip(((784, 28), (1047, 28), (1319, 50))),
    "sell": Blip(((1047, 28), (784, 40))),

    # -- outcomes -------------------------------------------------------
    "win": Blip(((523, 70), (659, 70), (784, 70), (1047, 150))),
    "defeat": Blip(((392, 110), (330, 110), (262, 110), (196, 260)),
                   wave=TRIANGLE),
}


# --------------------------------------------------------------------------
# Synthesis
# --------------------------------------------------------------------------


def _sample(kind: str, phase: float, seed: int) -> float:
    """One sample of `kind` at `phase` (0-1 through the cycle)."""
    if kind == SQUARE:
        return 1.0 if phase < 0.5 else -1.0
    if kind == TRIANGLE:
        return 4.0 * abs(phase - 0.5) - 1.0
    # Deterministic pseudo-noise: a plain LCG, so a capture sounds the same
    # every time rather than drawing from `random` and varying per run.
    return ((seed * 1103515245 + 12345) >> 16 & 0x7FFF) / 16383.5 - 1.0


def render(blip: Blip, amplitude: float = 1.0) -> bytes:
    """Render a blip to raw 16-bit mono PCM frames."""
    frames = bytearray()
    seed = 1
    for frequency, milliseconds in blip.steps:
        count = max(1, int(RATE * milliseconds / 1000))
        for index in range(count):
            if frequency <= 0:
                frames += struct.pack("<h", 0)
                continue
            seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
            phase = (index * frequency / RATE) % 1.0
            envelope = 1.0 - (index / count) * blip.decay
            value = _sample(blip.wave, phase, seed) * amplitude * envelope
            frames += struct.pack("<h", int(max(-1.0, min(1.0, value)) * 32767))
    return bytes(frames)


def to_wav(frames: bytes) -> bytes:
    """Wrap PCM frames in a WAV container."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(frames)
    return buffer.getvalue()


def wav_for(name: str, amplitude: float = 1.0) -> bytes:
    """A complete WAV file for one named sound."""
    return to_wav(render(SOUNDS[name], amplitude))
