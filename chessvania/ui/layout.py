"""How much room the board gets, and what size squares fit in it.

The fight and post-fight screens share one three-column layout: bench on the
left, board in the middle, panels on the right. The two outer columns are fixed
or elastic in CSS, but the board cannot be -- it has to land on a whole number
of squares, so its size is chosen here in Python and pushed into the CSS rather
than the other way round.

The constants below mirror `ChessvaniaApp.CSS`. That duplication is deliberate
and narrow: the alternative is measuring sibling widgets during a layout pass,
which is exactly the mis-measurement that has bitten this UI before. Keep them
in step -- `tests/test_layout.py` fails if the board stops fitting.
"""

from __future__ import annotations

from typing import Tuple

from .. import config
from .widgets.board_view import (
    CELL_LADDER,
    BoardView,
    board_size,
    choose_cell,
)

LEFT_COLUMN = 17
"""Width of the bench column (`#left`)."""

RIGHT_MIN = 25
"""Smallest the panel column (`#right`) may be squeezed to (`min-width`)."""

MAIN_PAD_X = 2
"""`#main` pads one column on each side, outside all three columns."""

STATUS_MAX_ROWS = 2
"""Tallest the status block under the board can get.

Counted off `FightScreen._status_text`: a transient line -- a notice, or
"<enemy> is thinking..." -- above the control hint. The promotion picker is
the same two lines.
"""

CHROME_ROWS = 3 + STATUS_MAX_ROWS
"""Rows the board never gets: the top bar, the padding above it, the
status block's top margin, and the status block itself at full height."""

ENEMY_PANEL_ROWS = 4
PURSE_PANEL_ROWS = 6
"""Outer heights of the two fixed panels above the scoresheet, borders in.

Both are pinned in the CSS rather than left on `height: auto`, so the column
below them does not move when the purse grows a skip-bonus line. Same narrow,
deliberate duplication as the column widths above."""

PANEL_GAP = 0
"""Rows between the panels in the right-hand column.

They are bordered, so they separate themselves; the blank row between them
was costing the scoresheet a whole rung once the board reclaimed its gutters."""

SHEET_CHROME = 3
"""Rows a scoresheet spends on things that are not moves: two of border and
the pinned `# WHITE BLACK` header."""

SHEET_ROWS = (10, 15)
"""Move rows the scoresheet may show, fewest first -- a ladder, like
`CELL_LADDER`, not a range.

Round numbers on purpose. Left to fill the column it drew 9 rows on the
smallest terminal and 17 on a large one: both arbitrary, neither of them
anything you could learn or rely on. Taking the largest rung that fits means
the count only ever lands on a number that was chosen. The moves above the
top rung are still written down, and the sheet scrolls back to them."""

DEV_BAR_ROWS = 6
"""The docked diagnostics strip, when `DEV_MODE` is on.

Reserves its EXPANDED height. The strip is 3 rows collapsed and 6 with f1
held open, and a dev session spends most of its time expanded -- reserving the
smaller number means the board resizes under you the moment you open it."""


def minimum_terminal(dev_mode: bool = False) -> Tuple[int, int]:
    """The smallest terminal the game supports, derived rather than declared.

    It is whatever the floor rung of `CELL_LADDER` needs once the two side
    columns and the chrome are paid for. Dropping or adding a rung moves this
    automatically, which is the point -- the number appears in the README and
    in half the test suite, and it has been wrong before.
    """
    board_w, board_h = board_size(*CELL_LADDER[0])
    return (board_w + LEFT_COLUMN + RIGHT_MIN + MAIN_PAD_X,
            board_h + CHROME_ROWS + (DEV_BAR_ROWS if dev_mode else 0))


def board_budget(width: int, height: int, dev_mode: bool = False) -> Tuple[int, int]:
    """(columns, rows) left over for the board at this terminal size."""
    available_w = width - LEFT_COLUMN - RIGHT_MIN - MAIN_PAD_X
    available_h = height - CHROME_ROWS - (DEV_BAR_ROWS if dev_mode else 0)
    return available_w, available_h


def scale_board(screen) -> Tuple[int, int]:
    """Pick a square size for the current terminal and apply it.

    Returns the chosen (cell width, cell height). Safe to call on every resize:
    `BoardView.set_cell` is a no-op when nothing changed, so a drag that does not
    cross a rung costs one comparison rather than a redraw.
    """
    view = screen.query_one("#board", BoardView)
    cell = choose_cell(*board_budget(
        screen.size.width, screen.size.height, config.DEV_MODE
    ))
    view.set_cell(*cell)

    width, height = board_size(*cell)
    view.styles.width = width
    view.styles.height = height
    screen.query_one("#center").styles.width = width

    # The panel column is pinned to the board's height rather than left to
    # fill the screen. Its last panel is elastic, so on a tall terminal it
    # grew past the bottom of the board and the two columns stopped lining
    # up. The board is the tallest thing the layout is built around; nothing
    # beside it should outrun it.
    screen.query_one("#right").styles.height = height
    # `query`, not `query_one`: the post-fight screen shares this layout but
    # has no scoresheet in its panel column. The row count is PUSHED rather
    # than left for the sheet to measure -- the style assignment below does
    # not take effect until Textual's next layout pass, so a sheet that read
    # its own height would be a resize behind.
    for sheet in screen.query("#log"):
        sheet.styles.height = sheet_height(height)
        sheet.rows = sheet_rows(height)
    return cell


def sheet_rows(column_height: int) -> int:
    """How many move rows the scoresheet shows beside a board this tall.

    Derived from the column rather than measured off the live widgets: the
    two panels above it are fixed heights, so this is arithmetic, and
    measuring siblings mid-layout is the mis-measurement this module exists
    to avoid.
    """
    afforded = (column_height
                - (ENEMY_PANEL_ROWS + PANEL_GAP)
                - (PURSE_PANEL_ROWS + PANEL_GAP)
                - SHEET_CHROME)
    fits = [rung for rung in SHEET_ROWS if rung <= afforded]
    # The floor even when it does not fit, for the same reason `choose_cell`
    # returns its floor rung: a cramped panel beats a one-line one, and below
    # the supported terminal size the whole screen is compromised anyway.
    return fits[-1] if fits else SHEET_ROWS[0]


def sheet_height(column_height: int) -> int:
    """Outer height of the scoresheet panel, borders included."""
    return sheet_rows(column_height) + SHEET_CHROME
