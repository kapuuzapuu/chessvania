"""Pure arithmetic: payouts, prices, sale values, skip compounding.

Ints in, ints out. Nothing here knows what an Army is -- that separation is why
the shop can be retuned without touching anything that manipulates pieces.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

import chess

from .. import config


@dataclass(frozen=True)
class Payout:
    """A fully itemised payout, so the UI can show its working."""

    move_count: int
    base: int
    stake_penalty: int
    skip_bonus: int
    total: int


def tier_for(move_count: int) -> Optional[Tuple[int, int]]:
    """The (threshold, gold) tier a move count lands in, or None past the end."""
    for threshold, gold in config.PAYOUT_TIERS:
        if move_count <= threshold:
            return threshold, gold
    return None


def base_payout(move_count: int) -> int:
    tier = tier_for(move_count)
    return tier[1] if tier else config.PAYOUT_FALLBACK


def compute_payout(move_count: int, stake: config.Stake, skip_bonus: int = 0) -> Payout:
    """What a win right now is worth, penalties and banked bonus included."""
    base = base_payout(move_count)
    penalised = max(config.MIN_PAYOUT, base - stake.payout_penalty)
    return Payout(
        move_count=move_count,
        base=base,
        stake_penalty=base - penalised,
        skip_bonus=skip_bonus,
        total=penalised + skip_bonus,
    )


def tier_ladder() -> List[Tuple[int, int]]:
    """The full ladder, for the always-visible readout during a fight."""
    return list(config.PAYOUT_TIERS)


def price_of(piece_type: int) -> int:
    return config.PIECE_PRICES[piece_type]


def sell_value(piece_type: int) -> int:
    """Half price, rounded down, never below the floor."""
    raw = math.floor(price_of(piece_type) * config.SELL_RATIO)
    return max(config.MIN_SELL, raw)


def buyable_types() -> List[int]:
    """Piece types the shop can stock. Kings are not for sale."""
    return [t for t in config.PIECE_PRICES if t != chess.KING]
