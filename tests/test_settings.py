"""Player settings: the rows, how they persist, and what they must not break."""

import asyncio
import json
import pathlib

import chess

from chessvania.app import ChessvaniaApp
from chessvania.core.progress import Profile, Settings
from chessvania.persistence import load_profile, save_profile
from chessvania.persistence.paths import profile_path
from chessvania.ui import theme
from chessvania.ui.screens.menu import MenuScreen
from chessvania.ui.screens.settings import ROWS, SettingsScreen

from chessvania.ui.layout import minimum_terminal

MIN_TERMINAL = minimum_terminal()


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
    await pilot.press("escape")
    await pilot.pause()
    return app.screen


# -- defaults ------------------------------------------------------------


def test_the_defaults():
    settings = Settings()
    assert settings.audio is True
    assert settings.volume == 70
    assert settings.boot_animation is True


# -- glyphs --------------------------------------------------------------


def test_the_two_sides_stay_distinguishable_without_colour():
    """The board draws sprites, but the bench and shop still use glyphs.

    They are the last place a side is told apart by shape rather than tint, so
    the outlined/solid split has to survive there.
    """
    for piece_type in (chess.PAWN, chess.KNIGHT, chess.BISHOP,
                       chess.ROOK, chess.QUEEN, chess.KING):
        yours = theme.piece_glyph(piece_type, chess.WHITE)
        theirs = theme.piece_glyph(piece_type, chess.BLACK)
        assert yours != theirs, "piece %d looks the same for both sides" % piece_type


def test_core_does_not_decide_how_a_piece_is_drawn():
    """Glyph choice is presentation; `core` returns piece types, not symbols."""
    import chessvania.core.army as army_module
    import chessvania.core.postfight as postfight_module

    for module in (army_module, postfight_module):
        assert "unicode_symbol" not in pathlib.Path(module.__file__).read_text(), (
            "%s is choosing a glyph" % module.__name__)


# -- persistence ---------------------------------------------------------


def test_settings_survive_a_save_and_load():
    profile = Profile()
    profile.settings.audio = False
    profile.settings.volume = 30
    profile.settings.boot_animation = False
    save_profile(profile)

    restored = load_profile()
    assert restored.settings.audio is False
    assert restored.settings.volume == 30
    assert restored.settings.boot_animation is False


def test_a_profile_written_before_settings_existed_still_loads():
    """Old saves have no settings block at all; they get the defaults."""
    profile_path().parent.mkdir(parents=True, exist_ok=True)
    profile_path().write_text(json.dumps({
        "version": 1,
        "defeated": ["Pawn Wall"],
        "earned": ["first_blood"],
        "runs_played": 4,
        "runs_won": 1,
        "highest_stake": 2,
    }))

    restored = load_profile()
    assert restored.settings == Settings()
    assert restored.runs_played == 4  # the rest of the profile is untouched
    assert "first_blood" in restored.earned


def test_an_unusable_settings_block_costs_only_the_settings():
    profile_path().parent.mkdir(parents=True, exist_ok=True)
    profile_path().write_text(json.dumps({
        "version": 1,
        "earned": ["blitz"],
        "runs_played": 9,
        "settings": "not a dict at all",
    }))

    restored = load_profile()
    assert restored.settings == Settings()
    assert restored.runs_played == 9
    assert "blitz" in restored.earned


def test_unknown_settings_keys_are_ignored():
    profile_path().parent.mkdir(parents=True, exist_ok=True)
    profile_path().write_text(json.dumps({
        "version": 1,
        "settings": {"boot_animation": False, "from_a_later_build": 17},
    }))

    restored = load_profile()
    assert restored.settings.boot_animation is False
    assert restored.settings.audio is True


# -- the screen ----------------------------------------------------------


def test_settings_opens_from_the_menu_and_comes_back():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=MIN_TERMINAL) as pilot:
            menu = await settled_menu(pilot, app)
            menu.index = [i.id for i in menu.items].index("settings")
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, SettingsScreen)

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, MenuScreen)

    drive(scenario)


def test_toggling_applies_immediately_and_writes_to_disk():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=MIN_TERMINAL) as pilot:
            menu = await settled_menu(pilot, app)
            menu.index = [i.id for i in menu.items].index("settings")
            await pilot.press("enter")
            await pilot.pause()

            screen = app.screen
            screen.index = [r.id for r in ROWS].index("audio")
            await pilot.press("enter")
            await pilot.pause()

            assert app.profile.settings.audio is False
            assert app.audio.enabled is False, "the change did not reach the player"
            assert load_profile().settings.audio is False, "not written to disk"

    drive(scenario)


def test_volume_steps_and_clamps():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=MIN_TERMINAL) as pilot:
            menu = await settled_menu(pilot, app)
            menu.index = [i.id for i in menu.items].index("settings")
            await pilot.press("enter")
            await pilot.pause()

            screen = app.screen
            screen.index = [r.id for r in ROWS].index("volume")
            start = app.profile.settings.volume

            await pilot.press("right")
            await pilot.pause()
            assert app.profile.settings.volume > start
            assert app.audio.volume == app.profile.settings.volume

            for _ in range(20):            # walk it off the top
                await pilot.press("right")
            await pilot.pause()
            assert app.profile.settings.volume == 100

            for _ in range(20):            # and off the bottom
                await pilot.press("left")
            await pilot.pause()
            assert app.profile.settings.volume == 0

    drive(scenario)


def test_turning_the_animation_off_skips_it_next_launch():
    async def scenario():
        profile = Profile()
        profile.settings.boot_animation = False
        save_profile(profile)

        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=MIN_TERMINAL) as pilot:
            await pilot.pause()
            menu = app.screen
            assert isinstance(menu, MenuScreen)
            assert menu.animating is False
            # straight to a finished menu, no keypress needed
            assert menu._visible_counts()[2] == len(menu.items)

    drive(scenario)


def test_the_animation_still_plays_when_it_is_left_on():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=MIN_TERMINAL) as pilot:
            assert app.screen.animating is True

    drive(scenario)


def test_the_saved_preference_is_applied_at_startup():
    async def scenario():
        profile = Profile()
        profile.settings.audio = False
        profile.settings.volume = 20
        save_profile(profile)

        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=MIN_TERMINAL) as pilot:
            await pilot.pause()
            assert app.audio.enabled is False
            assert app.audio.volume == 20

    drive(scenario)


def test_the_settings_screen_fits_the_minimum_terminal():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=(104, 36)) as pilot:
            menu = await settled_menu(pilot, app)
            menu.index = [i.id for i in menu.items].index("settings")
            await pilot.press("enter")
            await pilot.pause()

            screen = app.screen
            for widget_id in ("#page-heading", "#page-body", "#page-foot"):
                widget = screen.query_one(widget_id)
                region = widget.region
                assert region.right <= 104, "%s overflows width" % widget_id
                assert region.bottom <= 36, "%s pushed off the bottom" % widget_id

    drive(scenario)
