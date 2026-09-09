"""The 16-slot inventory, drawn as a 4x4 grid of bench slots.

The bench carries no side ambiguity -- everything in it is yours -- so it is the
one place veterancy colour can be loud without competing with the
whose-piece-is-whose signal the board needs.
"""

from __future__ import annotations

from typing import List, Optional

from rich.text import Text
from textual.message import Message
from textual.widgets import Static

from ... import config
from ...core.army import Piece
from .. import theme

COLUMNS = 4
CELL_WIDTH = 4


class BenchView(Static):
    """Renders inventory slots. Emits SlotClicked / SlotHovered."""

    class SlotClicked(Message):
        def __init__(self, index: int) -> None:
            self.index = index
            super().__init__()

    class CursorMoved(Message):
        def __init__(self, index: Optional[int]) -> None:
            self.index = index
            super().__init__()

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.pieces: List[Piece] = []
        self.selected: Optional[int] = None
        self.cursor: Optional[int] = None
        self.cursor_active = True

    def set_pieces(self, pieces: List[Piece]) -> None:
        self.pieces = list(pieces)
        self.redraw()

    def set_selection(self, index: Optional[int]) -> None:
        self.selected = index
        self.redraw()

    def set_cursor(self, index: Optional[int], active: bool = True) -> None:
        changed = index != self.cursor or active != self.cursor_active
        self.cursor = index
        self.cursor_active = active
        if changed:
            self.redraw()
            self.post_message(self.CursorMoved(index))

    def redraw(self) -> None:
        self.update(self._build_text())

    def _build_text(self) -> Text:
        text = Text()
        rows = config.INVENTORY_CAP // COLUMNS
        for row in range(rows):
            for column in range(COLUMNS):
                index = row * COLUMNS + column
                text.append_text(self._slot(index))
            if row < rows - 1:
                text.append("\n")
        return text

    def _slot(self, index: int) -> Text:
        piece = self.pieces[index] if index < len(self.pieces) else None

        if piece is None:
            body, color = "·", theme.GHOST
        else:
            body, color = theme.piece_glyph_for(piece), theme.player_color(piece)

        if index == self.selected:
            bracket = theme.GOLD
            body_style = "%s on %s" % (color, theme.SQ_SELECT)
        elif index == self.cursor:
            bracket = theme.GREEN if self.cursor_active else theme.FAINT
            body_style = "%s on %s" % (color, theme.SQ_TARGET)
        else:
            bracket = theme.BORDER_SOFT
            body_style = color

        cell = Text()
        cell.append("[", style=bracket)
        cell.append(body, style=body_style)
        cell.append("]", style=bracket)
        cell.append(" ")
        return cell

    # -- mouse -----------------------------------------------------------

    def _index_at(self, x: int, y: int) -> Optional[int]:
        if not 0 <= y < config.INVENTORY_CAP // COLUMNS:
            return None
        column = x // CELL_WIDTH
        if not 0 <= column < COLUMNS:
            return None
        return y * COLUMNS + column

    def on_click(self, event) -> None:
        index = self._index_at(event.x, event.y)
        if index is not None:
            self.post_message(self.SlotClicked(index))

    def on_mouse_move(self, event) -> None:
        index = self._index_at(event.x, event.y)
        if index is not None:
            self.set_cursor(index)
