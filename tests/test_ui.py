"""Integration smoke tests: boot the real Textual app and drive it.

The engine is stubbed so these run without a Stockfish binary.
"""

import asyncio

import chess

from textual.widgets import Button, Static

from chessvania import config
from chessvania.app import ChessvaniaApp
from chessvania.core.postfight import Step
from chessvania.ui import theme
from chessvania.ui.screens.fight import FightScreen, Zone
from chessvania.ui.widgets.board_view import CELL_LADDER, BoardView, board_size
from chessvania.ui.screens.loadout import LoadoutScreen
from chessvania.ui.screens.postfight import PostFightScreen
from chessvania.ui.screens.postfight import Zone as PostZone
from chessvania.ui.screens.menu import MenuScreen

from chessvania.ui.layout import minimum_terminal

MIN_TERMINAL = minimum_terminal()


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


async def settle_layout(pilot, selector, tries=60, steady=3):
    """Pause until a widget has held the same position for `steady` frames.

    `pilot.click(selector)` resolves the widget's region at click time, so
    clicking into a column that is still reflowing aims at the old position.
    One repeat is not enough to call it settled: a panel with `height: auto`
    can sit still for a frame between measurements and then move again."""
    previous, held = None, 0
    for _ in range(tries):
        await pilot.pause()
        region = pilot.app.screen.query_one(selector).region
        held = held + 1 if region == previous else 0
        if held >= steady:
            return region
        previous = region
    return previous


async def settle_until(pilot, predicate, tries=40):
    """Pump the event loop until `predicate` holds.

    `switch_screen` lands a frame or two after the click that caused it, and
    how many is load-dependent -- a fixed pause count is a flaky test waiting
    to happen."""
    for _ in range(tries):
        if predicate():
            return True
        await pilot.pause()
    return predicate()


def drive(scenario):
    """Run an async pilot scenario from a sync test."""
    asyncio.run(scenario())


def test_app_boots_to_the_menu():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=MIN_TERMINAL) as pilot:
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
        async with app.run_test(size=MIN_TERMINAL) as pilot:
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
        async with app.run_test(size=MIN_TERMINAL) as pilot:
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
        async with app.run_test(size=MIN_TERMINAL) as pilot:
            screen = await start_fight(pilot, app)
            for _ in range(12):
                await pilot.press("down")
            await pilot.pause()
            assert chess.square_rank(screen.cursor) == 0

    drive(scenario)


def test_selecting_then_moving_plays_the_move():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=MIN_TERMINAL) as pilot:
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
        async with app.run_test(size=MIN_TERMINAL) as pilot:
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
        async with app.run_test(size=MIN_TERMINAL) as pilot:
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
        async with app.run_test(size=MIN_TERMINAL) as pilot:
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
        async with app.run_test(size=MIN_TERMINAL) as pilot:
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
        async with app.run_test(size=MIN_TERMINAL) as pilot:
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
        async with app.run_test(size=MIN_TERMINAL) as pilot:
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
        async with app.run_test(size=MIN_TERMINAL) as pilot:
            screen = await promotion_ready_screen(pilot, app)
            await open_the_promotion_picker(pilot, screen)

            await pilot.press("escape")
            await pilot.pause()
            assert screen.promotion_moves == []
            assert screen.fight.player_moves == 0
            assert screen.fight.board.piece_at(chess.G7) is not None

    drive(scenario)


def test_post_fight_runs_on_the_keyboard():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=MIN_TERMINAL) as pilot:
            screen = await start_fight(pilot, app)
            app.finish_fight(app.run_state, screen.fight, [], won=True)
            await pilot.pause()

            post = app.screen
            phase = post.phase
            assert post.zone is PostZone.CONTROLS

            await pilot.press("enter")  # collect
            await pilot.pause()
            assert phase.step is Step.MANAGE

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
        async with app.run_test(size=MIN_TERMINAL) as pilot:
            screen = await start_fight(pilot, app)
            app.finish_fight(app.run_state, screen.fight, [], won=True)
            await pilot.pause()

            post = app.screen
            post.phase.collect_payout()
            post.refresh_all()
            await pilot.pause()
            assert post.phase.step is Step.MANAGE

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
        async with app.run_test(size=MIN_TERMINAL) as pilot:
            screen = await start_fight(pilot, app)
            assert not screen.query("Input")

    drive(scenario)


def test_winning_routes_into_the_post_fight_rail():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=MIN_TERMINAL) as pilot:
            await start_fight(pilot, app)

            fight_screen = app.screen
            app.finish_fight(app.run_state, fight_screen.fight, [], won=True)
            await pilot.pause()

            assert isinstance(app.screen, PostFightScreen)
            phase = app.screen.phase
            assert phase.step is Step.PAYOUT

            # payout -> manage (buy, sell and swap all at once) -> next fight
            await pilot.click("#finish")
            assert await settle_until(pilot, lambda: phase.step is Step.MANAGE)
            # Collecting makes the buy rows appear, which pushes #finish down
            # the column. Click again before that reflow lands and the click
            # aims at where the button used to be.
            await settle_layout(pilot, "#finish")
            assert app.run_state.gold > 0
            assert phase.swaps_left == config.MAX_SWAPS

            await pilot.click("#finish")
            assert await settle_until(
                pilot, lambda: isinstance(app.screen, FightScreen))
            assert app.run_state.fight_index == 1

    drive(scenario)


def test_buying_in_the_ui_benches_the_piece():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=MIN_TERMINAL) as pilot:
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


def test_the_whole_ui_fits_the_minimum_terminal():
    """104x30 is the supported minimum; every control must stay clickable."""

    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=(104, 36)) as pilot:
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
            assert_all_visible("manage")

            # and with a piece in hand, which is when the action strip appears
            app.screen.selection = Slot.on_bench(0) if app.run_state.army.inventory \
                else None
            app.screen.refresh_all()
            await pilot.pause()
            assert_all_visible("manage, holding")

    drive(scenario)


def test_losing_routes_to_defeat():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=MIN_TERMINAL) as pilot:
            await start_fight(pilot, app)

            app.finish_fight(app.run_state, app.screen.fight, [], won=False)
            await pilot.pause()

            from chessvania.ui.screens.gameover import GameOverScreen

            assert isinstance(app.screen, GameOverScreen)
            assert app.screen.won is False

    drive(scenario)


def test_a_spent_swap_budget_refuses_at_the_first_press():
    """No lit squares, no "legal" copy -- nothing that implies a swap is coming."""

    async def scenario():
        from chessvania.core.postfight import Slot

        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=MIN_TERMINAL) as pilot:
            screen = await start_fight(pilot, app)
            app.finish_fight(app.run_state, screen.fight, [], won=True)
            await pilot.pause()

            post = app.screen
            post.phase.collect_payout()
            assert post.phase.step is Step.MANAGE
            post.phase.swaps_used = config.MAX_SWAPS      # budget spent
            post.refresh_all()
            await pilot.pause()

            post._pick(Slot.on_board(chess.A2))
            await pilot.pause()

            assert post.selection is None, "a piece was picked up with no swaps left"
            board = post.query_one("#board", BoardView)
            assert not board.targets, "squares lit with no swaps left"
            assert post.query_one("#act-sell", Button).disabled

    drive(scenario)


def test_the_payout_panel_shows_what_you_are_about_to_be_paid():
    """It read `run.gold`, which before collecting is still last round's."""

    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=MIN_TERMINAL) as pilot:
            screen = await start_fight(pilot, app)
            app.run_state.gold = 0
            app.finish_fight(app.run_state, screen.fight, [], won=True)
            await pilot.pause()

            post = app.screen
            assert post.phase.step is Step.PAYOUT
            assert post.phase.payout.total > 0
            panel = post._market().plain
            assert str(post.phase.payout.total) in panel, (
                "the payout is not shown before collecting: %r" % panel)

    drive(scenario)


def test_sell_is_the_only_button_and_lights_only_for_bench_pieces():
    """Every other action points at a destination, so the click is the verb.

    Selling has nowhere to point, which is why it alone needs a control.
    """

    async def scenario():
        from chessvania.core.postfight import Slot

        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=MIN_TERMINAL) as pilot:
            screen = await start_fight(pilot, app)
            app.finish_fight(app.run_state, screen.fight, [], won=True)
            await pilot.pause()
            post = app.screen
            post.phase.collect_payout()
            post.phase.buy(0)                          # something to hold
            post.refresh_all()
            await pilot.pause()

            sell = post.query_one("#act-sell", Button)
            assert sell.disabled, "lit with nothing in hand"

            post.selection = Slot.on_bench(0)          # a bench piece
            post.refresh_all()
            await pilot.pause()
            assert not sell.disabled, "a benched piece can be sold"
            assert str(post.run.army.inventory[0].value // 2 or 1) in str(sell.label)

            king = post.run.army.king_square()
            post.selection = Slot.on_board(king)       # a board piece
            post.refresh_all()
            await pilot.pause()
            assert sell.disabled, "board pieces are not sellable"

    drive(scenario)


def test_the_swap_budget_reads_beside_the_bench_not_in_the_market():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=MIN_TERMINAL) as pilot:
            screen = await start_fight(pilot, app)
            app.finish_fight(app.run_state, screen.fight, [], won=True)
            await pilot.pause()
            post = app.screen
            post.phase.collect_payout()
            post.refresh_all()
            await pilot.pause()

            left = post.query_one("#swap-count", Static).render().plain
            assert "swaps" in left and str(config.MAX_SWAPS) in left
            assert "swap" not in post._receipt().plain.lower(), (
                "the budget is still being reported in the market panel too"
            )

    drive(scenario)


def test_the_sell_button_fits_the_column_it_is_drawn_in():
    """The left column is 17 wide; the thing this replaced was invisible there."""

    async def scenario():
        from chessvania.core.postfight import Slot

        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=MIN_TERMINAL) as pilot:
            screen = await start_fight(pilot, app)
            app.finish_fight(app.run_state, screen.fight, [], won=True)
            await pilot.pause()
            post = app.screen
            post.phase.collect_payout()
            post.phase.buy(4)                          # a queen, the longest label
            post.selection = Slot.on_bench(0)
            post.refresh_all()
            await pilot.pause()

            column = post.query_one("#left").region
            for selector in ("#act-sell", "#swap-count"):
                box = post.query_one(selector).region
                assert box.x >= column.x and box.x + box.width <= column.x + column.width, (
                    "%s (%s) escapes the %d-wide column" % (selector, box, column.width))
            sell = post.query_one("#act-sell", Button)
            assert len(str(sell.label)) <= sell.region.width, (
                "label %r is wider than the %d columns it has"
                % (str(sell.label), sell.region.width))

    drive(scenario)


def test_next_battle_is_the_only_way_out_and_banks_the_bonus_itself():
    """Skip used to be a second button you had to notice and press."""

    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=MIN_TERMINAL) as pilot:
            screen = await start_fight(pilot, app)
            app.finish_fight(app.run_state, screen.fight, [], won=True)
            await pilot.pause()
            post = app.screen
            post.phase.collect_payout()
            post.refresh_all()
            await pilot.pause()

            assert not post.query("#skip"), "the skip button should be gone"
            finish = post.query_one("#finish", Button)
            assert "next battle" in str(finish.label)

            note = post.query_one("#advance-note", Static).render().plain
            assert str(config.SKIP_BONUS) in note, (
                "the bonus is not explained anywhere: %r" % note)

            banked_before = app.run_state.banked_skip_bonus
            await settle_layout(pilot, "#finish")
            await pilot.click("#finish")
            assert await settle_until(
                pilot, lambda: isinstance(app.screen, FightScreen))
            assert app.run_state.banked_skip_bonus > banked_before, (
                "leaving unspent should have banked the bonus"
            )

    drive(scenario)


def test_the_note_says_the_bonus_is_gone_once_you_buy():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=MIN_TERMINAL) as pilot:
            screen = await start_fight(pilot, app)
            app.finish_fight(app.run_state, screen.fight, [], won=True)
            await pilot.pause()
            post = app.screen
            post.phase.collect_payout()
            post.refresh_all()
            await pilot.pause()
            before = post.query_one("#advance-note", Static).render().plain

            post.phase.buy(0)
            post.refresh_all()
            await pilot.pause()
            after = post.query_one("#advance-note", Static).render().plain
            assert before != after, "the note did not react to the purchase"
            assert "spent" in after

    drive(scenario)


def test_the_advance_note_fits_the_column():
    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=MIN_TERMINAL) as pilot:
            screen = await start_fight(pilot, app)
            app.finish_fight(app.run_state, screen.fight, [], won=True)
            await pilot.pause()
            post = app.screen
            post.phase.collect_payout()
            post.refresh_all()
            await pilot.pause()
            widget = post.query_one("#advance-note", Static)
            for line in widget.render().plain.split("\n"):
                assert len(line) <= widget.content_size.width, (
                    "%r overflows %d columns" % (line, widget.content_size.width))
    drive(scenario)


def test_the_payout_screen_draws_no_empty_panels():
    """A bordered box around nothing reads as something that failed to load."""

    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=MIN_TERMINAL) as pilot:
            screen = await start_fight(pilot, app)
            app.finish_fight(app.run_state, screen.fight, [], won=True)
            await pilot.pause()
            post = app.screen
            assert post.phase.step is Step.PAYOUT

            for selector in ("#controls", "#advance-note", "#receipt",
                             "#act-sell", "#swap-count"):
                assert not post.query_one(selector).display, (
                    "%s is on screen during the payout with nothing to show"
                    % selector)

            # ...and all of it comes back once there is something to do
            post.phase.collect_payout()
            post.refresh_all()
            await pilot.pause()
            for selector in ("#controls", "#advance-note", "#receipt",
                             "#act-sell", "#swap-count"):
                assert post.query_one(selector).display, "%s stayed hidden" % selector

    drive(scenario)


def test_the_payout_labels_its_numbers():
    """"◇0 → ◇5" on its own does not say what is going from 0 to 5."""

    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=MIN_TERMINAL) as pilot:
            screen = await start_fight(pilot, app)
            app.run_state.gold = 0
            app.finish_fight(app.run_state, screen.fight, [], won=True)
            await pilot.pause()
            panel = app.screen._market().plain
            assert "gold" in panel, "the before/after pair is unlabelled: %r" % panel

    drive(scenario)


# -- the enemy card ------------------------------------------------------


def _enemy_card(pilot, app):
    from chessvania.ui.widgets.enemy import EnemyCard

    return app.screen.query_one("#enemy", EnemyCard)


def test_the_enemy_card_names_the_opponent_its_tier_and_its_elo():
    """Three facts, no prose. The name leads; the rest qualifies it."""

    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=MIN_TERMINAL) as pilot:
            screen = await start_fight(pilot, app)
            card = _enemy_card(pilot, app).render().plain

            assert screen.fight.enemy_name.upper() in card
            assert screen.fight.tier.upper() in card
            assert str(screen.fight.elo) in card

    drive(scenario)


def test_the_enemy_card_shows_the_elo_the_engine_really_gets():
    """Not a tier label dressed up as a number -- the value handed to Stockfish."""

    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=MIN_TERMINAL) as pilot:
            screen = await start_fight(pilot, app)
            assert str(app.run_state.elo) in _enemy_card(pilot, app).render().plain

    drive(scenario)


def test_every_enemy_card_fits_the_rail():
    """Checked against all 20 enemies and all four tiers, not just the first."""

    async def scenario():
        from chessvania.data.enemies import POOLS
        from chessvania.ui.widgets.enemy import EnemyCard

        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=MIN_TERMINAL) as pilot:
            screen = await start_fight(pilot, app)
            card = _enemy_card(pilot, app)
            width = card.content_size.width

            for pool in POOLS.values():
                for formation in pool:
                    screen.fight.enemy_name = formation.name
                    screen.fight.tier = formation.tier
                    screen.fight.elo = 2200          # the widest number
                    for line in card._build(screen.fight).plain.split("\n"):
                        assert len(line) <= width, (
                            "%r is %d wide, rail is %d"
                            % (line, len(line), width))

    drive(scenario)


# -- the purse bar -------------------------------------------------------


def _purse_frames(moves_list, banked=0):
    """Render the purse at a list of move counts, inside the real rail."""
    from chessvania.ui.widgets.purse import Purse

    out = {}

    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=MIN_TERMINAL) as pilot:
            await start_fight(pilot, app)
            purse = app.screen.query_one("#payout", Purse)
            app.run_state.banked_skip_bonus = banked
            out["width"] = purse.content_size.width
            for moves in moves_list:
                out[moves] = purse._build(app.run_state, moves).plain

    drive(scenario)
    return out


def test_the_purse_fits_the_rail_at_every_move_count():
    """A bar that wraps is worse than the text it replaced."""
    frames = _purse_frames([0, 1, 9, 10, 11, 20, 30, 45, 46, 99], banked=2)
    width = frames.pop("width")
    for moves, frame in frames.items():
        for line in frame.split("\n"):
            assert len(line) <= width, (
                "move %d: %r is %d wide, rail is %d" % (moves, line, len(line), width))


def test_the_payout_falls_as_the_fight_runs_long():
    """With the prose gone, the lit rung IS the headline -- so test that."""
    from chessvania.ui.widgets.purse import Purse

    lit = {}

    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=MIN_TERMINAL) as pilot:
            await start_fight(pilot, app)
            purse = app.screen.query_one("#payout", Purse)
            for moves in (0, 15, 25, 40, 99):
                rung = purse._standing(moves)
                lit[moves] = purse._rungs(app.run_state)[rung]

    drive(scenario)
    paid = [lit[m] for m in (0, 15, 25, 40, 99)]
    assert paid == sorted(paid, reverse=True), paid
    assert paid[0] == config.PAYOUT_TIERS[0][1]
    assert paid[-1] == config.PAYOUT_FALLBACK, \
        "past the last tier it should pay the fallback"

BAR_ROW = 2
LADDER_ROW = 1


def test_the_bar_is_drawn_in_whole_cells_only():
    """The old tick used part-blocks, so its WEIGHT changed with its position.

    Nothing in the bar may be a partial block: a mark that is a hairline at
    one move and a slab at the next is encoding its own rounding error.
    """
    from chessvania.ui.widgets.purse import LIVE_CELL, SPENT_CELL

    frames = _purse_frames([0, 1, 7, 13, 22, 31, 44, 99])
    frames.pop("width")
    allowed = {LIVE_CELL, SPENT_CELL, " "}
    for moves, frame in frames.items():
        bar = frame.split("\n")[BAR_ROW]
        assert set(bar) <= allowed, "move %d: %r" % (moves, bar)
        # and each tick occupies exactly one cell, so the scale cannot drift
        assert len(bar) == len(bar.encode("utf-32-le")) // 4


def _bars_at(size, moves_list):
    """The bar row at a given terminal size, per move count."""
    from chessvania.ui.widgets.purse import Purse

    out = {}

    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=size) as pilot:
            await start_fight(pilot, app)
            purse = app.screen.query_one("#payout", Purse)
            out["width"] = purse.content_size.width
            for moves in moves_list:
                out[moves] = purse._build(app.run_state, moves).plain.split("\n")

    drive(scenario)
    return out


def test_every_single_move_advances_the_bar_by_exactly_one_block():
    """The complaint that started this: a move that changes nothing on screen.

    Within a tier, each move must spend exactly one block -- no rounding, no
    two moves sharing a cell.
    """
    counts = list(range(0, config.PAYOUT_TIERS[-1][0] + 1))
    frames = _bars_at(MIN_TERMINAL, counts)
    frames.pop("width")
    from chessvania.ui.widgets.purse import LIVE_CELL

    lit = [frames[m][BAR_ROW].count(LIVE_CELL) for m in counts]
    for moves in counts[1:]:
        before, after = lit[moves - 1], lit[moves]
        if after > before:
            continue  # crossing into the next tier refills the bar
        assert before - after == 1, (
            "move %d spent %d blocks, not 1 (%d -> %d)"
            % (moves, before - after, before, after))


def test_the_scale_does_not_change_with_the_window():
    """One block is one move at 104 columns and at 160. A bar you have to
    re-learn on every resize is not a bar."""
    probes = [0, 4, 13, 27, 41]
    narrow = _bars_at(MIN_TERMINAL, probes)
    wide = _bars_at((160, 44), probes)
    assert wide.pop("width") > narrow.pop("width"), "the rails were the same width"
    for moves in probes:
        assert narrow[moves][BAR_ROW] == wide[moves][BAR_ROW], (
            "move %d drew %r narrow and %r wide"
            % (moves, narrow[moves][BAR_ROW], wide[moves][BAR_ROW]))


def test_the_bar_covers_exactly_the_tier_you_are_standing_in():
    counts = [0, 5, 11, 21, 31, 44]
    frames = _bars_at(MIN_TERMINAL, counts)
    frames.pop("width")
    previous = 0
    spans = {}
    for threshold, _ in config.PAYOUT_TIERS:
        for moves in counts:
            if previous < moves <= threshold or (previous == 0 and moves == 0):
                spans[moves] = threshold - previous
        previous = threshold
    for moves, span in spans.items():
        bar = frames[moves][BAR_ROW]
        blocks = len(bar.replace(" ", ""))
        assert blocks == span, (
            "move %d: tier is %d moves but the bar has %d blocks (%r)"
            % (moves, span, blocks, bar))


def test_the_ladder_row_is_a_fixed_landmark():
    """It is marked by weight and colour, never by inserting characters, so
    the rungs sit at the same columns for the whole fight."""
    frames = _purse_frames([0, 10, 11, 29, 45, 99])
    frames.pop("width")
    rows = {f.split("\n")[LADDER_ROW] for f in frames.values()}
    assert len(rows) == 1, "the ladder reflowed: %r" % rows
    row = rows.pop()
    for _, gold in config.PAYOUT_TIERS:
        assert "%s%d" % (config.GOLD_GLYPH, gold) in row
    assert "%s%d" % (config.GOLD_GLYPH, config.PAYOUT_FALLBACK) in row, \
        "the fallback is a real outcome and belongs on the ladder"


def test_the_skip_bonus_is_added_to_the_ladder_and_not_hidden_inside_it():
    """Lit rung + bonus line = what you collect.

    If the rungs quietly carried the bonus, the panel would read ◇7 with a
    "+◇2" under it and invite you to expect ◇9.
    """
    bonus = 2
    plain = _purse_frames([5], banked=bonus)[5]
    assert "skip bonus" in plain and "banked" not in plain
    rungs = plain.split("\n")[LADDER_ROW]
    base = config.PAYOUT_TIERS[0][1]
    assert "%s%d" % (config.GOLD_GLYPH, base) in rungs, \
        "the top rung should still read %d: %r" % (base, rungs)
    assert "%s%d" % (config.GOLD_GLYPH, base + bonus) not in rungs, \
        "the bonus leaked into the ladder: %r" % rungs


def test_the_ladder_shows_what_a_stake_would_actually_pay():
    """The reason there is no 'win now' line: an NG+ penalty IS in the rungs
    (unlike the skip bonus), so the lit one needs no gloss."""
    from chessvania.ui.widgets.purse import Purse

    starved = next(s for s in config.STAKES if s.payout_penalty == 2)
    rungs = {}

    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=MIN_TERMINAL) as pilot:
            await start_fight(pilot, app)
            purse = app.screen.query_one("#payout", Purse)
            rungs["base"] = purse._rungs(app.run_state)
            app.run_state.stake = starved
            rungs["starved"] = purse._rungs(app.run_state)

    drive(scenario)
    assert rungs["starved"] != rungs["base"], \
        "the ladder ignored the stake penalty: %s" % (rungs["base"],)
    for base, lean in zip(rungs["base"], rungs["starved"]):
        assert lean == max(config.MIN_PAYOUT, base - starved.payout_penalty)


# -- the scoresheet ------------------------------------------------------


def _scoresheet(plies, size=None, seed=4):
    """Play `plies` legal plies and return the rendered sheet plus the fight."""
    import random

    from chessvania.ui.widgets.scoresheet import Scoresheet

    out = {}

    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=size or MIN_TERMINAL) as pilot:
            screen = await start_fight(pilot, app)
            board, rng = screen.fight.board, random.Random(seed)
            for _ in range(plies):
                if screen.fight.finished:
                    break
                move = rng.choice(list(board.legal_moves))
                if board.turn == chess.WHITE:
                    screen.fight.play_player(move)
                else:
                    screen.fight.apply_opponent(move)
            screen.refresh_all()
            await pilot.pause()
            sheet = screen.query_one("#log", Scoresheet)
            body = sheet.query_one("#sheet-body")
            out["fight"] = screen.fight
            out["width"] = body.content_size.width
            out["visible"] = body.content_size.height
            # No [:-1]: the sheet ends on its last row, not on a newline.
            out["lines"] = sheet._build(screen.fight).plain.split("\n")
            out["pairs"] = sheet._pairs(screen.fight)

    drive(scenario)
    return out


def test_the_scoresheet_shows_a_round_number_of_rows():
    """9 on a small screen and 17 on a large one were whatever the column had
    left over. These are numbers you can learn."""
    from chessvania.ui.layout import SHEET_ROWS, minimum_terminal

    assert _scoresheet(0, size=minimum_terminal())["visible"] == SHEET_ROWS[0]
    assert _scoresheet(0, size=(140, 50))["visible"] == SHEET_ROWS[-1]


def test_a_short_game_still_fills_the_sheet_and_a_long_one_keeps_every_move():
    """Blank numbered rows to the bottom when there is room; no truncation
    when there is not, because the body scrolls."""
    short = _scoresheet(7)
    assert len(short["lines"]) == short["visible"], (
        "a 7-ply game should fill the panel: %d of %d"
        % (len(short["lines"]), short["visible"]))

    long = _scoresheet(40)
    played = len(long["fight"].log)
    assert len(long["lines"]) >= played // 2 + 1, \
        "moves were dropped instead of scrolled"
    for sheet in (short, long):
        for line in sheet["lines"]:
            assert len(line) <= sheet["width"], "%r in %d" % (line, sheet["width"])


def test_the_scoresheet_does_not_take_the_arrow_keys_from_the_board():
    """A focusable scroll region inside the fight screen swallows the one
    input the whole game runs on."""
    from chessvania.ui.widgets.scoresheet import Scoresheet

    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=MIN_TERMINAL) as pilot:
            screen = await start_fight(pilot, app)
            body = screen.query_one("#log", Scoresheet).query_one("#sheet-body")
            assert not body.can_focus
            before = screen.cursor
            await pilot.press("up")
            await pilot.pause()
            assert screen.cursor != before, "the sheet ate the arrow key"

    drive(scenario)


def test_the_scoresheet_puts_your_moves_in_the_white_column():
    """Pairing is by ply parity; this is what says that parity is right."""
    sheet = _scoresheet(13)
    log = sheet["fight"].log
    for index, entry in enumerate(log):
        number, column = index // 2, index % 2
        assert sheet["pairs"][number][column] == entry.text
        assert entry.by_player == (column == 0), (
            "ply %d is in the %s column but by_player is %s"
            % (index, "white" if column == 0 else "black", entry.by_player))


def test_the_sheet_numbers_every_row_in_order_from_one():
    sheet = _scoresheet(40)
    numbers = [int(r.split(".")[0]) for r in sheet["lines"] if r.strip()]
    assert numbers == list(range(1, len(numbers) + 1)), numbers
    played = len(sheet["fight"].log)
    assert numbers[-1] == played // 2 + 1, "the live row is not the last row"


def test_the_caret_marks_the_cell_that_is_waiting():
    from chessvania.ui.widgets.scoresheet import CARET, NUM_W, SAN_W

    after_yours = _scoresheet(1)["lines"]
    live = [r for r in after_yours if CARET in r][-1]
    assert live.index(CARET) == NUM_W + SAN_W + 1, \
        "after your move the caret belongs in the black column: %r" % live

    fresh = _scoresheet(0)["lines"]
    live = [r for r in fresh if CARET in r][-1]
    assert live.index(CARET) == NUM_W, \
        "before a move is played the caret belongs in the white column: %r" % live


def test_the_sheet_never_draws_a_half_grown_frame_during_a_resize():
    """It used to take two resizes to fill the panel.

    `scale_board` assigns the panel's height and refreshes in the same pass,
    so a sheet that measured its own `content_size` read the PREVIOUS layout:
    crossing a board rung drew 10 rows, then 15. After everything settles
    both agree, which is why this records every content update rather than
    the end state -- the wrong frame is the one you see while dragging.
    """
    from textual.widgets import Static

    from chessvania.ui.layout import minimum_terminal, sheet_rows
    from chessvania.ui.widgets.scoresheet import Scoresheet

    drawn = []
    original = Static.update

    def record(self, renderable="", **kwargs):
        if self.id == "sheet-rows":
            drawn.append(len(renderable.plain.split("\n")))
        return original(self, renderable, **kwargs)

    async def scenario():
        app = ChessvaniaApp(engine=FakeEngine(), seed=1)
        async with app.run_test(size=minimum_terminal()) as pilot:
            screen = await start_fight(pilot, app)
            Static.update = record
            try:
                drawn.clear()
                await pilot.resize_terminal(150, 40)   # crosses a board rung
                await pilot.pause()
            finally:
                Static.update = original
            want = sheet_rows(screen.query_one("#board").region.height)
            assert drawn, "the sheet never redrew"
            assert set(drawn) == {want}, (
                "drew %s on the way to %d rows -- a frame behind" % (drawn, want))

    drive(scenario)
