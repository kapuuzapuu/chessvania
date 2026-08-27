"""What is about to be taken from you, and what you can take.

In an ordinary chess UI a threat readout is an evaluation aid. Here it is the
stakes panel. A rook lost in this fight is a rook lost for the rest of the run,
so the question worth answering every move is not "who is winning" but "what
dies if I ignore it". Everything below is framed around permanent loss.

This is a static read, not a search -- one ply of "who attacks what", the glance
a human takes before committing to a move. Its limits, stated so nobody mistakes
it for an engine:

  * Attackers and defenders come from `chess.Board.attackers`, which is purely
    geometric. It does not know a battery gains a second attacker once the first
    one moves off the line.
  * A defender that is absolutely pinned is discounted, because it usually
    cannot recapture. A pinned piece can still legally move ALONG its pin, so
    this occasionally drops a defender that would in fact hold. The direction is
    deliberate: over-warning costs a cautious move, under-warning costs a piece
    for the rest of the run.
  * Trade arithmetic is cheapest-attacker against the piece, not a full static
    exchange evaluation. It catches "your rook is attacked by a pawn"; it will
    not resolve a six-piece pile-up on one square.

The opportunity side is exact rather than geometric, because it is generated
from the player's own legal moves -- pins and checks are already accounted for
by the move generator.

Presentation lives elsewhere. This module returns levels and squares; `ui/theme`
decides what a level looks like.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, List, Optional, Tuple

import chess

from .army import PIECE_VALUES

_ATTACKER_VALUES = dict(PIECE_VALUES)
_ATTACKER_VALUES[chess.KING] = 100
"""The king is priced out of trade arithmetic rather than valued at zero.

It can only ever capture on a square nobody defends, so treating it as the
cheapest attacker would report every defended piece as a losing trade.
"""


class Danger(IntEnum):
    """How badly a square is compromised. Ordered, so `max` picks the worst."""

    SAFE = 0
    """Not attacked. Never reported -- absence of a threat is the default."""

    HELD = 1
    """Attacked, defended, and the cheapest attacker is not worth less than the
    piece. Losing it costs the enemy at least as much as it costs you."""

    TRADE = 2
    """Attacked and defended, but the cheapest attacker is worth less. You come
    out behind even when the recapture works."""

    HANGING = 3
    """Attacked with nothing defending it. Taken for free, gone for the run."""

    CHECK = 4
    """The king, attacked. Always the most urgent thing on the board."""


@dataclass(frozen=True)
class Threat:
    """One of your pieces and what stands to happen to it."""

    square: chess.Square
    piece_type: int
    level: Danger
    attackers: Tuple[chess.Square, ...]
    """Enemy squares hitting this one, cheapest piece first."""
    defenders: Tuple[chess.Square, ...]
    """Your squares covering this one, cheapest first, pinned pieces removed."""
    loss: int
    """Material gone for good if this plays out badly: the whole piece when it
    hangs, the difference when it is a losing trade, zero when it is held."""

    @property
    def cheapest_attacker(self) -> Optional[chess.Square]:
        return self.attackers[0] if self.attackers else None


@dataclass(frozen=True)
class Opportunity:
    """An enemy piece you can legally capture at a profit."""

    square: chess.Square
    piece_type: int
    takers: Tuple[chess.Square, ...]
    """Your squares that can legally make the capture, cheapest piece first."""
    free: bool
    """Nothing recaptures. The whole piece is profit."""
    gain: int


@dataclass(frozen=True)
class ThreatReport:
    """The whole picture for one side, at one position."""

    in_check: bool
    checkers: Tuple[chess.Square, ...]
    escapes: int
    """Legal moves available while in check. One is a very different position
    from twelve, and the count is the cheapest way to say so."""
    threats: Tuple[Threat, ...]
    """Worst first, so the UI can truncate from the bottom and lose the least."""
    opportunities: Tuple[Opportunity, ...]
    by_square: Dict[chess.Square, Threat] = field(default_factory=dict)
    by_target: Dict[chess.Square, Opportunity] = field(default_factory=dict)

    @property
    def material_at_risk(self) -> int:
        return sum(threat.loss for threat in self.threats)

    @property
    def worst(self) -> Danger:
        return max((threat.level for threat in self.threats), default=Danger.SAFE)

    def at(self, square: chess.Square) -> Optional[Threat]:
        return self.by_square.get(square)

    def opportunity_at(self, square: chess.Square) -> Optional[Opportunity]:
        return self.by_target.get(square)


def cover(board: chess.Board, square: chess.Square, color: chess.Color) -> Tuple[chess.Square, ...]:
    """Squares from which `color` covers `square`, cheapest piece first.

    Exported because the inspect panel wants the same numbers the report is
    built from, and recomputing them in the UI would put chess logic in the view
    layer.
    """
    return tuple(
        sorted(
            board.attackers(color, square),
            key=lambda origin: (_ATTACKER_VALUES[board.piece_type_at(origin)], origin),
        )
    )


def read(board: chess.Board, color: chess.Color = chess.WHITE) -> ThreatReport:
    """Assess every piece `color` owns, plus what it can profitably take."""
    enemy = not color

    threats: List[Threat] = []
    for square, piece in board.piece_map().items():
        if piece.color != color:
            continue
        threat = _assess(board, square, piece, color, enemy)
        if threat is not None:
            threats.append(threat)
    threats.sort(key=lambda t: (-int(t.level), -t.loss, -PIECE_VALUES[t.piece_type]))

    king = board.king(color)
    in_check = board.turn == color and board.is_check() and king is not None
    opportunities = _opportunities(board, color, enemy)

    return ThreatReport(
        in_check=in_check,
        checkers=cover(board, king, enemy) if in_check else (),
        escapes=board.legal_moves.count() if in_check else 0,
        threats=tuple(threats),
        opportunities=opportunities,
        by_square={threat.square: threat for threat in threats},
        by_target={chance.square: chance for chance in opportunities},
    )


def _assess(
    board: chess.Board,
    square: chess.Square,
    piece: chess.Piece,
    color: chess.Color,
    enemy: chess.Color,
) -> Optional[Threat]:
    attackers = cover(board, square, enemy)
    if not attackers:
        return None

    if piece.piece_type == chess.KING:
        # An attacked king is check by definition; defenders are irrelevant
        # because nothing recaptures a king.
        return Threat(square, chess.KING, Danger.CHECK, attackers, (), 0)

    defenders = tuple(
        origin for origin in cover(board, square, color)
        if not board.is_pinned(color, origin)
    )
    worth = PIECE_VALUES[piece.piece_type]

    if not defenders:
        return Threat(square, piece.piece_type, Danger.HANGING, attackers, defenders, worth)

    cheapest = _ATTACKER_VALUES[board.piece_type_at(attackers[0])]
    if cheapest < worth:
        return Threat(
            square, piece.piece_type, Danger.TRADE, attackers, defenders, worth - cheapest
        )
    return Threat(square, piece.piece_type, Danger.HELD, attackers, defenders, 0)


def _opportunities(
    board: chess.Board, color: chess.Color, enemy: chess.Color
) -> Tuple[Opportunity, ...]:
    """Captures that gain material, built from legal moves rather than geometry.

    Empty when it is not `color`'s turn: a capture you cannot play yet is not an
    opportunity, it is a plan, and the panel has no room for plans.
    """
    if board.turn != color:
        return ()

    takers: Dict[chess.Square, set] = {}
    victims: Dict[chess.Square, int] = {}
    for move in board.legal_moves:
        if not board.is_capture(move):
            continue
        if board.is_en_passant(move):
            victim = chess.PAWN
        else:
            victim = board.piece_type_at(move.to_square)
            if victim is None:
                continue
        takers.setdefault(move.to_square, set()).add(move.from_square)
        victims[move.to_square] = victim

    found: List[Opportunity] = []
    for square, origins in takers.items():
        ordered = tuple(
            sorted(origins, key=lambda o: (_ATTACKER_VALUES[board.piece_type_at(o)], o))
        )
        guards = cover(board, square, enemy)
        worth = PIECE_VALUES[victims[square]]
        gain = worth if not guards else worth - _ATTACKER_VALUES[board.piece_type_at(ordered[0])]
        if gain <= 0:
            continue
        found.append(
            Opportunity(
                square=square,
                piece_type=victims[square],
                takers=ordered,
                free=not guards,
                gain=gain,
            )
        )

    found.sort(key=lambda chance: (not chance.free, -chance.gain, chance.square))
    return tuple(found)
