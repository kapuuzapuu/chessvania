"""Deciding where the enemy stands, given the player's deployment.

The player is White and always moves first, so every fight must open from a
position that is legal with White to move. The case that bites is the enemy
starting in check: once armies get rearranged between fights, a rook can end up
aimed down an open file at the enemy king. That is not a free tempo, it is an
illegal position, and Stockfish will not accept it.

Rather than bending the turn order, the enemy is slid somewhere else. Every
variant here holds the same pieces in the same shape -- only the files move --
so the fight you were given is still the fight you fight.
"""

from __future__ import annotations

from typing import Dict, Iterator, Optional, Sequence

import chess

from .army import Army, compose_board
from .ladder import Formation
from .legality import is_legal_position


def pairing_is_playable(army: Army, enemy_fen: str) -> bool:
    """Can the player open as White against this exact enemy placement?"""
    return is_legal_position(compose_board(army, enemy_fen))


def formation_variants(fen: str) -> Iterator[str]:
    """Placements of one enemy formation, in order of preference.

    As authored first, then mirrored, then shifted a file or two sideways.
    """
    board = chess.Board(fen)
    mirrored = board.transform(chess.flip_horizontal)

    yield fen
    yield mirrored.fen()
    for source in (board, mirrored):
        for offset in (1, -1, 2, -2):
            shifted = _shift_files(source, offset)
            if shifted is not None:
                yield shifted.fen()


def choose_placement(
    army: Army,
    formation: Formation,
    pool: Sequence[Formation] = (),
) -> Formation:
    """Pick a placement the player can actually open against.

    Tries the drawn formation's own variants first, then other formations of the
    same tier. In practice the first or second candidate lands; the wider search
    exists so a pathological deployment can never wedge a run.

    This is game logic, not presentation -- the app calls it, but the decision
    and its fallbacks live here where they can be tested without a UI.
    """
    candidates = [formation]
    candidates += [f for f in pool if f is not formation]

    for candidate in candidates:
        for fen in formation_variants(candidate.fen):
            if pairing_is_playable(army, fen):
                return Formation(candidate.name, candidate.tier, fen)
    return formation


def _shift_files(board: chess.Board, offset: int) -> Optional[chess.Board]:
    """Slide every piece sideways, or None if that would leave the board."""
    shifted = chess.Board(None)
    for square, piece in board.piece_map().items():
        file = chess.square_file(square) + offset
        if not 0 <= file <= 7:
            return None
        shifted.set_piece_at(chess.square(file, chess.square_rank(square)), piece)
    return shifted
