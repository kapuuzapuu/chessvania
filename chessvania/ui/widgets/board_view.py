"""The 8x8 board, rendered as monospace cells with hover and click."""

from __future__ import annotations

from typing import Dict, Iterable, Optional, Set

import chess
from rich.text import Text
from textual.message import Message
from textual.widgets import Static

from ...core.threat import Danger, Threat
from .. import theme

CELL_WIDTH = 3
LEFT_MARGIN = 2
HEADER_ROWS = 1


class BoardView(Static):
    """Renders a chess.Board. Emits SquareClicked / SquareHovered."""

    class SquareClicked(Message):
        def __init__(self, square: chess.Square) -> None:
            self.square = square
            super().__init__()

    class CursorMoved(Message):
        def __init__(self, square: Optional[chess.Square]) -> None:
            self.square = square
            super().__init__()

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.board: chess.Board = chess.Board(None)
        self.veterancy: Dict[chess.Square, int] = {}
        self.selected: Optional[chess.Square] = None
        self.targets: Set[chess.Square] = set()
        self.last_move: Optional[chess.Move] = None
        self.flash_square: Optional[chess.Square] = None
        self.cursor: Optional[chess.Square] = None
        self.cursor_active = True
        self.threats: Dict[chess.Square, Threat] = {}
        self.flip = False

    # -- state -----------------------------------------------------------

    def set_board(
        self,
        board: chess.Board,
        veterancy: Optional[Dict[chess.Square, int]] = None,
        last_move: Optional[chess.Move] = None,
    ) -> None:
        self.board = board
        self.veterancy = veterancy or {}
        self.last_move = last_move
        self.redraw()

    def set_selection(
        self,
        selected: Optional[chess.Square],
        targets: Iterable[chess.Square] = (),
    ) -> None:
        self.selected = selected
        self.targets = set(targets)
        self.redraw()

    def set_threats(self, by_square: Optional[Dict[chess.Square, Threat]]) -> None:
        """Overlay `core.threat`'s per-square verdicts.

        Only the player's squares are marked. The enemy's opportunities are real
        information too, but a 3-column cell can carry one annotation before it
        stops being a chessboard -- and the half worth spending it on is the half
        that is permanent.
        """
        self.threats = dict(by_square or {})
        self.redraw()

    def set_cursor(self, square: Optional[chess.Square], active: bool = True) -> None:
        """Move the keyboard cursor. Mouse hover drives the same cursor."""
        changed = square != self.cursor or active != self.cursor_active
        self.cursor = square
        self.cursor_active = active
        if changed:
            self.redraw()
            self.post_message(self.CursorMoved(square))

    def flash(self, square: chess.Square, duration: float = 0.28) -> None:
        """Cell-based capture flash. Terminals cannot glide, so they blink."""
        self.flash_square = square
        self.redraw()
        self.set_timer(duration, self._clear_flash)

    def _clear_flash(self) -> None:
        self.flash_square = None
        self.redraw()

    # -- rendering -------------------------------------------------------

    def redraw(self) -> None:
        self.update(self._render_board())

    def _render_board(self) -> Text:
        text = Text()
        files = "abcdefgh"
        ranks = range(7, -1, -1) if not self.flip else range(8)

        text.append(" " * LEFT_MARGIN)
        for f in files:
            text.append(" %s " % f, style=theme.GHOST)
        text.append("\n")

        for rank in ranks:
            text.append("%d " % (rank + 1), style=theme.GHOST)
            for file in range(8):
                text.append_text(self._cell(chess.square(file, rank)))
            text.append(" %d" % (rank + 1), style=theme.GHOST)
            text.append("\n")

        return text

    def _cell(self, square: chess.Square) -> Text:
        file = chess.square_file(square)
        rank = chess.square_rank(square)
        piece = self.board.piece_at(square)
        is_target = square in self.targets
        threat = self.threats.get(square)

        background = theme.SQ_LIGHT if (file + rank) % 2 else theme.SQ_DARK
        if self.last_move is not None and square in (
            self.last_move.from_square,
            self.last_move.to_square,
        ):
            background = theme.SQ_MOVE
        if threat is not None and threat.level is Danger.CHECK:
            # Sits under the move-composing highlights below on purpose: while
            # you are picking a destination, the destination is what matters.
            background = theme.SQ_CHECK
        if is_target:
            # Captures read red, quiet moves green -- the cost is visible before
            # you commit to the move.
            background = theme.SQ_CAPTURE if piece is not None else theme.SQ_TARGET
        if square == self.selected:
            background = theme.SQ_SELECT
        if square == self.flash_square:
            background = theme.SQ_CAPTURE

        if piece is None:
            glyph = "·" if is_target else " "
            foreground = theme.GREEN if is_target else theme.FAINT
        else:
            glyph = piece.unicode_symbol()
            if piece.color == chess.WHITE:
                foreground = theme.player_color_for(
                    self.veterancy.get(square, 0), piece.piece_type
                )
            else:
                foreground = theme.enemy_color(piece.piece_type)

        marker = theme.threat_marker(threat.level) if threat is not None else None
        if threat is not None and threat.level is not Danger.CHECK:
            # Tint the piece itself so danger is legible without hunting for the
            # marker. The king is exempt: it already sits on a red square, and
            # red-on-red would hide the one piece you cannot afford to lose.
            foreground = theme.threat_color(threat.level) or foreground

        if square == self.flash_square:
            foreground = "#ffffff"

        cell = Text()
        if square == self.cursor:
            # A 3-wide cell has no room for a drawn border, so the cursor
            # brackets the square instead -- same read, no extra rows. The
            # threat marker yields to it; the inspect panel spells out the
            # square under the cursor in full anyway.
            edge = theme.GREEN if self.cursor_active else theme.FAINT
            cell.append("[", style="%s on %s" % (edge, background))
            cell.append(glyph, style="%s on %s" % (foreground, background))
            cell.append("]", style="%s on %s" % (edge, background))
        elif marker is not None:
            cell.append(" ", style="on %s" % background)
            cell.append(glyph, style="%s on %s" % (foreground, background))
            cell.append(
                marker,
                style="%s on %s" % (theme.threat_color(threat.level), background),
            )
        else:
            cell.append(" %s " % glyph, style="%s on %s" % (foreground, background))
        return cell

    # -- mouse -----------------------------------------------------------

    def _square_at(self, x: int, y: int) -> Optional[chess.Square]:
        row = y - HEADER_ROWS
        if not 0 <= row <= 7:
            return None
        file = (x - LEFT_MARGIN) // CELL_WIDTH
        if not 0 <= file <= 7:
            return None
        rank = row if self.flip else 7 - row
        return chess.square(file, rank)

    def on_click(self, event) -> None:
        square = self._square_at(event.x, event.y)
        if square is not None:
            self.post_message(self.SquareClicked(square))

    def on_mouse_move(self, event) -> None:
        """Hovering drives the same cursor the arrow keys do -- one highlight."""
        square = self._square_at(event.x, event.y)
        if square is not None:
            self.set_cursor(square)
