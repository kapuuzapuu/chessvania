"""The main menu, the boot animation, and the pages behind them."""

import asyncio

import chess

from chessvania import config
from chessvania.app import ChessvaniaApp
from chessvania.core.progress import Profile
from chessvania.persistence import has_saved_run, load_profile, save_profile
from chessvania.ui.screens.achievements import AchievementsScreen
from chessvania.ui.screens.bestiary import BestiaryScreen
from chessvania.ui.screens.fight import FightScreen
from chessvania.ui.screens.loadout import LoadoutScreen
from chessvania.ui.screens.menu import MenuScreen


class FakeEngine:
    def configure(self, elo):
        pass

    def __call__(self, board):
        return next(iter(board.legal_moves))

    def close(self):
        pass


def drive(scenario):
    asyncio.run(scenario())


async def settled_menu(pilot, app):
    """Skip the boot animation and hand back the menu."""
    await pilot.press("escape")
    await pilot.pause()
    return app.screen


# -- the boot animation --------------------------------------------------


def test_the_menu_animates_in_then_settles():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            menu = app.screen
            assert menu.animating is True
            assert menu._visible_counts() == (0, 0, 0)

            await pilot.pause(0.3)
            partial = menu._visible_counts()
            assert sum(partial) > 0, "animation never advanced"

            await pilot.pause(1.6)
            assert menu.animating is False
            banner, march, items = menu._visible_counts()
            assert items == len(menu.items)

    drive(scenario)


def test_any_key_skips_the_animation():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            menu = app.screen
            assert menu.animating is True

            await pilot.press("escape")
            await pilot.pause()
            assert menu.animating is False
            assert menu._visible_counts()[2] == len(menu.items)

    drive(scenario)


def test_the_first_keypress_only_skips_and_does_not_select():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, MenuScreen), "enter should not start a run"

            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, LoadoutScreen)

    drive(scenario)


# -- navigation ----------------------------------------------------------


def test_the_menu_lists_every_entry():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            menu = await settled_menu(pilot, app)
            assert [i.id for i in menu.items] == [
                "new", "load", "bestiary", "achievements", "settings", "quit"
            ]

    drive(scenario)


def test_load_is_disabled_without_a_saved_run():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            menu = await settled_menu(pilot, app)
            load = next(i for i in menu.items if i.id == "load")
            assert load.enabled is False
            assert "no run" in load.hint

    drive(scenario)


def test_the_cursor_skips_disabled_entries():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            menu = await settled_menu(pilot, app)
            assert menu.index == 0  # new game

            await pilot.press("down")
            await pilot.pause()
            # "load game" is disabled, so it should be stepped over
            assert menu.items[menu.index].id == "bestiary"

    drive(scenario)


def test_bestiary_and_achievements_open_and_come_back():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            menu = await settled_menu(pilot, app)

            menu.index = [i.id for i in menu.items].index("bestiary")
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, BestiaryScreen)

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, MenuScreen)

            app.screen.index = [i.id for i in app.screen.items].index("achievements")
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, AchievementsScreen)

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, MenuScreen)

    drive(scenario)


# -- save / resume -------------------------------------------------------


async def play_one_fight(pilot, app):
    await settled_menu(pilot, app)
    await pilot.press("enter")
    await pilot.pause()
    await pilot.click("#pick-0")
    await pilot.pause()
    screen = app.screen
    app.finish_fight(app.run_state, screen.fight, [], won=True)
    await pilot.pause()
    post = app.screen
    post.phase.collect_payout()
    post.phase.close_shop()
    post.phase.close_sell()
    post.phase.finish()
    app.finish_postfight(app.run_state)
    await pilot.pause()


def test_starting_a_run_writes_a_save():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            await settled_menu(pilot, app)
            await pilot.press("enter")
            await pilot.pause()
            await pilot.click("#pick-0")
            await pilot.pause()
            assert has_saved_run()

    drive(scenario)


def test_a_saved_run_can_be_resumed_next_launch():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            await play_one_fight(pilot, app)
            assert app.run_state.fight_index == 1

        resumed = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with resumed.run_test() as pilot:
            menu = await settled_menu(pilot, resumed)
            load = next(i for i in menu.items if i.id == "load")
            assert load.enabled is True

            menu.index = [i.id for i in menu.items].index("load")
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(resumed.screen, FightScreen)
            assert resumed.run_state.fight_index == 1

    drive(scenario)


def test_winning_records_the_enemy_and_an_achievement():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            await play_one_fight(pilot, app)
            assert app.profile.defeated, "no enemy recorded"
            assert app.profile.has("first_blood")

        assert load_profile().has("first_blood"), "profile was not persisted"

    drive(scenario)


def test_losing_clears_the_saved_run():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            await settled_menu(pilot, app)
            await pilot.press("enter")
            await pilot.pause()
            await pilot.click("#pick-0")
            await pilot.pause()
            assert has_saved_run()

            app.finish_fight(app.run_state, app.screen.fight, [], won=False)
            await pilot.pause()
            assert not has_saved_run(), "one life -- nothing should be resumable"

    drive(scenario)


# -- unlocks -------------------------------------------------------------


def test_locked_loadouts_are_absent_until_earned():
    async def scenario():
        from chessvania.data.loadouts import LOADOUTS

        locked = [lo for lo in LOADOUTS if lo.unlocked_by]
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            await settled_menu(pilot, app)
            await pilot.press("enter")
            await pilot.pause()
            names = [lo.name for lo in app.screen.available]
            for loadout in locked:
                assert loadout.name not in names

        save_profile(Profile(earned={lo.unlocked_by for lo in locked}))

        unlocked_app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with unlocked_app.run_test() as pilot:
            await settled_menu(pilot, unlocked_app)
            await pilot.press("enter")
            await pilot.pause()
            names = [lo.name for lo in unlocked_app.screen.available]
            for loadout in locked:
                assert loadout.name in names

    drive(scenario)
