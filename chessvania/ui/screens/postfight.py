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
                yield Static(id="bench-note")
            with Vertical(id="center"):
                yield BoardView(id="board")
                yield Static(id="status")
            with VerticalScroll(id="right"):
                yield Static(id="rail", classes="panel")
                with Vertical(id="controls", classes="panel"):
                    for index in range(len(catalogue())):
                        yield Button("", id="buy-%d" % index, classes="shop-button")
                    yield Button("", id="skip")
                    yield Button("done shopping", id="close-shop")
                    yield Button("done selling", id="close-sell")
                    yield Button("finish", id="finish")
        yield DevBar(id="devbar")

    def on_mount(self) -> None:
        self.query_one("#devbar", DevBar).display = config.DEV_MODE
        self.query_one("#topbar", TopBar).show(self.run, "post-fight")
        # The screen owns every key, so buttons must not swallow enter/arrows.
        for button in self.query("#controls Button"):
            button.can_focus = False
        self.board_cursor = self.run.army.king_square() or chess.E1
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
            (),
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

        note = Text()
        if self.phase.step is Step.SWAP:
            note.append("swaps left ", style=theme.FAINT)
            note.append("%d" % self.phase.swaps_left, style=theme.GREEN)
            note.append("\npick a piece,\nthen a target", style=theme.GHOST)
        elif self.phase.step is Step.SELL:
            note.append("click a piece\nto sell it", style=theme.FAINT)
        else:
            note.append("bench reserves", style=theme.FAINT)
        self.query_one("#bench-note", Static).update(note)

        rail = self.query_one("#rail", Static)
        rail_text = self._rail()
        rail.update(rail_text)
        # Auto-height mis-measures this panel: it is sized on a layout pass that
        # runs before its width is known, so it reserves room for wrapping that
        # never happens and shoves the buttons off the bottom. We know exactly
        # how many lines we just rendered, so pin it.
        rail.styles.height = rail_text.plain.count("\n") + 3  # lines + border

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
        """
        self.refresh_all()

    def _hint(self) -> Text:
        text = Text()
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
            verb = "sell" if self.phase.step is Step.SELL else "pick up or place"
            text.append("bench · ", style=theme.DIM)
            text.append("enter", style=theme.GREEN)
            text.append(" %s" % verb, style=theme.DIM)
        if len(zones) > 1:
            text.append(" · ", style=theme.GHOST)
            text.append("tab", style=theme.GREEN)
            text.append(" switch pane", style=theme.DIM)
        return text

    @property
    def _rail_width(self) -> int:
        """Track the panel's inner width so rules span it and headers don't wrap."""
        try:
            available = self.query_one("#rail", Static).content_size.width
        except Exception:
            available = 0
        if not available:
            available = RAIL_MIN_WIDTH
        return max(RAIL_MIN_WIDTH, min(available, RAIL_MAX_WIDTH))

    def _rail(self) -> Text:
        rule = "─" * self._rail_width
        text = Text()
        text.append_text(self._payout_section())
        text.append("%s\n" % rule, style=theme.BORDER)
        text.append_text(self._shop_section())
        text.append("%s\n" % rule, style=theme.BORDER)
        text.append_text(self._sell_section())
        text.append("%s\n" % rule, style=theme.BORDER)
        text.append_text(self._swap_section())
        text.rstrip()  # rich's rstrip mutates in place and returns None
        return text

    def _header(self, title: str, right: Text, active: bool) -> Text:
        text = Text()
        style = "%s bold" % theme.TEXT if active else theme.DIM
        text.append(title, style=style)
        pad = max(1, self._rail_width - len(title) - right.cell_len)
        text.append(" " * pad)
        text.append_text(right)
        text.append("\n")
        return text

    def _payout_section(self) -> Text:
        step = self.phase.step
        payout = self.phase.payout
        active = step is Step.PAYOUT

        right = Text("✓" if not active else "", style=theme.GREEN)
        text = self._header("PAYOUT", right, active)

        detail = Text()
        detail.append(
            "  won in %d move%s\n  " % (payout.move_count, "" if payout.move_count == 1 else "s"),
            style=theme.DIM,
        )
        detail.append("%s%d" % (config.GOLD_GLYPH, payout.base), style=theme.GOLD)
        if payout.stake_penalty:
            detail.append(" −%d stake" % payout.stake_penalty, style=theme.RED)
        if payout.skip_bonus:
            detail.append(" +%d banked" % payout.skip_bonus, style=theme.GREEN)
        detail.append(" → ", style=theme.DIM)
        detail.append("%s%d\n" % (config.GOLD_GLYPH, payout.total),
                      style="%s bold" % theme.GOLD)
        text.append_text(detail)

        # The casualty line. Permadeath is the point of the design, and this is
        # the moment it should be informing what you buy.
        if self.phase.casualties:
            lost = Text("  lost  ", style=theme.DIM)
            for piece in self.phase.casualties:
                lost.append("%s " % piece.symbol, style=theme.RED)
            lost.append("\n")
            text.append_text(lost)
        else:
            text.append("  no losses\n", style=theme.GHOST)
        return text

    def _shop_section(self) -> Text:
        step = self.phase.step
        active = step is Step.SHOP
        past = step in (Step.SELL, Step.SWAP, Step.DONE)

        if past:
            right = Text("✓", style=theme.GREEN)
        elif active:
            right = Text("%s %d" % (config.GOLD_GLYPH, self.run.gold), style=theme.GOLD)
        else:
            right = Text("locked", style=theme.GHOST)
        text = self._header("SHOP", right, active)

        if past:
            if self.phase.skipped:
                text.append("  skipped · +%d banked\n" % config.SKIP_BONUS,
                            style=theme.GREEN)
            elif self.phase.bought:
                bought = Text("  bought ", style=theme.DIM)
                for symbol, count in self.phase.purchase_counts().items():
                    bought.append("%s%s " % (
                        symbol, "×%d" % count if count > 1 else ""),
                        style=theme.SEASONED)
                bought.append("\n")
                text.append_text(bought)
            else:
                text.append("  bought nothing\n", style=theme.GHOST)
            return text

        if not active:
            return text

        # The stock itself lives on the buttons below -- listing it here too
        # would just be the same four rows twice.
        if self.run.army.inventory_full:
            text.append("  bench full — sell after closing\n", style=theme.RED)
        else:
            text.append("  purchases go to the bench\n", style=theme.GHOST)
        return text

    def _sell_section(self) -> Text:
        step = self.phase.step
        active = step is Step.SELL
        past = step in (Step.SWAP, Step.DONE)

        if past:
            right = Text("✓", style=theme.GREEN)
        elif active:
            right = Text("%s %d" % (config.GOLD_GLYPH, self.run.gold), style=theme.GOLD)
        else:
            right = Text("close shop first", style=theme.GHOST)
        text = self._header("SELL", right, active)

        if past:
            if self.phase.sold_count:
                text.append("  sold %d\n" % self.phase.sold_count, style=theme.DIM)
            else:
                text.append("  sold nothing\n", style=theme.GHOST)
        elif active:
            text.append("  click a benched piece\n", style=theme.DIM)
            text.append("  half price, rounded down\n", style=theme.GHOST)
        return text

    def _swap_section(self) -> Text:
        step = self.phase.step
        active = step is Step.SWAP

        if active:
            right = Text("%d left" % self.phase.swaps_left, style=theme.GREEN)
        elif step is Step.DONE:
            right = Text("✓", style=theme.GREEN)
        else:
            right = Text("locked", style=theme.GHOST)
        text = self._header("SWAP", right, active)

        if active:
            text.append("  board ↔ bench, or move\n", style=theme.DIM)
            text.append("  to an empty square\n", style=theme.GHOST)
        return text

    # -- controls --------------------------------------------------------

    def _sync_controls(self) -> None:
        step = self.phase.step

        for index in range(len(catalogue())):
            button = self.query_one("#buy-%d" % index, Button)
            visible = step is Step.SHOP and index < len(self.phase.stock)
            button.display = visible
            if visible:
                item = self.phase.stock[index]
                ok, reason = self.phase.can_buy(index)
                button.label = "%s %s  %s%d" % (
                    item.symbol, item.name.lower(), config.GOLD_GLYPH, item.price
                )
                button.disabled = not ok

        skip = self.query_one("#skip", Button)
        skip.display = step is Step.SHOP and self.phase.can_skip
        if skip.display:
            kept, bonus = self.phase.skip_preview()
            # The numbers go on the button: a bare "skip" hides the most
            # interesting economic decision in the game.
            skip.label = "skip · keep %s%d, +%d next" % (
                config.GOLD_GLYPH, kept, bonus
            )

        self.query_one("#close-shop", Button).display = step is Step.SHOP
        self.query_one("#close-sell", Button).display = step is Step.SELL
        finish = self.query_one("#finish", Button)
        finish.display = step in (Step.PAYOUT, Step.SWAP)
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
        """Which panes the keyboard can reach, given the step we're on."""
        if self.phase.step is Step.SELL:
            return [Zone.CONTROLS, Zone.BENCH]
        if self.phase.step is Step.SWAP:
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

    def _interact(self, slot: Slot) -> None:
        self.notice = None
        if self.phase.step is Step.SELL and not slot.is_board:
            self._sell(slot.index)
        elif self.phase.step is Step.SWAP:
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

    def action_clear_selection(self) -> None:
        self.selection = None
        self.refresh_all()

    def _say(self, message: str, style: str) -> None:
        self.notice = Text(message, style=style)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self._activate_control(event.button.id or "")

    def _activate_control(self, button_id: str) -> None:
        self.notice = None

        if button_id.startswith("buy-"):
            index = int(button_id.split("-")[1])
            ok, reason = self.phase.buy(index)
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
        elif button_id == "close-shop":
            self.phase.close_shop()
        elif button_id == "close-sell":
            self.phase.close_sell()
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
            self._say("no piece in that slot", theme.GHOST)
            self.refresh_all()
            return
        piece = inventory[index]
        value = sell_value(piece.piece_type)
        ok, reason = self.phase.sell(index)
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
        """First press selects an occupied slot; the second is the destination."""
        if self.selection is None:
            if not self._occupied(slot):
                self._say("pick a piece first", theme.GHOST)
                self.refresh_all()
                return
            self.selection = slot
            self.refresh_all()
            return

        if slot == self.selection:
            self.selection = None
            self.refresh_all()
            return

        ok, reason = self.phase.swap(self.selection, slot)
        self.selection = None
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
            % (piece.symbol, piece.name.lower(), piece.veterancy_label,
               config.GOLD_GLYPH, sell_value(piece.piece_type)),
            theme.FAINT,
        )
        self.query_one("#status", Static).update(self.notice)

    def on_board_view_cursor_moved(self, event: BoardView.CursorMoved) -> None:
        if event.square is not None and self.zone is Zone.BOARD:
            self.board_cursor = event.square

    def action_quit(self) -> None:
        self.app.exit()
