"""Dev mode: inert by default, diagnostics when switched on in code."""

import asyncio

import chess
import pytest

from chessvania import config
from chessvania.app import ChessvaniaApp
from chessvania.core.fight import Outcome
from chessvania.core.postfight import Step
from chessvania.ui.screens.fight import FightScreen
from chessvania.ui.screens.gameover import GameOverScreen
from chessvania.ui.screens.postfight import PostFightScreen


class FakeEngine:
    def configure(self, elo):
        pass

    def __call__(self, board):
        return next(iter(board.legal_moves))

    def close(self):
        pass


@pytest.fixture
def dev_mode(monkeypatch):
    monkeypatch.setattr(config, "DEV_MODE", True)
    return True


def drive(scenario):
    asyncio.run(scenario())


async def start_fight(pilot, app):
    await pilot.press("escape")      # skip the boot animation
    await pilot.pause()
    await pilot.press("enter")       # "new game"
    await pilot.pause()
    await pilot.click("#pick-0")
    await pilot.pause()
    return app.screen


# -- off by default -----------------------------------------------------


def test_dev_mode_ships_off():
    assert config.DEV_MODE is False


def test_the_dev_bar_is_hidden_when_off():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            screen = await start_fight(pilot, app)
            assert screen.query_one("#devbar").display is False

    drive(scenario)


def test_dev_keys_do_nothing_when_off():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            screen = await start_fight(pilot, app)
            gold = app.run_state.gold

            for key in ("f2", "f3", "f4", "f5"):
                await pilot.press(key)
                await pilot.pause()

            assert app.run_state.gold == gold
            assert screen.fight.finished is False
            assert isinstance(app.screen, FightScreen)

    drive(scenario)


# -- on ------------------------------------------------------------------


def test_the_dev_bar_appears_when_on(dev_mode):
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            screen = await start_fight(pilot, app)
            assert screen.query_one("#devbar").display is True

    drive(scenario)


def test_f1_expands_the_detail_view(dev_mode):
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            screen = await start_fight(pilot, app)
            bar = screen.query_one("#devbar")
            assert bar.expanded is False

            await pilot.press("f1")
            await pilot.pause()
            assert bar.expanded is True

            await pilot.press("f1")
            await pilot.pause()
            assert bar.expanded is False

    drive(scenario)


def test_f2_grants_gold(dev_mode):
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            await start_fight(pilot, app)
            before = app.run_state.gold

            await pilot.press("f2")
            await pilot.pause()
            assert app.run_state.gold == before + config.DEV_GOLD_STEP

    drive(scenario)


def test_f3_wins_the_fight_instantly(dev_mode):
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            screen = await start_fight(pilot, app)
            await pilot.press("f3")
            await pilot.pause()

            assert screen.fight.outcome is Outcome.PLAYER_WIN
            assert screen.fight.forced is True

    drive(scenario)


def test_f4_loses_the_fight_instantly(dev_mode):
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            screen = await start_fight(pilot, app)
            await pilot.press("f4")
            await pilot.pause(2.0)

            assert screen.fight.outcome is Outcome.PLAYER_LOSS
            assert isinstance(app.screen, GameOverScreen)

    drive(scenario)


def test_f5_removes_the_enemy_piece_under_the_cursor(dev_mode):
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            screen = await start_fight(pilot, app)

            target = next(
                square for square, piece in screen.fight.board.piece_map().items()
                if piece.color == chess.BLACK and piece.piece_type != chess.KING
            )
            screen.cursor = target
            await pilot.press("f5")
            await pilot.pause()

            assert screen.fight.board.piece_at(target) is None

    drive(scenario)


def test_f5_refuses_to_remove_the_enemy_king(dev_mode):
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            screen = await start_fight(pilot, app)
            king = screen.fight.board.king(chess.BLACK)
            screen.cursor = king

            await pilot.press("f5")
            await pilot.pause()
            assert screen.fight.board.piece_at(king) is not None
            assert screen.fight.finished is False

    drive(scenario)


def test_post_fight_dev_keys(dev_mode):
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            screen = await start_fight(pilot, app)
            app.finish_fight(app.run_state, screen.fight, [], won=True)
            await pilot.pause()
            post = app.screen
            assert isinstance(post, PostFightScreen)

            before = app.run_state.gold
            await pilot.press("f2")
            await pilot.pause()
            assert app.run_state.gold == before + config.DEV_GOLD_STEP

            post.phase.swaps_used = config.MAX_SWAPS
            await pilot.press("f5")
            await pilot.pause()
            assert post.phase.swaps_left == config.MAX_SWAPS

            await pilot.press("f3")  # skip the phase entirely
            await pilot.pause()
            assert app.run_state.fight_index == 1
            assert isinstance(app.screen, FightScreen)

    drive(scenario)


def test_dev_mode_leaves_progression_intact(dev_mode):
    """It is a debugger, not a sandbox -- a forced win still advances the run."""

    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            screen = await start_fight(pilot, app)
            assert app.run_state.fight_index == 0

            await pilot.press("f3")
            await pilot.pause(2.0)
            assert isinstance(app.screen, PostFightScreen)
            assert app.screen.phase.step is Step.PAYOUT

            await pilot.press("f3")
            await pilot.pause()
            assert app.run_state.fight_index == 1

    drive(scenario)
