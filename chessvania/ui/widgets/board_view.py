"""The 8x8 board, rendered as monospace cells with hover and click."""

from __future__ import annotations

from typing import Dict, Iterable, Optional, Set

import chess
from rich.text import Text
from textual.message import Message
from textual.widgets import Static

from ...core.threat import Danger, Threat
from .. import theme

LEFT_MARGIN = 2
RIGHT_MARGIN = 2
HEADER_ROWS = 1

CELL_LADDER = ((3, 1), (5, 2), (7, 3), (9, 4))
"""(columns, rows) per square, smallest first.

Terminal cells are roughly twice as tall as they are wide, so a square that
*looks* square needs about two columns per row -- that ratio, not the terminal's
own, is what keeps the board from reading as letterboxed. Widths are odd so a
single glyph centres exactly.

The first rung is the floor: 3x1 is what fits an 80x24 terminal, which is the
smallest size the game supports.
"""

CELL_WIDTH = CELL_LADDER[0][0]
"""Backwards-compatible alias for the floor cell width."""


def board_size(cell_w: int, cell_h: int):
    """(columns, rows) the widget needs to draw a board at this cell size."""
    return (8 * cell_w + LEFT_MARGIN + RIGHT_MARGIN, 8 * cell_h + HEADER_ROWS)


def choose_cell(available_w: int, available_h: int):
    """The largest cell size that fits the space, never smaller than the floor.

    Returns the floor rung even when it does not fit, because a cramped board is
    a better failure than no board: below 80x24 the whole screen is compromised
    anyway, and clamping here would only hide that.
    """
    best = CELL_LADDER[0]
    for cell_w, cell_h in CELL_LADDER:
        width, height = board_size(cell_w, cell_h)
        if width <= available_w and height <= available_h:
            best = (cell_w, cell_h)
    return best


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
        self.cell_w, self.cell_h = CELL_LADDER[0]

    def set_cell(self, cell_w: int, cell_h: int) -> None:
        """Resize the squares. The screen picks the size; the widget draws it."""
        if (cell_w, cell_h) == (self.cell_w, self.cell_h):
            return
        self.cell_w, self.cell_h = cell_w, cell_h
        self.redraw()

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

    @property
    def glyph_row(self) -> int:
        """Which sub-row of a tall cell carries the piece.

        Biased upward rather than centred so that an even-height cell puts its
        padding *below* the glyph. Centring would leave a blank row between the
        file header and rank 8, which reads as the board having slipped down.
        """
        return (self.cell_h - 1) // 2

    def _render_board(self) -> Text:
        text = Text()
        files = "abcdefgh"
        ranks = range(7, -1, -1) if not self.flip else range(8)

        text.append(" " * LEFT_MARGIN)
        for f in files:
            text.append(f.center(self.cell_w), style=theme.GHOST)
        text.append("\n")

        for rank in ranks:
            for sub_row in range(self.cell_h):
                labelled = sub_row == self.glyph_row
                label = "%d " % (rank + 1) if labelled else "  "
                text.append(label, style=theme.GHOST)
                for file in range(8):
                    text.append_text(self._cell(chess.square(file, rank), sub_row))
                text.append(" %d" % (rank + 1) if labelled else "  ",
                            style=theme.GHOST)
                text.append("\n")

        return text

    def _cell(self, square: chess.Square, sub_row: int = 0) -> Text:
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
            glyph = theme.piece_glyph(piece.piece_type, piece.color)
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
        if sub_row != self.glyph_row:
            # A tall cell is one square: only the middle row carries anything,
            # the rest is the square's colour.
            cell.append(" " * self.cell_w, style="on %s" % background)
            return cell

        # Build the row as characters so every cell width is laid out the same
        # way: glyph in the middle, decoration on the edges.
        chars = [" "] * self.cell_w
        styles = ["on %s" % background] * self.cell_w
        middle = self.cell_w // 2
        chars[middle] = glyph
        styles[middle] = "%s on %s" % (foreground, background)

        if square == self.cursor:
            # The cursor brackets the square rather than boxing it: even at the
            # widest cell there is no row to spare for a drawn border without
            # the board losing a rung. The threat marker yields to it; the
            # inspect panel spells the square out in full anyway.
            edge = theme.GREEN if self.cursor_active else theme.FAINT
            chars[0], chars[-1] = "[", "]"
            styles[0] = styles[-1] = "%s on %s" % (edge, background)
        elif marker is not None:
            chars[-1] = marker
            styles[-1] = "%s on %s" % (theme.threat_color(threat.level), background)

        for char, style in zip(chars, styles):
            cell.append(char, style=style)
        return cell

    # -- mouse -----------------------------------------------------------

    def _square_at(self, x: int, y: int) -> Optional[chess.Square]:
        row = y - HEADER_ROWS
        if row < 0:
            return None
        rank_index = row // self.cell_h
        if not 0 <= rank_index <= 7:
            return None
        column = x - LEFT_MARGIN
        if column < 0:
            return None
        file = column // self.cell_w
        if not 0 <= file <= 7:
            return None
        rank = rank_index if self.flip else 7 - rank_index
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
