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

STATUS_MAX_ROWS = 9
"""Tallest the status block under the board can get.

Counted off `FightScreen._status_text`, worst case:

    1  a notice, or "<enemy> is thinking..."
    1  the THREAT header
    1  a check line
    3  threat lines           (`fight.THREAT_ROWS`)
    1  "+N more attacked"
    1  an opportunity line
    1  the control hint

Raise THREAT_ROWS, or add another optional line, and this must follow."""

CHROME_ROWS = 3 + STATUS_MAX_ROWS
"""Rows the board never gets: the top bar, the padding above it, the status
block's top margin, and the status block itself at full height.

This reserved only 5 rows until the small squares were dropped. The board was
then 9 rows tall and the slack hid the shortfall; at 25 rows there is none, and
a busy threat readout ran straight off the bottom of the screen."""

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
    return cell
