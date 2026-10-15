"""The post-fight phase, drawn as a rail in the right-hand column.

The screen keeps the fight's skeleton -- bench left, board centre -- and only
re-tasks the right column. The board and bench stay exactly where they were,
which matters because buying and swapping both target them.

The four steps are always visible: finished ones collapse to a receipt, the
active one expands, and future ones show their unlock condition. Selling being
locked until the shop closes is a rule players would otherwise experience as a
bug, so it is stated rather than merely enforced.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

import chess
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Static

from ... import config
from ...core.army import PIECE_NAMES, Piece
from ...core.economy import sell_value
from ...core.postfight import PostFight, Slot, Step, catalogue
from ...core.run import RunState
from .. import theme
from ..layout import scale_board
from ..widgets.bench import COLUMNS as BENCH_COLUMNS
from ..widgets.bench import BenchView
from ..widgets.board_view import BoardView
from ..widgets.devbar import POSTFIGHT_KEYS, DevBar
from ..widgets.topbar import TopBar

RAIL_MIN_WIDTH = 23
RAIL_MAX_WIDTH = 40

DELTAS = {"up": (0, 1), "down": (0, -1), "left": (-1, 0), "right": (1, 0)}


class Zone(Enum):
    CONTROLS = "controls"
    BOARD = "board"
    BENCH = "bench"


class PostFightScreen(Screen):
    BINDINGS = [
        ("up", "cursor('up')", "Move"),
        ("down", "cursor('down')", "Move"),
        ("left", "cursor('left')", "Move"),
        ("right", "cursor('right')", "Move"),
        ("enter", "select", "Choose"),
        ("space", "select", "Choose"),
        ("tab", "switch_zone", "Switch pane"),
        ("escape", "clear_selection", "Clear selection"),
        ("ctrl+q", "quit", "Quit"),
        # Diagnostics -- inert unless config.DEV_MODE is on.
        ("f1", "dev_detail", "Dev detail"),
        ("f2", "dev_gold", "Dev gold"),
        ("f3", "dev_skip", "Dev skip phase"),
        ("f5", "dev_swaps", "Dev refill swaps"),
        ("s", "sell", "Sell"),
    ]

    def __init__(self, run: RunState, phase: PostFight) -> None:
        super().__init__()
        self.run = run
        self.phase = phase
        self.selection: Optional[Slot] = None
        self.notice: Optional[Text] = None
        self.zone = Zone.CONTROLS
        self.control_index = 0
        self.board_cursor: chess.Square = chess.E1
        self.bench_cursor = 0

    # -- layout ----------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield TopBar(id="topbar")
        with Horizontal(id="main"):
            with Vertical(id="left"):
                yield Static(id="bench-label")
                yield BenchView(id="bench")
                with Horizontal(id="verbs"):
                    yield Button("sell", id="act-sell")
                    yield Button("swap", id="act-swap")
                yield Static(id="swap-count")
            with Vertical(id="center"):
                yield BoardView(id="board")
                yield Static(id="status")
            with VerticalScroll(id="right"):
                yield Static(id="market", classes="panel")
                with Vertical(id="controls", classes="panel"):
                    for index in range(len(catalogue())):
                        yield Button("", id="buy-%d" % index, classes="shop-button")
                    yield Button("", id="skip")
                    yield Button("finish", id="finish")
                yield Static(id="receipt", classes="panel")
        yield DevBar(id="devbar")

    def on_mount(self) -> None:
        self.query_one("#devbar", DevBar).display = config.DEV_MODE
        self.query_one("#topbar", TopBar).show(self.run, "post-fight")
        # The screen owns every key, so buttons must not swallow enter/arrows.
        # The two verb buttons are deliberately not in the tab cycle either:
        # the keyboard already has enter and s for them, and they are there to
        # show what is possible, not to be navigated to.
        for button in self.query("Button"):
            button.can_focus = False
        self.board_cursor = self.run.army.king_square() or chess.E1
        scale_board(self)
        self.refresh_all()

    # -- rendering -------------------------------------------------------

    def _army_board(self) -> chess.Board:
        board = chess.Board(None)
        for square, piece in self.run.army.deployment.items():
            board.set_piece_at(square, chess.Piece(piece.piece_type, chess.WHITE))
        return board

    def _veterancy_map(self) -> Dict[chess.Square, int]:
        return {sq: p.veterancy for sq, p in self.run.army.deployment.items()}

    def refresh_all(self) -> None:
        army = self.run.army
        if self.zone not in self._zones():
            self.zone = Zone.CONTROLS

        board_view = self.query_one("#board", BoardView)
        board_view.set_board(self._army_board(), self._veterancy_map())
        board_view.set_selection(
            self.selection.index if self.selection and self.selection.is_board else None,
            self._placement_targets(),
            captures=False,
        )
        board_view.set_cursor(self.board_cursor, active=self.zone is Zone.BOARD)

        bench = self.query_one("#bench", BenchView)
        bench.set_pieces(army.inventory)
        bench.set_selection(
            self.selection.index if self.selection and not self.selection.is_board else None
        )
        bench.set_cursor(self.bench_cursor, active=self.zone is Zone.BENCH)

        label = Text()
        label.append("INVENTORY ", style=theme.DIM)
        label.append("%d" % army.inventory_count, style=theme.TEXT)
        label.append("/%d" % config.INVENTORY_CAP, style=theme.GHOST)
        self.query_one("#bench-label", Static).update(label)

        self._sync_verbs()

        market = self.query_one("#market", Static)
        market_text = self._market()
        market.update(market_text)
        # Auto-height mis-measures this panel: it is sized on a layout pass that
        # runs before its width is known, so it reserves room for wrapping that
        # never happens and shoves the buttons off the bottom. We know exactly
        # how many lines we just rendered, so pin it.
        market.styles.height = market_text.plain.count("\n") + 3

        receipt = self.query_one("#receipt", Static)
        receipt_text = self._receipt()
        receipt.update(receipt_text)
        receipt.styles.height = receipt_text.plain.count("\n") + 3

        self._sync_controls()
        self._apply_control_focus()
        self.query_one("#status", Static).update(self.notice or self._hint())
        if config.DEV_MODE:
            self.query_one("#devbar", DevBar).show(
                self.run,
                keys=POSTFIGHT_KEYS,
                extra="step %s · swaps left %d · spent %d · skipped %s"
                % (self.phase.step.value, self.phase.swaps_left,
                   self.phase.gold_spent, self.phase.skipped),
            )

    def on_resize(self, event=None) -> None:
        """Re-render once the real width is known.

        The rail sizes its rules and headers from the panel's width, which is
        still zero on the first layout pass -- so without this the panel keeps
        the too-tall height it measured before it knew how wide it was, and
        pushes the buttons off the bottom of the screen.

        It is also where the board picks its square size, for the same reason:
        the budget depends on the terminal, not on the first layout pass.
        """
        scale_board(self)
        self.refresh_all()

    def _hint(self) -> Text:
        """What the keys do right now, under the board where there is width.

        When something is in hand this is the action legend: the swap line
        completes itself from wherever the cursor is, so enter is never a
        guess. The left column only has thirteen columns to play with, which
        is not enough to say any of this.
        """
        text = Text()
        held = self.selection
        if held is not None and self.phase.step is Step.MANAGE:
            piece = self._piece_at(held)
            if piece is not None:
                text.append("holding %s " % theme.piece_glyph_for(piece),
                            style=theme.SEASONED)
                text.append("· ", style=theme.GHOST)
                text.append("enter", style=theme.GREEN)
                text.append(" %s" % self._swap_label(), style=theme.DIM)
                if not held.is_board:
                    text.append(" · ", style=theme.GHOST)
                    text.append("s", style=theme.GREEN)
                    text.append(" sell ", style=theme.DIM)
                    text.append("+%s%d" % (config.GOLD_GLYPH,
                                           sell_value(piece.piece_type)),
                                style=theme.GOLD)
                text.append(" · ", style=theme.GHOST)
                text.append("esc", style=theme.GREEN)
                text.append(" put back", style=theme.DIM)
                return text

        zones = self._zones()
        if self.zone is Zone.CONTROLS:
            text.append("↑↓", style=theme.GREEN)
            text.append(" choose · ", style=theme.DIM)
            text.append("enter", style=theme.GREEN)
            text.append(" confirm", style=theme.DIM)
        elif self.zone is Zone.BOARD:
            text.append("board · ", style=theme.DIM)
            text.append("enter", style=theme.GREEN)
            text.append(" pick up or place", style=theme.DIM)
        else:
            text.append("bench · ", style=theme.DIM)
            text.append("enter", style=theme.GREEN)
            text.append(" pick up · ", style=theme.DIM)
            text.append("s", style=theme.GREEN)
            text.append(" sell", style=theme.DIM)
        if len(zones) > 1:
            text.append(" · ", style=theme.GHOST)
            text.append("tab", style=theme.GREEN)
            text.append(" switch pane", style=theme.DIM)
        return text

    def _sync_verbs(self) -> None:
        """Light the two verbs the held piece actually has.

        They are indicators first and controls second: greyed out they say
        "pick something up", lit they say what that something can do. Selling
        is bench-only, so a board piece lights swap alone.
        """
        held = self.selection
        piece = self._piece_at(held) if held is not None else None
        managing = self.phase.step is Step.MANAGE

        sell = self.query_one("#act-sell", Button)
        swap = self.query_one("#act-swap", Button)
        sell.disabled = not (managing and piece is not None and not held.is_board)
        swap.disabled = not (managing and piece is not None
                             and bool(self._placement_targets()))

        sell.label = ("sell %s%d" % (config.GOLD_GLYPH,
                                     sell_value(piece.piece_type))
                      if not sell.disabled and piece is not None else "sell")
        swap.label = "swap"

        count = Text()
        if managing:
            count.append("swaps ", style=theme.DIM)
            count.append("%d" % self.phase.swaps_left, style=theme.GREEN)
            count.append("/%d" % config.MAX_SWAPS, style=theme.GHOST)
        self.query_one("#swap-count", Static).update(count)

    def _swap_label(self) -> str:
        """What enter would do from here -- the sentence finishes at the cursor."""
        if self.zone is Zone.BENCH:
            return "swap to bench"
        if self.zone is not Zone.BOARD:
            return "swap to board"
        occupant = self.run.army.deployment.get(self.board_cursor)
        where = chess.square_name(self.board_cursor)
        if occupant is not None:
            return "swap with %s %s" % (theme.piece_glyph_for(occupant), where)
        return "swap to %s" % where

    def _piece_at(self, slot: Slot):
        if slot.is_board:
            return self.run.army.deployment.get(slot.index)
        inventory = self.run.army.inventory
        return inventory[slot.index] if slot.index < len(inventory) else None

    @property
    def _rail_width(self) -> int:
        """Track the panel's inner width so rules span it and headers don't wrap."""
        try:
            available = self.query_one("#market", Static).content_size.width
        except Exception:
            available = 0
        if not available:
            available = RAIL_MIN_WIDTH
        return max(RAIL_MIN_WIDTH, min(available, RAIL_MAX_WIDTH))

    def _market(self) -> Text:
        """The header over the buy list: what you have, and what you owe it to."""
        text = Text()
        collecting = self.phase.step is Step.PAYOUT
        title = "PAYOUT" if collecting else "MARKET"
        # Before collecting, `run.gold` is still last round's number -- showing
        # it reads as "you won nothing". Show the incoming amount instead.
        right = Text(
            "+%s %d" % (config.GOLD_GLYPH, self.phase.payout.total) if collecting
            else "%s %d" % (config.GOLD_GLYPH, self.run.gold),
            style=theme.GOLD,
        )
        pad = max(1, self._rail_width - len(title) - right.cell_len)
        text.append(title, style="%s bold" % theme.TEXT)
        text.append(" " * pad)
        text.append_text(right)
        text.append("\n")

        if self.phase.step is Step.PAYOUT:
            payout = self.phase.payout
            text.append("  won in %d moves\n" % payout.move_count, style=theme.DIM)
            text.append("  %s%d → %s%d\n" % (
                config.GOLD_GLYPH, self.run.gold,
                config.GOLD_GLYPH, self.run.gold + payout.total),
                style=theme.GOLD)
            if payout.skip_bonus:
                text.append("  banked +%d\n" % payout.skip_bonus, style=theme.GREEN)
            if self.phase.casualties:
                lost = Text("  lost  ", style=theme.DIM)
                for piece in self.phase.casualties:
                    lost.append("%s " % theme.piece_glyph_for(piece), style=theme.RED)
                lost.append("\n")
                text.append_text(lost)
            else:
                text.append("  no losses\n", style=theme.GHOST)
        elif self.phase.skipped:
            text.append("  shop skipped\n", style=theme.GREEN)
        return text

    def _receipt(self) -> Text:
        """What this phase has cost and earned so far.

        Replaces the four-section rail: with one open step there is no sequence
        left to draw, so the panel reports history instead of position.
        """
        text = Text()
        text.append("THIS ROUND\n", style=theme.DIM)

        counts = self.phase.purchase_counts()
        if counts:
            bought = Text("  bought ", style=theme.DIM)
            for piece_type, count in counts.items():
                bought.append("%s%s " % (theme.piece_glyph(piece_type),
                                         "x%d" % count if count > 1 else ""),
                              style=theme.SEASONED)
            bought.append("\n")
            text.append_text(bought)
        if self.phase.sold_count:
            text.append("  sold %d\n" % self.phase.sold_count, style=theme.DIM)
        if not counts and not self.phase.sold_count:
            text.append("  nothing traded\n", style=theme.GHOST)
        return text

    def _sync_controls(self) -> None:
        step = self.phase.step

        for index in range(len(catalogue())):
            button = self.query_one("#buy-%d" % index, Button)
            visible = step is Step.MANAGE and index < len(self.phase.stock)
            button.display = visible
            if visible:
                item = self.phase.stock[index]
                ok, reason = self.phase.can_buy(index)
                button.label = "%s %s  %s%d" % (
                    theme.piece_glyph(item.piece_type), item.name.lower(),
                    config.GOLD_GLYPH, item.price
                )
                button.disabled = not ok

        skip = self.query_one("#skip", Button)
        skip.display = step is Step.MANAGE and self.phase.can_skip
        if skip.display:
            kept, bonus = self.phase.skip_preview()
            # The numbers go on the button: a bare "skip" hides the most
            # interesting economic decision in the game.
            skip.label = "skip · keep %s%d, +%d next" % (
                config.GOLD_GLYPH, kept, bonus
            )

        finish = self.query_one("#finish", Button)
        finish.display = True
        finish.label = "collect" if step is Step.PAYOUT else "next fight"

    def _visible_controls(self) -> List[Button]:
        """The buttons currently on screen, in the order they are laid out."""
        return [b for b in self.query("#controls Button") if b.display]

    def _apply_control_focus(self) -> None:
        controls = self._visible_controls()
        if not controls:
            self.control_index = 0
            return
        self.control_index = min(self.control_index, len(controls) - 1)
        focused = self.zone is Zone.CONTROLS
        for index, button in enumerate(controls):
            button.set_class(focused and index == self.control_index, "focused")

    # -- keyboard --------------------------------------------------------

    def _zones(self) -> List["Zone"]:
        """Which panes the keyboard can reach.

        During MANAGE that is all of them, because buying, selling and swapping
        are simultaneous now -- there is no step left to gate a pane behind."""
        if self.phase.step is Step.MANAGE:
            return [Zone.CONTROLS, Zone.BOARD, Zone.BENCH]
        return [Zone.CONTROLS]

    def action_switch_zone(self) -> None:
        zones = self._zones()
        if self.zone not in zones:
            self.zone = zones[0]
        else:
            self.zone = zones[(zones.index(self.zone) + 1) % len(zones)]
        self.notice = None
        self.refresh_all()

    def action_cursor(self, direction: str) -> None:
        if self.zone is Zone.CONTROLS:
            controls = self._visible_controls()
            if controls and direction in ("up", "down"):
                step = 1 if direction == "down" else -1
                self.control_index = (self.control_index + step) % len(controls)
        elif self.zone is Zone.BOARD:
            df, dr = DELTAS[direction]
            file = min(7, max(0, chess.square_file(self.board_cursor) + df))
            rank = min(7, max(0, chess.square_rank(self.board_cursor) + dr))
            self.board_cursor = chess.square(file, rank)
        else:
            rows = config.INVENTORY_CAP // BENCH_COLUMNS
            column = self.bench_cursor % BENCH_COLUMNS
            row = self.bench_cursor // BENCH_COLUMNS
            if direction == "left":
                column = max(0, column - 1)
            elif direction == "right":
                column = min(BENCH_COLUMNS - 1, column + 1)
            elif direction == "up":
                row = max(0, row - 1)
            else:
                row = min(rows - 1, row + 1)
            self.bench_cursor = row * BENCH_COLUMNS + column
        self.notice = None
        self.refresh_all()

    def action_select(self) -> None:
        if self.zone is Zone.CONTROLS:
            controls = self._visible_controls()
            if controls:
                self._activate_control(controls[self.control_index].id or "")
        elif self.zone is Zone.BOARD:
            self._interact(Slot.on_board(self.board_cursor))
        else:
            self._interact(Slot.on_bench(self.bench_cursor))

    def _placement_targets(self) -> List[chess.Square]:
        """Every square the held piece may legally be put on.

        Asks `can_swap` once per square rather than restating the rule, so a
        square that lights up is by construction a square the swap accepts --
        the deployment zone, the pawn rank, the board cap and the king rule all
        come along for free, and none of them can drift out of step here.
        """
        if self.selection is None or self.phase.step is not Step.MANAGE:
            return []
        return [square for square in chess.SQUARES
                if self.phase.can_swap(self.selection, Slot.on_board(square))[0]]

    def _interact(self, slot: Slot) -> None:
        """Enter always means pick-up-or-place. Selling has its own key.

        With the three steps merged, a bench press can no longer be
        disambiguated by the phase, so the verb is fixed and the destination
        decides what happened."""
        self.notice = None
        if self.phase.step is Step.MANAGE:
            self._pick(slot)

    # -- diagnostics -----------------------------------------------------

    def action_dev_detail(self) -> None:
        """f1 -- expand the dev bar with the phase's internal state."""
        if not config.DEV_MODE:
            return
        self.query_one("#devbar", DevBar).toggle()
        self.refresh_all()

    def action_dev_gold(self) -> None:
        """f2 -- top up gold, for exercising the shop without earning it."""
        if not config.DEV_MODE:
            return
        self.run.gold += config.DEV_GOLD_STEP
        self.query_one("#topbar", TopBar).tick_gold_to(self.run.gold)
        self._say("dev · +%d gold" % config.DEV_GOLD_STEP, theme.GOLD)
        self.refresh_all()

    def action_dev_skip(self) -> None:
        """f3 -- straight to the next fight, whatever step we are on.

        Pairs with f3 in a fight to blitz a run and reach the late antes.
        """
        if not config.DEV_MODE:
            return
        self.phase.finish()
        self.app.finish_postfight(self.run)

    def action_dev_swaps(self) -> None:
        """f5 -- refill the swap budget, for testing deployments freely."""
        if not config.DEV_MODE:
            return
        self.phase.swaps_used = 0
        self._say("dev · swaps refilled", theme.GOLD)
        self.refresh_all()

    # -- interaction -----------------------------------------------------

    def action_sell(self) -> None:
        """Sell the bench piece in hand, or the one under the cursor.

        Bench-only by design: cashing out a deployed piece means recalling it
        first, and that costs a swap, so "deploy everything and sell the
        survivors" is not free."""
        if self.phase.step is not Step.MANAGE:
            return
        held = self.selection
        if held is not None and not held.is_board:
            index = held.index
        elif held is None and self.zone is Zone.BENCH:
            index = self.bench_cursor
        else:
            self.app.play_sound("deny")
            self._say("only bench pieces can be sold", theme.GHOST)
            self.refresh_all()
            return
        self.selection = None
        self._sell(index)

    def action_clear_selection(self) -> None:
        self.selection = None
        self.refresh_all()

    def _say(self, message: str, style: str) -> None:
        self.notice = Text(message, style=style)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self._activate_control(event.button.id or "")

    def _act_swap(self) -> None:
        """Commit at the cursor if it is already on a legal square, else go there.

        After picking a piece up the cursor is auto-jumped onto a legal target,
        so the common case is that this button simply does the swap.
        """
        targets = self._placement_targets()
        if not targets:
            return
        if self.zone is Zone.BOARD and self.board_cursor in targets:
            self._pick(Slot.on_board(self.board_cursor))
            return
        self.zone = Zone.BOARD
        self.board_cursor = min(targets, key=lambda sq: abs(sq - self.board_cursor))
        self.refresh_all()

    def _activate_control(self, button_id: str) -> None:
        self.notice = None

        if button_id.startswith("buy-"):
            index = int(button_id.split("-")[1])
            ok, reason = self.phase.buy(index)
            self.app.play_sound("buy" if ok else "deny")
            if not ok:
                self._say(reason, theme.RED)
            else:
                item = self.phase.stock[index]
                self._say("%s benched" % PIECE_NAMES[item.piece_type].lower(), theme.GREEN)
        elif button_id == "skip":
            ok, reason = self.phase.skip_shop()
            if not ok:
                self._say(reason, theme.RED)
            else:
                self._say("banked — the next payout compounds", theme.GREEN)
        elif button_id == "act-sell":
            self.action_sell()
            return
        elif button_id == "act-swap":
            self._act_swap()
            return
        elif button_id == "finish":
            if self.phase.step is Step.PAYOUT:
                payout = self.phase.collect_payout()
                self.query_one("#topbar", TopBar).tick_gold_to(self.run.gold)
                self._say("+%s%d" % (config.GOLD_GLYPH, payout.total), theme.GOLD)
            else:
                self.phase.finish()
                self.app.finish_postfight(self.run)
                return

        self.refresh_all()

    def _sell(self, index: int) -> None:
        inventory = self.run.army.inventory
        if index >= len(inventory):
            self.app.play_sound("deny")
            self._say("no piece in that slot", theme.GHOST)
            self.refresh_all()
            return
        piece = inventory[index]
        value = sell_value(piece.piece_type)
        ok, reason = self.phase.sell(index)
        self.app.play_sound("sell" if ok else "deny")
        self._say(
            "sold %s for %s%d" % (piece.name.lower(), config.GOLD_GLYPH, value)
            if ok else reason,
            theme.GOLD if ok else theme.RED,
        )
        self.refresh_all()

    def on_bench_view_slot_clicked(self, event: BenchView.SlotClicked) -> None:
        self.zone = Zone.BENCH
        self.bench_cursor = event.index
        self._interact(Slot.on_bench(event.index))

    def on_board_view_square_clicked(self, event: BoardView.SquareClicked) -> None:
        self.zone = Zone.BOARD
        self.board_cursor = event.square
        self._interact(Slot.on_board(event.square))

    def _pick(self, slot: Slot) -> None:
        """First press selects an occupied slot; the second is the destination.

        Spent budget refuses at the first press rather than the second. Letting
        a piece light up and the rail announce "lit squares are legal" when
        nothing can actually move is a promise the phase cannot keep.
        """
        if self.phase.swaps_left <= 0:
            self.selection = None
            self.app.play_sound("deny")
            self._say("no swaps left — finish the phase", theme.RED)
            self.refresh_all()
            return

        if self.selection is None:
            if not self._occupied(slot):
                self._say("pick a piece first", theme.GHOST)
                self.refresh_all()
                return
            self.selection = slot
            self.app.play_sound("pickup")
            # Lifting a piece is a statement of intent: go where it can land.
            # Without this every deployment costs a tab the player must know
            # to press.
            if not slot.is_board:
                targets = self._placement_targets()
                if targets:
                    self.zone = Zone.BOARD
                    self.board_cursor = min(
                        targets, key=lambda sq: abs(sq - self.board_cursor))
            self.refresh_all()
            return

        if slot == self.selection:
            self.selection = None
            self.refresh_all()
            return

        ok, reason = self.phase.swap(self.selection, slot)
        self.selection = None
        self.app.play_sound("select" if ok else "deny")
        self._say(
            "swapped · %d left" % self.phase.swaps_left if ok else reason,
            theme.GREEN if ok else theme.RED,
        )
        self.refresh_all()

    def _occupied(self, slot: Slot) -> bool:
        if slot.is_board:
            return slot.index in self.run.army.deployment
        return slot.index < len(self.run.army.inventory)

    # -- cursor readout --------------------------------------------------

    def on_bench_view_cursor_moved(self, event: BenchView.CursorMoved) -> None:
        if event.index is None or self.zone is not Zone.BENCH:
            return
        self.bench_cursor = event.index
        inventory = self.run.army.inventory
        if event.index >= len(inventory):
            return
        piece = inventory[event.index]
        self._say(
            "%s %s · %s · sells for %s%d"
            % (theme.piece_glyph_for(piece), piece.name.lower(), piece.veterancy_label,
               config.GOLD_GLYPH, sell_value(piece.piece_type)),
            theme.FAINT,
        )
        self.query_one("#status", Static).update(self.notice)

    def on_board_view_cursor_moved(self, event: BoardView.CursorMoved) -> None:
        if event.square is not None and self.zone is Zone.BOARD:
            self.board_cursor = event.square

    def action_quit(self) -> None:
        self.app.exit()
