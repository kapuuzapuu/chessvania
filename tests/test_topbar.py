"""The top bar degrades in tiers instead of only sacrificing the enemy's name."""

import asyncio
import random

from rich.cells import cell_len

from chessvania import config
from chessvania.app import ChessvaniaApp
from chessvania.core.army import army_from_fen
from chessvania.core.fight import Fight
from chessvania.core.ladder import build_ladder
from chessvania.core.run import new_run
from chessvania.data.enemies import POOLS
from chessvania.ui.screens.fight import FightScreen
from chessvania.ui.widgets.topbar import COUNTER_TIERS, TopBar

LONG_NAME = "Iron Phalanx"
LONG_TIER = "mini-boss"
SUBTITLE = "%s · %s" % (LONG_NAME, LONG_TIER)


class FakeEngine:
    def configure(self, elo):
        pass

    def __call__(self, board):
        return next(iter(board.legal_moves))

    def close(self):
        pass


def drive(scenario):
    asyncio.run(scenario())


async def bar_at(pilot, app, width, height=30):
    await pilot.resize_terminal(width, height)
    await pilot.pause()
    await pilot.pause()
    return app.screen.query_one("#topbar", TopBar)


async def open_fight(app, pilot, gold=12):
    army = army_from_fen("8/8/8/8/8/8/PPPPPPPP/RNBQKBNR w - - 0 1")
    ladder = build_ladder(POOLS, config.STAKES[0], random.Random(0))
    run = new_run(army, ladder, config.STAKES[0])
    run.gold = gold
    fight = Fight(
        army=army,
        enemy_fen="rnbqkbnr/pppppppp/8/8/8/8/8/8 b - - 0 1",
        opponent=FakeEngine(),
        enemy_name=LONG_NAME,
        tier=LONG_TIER,
    )
    await app.push_screen(FightScreen(run, fight))
    await pilot.pause()


# -- the tier list -------------------------------------------------------


def test_the_tiers_only_get_terser():
    """Roomiest first: gutters never widen and labels never grow back."""
    previous = None
    for short, gutter in COUNTER_TIERS:
        if previous is not None:
            was_short, was_gutter = previous
            assert (short, -gutter) >= (was_short, -was_gutter)
        previous = (short, gutter)


# -- the regression this was built for -----------------------------------


def test_the_enemy_name_survives_at_the_minimum_terminal_size():
    """80x24 is the supported floor; the name used to be cut off there."""
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=(80, 24)) as pilot:
            await open_fight(app, pilot)
            bar = await bar_at(pilot, app, 80, 24)
            assert SUBTITLE in bar.render().plain
            assert "…" not in bar.render().plain

    drive(scenario)


def test_the_counters_are_never_truncated():
    """Half of "GOLD" tells you less than nothing, so they get terser instead."""
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=(120, 40)) as pilot:
            await open_fight(app, pilot, gold=12)
            for width in range(58, 162, 4):
                bar = await bar_at(pilot, app, width)
                plain = bar.render().plain
                # the gold value is the last thing on the line, so if the block
                # were being clipped this is what would vanish first
                assert plain.rstrip().endswith("12"), (
                    "%d cols lost the gold value: %r" % (width, plain))

    drive(scenario)


def test_the_bar_never_overflows_its_width():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=(120, 40)) as pilot:
            await open_fight(app, pilot)
            for width in range(58, 162, 2):
                bar = await bar_at(pilot, app, width)
                drawn = cell_len(bar.render().plain)
                assert drawn <= bar.content_size.width, (
                    "%d cols: drew %d into %d" % (
                        width, drawn, bar.content_size.width))

    drive(scenario)


def test_a_wide_terminal_keeps_the_readable_labels():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=(120, 40)) as pilot:
            await open_fight(app, pilot)
            bar = await bar_at(pilot, app, 140)
            plain = bar.render().plain
            for word in ("RUN", "ANTE", "FIGHT", "ELO", "GOLD"):
                assert word in plain

    drive(scenario)


def test_a_narrow_terminal_packs_the_counters_down():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=(120, 40)) as pilot:
            await open_fight(app, pilot)
            bar = await bar_at(pilot, app, 80)
            plain = bar.render().plain
            assert "FIGHT" not in plain and "GOLD" not in plain
            assert "F1/3" in plain

    drive(scenario)


def test_the_name_still_yields_when_nothing_else_can_give():
    """Below every tier the name is what goes -- the counters stay whole."""
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=(120, 40)) as pilot:
            await open_fight(app, pilot)
            bar = await bar_at(pilot, app, 58)
            plain = bar.render().plain
            assert "…" in plain, "the name should have been trimmed"
            assert plain.rstrip().endswith("12"), "the counters were cut instead"

    drive(scenario)
