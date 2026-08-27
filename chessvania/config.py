"""Every tunable constant in the game.

Nothing here is balanced. These are placeholder scaffolds so the game is
playable; real values come from playing it. Keep game rules out of this file --
it holds numbers, not logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import chess

# --------------------------------------------------------------------------
# Dev mode
# --------------------------------------------------------------------------

DEV_MODE = False
"""Diagnostics mode. Deliberately NOT reachable from any menu -- flip this line
to True and the dev bar plus its F-key shortcuts appear. `__main__` also turns
it on for CHESSVANIA_DEV=1; the environment is read there rather than here so
this module stays what it claims to be, a file of plain constants with no
import-time side effects.

It is a debugging tool rather than a cheat mode: unlocks and progression behave
exactly as normal while it is on, so a run played in dev mode is still a real
run."""

DEV_GOLD_STEP = 10
"""Gold granted per press of the dev gold key."""

# --------------------------------------------------------------------------
# Army limits
# --------------------------------------------------------------------------

INVENTORY_CAP = 16
"""Hard cap on bench slots. Separate storage from the board."""

MAX_SWAPS = 3
"""Swaps allowed per post-fight phase. Purchases land on the bench, so a swap
is also how you deploy -- this budget is the tightest constraint in the phase."""

BOARD_PIECE_CAP = 16
MAX_PAWNS = 8

# --------------------------------------------------------------------------
# Economy
# --------------------------------------------------------------------------

PAYOUT_TIERS: Tuple[Tuple[int, int], ...] = (
    (10, 5),
    (20, 4),
    (30, 3),
    (45, 2),
)
"""(max player moves, gold) -- first tier whose threshold is met wins."""

PAYOUT_FALLBACK = 1
"""Paid when the move count exceeds every tier."""

MIN_PAYOUT = 1
"""Stake payout penalties never push a win below this."""

PIECE_PRICES: Dict[int, int] = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
}

SELL_RATIO = 0.5
MIN_SELL = 1

SKIP_BONUS = 2
"""Flat bonus added to the next payout when the shop is skipped without
spending. Unspent gold also simply stays in the purse, so skipping compounds:
you keep the gold AND the next win pays more."""


# --------------------------------------------------------------------------
# Run structure
# --------------------------------------------------------------------------

ANTES = 3
FIGHTS_PER_ANTE = 3

TIER_LOW = "low"
TIER_MID = "mid"
TIER_MINIBOSS = "mini-boss"
TIER_FINAL = "final-boss"

ELO_RAMP: Dict[int, Tuple[int, int, int]] = {
    1: (700, 900, 1100),
    2: (1200, 1400, 1600),
    3: (1700, 1900, 2200),
}
"""ante -> (low, mid, boss). Each ante's floor sits above the previous
ante's ceiling, so difficulty never regresses."""


@dataclass(frozen=True)
class Stake:
    """One rung of the NG+ ladder, layered over the base ramp and payouts."""

    name: str
    elo_bonus: int = 0
    payout_penalty: int = 0


STAKES: Tuple[Stake, ...] = (
    Stake("Base", 0, 0),
    Stake("Sharpened", 150, 0),
    Stake("Lean", 0, 1),
    Stake("Honed", 300, 0),
    Stake("Starved", 0, 2),
    Stake("Merciless", 450, 1),
)

# --------------------------------------------------------------------------
# Stockfish strength mapping
# --------------------------------------------------------------------------
#
# Stockfish's UCI_Elo bottoms out at 1320 (verified against Stockfish 18), but
# the ramp above starts at 700. Below the floor we fall back to `Skill Level`
# plus a shallow search depth, which is how you get genuinely weak play.

UCI_ELO_FLOOR = 1320

WEAK_LADDER: Tuple[Tuple[int, int, int], ...] = (
    # (max target elo, Skill Level 0-20, search depth)
    (750, 0, 1),
    (950, 2, 2),
    (1150, 5, 3),
    (UCI_ELO_FLOOR - 1, 8, 4),
)

STRONG_DEPTH = 12
"""Search depth cap once UCI_Elo is doing the limiting. Keeps replies fast;
UCI_Elo, not depth, is what sets strength up here."""

ENGINE_TIMEOUT = 10.0
"""Seconds to wait on a single engine reply before giving up."""


@dataclass(frozen=True)
class Strength:
    """A resolved engine configuration for one target Elo."""

    target_elo: int
    depth: int
    skill_level: Optional[int] = None
    uci_elo: Optional[int] = None


def strength_for(target_elo: int) -> Strength:
    """Map a target Elo onto whichever Stockfish lever can actually reach it."""
    if target_elo < UCI_ELO_FLOOR:
        for ceiling, skill, depth in WEAK_LADDER:
            if target_elo <= ceiling:
                return Strength(target_elo, depth, skill_level=skill)
    capped = max(UCI_ELO_FLOOR, min(target_elo, 3190))
    return Strength(target_elo, STRONG_DEPTH, uci_elo=capped)


# --------------------------------------------------------------------------
# Rules locked during design (see the spec's "open decisions")
# --------------------------------------------------------------------------

STALEMATE_LOSES = True
"""Whoever gets stalemated WINS. Delivering stalemate is a loss, so you have to
actually mate. Set False to treat stalemate as a plain loss for the player."""

# --------------------------------------------------------------------------
# Presentation
# --------------------------------------------------------------------------

GOLD_GLYPH = "◇"
"""Swappable -- the word GOLD carries the meaning, this is decoration."""

VETERAN_THRESHOLDS: Tuple[int, int] = (3, 6)
"""Fights survived at which a piece reads as seasoned / veteran."""
