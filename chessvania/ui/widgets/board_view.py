"""The 8x8 board, rendered as monospace cells with hover and click."""

from __future__ import annotations

from typing import Dict, Iterable, Optional, Set

import chess
from rich.text import Text
from textual.message import Message
from textual.widgets import Static

from .. import piece_art, theme

# The board has no gutters. Ranks and files are written INSIDE the corner of
# an edge square, the way a printed diagram or a chess site does it, which
# buys back four columns and a row for the board itself.
#
# It works because `ui.piece_art` guarantees -- and `tests/test_piece_art.py`
# enforces -- that every sprite keeps its outer column on each side clear and
# a clear character row on top. The rank's corner (top right) and the file's
# corner (bottom left) are exactly the two those rules protect.

TARGET_DOT = "·"
"""Marks an empty square you could move to, on an odd-height cell."""

TARGET_HALF = "▄"
"""The same mark on an even-height cell, which has no middle row.

Its ink sits in the lower half of the upper inner row -- half a pixel above the
cell's true centre, against the full pixel a plain dot would be out by. A `▀` on
the row beneath would land it exactly, but two rows of mark read as a block
rather than a dot, so the half-pixel is the better trade."""

CELL_LADDER = ((7, 3), (9, 4))
"""(columns, rows) per square, smallest first.

Terminal cells are roughly twice as tall as they are wide, so a square that
*looks* square needs about two columns per row -- that ratio, not the terminal's
own, is what keeps the board from reading as letterboxed. Widths are odd so a
single glyph centres exactly.

The first rung is the floor: 7x3 is what fits a 104x30 terminal, which is the
smallest size the game supports. Smaller squares existed once -- 3x1 drew a bare
Unicode glyph and 5x2 a cramped sprite -- and were dropped once the drawn pieces
became the point; a board that small could not carry them.
"""

CELL_WIDTH = CELL_LADDER[0][0]
"""Backwards-compatible alias for the floor cell width."""


def board_size(cell_w: int, cell_h: int):
    """(columns, rows) the widget needs to draw a board at this cell size."""
    return (8 * cell_w, 8 * cell_h)


def choose_cell(available_w: int, available_h: int):
    """The largest cell size that fits the space, never smaller than the floor.

    Returns the floor rung even when it does not fit, because a cramped board is
    a better failure than no board: below 104x30 the whole screen is compromised
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
        self.targets_are_captures = True
        """In a fight an occupied target is a capture and reads red. In the swap
        phase it is an exchange with your own piece, so it must not."""
        self.last_move: Optional[chess.Move] = None
        self.flash_square: Optional[chess.Square] = None
        self.cursor: Optional[chess.Square] = None
        self.cursor_active = True
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
        captures: bool = True,
    ) -> None:
        self.selected = selected
        self.targets = set(targets)
        self.targets_are_captures = captures
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
        padding *below* the glyph. Centring would leave a blank row along the
        top edge, which reads as the board having slipped down.
        """
        return (self.cell_h - 1) // 2

    def _render_board(self) -> Text:
        text = Text()
        ranks = range(7, -1, -1) if not self.flip else range(8)
        for row, rank in enumerate(ranks):
            for sub_row in range(self.cell_h):
                if row or sub_row:
                    text.append("\n")
                for file in range(8):
                    text.append_text(self._cell(chess.square(file, rank), sub_row))
        return text

    def _coordinate(self, square: chess.Square, sub_row: int):
        """(column, character) this cell corner carries, or None.

        The rank goes in the top-right of the last file drawn and the file
        letter in the bottom-left of the nearest rank -- the two corners
        `piece_art` keeps clear of sprite, so a label never lands on a piece.
        """
        file = chess.square_file(square)
        rank = chess.square_rank(square)
        if sub_row == 0 and file == 7:
            return self.cell_w - 1, "%d" % (rank + 1)
        if sub_row == self.cell_h - 1 and rank == (7 if self.flip else 0):
            return 0, "abcdefgh"[file]
        return None

    def _cell(self, square: chess.Square, sub_row: int = 0) -> Text:
        file = chess.square_file(square)
        rank = chess.square_rank(square)
        piece = self.board.piece_at(square)
        is_target = square in self.targets

        light = (file + rank) % 2
        background = theme.SQ_LIGHT if light else theme.SQ_DARK
        if self.last_move is not None and square in (
            self.last_move.from_square,
            self.last_move.to_square,
        ):
            background = theme.SQ_MOVE
        if is_target:
            # Captures read red, quiet moves green -- the cost is visible before
            # you commit to the move. A swap-phase target is never a capture.
            if piece is not None and self.targets_are_captures:
                background = theme.SQ_CAPTURE_LIGHT if light else theme.SQ_CAPTURE_DARK
            else:
                background = theme.SQ_TARGET_LIGHT if light else theme.SQ_TARGET_DARK
        if square == self.selected:
            background = theme.SQ_SELECT
        if square == self.flash_square:
            background = theme.SQ_CAPTURE_LIGHT if light else theme.SQ_CAPTURE_DARK

        if piece is None:
            # Even-height cells have no middle row, so they use a half block
            # that hugs the centre line instead of a dot that floats above it.
            glyph = (TARGET_HALF if self.cell_h % 2 == 0 else TARGET_DOT) \
                if is_target else " "
            foreground = theme.GREEN if is_target else theme.FAINT
        else:
            glyph = theme.piece_glyph(piece.piece_type, piece.color)
            if piece.color == chess.WHITE:
                foreground = theme.player_color_for(
                    self.veterancy.get(square, 0), piece.piece_type
                )
            else:
                foreground = theme.enemy_color(piece.piece_type)

        if square == self.flash_square:
            foreground = "#ffffff"

        sprite = None
        if piece is not None:
            sprite = piece_art.art_for(self.cell_w, self.cell_h, piece.piece_type)

        if square == self.cursor:
            # The ONLY cursor signal. An occupied square is filled edge to edge
            # with art and an empty one is a flat tile, so there is nowhere to
            # put a bracket that does not sit on top of something -- and the
            # tint carries it on its own.
            if self.cursor_active and square != self.flash_square:
                background = theme.SQ_CURSOR

        # One code path for all three kinds of row -- sprite, empty, and the
        # glyph fallback -- because the coordinate overlay has to apply to
        # every one of them and a cell that returned early would skip it.
        if sprite is not None:
            chars = list(sprite[sub_row])
            styles = ["%s on %s" % (foreground, background)] * self.cell_w
        elif sub_row != self.glyph_row:
            # A tall cell is one square: only the middle row carries anything,
            # the rest is the square's colour.
            chars = [" "] * self.cell_w
            styles = ["on %s" % background] * self.cell_w
        else:
            # Build the row as characters so every cell width is laid out the
            # same way: glyph in the middle, decoration on the edges.
            chars = [" "] * self.cell_w
            styles = ["on %s" % background] * self.cell_w
            middle = self.cell_w // 2
            chars[middle] = glyph
            styles[middle] = "%s on %s" % (foreground, background)

        coordinate = self._coordinate(square, sub_row)
        if coordinate is not None:
            column, mark = coordinate
            chars[column] = mark
            styles[column] = "%s on %s" % (theme.COORD, background)

        cell = Text()
        for char, style in zip(chars, styles):
            cell.append(char, style=style)
        return cell

    # -- mouse -----------------------------------------------------------

    def _square_at(self, x: int, y: int) -> Optional[chess.Square]:
        if x < 0 or y < 0:
            return None
        rank_index = y // self.cell_h
        if not 0 <= rank_index <= 7:
            return None
        file = x // self.cell_w
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
