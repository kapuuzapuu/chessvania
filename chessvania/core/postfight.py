"""The post-fight phase machine: payout -> shop -> sell -> swap.

The ordering is deliberate and enforced here rather than in the UI. Selling is
locked until the shop closes, so sale gold can never fund the purchase you are
standing in front of -- it always arrives for the *next* shop.

Purchases land on the bench, never straight onto the board. Deploying costs a
swap, which is what gives the three-swap budget teeth.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

import chess

from .. import config
from .army import Army, Piece
from .economy import Payout, buyable_types, price_of, sell_value
from .run import RunState


class Step(Enum):
    PAYOUT = "payout"
    SHOP = "shop"
    SELL = "sell"
    SWAP = "swap"
    DONE = "done"


STEP_ORDER = (Step.PAYOUT, Step.SHOP, Step.SELL, Step.SWAP, Step.DONE)


@dataclass(frozen=True)
class Slot:
    """A place a piece can live: a board square, or a bench position."""

    kind: str
    index: int

    @classmethod
    def on_board(cls, square: chess.Square) -> "Slot":
        return cls("board", square)

    @classmethod
    def on_bench(cls, index: int) -> "Slot":
        return cls("bench", index)

    @property
    def is_board(self) -> bool:
        return self.kind == "board"


@dataclass(frozen=True)
class StockItem:
    piece_type: int
    price: int

    @property
    def name(self) -> str:
        from .army import PIECE_NAMES

        return PIECE_NAMES[self.piece_type]

    @property
    def symbol(self) -> str:
        return chess.Piece(self.piece_type, chess.WHITE).unicode_symbol()


def catalogue() -> List[StockItem]:
    """The shop's permanent stock: every piece type, cheapest first.

    Nothing is ever rolled or sold out. With only five buyable types a random
    subset was never real variety, and a fixed catalogue turns the shop into a
    clean economic decision -- what can I afford, and what can I deploy?

    Buying is bounded by three things instead: gold, the bench cap, and the
    swap budget you need to actually field a purchase.
    """
    return [StockItem(piece_type=t, price=price_of(t)) for t in buyable_types()]


class PostFight:
    """Drives one post-fight phase. All four steps, in order, once each."""

    def __init__(
        self,
        run: RunState,
        move_count: int,
        casualties: Optional[List[Piece]] = None,
    ) -> None:
        self.run = run
        self.payout: Payout = run.preview_payout(move_count)
        self.casualties: List[Piece] = list(casualties or [])
        self.step = Step.PAYOUT
        self.stock = catalogue()
        self.gold_spent = 0
        self.swaps_used = 0
        self.sold_count = 0
        self.bought: List[Piece] = []
        self.skipped = False

    # -- step 1: payout --------------------------------------------------

    def collect_payout(self) -> Payout:
        if self.step is not Step.PAYOUT:
            return self.payout
        self.run.collect(self.payout)
        self.step = Step.SHOP
        return self.payout

    # -- step 2: shop ----------------------------------------------------

    @property
    def gold(self) -> int:
        return self.run.gold

    def can_buy(self, index: int) -> Tuple[bool, str]:
        if self.step is not Step.SHOP:
            return False, "the shop is closed"
        if not 0 <= index < len(self.stock):
            return False, "no such item"
        item = self.stock[index]
        if self.run.army.inventory_full:
            return False, "bench full"
        if item.price > self.run.gold:
            return False, "not enough gold"
        return True, ""

    def buy(self, index: int) -> Tuple[bool, str]:
        ok, reason = self.can_buy(index)
        if not ok:
            return False, reason
        item = self.stock[index]
        self.run.spend(item.price)
        piece = Piece(piece_type=item.piece_type, bought=True)
        self.run.army.add_to_inventory(piece)
        self.bought.append(piece)
        self.gold_spent += item.price
        return True, ""

    def purchase_counts(self) -> "OrderedDict[str, int]":
        """Bought pieces grouped for the receipt, so 3 pawns is not '♙ ♙ ♙'."""
        counts: "OrderedDict[str, int]" = OrderedDict()
        for piece in self.bought:
            counts[piece.symbol] = counts.get(piece.symbol, 0) + 1
        return counts

    @property
    def can_skip(self) -> bool:
        """Skipping only compounds if you have not spent a thing."""
        return self.step is Step.SHOP and self.gold_spent == 0

    def skip_preview(self) -> Tuple[int, int]:
        """(gold kept, bonus added to the next payout) -- shown on the button.

        A bare 'skip' hides the most interesting decision in the game, so the
        numbers go on the control itself.
        """
        return self.run.gold, config.SKIP_BONUS

    def skip_shop(self) -> Tuple[bool, str]:
        if not self.can_skip:
            return False, "you have already spent gold this visit"
        self.run.bank_skip_bonus()
        self.skipped = True
        self.step = Step.SELL
        return True, ""

    def close_shop(self) -> None:
        if self.step is Step.SHOP:
            self.step = Step.SELL

    # -- step 3: sell ----------------------------------------------------

    def can_sell(self, bench_index: int) -> Tuple[bool, str]:
        if self.step is not Step.SELL:
            return False, "selling opens once the shop closes"
        if not 0 <= bench_index < len(self.run.army.inventory):
            return False, "no piece in that slot"
        return True, ""

    def sell(self, bench_index: int) -> Tuple[bool, str]:
        ok, reason = self.can_sell(bench_index)
        if not ok:
            return False, reason
        piece = self.run.army.inventory[bench_index]
        value = sell_value(piece.piece_type)
        self.run.army.remove_from_inventory(piece.id)
        self.run.gold += value
        self.sold_count += 1
        return True, ""

    def close_sell(self) -> None:
        if self.step is Step.SELL:
            self.step = Step.SWAP

    # -- step 4: swap ----------------------------------------------------

    @property
    def swaps_left(self) -> int:
        return max(0, config.MAX_SWAPS - self.swaps_used)

    def can_swap(self, a: Slot, b: Slot) -> Tuple[bool, str]:
        if self.step is not Step.SWAP:
            return False, "swapping opens after selling"
        if self.swaps_left <= 0:
            return False, "no swaps left"
        if a == b:
            return False, "pick two different slots"
        for slot in (a, b):
            if not slot.is_board and not 0 <= slot.index < config.INVENTORY_CAP:
                return False, "no such bench slot"
        candidate = self.run.army.copy()
        ok, reason = _apply_swap(candidate, a, b)
        if not ok:
            return False, reason
        problems = candidate.violations()
        if problems:
            return False, problems[0]
        return True, ""

    def swap(self, a: Slot, b: Slot) -> Tuple[bool, str]:
        ok, reason = self.can_swap(a, b)
        if not ok:
            return False, reason
        candidate = self.run.army.copy()
        _apply_swap(candidate, a, b)
        self.run.army = candidate
        self.swaps_used += 1
        return True, ""

    # -- finish ----------------------------------------------------------

    def finish(self) -> None:
        self.step = Step.DONE
        self.run.on_postfight_done()

    @property
    def done(self) -> bool:
        return self.step is Step.DONE


def _read(army: Army, bench: List[Optional[Piece]], slot: Slot) -> Optional[Piece]:
    if slot.is_board:
        return army.deployment.get(slot.index)
    return bench[slot.index]


def _apply_swap(army: Army, a: Slot, b: Slot) -> Tuple[bool, str]:
    """Exchange the contents of two slots. Empty destinations mean 'move'.

    Works on a padded copy of the bench so empty slots are addressable, then
    compacts it back -- bench order carries no meaning.
    """
    bench: List[Optional[Piece]] = list(army.inventory)
    bench += [None] * (config.INVENTORY_CAP - len(bench))

    piece_a = _read(army, bench, a)
    piece_b = _read(army, bench, b)

    if piece_a is None and piece_b is None:
        return False, "both slots are empty"

    for piece, destination in ((piece_a, b), (piece_b, a)):
        if piece is not None and piece.piece_type == chess.KING and not destination.is_board:
            return False, "the king cannot leave the board"

    def write(slot: Slot, piece: Optional[Piece]) -> None:
        if slot.is_board:
            if piece is None:
                army.deployment.pop(slot.index, None)
            else:
                army.deployment[slot.index] = piece
        else:
            bench[slot.index] = piece

    write(a, piece_b)
    write(b, piece_a)
    army.inventory = [p for p in bench if p is not None]
    return True, ""
