"""The board scales with the terminal, with 80x24 as the floor."""

import asyncio
import os
import random

import chess

from chessvania import config
from chessvania.app import ChessvaniaApp
from chessvania.core.army import army_from_fen
from chessvania.core.fight import Fight
from chessvania.core.ladder import build_ladder
from chessvania.core.postfight import PostFight
from chessvania.core.run import new_run
from chessvania.data.enemies import POOLS
from chessvania.ui.layout import LEFT_COLUMN, MAIN_PAD_X, RIGHT_MIN, board_budget
from chessvania.ui.screens.fight import FightScreen
from chessvania.ui.screens.postfight import PostFightScreen
from chessvania.ui.widgets.board_view import (
    CELL_LADDER,
    BoardView,
    board_size,
    choose_cell,
)

FLOOR = (80, 24)


class FakeEngine:
    def configure(self, elo):
        pass

    def __call__(self, board):
        return next(iter(board.legal_moves))

    def close(self):
        pass


def drive(scenario):
    asyncio.run(scenario())


def make_run():
    army = army_from_fen("8/8/8/8/8/8/PPPPPPPP/RNBQKBNR w - - 0 1")
    ladder = build_ladder(POOLS, config.STAKES[0], random.Random(0))
    return new_run(army, ladder, config.STAKES[0])


def make_fight(run):
    return Fight(
        army=run.army,
        enemy_fen="rnbqkbnr/pppppppp/8/8/8/8/8/8 b - - 0 1",
        opponent=FakeEngine(),
    )


# -- the ladder itself ---------------------------------------------------


def test_the_ladder_only_grows():
    widths = [w for w, _ in CELL_LADDER]
    heights = [h for _, h in CELL_LADDER]
    assert widths == sorted(widths) and len(set(widths)) == len(widths)
    assert heights == sorted(heights) and len(set(heights)) == len(heights)


def test_every_cell_is_odd_so_a_glyph_centres():
    for cell_w, _ in CELL_LADDER:
        assert cell_w % 2 == 1, "cell width %d has no centre column" % cell_w


def test_every_cell_stays_roughly_square_on_screen():
    """Terminal cells are about twice as tall as wide, so squares need ~2:1."""
    for cell_w, cell_h in CELL_LADDER:
        assert abs(cell_w - 2 * cell_h) <= 1, "cell %dx%d is letterboxed" % (
            cell_w, cell_h)


def test_an_80x24_terminal_gets_the_floor_rung():
    assert choose_cell(*board_budget(*FLOOR)) == CELL_LADDER[0]


def test_the_floor_is_never_undercut():
    """Below 80x24 the board stays drawable rather than collapsing."""
    for size in ((70, 20), (40, 12), (1, 1)):
        assert choose_cell(*board_budget(*size)) == CELL_LADDER[0]


def test_a_bigger_terminal_gets_a_bigger_board():
    small = choose_cell(*board_budget(*FLOOR))
    large = choose_cell(*board_budget(160, 50))
    assert large[0] > small[0] and large[1] > small[1]


def test_each_rung_fits_the_size_it_claims():
    """board_size must match what the widget actually draws, or the CSS lies.

    Runs inside a live app because a Textual widget needs a running loop to
    exist at all -- building one standalone works in isolation and then fails
    the moment another async test has run first.
    """
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=FLOOR) as pilot:
            run = make_run()
            await app.push_screen(FightScreen(run, make_fight(run)))
            await pilot.pause()
            view = app.screen.query_one("#board", BoardView)

            for cell_w, cell_h in CELL_LADDER:
                view.cell_w, view.cell_h = cell_w, cell_h
                lines = view._render_board().plain.rstrip("\n").split("\n")
                rendered = (max(len(line) for line in lines), len(lines))
                assert rendered == board_size(cell_w, cell_h), (
                    "cell %dx%d" % (cell_w, cell_h))

    drive(scenario)


def test_a_chosen_rung_always_fits_its_three_columns():
    for width in range(76, 220, 2):
        for height in range(20, 60, 2):
            cell = choose_cell(*board_budget(width, height))
            board_w, _ = board_size(*cell)
            needed = board_w + LEFT_COLUMN + RIGHT_MIN + MAIN_PAD_X
            if cell != CELL_LADDER[0]:
                assert needed <= width, "%dx%d picked %s" % (width, height, cell)


# -- the mouse follows the squares --------------------------------------


def test_clicking_lands_on_the_right_square_at_every_size():
    """The hit-test has to follow the cell size, or the mouse drifts as it grows."""
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=FLOOR) as pilot:
            run = make_run()
            await app.push_screen(FightScreen(run, make_fight(run)))
            await pilot.pause()
            view = app.screen.query_one("#board", BoardView)

            for cell_w, cell_h in CELL_LADDER:
                view.cell_w, view.cell_h = cell_w, cell_h
                for square in (chess.A8, chess.E4, chess.H1, chess.D5):
                    file = chess.square_file(square)
                    rank = chess.square_rank(square)
                    x = 2 + file * cell_w + cell_w // 2
                    y = 1 + (7 - rank) * cell_h + cell_h // 2
                    assert view._square_at(x, y) == square, (
                        "cell %dx%d square %s" % (
                            cell_w, cell_h, chess.square_name(square)))

    drive(scenario)


# -- live screens --------------------------------------------------------


def _overflow(screen, size):
    worst_w = worst_h = 0
    for widget_id in ("#topbar", "#left", "#center", "#board", "#right"):
        region = screen.query_one(widget_id).region
        worst_w = max(worst_w, region.x + region.width)
        worst_h = max(worst_h, region.y + region.height)
    return worst_w > size[0] or worst_h > size[1], (worst_w, worst_h)


def test_the_fight_board_grows_and_shrinks_with_the_terminal():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=FLOOR) as pilot:
            run = make_run()
            await app.push_screen(FightScreen(run, make_fight(run)))
            await pilot.pause()
            view = app.screen.query_one("#board", BoardView)
            assert (view.cell_w, view.cell_h) == CELL_LADDER[0]

            await pilot.resize_terminal(160, 50)
            await pilot.pause()
            await pilot.pause()
            grown = (view.cell_w, view.cell_h)
            assert grown != CELL_LADDER[0], "board never grew"

            # ...and back down again
            await pilot.resize_terminal(*FLOOR)
            await pilot.pause()
            await pilot.pause()
            assert (view.cell_w, view.cell_h) == CELL_LADDER[0]

    drive(scenario)


def test_nothing_overflows_at_any_terminal_size():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=FLOOR) as pilot:
            run = make_run()
            await app.push_screen(FightScreen(run, make_fight(run)))
            await pilot.pause()
            for size in ((80, 24), (88, 26), (100, 30), (104, 32),
                         (120, 40), (160, 50), (200, 60)):
                await pilot.resize_terminal(*size)
                await pilot.pause()
                await pilot.pause()
                bad, worst = _overflow(app.screen, size)
                assert not bad, "%dx%d overflowed to %s" % (size + (worst,))

    drive(scenario)


def test_the_postfight_board_scales_too():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=FLOOR) as pilot:
            run = make_run()
            phase = PostFight(run, 5, [])
            await app.push_screen(PostFightScreen(run, phase))
            await pilot.pause()
            view = app.screen.query_one("#board", BoardView)
            assert (view.cell_w, view.cell_h) == CELL_LADDER[0]

            await pilot.resize_terminal(160, 50)
            await pilot.pause()
            await pilot.pause()
            assert (view.cell_w, view.cell_h) != CELL_LADDER[0]
            bad, worst = _overflow(app.screen, (160, 50))
            assert not bad, "post-fight overflowed to %s" % (worst,)

    drive(scenario)
