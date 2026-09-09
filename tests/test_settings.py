"""Player settings: the two toggles, how they persist, and what they must not break."""

import asyncio
import json

import chess

from chessvania.app import ChessvaniaApp
from chessvania.core.progress import Profile, Settings
from chessvania.persistence import load_profile, save_profile
from chessvania.persistence.paths import profile_path
from chessvania.ui import theme
from chessvania.ui.screens.menu import MenuScreen
from chessvania.ui.screens.settings import TOGGLES, SettingsScreen


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


def test_the_defaults_are_the_printed_diagram_convention():
    settings = Settings()
    assert settings.filled_player_pieces is False
    assert settings.boot_animation is True


# -- glyphs --------------------------------------------------------------


def test_filling_your_pieces_swaps_both_sides_rather_than_one():
    """The two armies must never end up sharing a fill."""
    theme.set_piece_fill(False)
    assert theme.piece_glyph(chess.QUEEN, chess.WHITE) == "♕"  # outlined
    assert theme.piece_glyph(chess.QUEEN, chess.BLACK) == "♛"  # solid

    theme.set_piece_fill(True)
    assert theme.piece_glyph(chess.QUEEN, chess.WHITE) == "♛"
    assert theme.piece_glyph(chess.QUEEN, chess.BLACK) == "♕"


def test_the_sides_stay_distinguishable_without_colour_either_way():
    """The accessibility promise in theme.py's docstring, enforced.

    Colour is allowed to reinforce which army a piece belongs to; it is never
    allowed to be the only thing carrying it.
    """
    for filled in (False, True):
        theme.set_piece_fill(filled)
        for piece_type in chess.PIECE_TYPES:
            mine = theme.piece_glyph(piece_type, chess.WHITE)
            theirs = theme.piece_glyph(piece_type, chess.BLACK)
            assert mine != theirs, "fill=%s type=%s" % (filled, piece_type)


def test_core_does_not_decide_how_a_piece_is_drawn():
    """Glyph choice is a preference, so it belongs to the UI layer alone."""
    from chessvania.core.army import Piece
    from chessvania.core.postfight import StockItem

    assert not hasattr(Piece(chess.ROOK), "symbol")
    assert not hasattr(StockItem(piece_type=chess.ROOK, price=5), "symbol")


def test_the_receipt_groups_by_piece_type_not_by_glyph():
    """Core hands the UI data; the UI decides what it looks like."""
    import random

    from chessvania.core.army import army_from_fen
    from chessvania.core.ladder import build_ladder
    from chessvania.core.postfight import PostFight
    from chessvania.core.run import new_run
    from chessvania.data.enemies import POOLS
    from chessvania import config

    army = army_from_fen("8/8/8/8/8/8/PPPPPPPP/RN2KN1R w - - 0 1")
    ladder = build_ladder(POOLS, config.STAKES[0], random.Random(0))
    run = new_run(army, ladder, config.STAKES[0])
    run.gold = 99

    phase = PostFight(run, 5, [])
    phase.collect_payout()
    pawn = next(i for i, item in enumerate(phase.stock)
                if item.piece_type == chess.PAWN)
    for _ in range(3):
        phase.buy(pawn)

    counts = phase.purchase_counts()
    assert list(counts) == [chess.PAWN], "keys should be piece types, not glyphs"
    assert list(counts.values()) == [3]


# -- persistence ---------------------------------------------------------


def test_settings_survive_a_save_and_load():
    profile = Profile()
    profile.settings.filled_player_pieces = True
    profile.settings.boot_animation = False
    save_profile(profile)

    restored = load_profile()
    assert restored.settings.filled_player_pieces is True
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
    assert restored.settings.filled_player_pieces is False


# -- the screen ----------------------------------------------------------


def test_settings_opens_from_the_menu_and_comes_back():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
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
        async with app.run_test() as pilot:
            menu = await settled_menu(pilot, app)
            menu.index = [i.id for i in menu.items].index("settings")
            await pilot.press("enter")
            await pilot.pause()

            screen = app.screen
            screen.index = [t.id for t in TOGGLES].index("pieces")
            await pilot.press("enter")
            await pilot.pause()

            # applied to the live presentation layer...
            assert app.profile.settings.filled_player_pieces is True
            assert theme.player_filled() is True
            # ...and persisted without a confirm step
            assert load_profile().settings.filled_player_pieces is True

    drive(scenario)


def test_turning_the_animation_off_skips_it_next_launch():
    async def scenario():
        profile = Profile()
        profile.settings.boot_animation = False
        save_profile(profile)

        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
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
        async with app.run_test() as pilot:
            assert app.screen.animating is True

    drive(scenario)


def test_the_saved_preference_is_applied_at_startup():
    async def scenario():
        profile = Profile()
        profile.settings.filled_player_pieces = True
        save_profile(profile)

        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert theme.player_filled() is True

    drive(scenario)


def test_the_settings_screen_fits_an_80x24_terminal():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=(80, 24)) as pilot:
            menu = await settled_menu(pilot, app)
            menu.index = [i.id for i in menu.items].index("settings")
            await pilot.press("enter")
            await pilot.pause()

            screen = app.screen
            for widget_id in ("#page-heading", "#page-body", "#page-foot"):
                widget = screen.query_one(widget_id)
                region = widget.region
                assert region.right <= 80, "%s overflows width" % widget_id
                assert region.bottom <= 24, "%s pushed off the bottom" % widget_id

    drive(scenario)
