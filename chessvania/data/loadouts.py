"""Starting armies. Only the WHITE pieces of each FEN are used."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class Loadout:
    name: str
    blurb: str
    fen: str
    unlocked_by: Optional[str] = None
    """Achievement id that unlocks this, or None if it is always available."""


LOADOUTS: List[Loadout] = [
    Loadout(
        "Shield",
        "rooks and knights behind a full pawn wall - durable, slow to open",
        "8/8/8/8/8/8/PPPPPPPP/RN2KN1R w - - 0 1",
    ),
    Loadout(
        "Speartip",
        "a queen and two bishops over a thin line - sharp, fragile",
        "8/8/8/8/8/8/1PPPPPP1/2BQKBN1 w - - 0 1",
    ),
    Loadout(
        "Textbook",
        "the standard opening army - far stronger than the others, a soft start",
        "8/8/8/8/8/8/PPPPPPPP/RNBQKBNR w - - 0 1",
    ),
    Loadout(
        "Cavalry",
        "four knights and a rook - awkward to trade against, hard to pin down",
        "8/8/8/8/8/8/PPPPPPPP/RNN1KNN1 w - - 0 1",
        unlocked_by="first_boss",
    ),
    Loadout(
        "Endgame",
        "a queen, two rooks and a thin pawn line - no development, all threat",
        "8/8/8/8/8/8/1PPPPPP1/R2QK2R w - - 0 1",
        unlocked_by="champion",
    ),
]

DEFAULT = LOADOUTS[0]
