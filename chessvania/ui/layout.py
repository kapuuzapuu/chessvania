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
from .widgets.board_view import BoardView, board_size, choose_cell

LEFT_COLUMN = 17
"""Width of the bench column (`#left`)."""

RIGHT_MIN = 25
"""Smallest the panel column (`#right`) may be squeezed to (`min-width`)."""

MAIN_PAD_X = 2
"""`#main` pads one column on each side, outside all three columns."""

CHROME_ROWS = 5
"""Rows the board never gets: the top bar, the padding above it, and the status
block beneath it with its margin."""

DEV_BAR_ROWS = 2
"""The docked diagnostics strip, when `DEV_MODE` is on."""


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
