"""One encounter: the player's army against an enemy formation.

The opponent is injected as a plain callable, so this module never imports the
engine package. Stockfish supplies one implementation; the tests supply
scripted movers and play whole fights without a binary on the machine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional

import chess

from .. import config
from .army import Army, Piece, compose_board

Opponent = Callable[[chess.Board], chess.Move]
"""Given a legal position with Black to move, return a legal move."""


class Outcome(Enum):
    PLAYER_WIN = "win"
    PLAYER_LOSS = "loss"


@dataclass
class LogEntry:
    text: str
    by_player: bool
    capture: bool = False
    check: bool = False


class PieceTracker:
    """Follows army pieces through a fight by square, so identity survives.

    Counting pieces at the end would tell you *that* a rook died; this tells you
    *which* rook -- the one that had survived six fights.
    """

    def __init__(self, army: Army) -> None:
        self.at: Dict[chess.Square, int] = {
            square: piece.id for square, piece in army.deployment.items()
        }
        self.captured: List[int] = []

    def observe(self, board: chess.Board, move: chess.Move) -> None:
        """Record the effect of `move`. Must be called BEFORE board.push()."""
        if board.is_en_passant(move):
            offset = -8 if board.turn == chess.WHITE else 8
            captured_square = move.to_square + offset
        else:
            captured_square = move.to_square

        victim = self.at.pop(captured_square, None)
        if victim is not None:
            self.captured.append(victim)

        mover = self.at.pop(move.from_square, None)
        if mover is None:
            return

        self.at[move.to_square] = mover
        if board.is_castling(move):
            self._move_castling_rook(board, move)

    def _move_castling_rook(self, board: chess.Board, move: chess.Move) -> None:
        rank = chess.square_rank(move.from_square)
        kingside = chess.square_file(move.to_square) > chess.square_file(move.from_square)
        rook_from = chess.square(7 if kingside else 0, rank)
        rook_to = chess.square(5 if kingside else 3, rank)
        rook_id = self.at.pop(rook_from, None)
        if rook_id is not None:
            self.at[rook_to] = rook_id


@dataclass
class Fight:
    """A single encounter. Owns the rules; the opponent is somebody else's job."""

    army: Army
    enemy_fen: str
    opponent: Opponent
    enemy_name: str = "the enemy"
    tier: str = config.TIER_LOW
    elo: int = 1000

    board: chess.Board = field(init=False)
    tracker: PieceTracker = field(init=False)
    player_moves: int = field(init=False, default=0)
    log: List[LogEntry] = field(init=False, default_factory=list)
    outcome: Optional[Outcome] = field(init=False, default=None)

    forced: bool = field(init=False, default=False)
    """Set when `force_outcome` ended this fight instead of the board doing it.
    Its only consumer is the UI, which would otherwise read the position and
    report a forced win as "the position is dead"."""

    def __post_init__(self) -> None:
        self.board = compose_board(self.army, self.enemy_fen)
        self.tracker = PieceTracker(self.army)
        self.resolve()

    # -- queries ---------------------------------------------------------

    @property
    def finished(self) -> bool:
        return self.outcome is not None

    @property
    def player_to_move(self) -> bool:
        return self.board.turn == chess.WHITE and not self.finished

    def legal_moves(self) -> List[chess.Move]:
        return list(self.board.legal_moves)

    def moves_from(self, square: chess.Square) -> List[chess.Move]:
        return [m for m in self.board.legal_moves if m.from_square == square]

    def parse(self, text: str) -> Optional[chess.Move]:
        """Accept either coordinate notation (e2e4) or SAN (Nf3)."""
        text = text.strip()
        if not text:
            return None
        for parser in (self.board.parse_san, chess.Move.from_uci):
            try:
                move = parser(text)
            except (ValueError, chess.InvalidMoveError, chess.IllegalMoveError,
                    chess.AmbiguousMoveError):
                continue
            if move in self.board.legal_moves:
                return move
        return None

    # -- play ------------------------------------------------------------

    def play_player(self, move: chess.Move) -> bool:
        if self.finished or self.board.turn != chess.WHITE:
            return False
        if move not in self.board.legal_moves:
            return False
        self._push(move, by_player=True)
        self.player_moves += 1
        return True

    def opponent_move(self) -> Optional[chess.Move]:
        """Ask the opponent for a move without applying it.

        Split from `apply_opponent` so the UI can do the blocking engine call on
        a worker thread and apply the result back on the main thread.
        """
        if self.finished or self.board.turn != chess.BLACK:
            return None
        return self.opponent(self.board)

    def apply_opponent(self, move: chess.Move) -> bool:
        if self.finished or self.board.turn != chess.BLACK:
            return False
        if move not in self.board.legal_moves:
            raise ValueError("opponent returned an illegal move: %s" % move)
        self._push(move, by_player=False)
        return True

    def play_opponent(self) -> Optional[chess.Move]:
        """Ask and apply in one go (headless callers and tests)."""
        move = self.opponent_move()
        if move is None:
            return None
        self.apply_opponent(move)
        return move

    def _push(self, move: chess.Move, by_player: bool) -> None:
        san = self.board.san(move)
        capture = self.board.is_capture(move)
        self.tracker.observe(self.board, move)
        self.board.push(move)
        self.log.append(
            LogEntry(
                text=san,
                by_player=by_player,
                capture=capture,
                check=self.board.is_check(),
            )
        )
        self.resolve()

    def resolve(self) -> None:
        """Apply the locked win/lose rules and set `outcome` if the fight ended.

        Called automatically after every move. It is public because anything
        that edits the board behind the move stack -- currently only the dev
        tools -- has to re-ask whether the fight is over.

        Checkmate is the win condition. Stalemate inverts: whoever gets
        stalemated wins, so delivering it is a loss and you have to actually
        mate. Other draws (repetition, 50-move, dead position) are a failure to
        win, and the player eats them.
        """
        board = self.board
        if board.is_checkmate():
            mated_is_player = board.turn == chess.WHITE
            self.outcome = Outcome.PLAYER_LOSS if mated_is_player else Outcome.PLAYER_WIN
            return

        if board.is_stalemate():
            stalemated_is_player = board.turn == chess.WHITE
            if config.STALEMATE_LOSES:
                # The stalemated side wins.
                self.outcome = (
                    Outcome.PLAYER_WIN if stalemated_is_player else Outcome.PLAYER_LOSS
                )
            else:
                self.outcome = Outcome.PLAYER_LOSS
            return

        if (
            board.is_insufficient_material()
            or board.is_fivefold_repetition()
            or board.is_seventyfive_moves()
        ):
            self.outcome = Outcome.PLAYER_LOSS

    def force_outcome(self, outcome: Outcome) -> None:
        """End the fight immediately, bypassing the board.

        A neutral capability -- core has no notion of dev mode. The UI is what
        decides this may only be triggered from a diagnostics shortcut.
        """
        self.outcome = outcome
        self.forced = True

    # -- aftermath -------------------------------------------------------

    def apply_to_army(self) -> List[Piece]:
        """Write the fight's results back onto the persistent army.

        The army holds a FORMATION -- the home squares you arranged in the swap
        phase -- not a live position. A fight mutates its own board and leaves
        the formation alone, so surviving pieces stay on the squares you put
        them on rather than wherever the fight happened to strand them.

        What does carry across: the dead are removed for good and survivors age
        by one fight. Bench pieces deliberately gain nothing -- veterancy is
        earned on the board.

        Promotion deliberately does NOT carry across. A pawn that queens does so
        for that fight only and comes back a pawn. Making it permanent would
        make stalling to promote every pawn the dominant strategy -- +8 material
        a pawn against a payout that only drops by one for a slow win. Promotion
        stays a tactical tool: queen to win faster, not to get richer.
        """
        by_id = {piece.id: piece for piece in self.army.deployment.values()}
        killed = set(self.tracker.captured)

        surviving: Dict[chess.Square, Piece] = {}
        for square, piece in self.army.deployment.items():
            if piece.id in killed:
                continue
            piece.fights_survived += 1
            surviving[square] = piece

        casualties = [by_id[pid] for pid in self.tracker.captured if pid in by_id]
        self.army.deployment = surviving
        return casualties
