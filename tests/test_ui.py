"""Integration smoke tests: boot the real Textual app and drive it.

The engine is stubbed so these run without a Stockfish binary.
"""

import asyncio

import chess

from chessvania import config
from chessvania.app import ChessvaniaApp
from chessvania.core.postfight import Step
from chessvania.core.threat import Danger
from chessvania.ui.screens.fight import STATUS_WIDTH, FightScreen, Zone
from chessvania.ui.widgets.board_view import BoardView
from chessvania.ui.screens.loadout import LoadoutScreen
from chessvania.ui.screens.postfight import PostFightScreen
from chessvania.ui.screens.postfight import Zone as PostZone
from chessvania.ui.screens.menu import MenuScreen


class FakeEngine:
    """Plays the first legal move, instantly."""

    def __init__(self):
        self.configured = []

    def configure(self, elo):
        self.configured.append(elo)

    def __call__(self, board):
        return next(iter(board.legal_moves))

    def close(self):
        pass


def drive(scenario):
    """Run an async pilot scenario from a sync test."""
    asyncio.run(scenario())


def test_app_boots_to_the_menu():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            assert isinstance(app.screen, MenuScreen)
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, LoadoutScreen)

    drive(scenario)


def test_starting_a_run_reaches_the_fight_screen():
    async def scenario():
        engine = FakeEngine()
        app = ChessvaniaApp(engine=engine, seed=1)
        async with app.run_test() as pilot:
            await start_fight(pilot, app)

            assert isinstance(app.screen, FightScreen)
            run = app.run_state
            assert run is not None
            assert run.ante == 1 and run.fight_in_ante == 1
            assert len(run.ladder) == config.ANTES * config.FIGHTS_PER_ANTE
            # the engine was configured for this fight's Elo before play began
            assert engine.configured == [run.ladder[0].elo]

    drive(scenario)


async def start_fight(pilot, app):
    await pilot.press("escape")      # skip the boot animation
    await pilot.pause()
    await pilot.press("enter")       # "new game"
    await pilot.pause()
    await pilot.click("#pick-0")
    await pilot.pause()
    return app.screen


async def settle(pilot, screen):
    """Wait for the (stubbed) engine worker to land."""
    for _ in range(20):
        if not screen.thinking:
            return
        await pilot.pause(0.02)


async def move_cursor_to(pilot, screen, square):
    """Walk the cursor with arrow keys only -- no direct assignment."""
    for _ in range(16):
        if screen.cursor == square:
            return
        cf, cr = chess.square_file(screen.cursor), chess.square_rank(screen.cursor)
        tf, tr = chess.square_file(square), chess.square_rank(square)
        if cf != tf:
            await pilot.press("right" if tf > cf else "left")
        elif cr != tr:
            await pilot.press("up" if tr > cr else "down")
        await pilot.pause()
    raise AssertionError("cursor never reached %s" % chess.square_name(square))


def test_arrow_keys_move_the_cursor():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            screen = await start_fight(pilot, app)
            start = screen.cursor

            await pilot.press("up")
            await pilot.pause()
            assert chess.square_rank(screen.cursor) == chess.square_rank(start) + 1

            await pilot.press("left")
            await pilot.pause()
            assert chess.square_file(screen.cursor) == chess.square_file(start) - 1

    drive(scenario)


def test_the_cursor_stops_at_the_board_edge():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            screen = await start_fight(pilot, app)
            for _ in range(12):
                await pilot.press("down")
            await pilot.pause()
            assert chess.square_rank(screen.cursor) == 0

    drive(scenario)


def test_selecting_then_moving_plays_the_move():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            screen = await start_fight(pilot, app)
            assert screen.fight.player_moves == 0

            await move_cursor_to(pilot, screen, chess.E2)
            await pilot.press("enter")
            await pilot.pause()
            assert screen.selected == chess.E2

            await move_cursor_to(pilot, screen, chess.E4)
            await pilot.press("enter")
            await pilot.pause()
            await settle(pilot, screen)

            assert screen.fight.player_moves == 1
            assert screen.fight.board.piece_at(chess.E4) is not None
            assert screen.selected is None

    drive(scenario)


def test_escape_clears_a_selection():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            screen = await start_fight(pilot, app)
            await move_cursor_to(pilot, screen, chess.E2)
            await pilot.press("enter")
            await pilot.pause()
            assert screen.selected == chess.E2

            await pilot.press("escape")
            await pilot.pause()
            assert screen.selected is None
            assert screen.fight.player_moves == 0

    drive(scenario)


def test_selecting_an_empty_square_does_nothing():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            screen = await start_fight(pilot, app)
            await move_cursor_to(pilot, screen, chess.E5)
            await pilot.press("enter")
            await pilot.pause()
            assert screen.selected is None
            assert screen.fight.player_moves == 0

    drive(scenario)


def test_tab_switches_between_board_and_bench():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            screen = await start_fight(pilot, app)
            assert screen.zone is Zone.BOARD

            await pilot.press("tab")
            await pilot.pause()
            assert screen.zone is Zone.BENCH

            # arrows now drive the bench, not the board
            before = screen.cursor
            await pilot.press("right")
            await pilot.pause()
            assert screen.cursor == before
            assert screen.bench_cursor == 1

            await pilot.press("tab")
            await pilot.pause()
            assert screen.zone is Zone.BOARD

    drive(scenario)


async def promotion_ready_screen(pilot, app):
    """Swap in a fight where a pawn is one push from the last rank."""
    from chessvania.core.army import army_from_fen
    from chessvania.core.fight import Fight

    await start_fight(pilot, app)
    run = app.run_state
    run.army = army_from_fen("8/6P1/8/8/8/8/8/4K3 w - - 0 1")
    fight = Fight(
        army=run.army,
        enemy_fen="k7/8/8/8/8/8/8/8 w - - 0 1",
        opponent=FakeEngine(),
    )
    app.switch_screen(FightScreen(run, fight))
    await pilot.pause()
    return app.screen


async def open_the_promotion_picker(pilot, screen):
    await move_cursor_to(pilot, screen, chess.G7)
    await pilot.press("enter")
    await pilot.pause()
    await move_cursor_to(pilot, screen, chess.G8)
    await pilot.press("enter")
    await pilot.pause()


def test_promotion_opens_a_picker_instead_of_auto_queening():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            screen = await promotion_ready_screen(pilot, app)
            await open_the_promotion_picker(pilot, screen)

            assert len(screen.promotion_moves) == 4
            assert [m.promotion for m in screen.promotion_moves] == [
                chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT
            ]
            assert screen.fight.player_moves == 0  # nothing committed yet

    drive(scenario)


def test_the_picker_can_under_promote_by_letter():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            screen = await promotion_ready_screen(pilot, app)
            await open_the_promotion_picker(pilot, screen)

            await pilot.press("n")
            await pilot.pause()
            await settle(pilot, screen)

            assert screen.promotion_moves == []
            assert screen.fight.board.piece_at(chess.G8).piece_type == chess.KNIGHT

    drive(scenario)


def test_the_picker_can_under_promote_with_arrows():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            screen = await promotion_ready_screen(pilot, app)
            await open_the_promotion_picker(pilot, screen)

            await pilot.press("right")  # queen -> rook
            await pilot.pause()
            assert screen.promotion_index == 1

            await pilot.press("enter")
            await pilot.pause()
            await settle(pilot, screen)
            assert screen.fight.board.piece_at(chess.G8).piece_type == chess.ROOK

    drive(scenario)


def test_escape_cancels_a_promotion():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            screen = await promotion_ready_screen(pilot, app)
            await open_the_promotion_picker(pilot, screen)

            await pilot.press("escape")
            await pilot.pause()
            assert screen.promotion_moves == []
            assert screen.fight.player_moves == 0
            assert screen.fight.board.piece_at(chess.G7) is not None

    drive(scenario)


async def threat_screen(pilot, app, player_fen, enemy_fen):
    """Drop a crafted position onto a live fight screen."""
    from chessvania.core.army import army_from_fen
    from chessvania.core.fight import Fight

    await start_fight(pilot, app)
    run = app.run_state
    run.army = army_from_fen(player_fen)
    fight = Fight(army=run.army, enemy_fen=enemy_fen, opponent=FakeEngine(),
                  enemy_name="Bulwark")
    app.switch_screen(FightScreen(run, fight))
    await pilot.pause()
    return app.screen


# a1 rook hangs to the bishop on f6, and nothing else is touched
HANGING = ("8/8/8/8/8/8/4PPPP/R3K3 w - - 0 1", "4k3/8/5b2/8/8/8/8/8 w - - 0 1")
# in check from b1, three pieces hanging, and the checker is itself free
CROWDED = ("8/8/8/8/8/8/1PPPPPP1/R3K2R w - - 0 1",
           "4k2r/8/1b1b1b2/8/8/8/8/1r6 w - - 0 1")


def test_the_status_panel_reads_out_threats():
    """It used to hold keyboard hints, which say nothing about what is at stake."""

    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            screen = await threat_screen(pilot, app, *HANGING)
            panel = screen._status_text().plain

            assert "THREAT" in panel
            assert "5 at risk" in panel          # the whole rook, for good
            assert "♖a1" in panel and "♝f6" in panel

    drive(scenario)


def test_a_hanging_piece_is_marked_on_the_board():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            screen = await threat_screen(pilot, app, *HANGING)
            board = screen.query_one("#board", BoardView)

            assert board.threats[chess.A1].level is Danger.HANGING
            # the marker rides in the cell's trailing column
            assert "♖!" in board._render_board().plain

    drive(scenario)


def test_check_is_called_out_with_a_way_out_count():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            screen = await threat_screen(pilot, app, *CROWDED)
            panel = screen._status_text().plain

            assert "IN CHECK" in panel
            assert "♜b1 checks" in panel
            assert "out" in panel
            assert screen.query_one("#board", BoardView).threats[chess.E1].level is Danger.CHECK

    drive(scenario)


def test_the_inspect_panel_explains_the_square_under_the_cursor():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            screen = await threat_screen(pilot, app, *CROWDED)

            await move_cursor_to(pilot, screen, chess.A1)
            assert "takes it for free" in screen.query_one("#inspect").render().plain

            await move_cursor_to(pilot, screen, chess.B1)  # the enemy rook
            assert "takes it free" in screen.query_one("#inspect").render().plain

            await move_cursor_to(pilot, screen, chess.D4)  # an empty square
            assert "covered by" in screen.query_one("#inspect").render().plain

    drive(scenario)


def test_the_threat_panel_never_wraps_or_falls_off_the_fold():
    """Every row is built to 27 columns for a 28-column centre panel.

    A wrapped row silently doubles the panel's height, and the board is directly
    above it -- so a wrap here is how the board goes off an 80x24 terminal.
    """

    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=(80, 24)) as pilot:
            screen = await threat_screen(pilot, app, *CROWDED)

            for line in screen._threat_panel().plain.split("\n"):
                assert len(line) <= STATUS_WIDTH, "too wide for the column: %r" % line
            assert len(screen._hint_line().plain) <= STATUS_WIDTH

            status = screen.query_one("#status")
            assert status.region.y + status.region.height <= screen.size.height

    drive(scenario)


def test_the_threat_panel_survives_a_notice_and_the_dev_bar():
    """The busiest this panel gets: a casualty notice, a full threat list and
    the diagnostics strip all competing for the same 24 rows."""

    async def scenario():
        config.DEV_MODE = True
        try:
            app = ChessvaniaApp(engine=FakeEngine(), seed=1)
            async with app.run_test(size=(80, 24)) as pilot:
                screen = await threat_screen(pilot, app, *CROWDED)
                await pilot.press("f1")  # expand the dev bar
                screen.set_status("Bulwark takes your rook — gone for good")
                await pilot.pause()

                status = screen.query_one("#status")
                assert status.region.y + status.region.height <= screen.size.height
                assert screen.query_one("#board").region.height == 9
        finally:
            config.DEV_MODE = False

    drive(scenario)


def test_post_fight_runs_on_the_keyboard():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            screen = await start_fight(pilot, app)
            app.finish_fight(app.run_state, screen.fight, [], won=True)
            await pilot.pause()

            post = app.screen
            phase = post.phase
            assert post.zone is PostZone.CONTROLS

            await pilot.press("enter")  # collect
            await pilot.pause()
            assert phase.step is Step.SHOP

            app.run_state.gold = 20
            post.refresh_all()
            await pilot.pause()

            await pilot.press("enter")  # buy whatever is first
            await pilot.pause()
            assert app.run_state.army.inventory_count == 1

            await pilot.press("down")  # walk to a later control
            await pilot.pause()
            assert post.control_index == 1

    drive(scenario)


def test_swap_step_exposes_board_and_bench_to_the_keyboard():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            screen = await start_fight(pilot, app)
            app.finish_fight(app.run_state, screen.fight, [], won=True)
            await pilot.pause()

            post = app.screen
            post.phase.collect_payout()
            post.phase.close_shop()
            post.phase.close_sell()
            post.refresh_all()
            await pilot.pause()
            assert post.phase.step is Step.SWAP

            await pilot.press("tab")
            await pilot.pause()
            assert post.zone is PostZone.BOARD

            before = post.board_cursor
            await pilot.press("up")
            await pilot.pause()
            assert post.board_cursor != before

            await pilot.press("tab")
            await pilot.pause()
            assert post.zone is PostZone.BENCH

    drive(scenario)


def test_there_is_no_text_input_left():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            screen = await start_fight(pilot, app)
            assert not screen.query("Input")

    drive(scenario)


def test_winning_routes_into_the_post_fight_rail():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            await start_fight(pilot, app)

            fight_screen = app.screen
            app.finish_fight(app.run_state, fight_screen.fight, [], won=True)
            await pilot.pause()

            assert isinstance(app.screen, PostFightScreen)
            phase = app.screen.phase
            assert phase.step is Step.PAYOUT

            # payout -> shop -> sell -> swap -> next fight
            await pilot.click("#finish")
            await pilot.pause()
            assert phase.step is Step.SHOP
            assert app.run_state.gold > 0

            await pilot.click("#close-shop")
            await pilot.pause()
            assert phase.step is Step.SELL

            await pilot.click("#close-sell")
            await pilot.pause()
            assert phase.step is Step.SWAP
            assert phase.swaps_left == config.MAX_SWAPS

            await pilot.click("#finish")
            await pilot.pause()
            assert isinstance(app.screen, FightScreen)
            assert app.run_state.fight_index == 1

    drive(scenario)


def test_buying_in_the_ui_benches_the_piece():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            await start_fight(pilot, app)

            app.finish_fight(app.run_state, app.screen.fight, [], won=True)
            await pilot.pause()
            await pilot.click("#finish")
            await pilot.pause()

            app.run_state.gold = 20
            app.screen.refresh_all()
            await pilot.pause()

            board_before = dict(app.run_state.army.deployment)
            await pilot.click("#buy-0")
            await pilot.pause()

            assert app.run_state.army.inventory_count == 1
            assert app.run_state.army.deployment == board_before

    drive(scenario)


def test_the_whole_ui_fits_an_80x24_terminal():
    """The mockup targets 80x24; every control must stay clickable there."""

    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=(80, 24)) as pilot:
            await start_fight(pilot, app)

            def assert_all_visible(where):
                region = app.screen.size.region
                for widget in app.screen.query("Button"):
                    if not widget.display:
                        continue
                    box = widget.region
                    assert box.x + box.width <= region.width, (
                        "%s: %s overflows the right edge" % (where, widget.id)
                    )
                    assert box.y + box.height <= region.height, (
                        "%s: %s falls below the fold" % (where, widget.id)
                    )

            app.finish_fight(app.run_state, app.screen.fight, [], won=True)
            await pilot.pause()
            assert_all_visible("payout")

            await pilot.click("#finish")
            await pilot.pause()
            assert_all_visible("shop")

            await pilot.click("#close-shop")
            await pilot.pause()
            assert_all_visible("sell")

            await pilot.click("#close-sell")
            await pilot.pause()
            assert_all_visible("swap")

    drive(scenario)


def test_losing_routes_to_defeat():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test() as pilot:
            await start_fight(pilot, app)

            app.finish_fight(app.run_state, app.screen.fight, [], won=False)
            await pilot.pause()

            from chessvania.ui.screens.gameover import GameOverScreen

            assert isinstance(app.screen, GameOverScreen)
            assert app.screen.won is False

    drive(scenario)
