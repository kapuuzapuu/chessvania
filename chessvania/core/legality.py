"""Position legality, delegated to python-chess wherever possible.

`chess.Board.status()` already checks nearly every constraint the army rules
care about (piece counts, pawn counts, back-rank pawns, king counts), so this
module is mostly a translation layer from its flags into player-facing English.
"""

from __future__ import annotations

from typing import List, Optional

import chess

from .. import config

_STATUS_MESSAGES = (
    (chess.STATUS_NO_WHITE_KING, "your army has no king"),
    (chess.STATUS_NO_BLACK_KING, "the enemy has no king"),
    (chess.STATUS_TOO_MANY_KINGS, "a side has more than one king"),
    (chess.STATUS_TOO_MANY_WHITE_PIECES, "your army exceeds 16 pieces on the board"),
    (chess.STATUS_TOO_MANY_BLACK_PIECES, "the enemy exceeds 16 pieces on the board"),
    (chess.STATUS_TOO_MANY_WHITE_PAWNS, "your army exceeds 8 pawns"),
    (chess.STATUS_TOO_MANY_BLACK_PAWNS, "the enemy exceeds 8 pawns"),
    (chess.STATUS_PAWNS_ON_BACKRANK, "a pawn is on the first or last rank"),
    (chess.STATUS_OPPOSITE_CHECK, "the side not to move is in check"),
    (chess.STATUS_EMPTY, "the board is empty"),
    (chess.STATUS_BAD_CASTLING_RIGHTS, "castling rights do not match the pieces"),
    (chess.STATUS_INVALID_EP_SQUARE, "invalid en passant square"),
    (chess.STATUS_IMPOSSIBLE_CHECK, "this check could not have arisen legally"),
)


def position_errors(board: chess.Board) -> List[str]:
    """Return every reason `board` is not a legal standard-chess position."""
    status = board.status()
    if status == chess.STATUS_VALID:
        return []
    return [message for flag, message in _STATUS_MESSAGES if status & flag]


def is_legal_position(board: chess.Board) -> bool:
    return board.status() == chess.STATUS_VALID


def placement_error(piece_type: int, square: chess.Square) -> Optional[str]:
    """Why this piece may not rest on this square, or None if it may.

    Two rules compose here. Standard chess forbids a pawn on rank 1 or 8, and
    Chessvania confines your deployment to the first `DEPLOYMENT_RANKS` ranks --
    so pawns end up with ranks 2 to 3 without that being stated anywhere.

    Returns prose rather than a bool because the swap phase shows it verbatim.
    """
    rank = chess.square_rank(square)
    if rank >= config.DEPLOYMENT_RANKS:
        return "you deploy on ranks 1-%d" % config.DEPLOYMENT_RANKS
    if piece_type == chess.PAWN and rank in (0, 7):
        return "a pawn cannot sit on rank %d" % (rank + 1)
    return None


def square_accepts(piece_type: int, square: chess.Square) -> bool:
    """Can this piece type legally occupy this square at rest?

    Driving placement highlighting off this means illegal squares simply never
    light up -- the affordance is the rule.
    """
    return placement_error(piece_type, square) is None
