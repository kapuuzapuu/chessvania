"""The player's persistent army: pieces on the board plus the bench.

Pieces carry identity across the whole run so that veterancy (fights survived)
and the casualty report are exact rather than inferred from piece counts.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field, replace
from typing import Dict, Iterable, List, Optional

import chess

from .. import config
from .legality import square_accepts

_ids = itertools.count(1)


def next_piece_id() -> int:
    return next(_ids)


def reserve_piece_ids(highest: int) -> None:
    """Push the id generator past `highest`.

    Loading a saved run restores pieces with their original ids; without this
    the counter would still be at 1 and the next bought piece would collide with
    a loaded one, silently corrupting veterancy and casualty reporting.
    """
    global _ids
    _ids = itertools.count(highest + 1)


PIECE_NAMES = {
    chess.PAWN: "Pawn",
    chess.KNIGHT: "Knight",
    chess.BISHOP: "Bishop",
    chess.ROOK: "Rook",
    chess.QUEEN: "Queen",
    chess.KING: "King",
}

PIECE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}


@dataclass
class Piece:
    """One piece the player owns, with identity that survives fights."""

    piece_type: int
    id: int = field(default_factory=next_piece_id)
    fights_survived: int = 0
    bought: bool = False

    @property
    def name(self) -> str:
        return PIECE_NAMES[self.piece_type]

    @property
    def value(self) -> int:
        return PIECE_VALUES[self.piece_type]

    @property
    def veterancy(self) -> int:
        """0 = fresh, 1 = seasoned, 2 = veteran.

        Purely cosmetic today: it drives the bench tint and the inspect line.
        Nothing in the rules reads it yet, but it has to be *tracked* from the
        first fight or it can never be added later.
        """
        seasoned, veteran = config.VETERAN_THRESHOLDS
        if self.fights_survived >= veteran:
            return 2
        if self.fights_survived >= seasoned:
            return 1
        return 0

    @property
    def veterancy_label(self) -> str:
        return ("fresh", "seasoned", "veteran")[self.veterancy]


@dataclass
class Army:
    """Everything the player owns: a deployment plus a bench.

    THE INVARIANT: `deployment` is where pieces START a fight, not where they
    currently stand. A fight copies it onto a board and mutates that board; the
    deployment itself is only ever edited between fights, by the swap phase.
    Whatever mess a fight leaves behind is discarded -- your pieces come back to
    the squares you chose for them.

    So a fight must never write to this. `Fight.apply_to_army` is the one place
    allowed to change it, and all it does is remove the dead and age survivors.

    Vocabulary: the player has a DEPLOYMENT, the enemy has a FORMATION (see
    `core.ladder.Formation`). Both are arrangements of pieces; keeping the two
    words apart is what stops "whose pieces are these?" ambiguity.

    The player is always White.
    """

    deployment: Dict[chess.Square, Piece] = field(default_factory=dict)
    """Home square -> piece. Persists across the whole run."""

    inventory: List[Piece] = field(default_factory=list)
    """The bench: reserves that sit out fights entirely. Capped at 16."""

    # -- queries ---------------------------------------------------------

    @property
    def deployed_count(self) -> int:
        return len(self.deployment)

    @property
    def pawn_count(self) -> int:
        return sum(1 for p in self.deployment.values() if p.piece_type == chess.PAWN)

    @property
    def inventory_count(self) -> int:
        return len(self.inventory)

    @property
    def inventory_full(self) -> bool:
        return len(self.inventory) >= config.INVENTORY_CAP

    @property
    def inventory_space(self) -> int:
        return config.INVENTORY_CAP - len(self.inventory)

    def king_square(self) -> Optional[chess.Square]:
        for square, piece in self.deployment.items():
            if piece.piece_type == chess.KING:
                return square
        return None

    def material(self) -> int:
        return sum(p.value for p in self.deployment.values())

    def all_pieces(self) -> Iterable[Piece]:
        return itertools.chain(self.deployment.values(), self.inventory)

    def find(self, piece_id: int) -> Optional[Piece]:
        for piece in self.all_pieces():
            if piece.id == piece_id:
                return piece
        return None

    def square_of(self, piece_id: int) -> Optional[chess.Square]:
        for square, piece in self.deployment.items():
            if piece.id == piece_id:
                return square
        return None

    # -- mutation --------------------------------------------------------

    def add_to_inventory(self, piece: Piece) -> bool:
        """Bench a piece. Returns False if the bench is full."""
        if self.inventory_full:
            return False
        self.inventory.append(piece)
        return True

    def remove_from_inventory(self, piece_id: int) -> Optional[Piece]:
        for index, piece in enumerate(self.inventory):
            if piece.id == piece_id:
                return self.inventory.pop(index)
        return None

    def can_place(self, piece: Piece, square: chess.Square) -> bool:
        """Would putting `piece` on `square` keep the army legal?

        Assumes `square` is empty or is being vacated by the swap partner; the
        caller owns that part. This checks the standing constraints only.
        """
        if not square_accepts(piece.piece_type, square):
            return False
        occupant = self.deployment.get(square)
        if occupant is None:
            if self.deployed_count >= config.BOARD_PIECE_CAP:
                return False
            if piece.piece_type == chess.PAWN and self.pawn_count >= config.MAX_PAWNS:
                return False
        return True

    def violations(self) -> List[str]:
        """Standing rule breaches, independent of any enemy formation.

        `compose_board` + `legality.position_errors` catch everything once an
        enemy is present; this is the subset the army must satisfy on its own,
        which is what the swap phase needs to validate against.
        """
        problems: List[str] = []
        kings = sum(1 for p in self.deployment.values() if p.piece_type == chess.KING)
        if kings != 1:
            problems.append("your army must keep exactly one king on the board")
        if self.deployed_count > config.BOARD_PIECE_CAP:
            problems.append("no more than %d pieces on the board" % config.BOARD_PIECE_CAP)
        if self.pawn_count > config.MAX_PAWNS:
            problems.append("no more than %d pawns" % config.MAX_PAWNS)
        if len(self.inventory) > config.INVENTORY_CAP:
            problems.append("the bench holds %d pieces" % config.INVENTORY_CAP)
        for square, piece in self.deployment.items():
            if not square_accepts(piece.piece_type, square):
                problems.append(
                    "a pawn cannot sit on %s" % chess.square_name(square)
                )
        return problems

    def copy(self) -> "Army":
        return Army(
            deployment={sq: replace(p) for sq, p in self.deployment.items()},
            inventory=[replace(p) for p in self.inventory],
        )


def compose_board(army: Army, enemy_fen: str) -> chess.Board:
    """Merge the player's army (White) with an enemy formation (Black).

    The enemy formation is a normal FEN; only its black pieces are used. The
    result is an ordinary legal chess position with White to move -- which is
    the entire reason Stockfish can play the other side.
    """
    board = chess.Board(None)

    source = chess.Board(enemy_fen)
    for square, piece in source.piece_map().items():
        if piece.color == chess.BLACK:
            board.set_piece_at(square, piece)

    for square, piece in army.deployment.items():
        board.set_piece_at(square, chess.Piece(piece.piece_type, chess.WHITE))

    board.castling_rights = _castling_rights(board)
    board.fullmove_number = 1
    board.turn = chess.WHITE
    return board


def _castling_rights(board: chess.Board) -> chess.Bitboard:
    """Grant castling only where the king and rook actually sit unmoved.

    Armies get shuffled between fights, so rights are derived from placement
    rather than carried around -- an army that happens to hold the standard
    setup keeps castling, and one that doesn't simply cannot.
    """
    rights = chess.BB_EMPTY
    pairs = (
        (chess.WHITE, chess.E1, chess.A1, chess.H1, chess.BB_A1, chess.BB_H1),
        (chess.BLACK, chess.E8, chess.A8, chess.H8, chess.BB_A8, chess.BB_H8),
    )
    for color, king_sq, a_sq, h_sq, bb_a, bb_h in pairs:
        if board.piece_at(king_sq) != chess.Piece(chess.KING, color):
            continue
        if board.piece_at(a_sq) == chess.Piece(chess.ROOK, color):
            rights |= bb_a
        if board.piece_at(h_sq) == chess.Piece(chess.ROOK, color):
            rights |= bb_h
    return rights


def army_from_fen(fen: str, bought: bool = False) -> Army:
    """Build an army from the White pieces of a FEN (used for loadouts)."""
    source = chess.Board(fen)
    pieces: Dict[chess.Square, Piece] = {}
    for square, piece in source.piece_map().items():
        if piece.color == chess.WHITE:
            pieces[square] = Piece(piece_type=piece.piece_type, bought=bought)
    return Army(deployment=pieces)
