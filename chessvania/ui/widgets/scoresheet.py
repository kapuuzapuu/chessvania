"""The fight's moves, written the way a scoresheet is written.

    #   WHITE   BLACK
    5.  bxc3    Bg4
    6.  f3      Bh5
    7.  Bg5     h6
    8.  ▌
    9.
    10.

Plies are paired by move number rather than listed one per line. You are
always White, so the column already says who played -- which is why neither
side is colour-coded here and nothing is prefixed with a name. Two columns
of SAN in the same cream is what a scoresheet looks like, and SAN already
carries the capture (`x`), the check (`+`) and the mate (`#`), so none of
those need a colour either.

The newest move is tinted in `theme.SQ_MOVE` -- the same olive the board
paints the last move's squares with. One colour, one meaning: it is the move
that just happened, wherever you happen to be looking.

The caret marks the cell waiting to be filled, which is the only thing on
the panel that says whose turn it is. Rows below it are drawn empty but
numbered, the way a printed sheet has lines left on it.

The whole game is written down, and the body scrolls, but the column header
is a sibling of the scrolling region rather than its first line -- a sheet
that loses "WHITE / BLACK" exactly when it gets long enough to need them is
worse than one that cannot scroll at all. It follows play only while you are
already at the bottom, so scrolling back to look at move 3 is not undone by
the engine replying.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static

from ...core.fight import Fight
from .. import theme
from ..layout import SHEET_ROWS

NUM_W = 4
SAN_W = 7
"""Widest legal SAN is seven columns (`exd8=Q+`, `Qa1xb2+`)."""

CARET = "▌"
HIGHLIGHT = "%s on %s" % (theme.TEXT, theme.SQ_MOVE)


class Scoresheet(Vertical):
    """Reads a `Fight`; owns no state of its own."""

    DEFAULT_CSS = """
    Scoresheet > #sheet-head { height: 1; }
    Scoresheet > #sheet-body {
        height: 1fr;
        overflow-y: auto;
        scrollbar-size-vertical: 1;
        scrollbar-background: %(panel)s;
        scrollbar-background-hover: %(panel)s;
        scrollbar-background-active: %(panel)s;
        scrollbar-color: %(rule)s;
        scrollbar-color-hover: %(label)s;
        scrollbar-color-active: %(gold)s;
    }
    """ % {"panel": theme.PANEL, "rule": theme.RULE_STRONG,
           "label": theme.LABEL, "gold": theme.GOLD}
    """Textual's default scrollbar is its own blue accent, which is the one
    colour this palette does not contain. Dressed off `theme` instead."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.rows = SHEET_ROWS[0]
        """How many move rows to draw to. Set by `ui.layout.scale_board`, the
        same way the board is told its cell size.

        NOT measured off this widget. `scale_board` assigns the panel's height
        and then refreshes in the same pass, so `content_size` still holds the
        PREVIOUS layout -- reading it meant one resize grew the panel and the
        next one filled it. Measuring siblings mid-layout is the recurring
        bug this project has; measuring yourself mid-layout is the same bug."""

    def compose(self) -> ComposeResult:
        yield Static(self._header(), id="sheet-head")
        # can_focus=False: a focusable scroll region inside the fight screen
        # swallows the arrow keys, and the arrow keys are how the board cursor
        # moves. The wheel still scrolls it -- wheel events go to whatever is
        # under the pointer rather than to whatever has focus.
        with VerticalScroll(id="sheet-body", can_focus=False):
            yield Static(id="sheet-rows")

    def show(self, fight: Fight) -> None:
        body = self.query_one("#sheet-body", VerticalScroll)
        # Ask BEFORE the update: "were you reading the live end of the sheet?"
        following = body.scroll_offset.y >= body.max_scroll_y
        self.query_one("#sheet-rows", Static).update(self._build(fight))
        if following:
            body.scroll_end(animate=False)

    # -- reading the fight -----------------------------------------------

    def _pairs(self, fight: Fight) -> List[Tuple[Optional[str], Optional[str]]]:
        """The log as (white, black) per move number.

        Pairing is by ply parity, which holds because the player is White and
        White opens. `test_the_scoresheet_puts_your_moves_in_the_white_column`
        pins that against `LogEntry.by_player` rather than trusting it.
        """
        rows: List[List[Optional[str]]] = []
        for index, entry in enumerate(fight.log):
            if index % 2 == 0:
                rows.append([entry.text, None])
            else:
                rows[-1][1] = entry.text
        return [(white, black) for white, black in rows]

    def _live_cell(self, fight: Fight) -> Optional[Tuple[int, int]]:
        """(move number, column) of the cell awaiting a move, 0 = white."""
        if fight.finished:
            return None
        played = len(fight.log)
        return played // 2 + 1, played % 2

    # -- drawing ---------------------------------------------------------

    def _build(self, fight: Fight) -> Text:
        """Named to avoid shadowing Textual's internal `Widget._render()`."""
        pairs = self._pairs(fight)
        live = self._live_cell(fight)
        last = live[0] if live else len(pairs)

        # Every move played, then blank lines to the bottom of the panel, so
        # a short game still looks like a sheet with room left on it.
        text = Text()
        for number in range(1, max(last, self.rows) + 1):
            # Separator, not terminator. A trailing newline makes the body one
            # line taller than its content, and the scroll then stops a row
            # short of the live move.
            if number > 1:
                text.append("\n")
            text.append_text(self._row(number, pairs, live, len(fight.log)))
        return text

    def _header(self) -> Text:
        return Text("%-*s%-*s%s" % (NUM_W, "#", SAN_W + 1, "WHITE", "BLACK"),
                    style=theme.DIM)

    def _row(self, number: int, pairs, live, played: int) -> Text:
        text = Text()
        text.append("%-*s" % (NUM_W, "%d." % number), style=theme.GHOST)

        pair = pairs[number - 1] if number <= len(pairs) else (None, None)
        for column, san in enumerate(pair):
            width = SAN_W + 1 if column == 0 else SAN_W
            if san is not None:
                newest = (number - 1) * 2 + column == played - 1
                text.append(san[:SAN_W], style=HIGHLIGHT if newest else theme.TEXT)
                text.append(" " * (width - len(san[:SAN_W])))
            elif live == (number, column):
                text.append(CARET, style=theme.TEAL)
                text.append(" " * (width - 1))
            else:
                text.append(" " * width)
        return text
