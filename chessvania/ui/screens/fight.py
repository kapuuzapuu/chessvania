"""The fight screen: board, bench, live payout readout, move log, inspect.

Driven entirely by the keyboard -- arrows move a cursor, enter selects and then
commits. The mouse drives the same cursor, so there is only ever one highlight
on screen and no second input model to learn.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

import chess
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

from ... import config
from ...core.army import PIECE_NAMES, PIECE_VALUES, Piece
from ...core.economy import tier_ladder
from ...core.fight import Fight, Outcome
from ...core.run import RunState
from ...core.threat import Danger, ThreatReport, cover, read as read_threats
from .. import theme
from ..widgets.bench import COLUMNS as BENCH_COLUMNS
from ..widgets.bench import BenchView
from ..widgets.board_view import BoardView
from ..widgets.devbar import DevBar
from ..widgets.topbar import TopBar

DELTAS = {"up": (0, 1), "down": (0, -1), "left": (-1, 0), "right": (1, 0)}

PROMOTION_ORDER = (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT)
PROMOTION_KEYS = {"q": chess.QUEEN, "r": chess.ROOK, "b": chess.BISHOP, "n": chess.KNIGHT}

STATUS_WIDTH = 27
"""The centre column is 28 columns wide; building to 27 keeps a column of slack.

A line that wraps silently doubles this panel's height and pushes the board off
an 80x24 terminal, so every row below is measured rather than trusted.
"""

THREAT_ROWS = 3
"""Threat lines the panel will show. `ThreatReport.threats` is sorted worst
first, so truncating from the bottom drops the least important warning."""


class Zone(Enum):
    BOARD = "board"
    BENCH = "bench"


class FightScreen(Screen):
    BINDINGS = [
        ("up", "cursor('up')", "Move"),
        ("down", "cursor('down')", "Move"),
        ("left", "cursor('left')", "Move"),
        ("right", "cursor('right')", "Move"),
        ("enter", "select", "Select"),
        ("space", "select", "Select"),
        ("escape", "cancel", "Cancel"),
        ("tab", "switch_zone", "Board / bench"),
        ("ctrl+q", "quit", "Quit"),
        # Diagnostics -- inert unless config.DEV_MODE is on.
        ("f1", "dev_detail", "Dev detail"),
        ("f2", "dev_gold", "Dev gold"),
        ("f3", "dev_win", "Dev win"),
        ("f4", "dev_lose", "Dev lose"),
        ("f5", "dev_kill", "Dev kill"),
    ]

    def __init__(self, run: RunState, fight: Fight) -> None:
        super().__init__()
        self.run = run
        self.fight = fight
        self.zone = Zone.BOARD
        self.selected: Optional[chess.Square] = None
        self.cursor: chess.Square = fight.board.king(chess.WHITE) or chess.E2
        self.bench_cursor = 0
        self.thinking = False
        self.notice: Optional[Text] = None
        self.promotion_moves: List[chess.Move] = []
        self.promotion_index = 0
        self.report: ThreatReport = read_threats(fight.board)
        """Recomputed every refresh. It is a static read over 32 squares, which
        costs nothing next to a Textual repaint."""
        self._by_id: Dict[int, Piece] = {
            p.id: p for p in run.army.deployment.values()
        }

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
            with Vertical(id="right"):
                yield Static(id="payout", classes="panel")
                with VerticalScroll(id="logbox", classes="panel"):
                    yield Static(id="log")
                yield Static(id="inspect", classes="panel")
        yield DevBar(id="devbar")

    def on_mount(self) -> None:
        self.query_one("#devbar", DevBar).display = config.DEV_MODE
        self.refresh_all()

    # -- rendering -------------------------------------------------------

    def _veterancy_map(self) -> Dict[chess.Square, int]:
        """Current square -> veterancy, following pieces as they move."""
        return {
            square: self._by_id[pid].veterancy
            for square, pid in self.fight.tracker.at.items()
            if pid in self._by_id
        }

    def refresh_all(self) -> None:
        spec_label = "%s · %s" % (self.fight.enemy_name, self.fight.tier)
        self.query_one("#topbar", TopBar).show(self.run, spec_label)

        self.report = read_threats(self.fight.board)

        last = self.fight.board.peek() if self.fight.board.move_stack else None
        board_view = self.query_one("#board", BoardView)
        board_view.set_board(self.fight.board, self._veterancy_map(), last)
        board_view.set_threats(self.report.by_square)
        board_view.set_selection(self.selected, self._targets())
        board_view.set_cursor(self.cursor, active=self.zone is Zone.BOARD)

        army = self.run.army
        bench = self.query_one("#bench", BenchView)
        bench.set_pieces(army.inventory)
        bench.set_cursor(self.bench_cursor, active=self.zone is Zone.BENCH)

        self.query_one("#bench-label", Static).update(self._bench_label(army))
        self.query_one("#bench-note", Static).update(
            Text("reserves\noff-board", style=theme.FAINT)
        )
        self.query_one("#payout", Static).update(self._payout_panel())
        self.query_one("#log", Static).update(self._log_panel())
        self._refresh_status()
        self._refresh_inspect()
        if config.DEV_MODE:
            self.query_one("#devbar", DevBar).show(self.run, self.fight)

    def _targets(self) -> List[chess.Square]:
        if self.selected is None:
            return []
        return [m.to_square for m in self.fight.moves_from(self.selected)]

    def _bench_label(self, army) -> Text:
        text = Text()
        text.append("INVENTORY ", style=theme.DIM)
        text.append("%d" % army.inventory_count, style=theme.TEXT)
        text.append("/%d" % config.INVENTORY_CAP, style=theme.GHOST)
        return text

    def _payout_panel(self) -> Text:
        moves = self.fight.player_moves
        payout = self.run.preview_payout(moves)

        text = Text()
        text.append("IF YOU WIN NOW\n", style=theme.DIM)
        text.append("moves ", style=theme.DIM)
        text.append("%-4d" % moves, style="%s bold" % theme.TEXT)
        text.append("→ %s %d gold\n" % (config.GOLD_GLYPH, payout.total), style=theme.GOLD)

        current = None
        for threshold, _ in tier_ladder():
            if moves <= threshold:
                current = threshold
                break

        for index, (threshold, gold) in enumerate(tier_ladder()):
            if index:
                text.append(" · ", style=theme.GHOST)
            text.append(
                "≤%d → %s%d" % (threshold, config.GOLD_GLYPH, gold),
                style=theme.GREEN if threshold == current else theme.FAINT,
            )
        text.append("\n")

        if self.run.banked_skip_bonus:
            text.append("skip-bonus banked ", style=theme.DIM)
            text.append("+%d" % self.run.banked_skip_bonus, style=theme.GREEN)
            text.append(" (already counted above)", style=theme.GHOST)
        else:
            text.append("no banked bonus", style=theme.GHOST)
        return text

    def _log_panel(self) -> Text:
        text = Text()
        text.append("MOVE LOG\n", style=theme.DIM)
        for entry in self.fight.log[-40:]:
            who = "you" if entry.by_player else self.fight.enemy_name
            style = theme.TEXT if entry.by_player else theme.ENEMY_PIECE
            if entry.capture:
                style = theme.GOLD if entry.by_player else theme.RED
            text.append("› ", style=theme.GHOST)
            text.append("%s · %s" % (who, entry.text), style=style)
            text.append("\n")
        return text

    # -- status line -----------------------------------------------------

    def set_status(self, message: str, style: Optional[str] = None) -> None:
        self.notice = Text(message, style=style or theme.DIM)
        self._refresh_status()

    def _refresh_status(self) -> None:
        self.query_one("#status", Static).update(self._status_text())

    def _status_text(self) -> Text:
        """One transient line, then the threat readout, then a control hint.

        The readout is the resting state of this panel. It used to hold nothing
        but keyboard hints, which every player has memorised by the second fight
        and which say nothing about the only thing at stake here -- which of
        your pieces is about to be taken off the run for good.
        """
        if self.promotion_moves:
            return self._promotion_picker()

        text = Text()
        if self.thinking:
            text.append("%s is thinking…\n" % self.fight.enemy_name,
                        style=theme.ENEMY_PIECE)
        elif self.notice is not None:
            text.append_text(self.notice)
            text.append("\n")

        text.append_text(self._threat_panel())
        text.append("\n")
        text.append_text(self._hint_line())
        return text

    def _hint_line(self) -> Text:
        """Controls, in one row of GHOST. The arrow keys used to be spelled out
        here; the cursor already says what they do, and the row has to stay
        inside 27 columns or it wraps and costs the panel a line."""
        text = Text()
        if self.zone is Zone.BENCH:
            text.append("tab", style=theme.GREEN)
            text.append(" back to the board", style=theme.GHOST)
        elif self.selected is not None:
            text.append("enter", style=theme.GREEN)
            text.append(" move · ", style=theme.GHOST)
            text.append("esc", style=theme.GREEN)
            text.append(" cancel", style=theme.GHOST)
        else:
            text.append("enter", style=theme.GREEN)
            text.append(" pick up · ", style=theme.GHOST)
            text.append("tab", style=theme.GREEN)
            text.append(" bench", style=theme.GHOST)
        return text

    # -- threat readout --------------------------------------------------

    def _mark(self, square: chess.Square) -> str:
        """A piece and where it stands, as one token: `♞g5`."""
        piece = self.fight.board.piece_at(square)
        glyph = theme.piece_glyph(piece.piece_type, piece.color) if piece else ""
        return "%s%s" % (glyph, chess.square_name(square))

    def _row(self, left: Text, right: Optional[Text] = None) -> Text:
        """Left-aligned text with an optional right-aligned tail, padded to fit.

        Drops the tail rather than wrapping if the two collide -- losing the
        number is survivable, gaining a row is not.
        """
        if right is None:
            return left
        gap = STATUS_WIDTH - left.cell_len - right.cell_len
        if gap < 1:
            return left
        left.append(" " * gap)
        left.append_text(right)
        return left

    def _threat_panel(self) -> Text:
        report = self.report
        text = Text()
        text.append_text(self._row(Text("THREAT", style=theme.DIM), self._verdict()))

        if report.in_check:
            text.append("\n")
            text.append_text(self._check_line())

        shown = 0
        for threat in report.threats:
            if shown >= THREAT_ROWS:
                break
            if threat.level is Danger.CHECK:
                continue  # already said, louder, on its own line
            text.append("\n")
            text.append_text(self._threat_line(threat))
            shown += 1

        remaining = len([t for t in report.threats if t.level is not Danger.CHECK]) - shown
        if remaining > 0:
            text.append("\n")
            text.append("  +%d more attacked" % remaining, style=theme.GHOST)

        if report.opportunities:
            text.append("\n")
            text.append_text(self._opportunity_line(report.opportunities[0]))
        return text

    def _verdict(self) -> Text:
        """The one-glance summary, right-aligned against the panel title."""
        report = self.report
        if report.in_check:
            return Text("IN CHECK", style="%s bold" % theme.DANGER)
        if report.material_at_risk:
            return Text(
                "%d at risk" % report.material_at_risk,
                style=theme.DANGER if report.worst is Danger.HANGING else theme.CAUTION,
            )
        if report.threats:
            return Text("trades even", style=theme.GREEN)
        return Text("nothing attacked", style=theme.GREEN)

    def _check_line(self) -> Text:
        report = self.report
        marks = " ".join(self._mark(square) for square in report.checkers)
        left = Text()
        left.append("+ ", style="%s bold" % theme.DANGER)
        left.append(marks, style=theme.ENEMY_PIECE)
        left.append(" checks" if len(report.checkers) == 1 else " double check",
                    style=theme.DANGER)
        # Escape count is the tension: one way out plays very differently from ten.
        tail = Text(
            "%d out" % report.escapes,
            style=theme.DANGER if report.escapes <= 2 else theme.DIM,
        )
        return self._row(left, tail)

    def _threat_line(self, threat) -> Text:
        color = theme.threat_color(threat.level) or theme.DIM
        left = Text()
        left.append("%s " % (theme.threat_marker(threat.level) or " "), style=color)
        left.append(self._mark(threat.square), style=theme.TEXT)

        if threat.level is Danger.HANGING:
            left.append(" free to ", style=theme.DIM)
            left.append(self._mark(threat.cheapest_attacker), style=theme.ENEMY_PIECE)
        elif threat.level is Danger.TRADE:
            left.append(" trades down", style=theme.DIM)
        else:
            left.append(" attacked, held", style=theme.DIM)

        tail = Text("-%d" % threat.loss, style=color) if threat.loss else None
        return self._row(left, tail)

    def _opportunity_line(self, chance) -> Text:
        left = Text()
        left.append("> ", style=theme.GOLD)
        left.append(self._mark(chance.square), style=theme.ENEMY_PIECE)
        left.append(" is free" if chance.free else " is worth taking", style=theme.DIM)
        return self._row(left, Text("+%d" % chance.gain, style=theme.GOLD))

    def _promotion_picker(self) -> Text:
        text = Text()
        text.append("promote to  ", style=theme.GOLD)
        for index, move in enumerate(self.promotion_moves):
            glyph = theme.piece_glyph(move.promotion)
            chosen = index == self.promotion_index
            text.append(
                "[%s]" % glyph if chosen else " %s " % glyph,
                style="%s bold" % theme.GOLD if chosen else theme.FAINT,
            )
        text.append("\n←→ or q/r/b/n · enter", style=theme.GHOST)
        return text

    # -- inspect ---------------------------------------------------------

    def _refresh_inspect(self) -> None:
        if self.zone is Zone.BENCH:
            self._inspect(self._bench_inspect())
        else:
            self._inspect(self._square_inspect(self.cursor))

    def _inspect(self, message: Text) -> None:
        panel = Text()
        panel.append("INSPECT\n", style=theme.DIM)
        panel.append_text(message)
        self.query_one("#inspect", Static).update(panel)

    def _square_inspect(self, square: Optional[chess.Square]) -> Text:
        if square is None:
            return Text("—", style=theme.GHOST)
        piece = self.fight.board.piece_at(square)
        if piece is None:
            return self._empty_square_inspect(square)

        text = Text()
        if piece.color == chess.WHITE:
            pid = self.fight.tracker.at.get(square)
            owned = self._by_id.get(pid) if pid is not None else None
            color = theme.player_color(owned) if owned else theme.FRESH
            text.append("%s " % theme.piece_glyph(piece.piece_type, piece.color),
                        style=color)
            text.append(PIECE_NAMES[piece.piece_type], style=theme.TEXT)
            text.append(" · yours · value %d" % PIECE_VALUES[piece.piece_type],
                        style=theme.FAINT)
            if owned:
                text.append("\n%s · %d fights survived"
                            % (owned.veterancy_label, owned.fights_survived),
                            style=color if owned.veterancy else theme.FAINT)
            detail = self._own_piece_detail(square)
        else:
            text.append("%s " % theme.piece_glyph(piece.piece_type, piece.color),
                        style=theme.enemy_color(piece.piece_type))
            text.append("Enemy %s" % PIECE_NAMES[piece.piece_type], style=theme.TEXT)
            text.append(" · value %d" % PIECE_VALUES[piece.piece_type], style=theme.FAINT)
            detail = self._enemy_piece_detail(square)

        if detail is not None:
            text.append("\n")
            text.append_text(detail)
        return text

    def _empty_square_inspect(self, square: chess.Square) -> Text:
        """Whether it is safe to stand here -- the question you ask of an empty
        square, and one the board's own colours cannot answer."""
        text = Text(chess.square_name(square), style=theme.GHOST)
        guards = cover(self.fight.board, square, chess.BLACK)
        text.append("\n")
        if guards:
            text.append("covered by ", style=theme.DIM)
            text.append(self._marks(guards), style=theme.ENEMY_PIECE)
        else:
            text.append("uncontested", style=theme.GREEN)
        return text

    def _own_piece_detail(self, square: chess.Square) -> Optional[Text]:
        threat = self.report.at(square)
        if threat is None:
            return None
        color = theme.threat_color(threat.level) or theme.DIM
        text = Text()
        text.append("%s " % (theme.threat_marker(threat.level) or " "), style=color)

        if threat.level is Danger.CHECK:
            text.append("in check from ", style=color)
            text.append(self._marks(threat.attackers), style=theme.ENEMY_PIECE)
        elif threat.level is Danger.HANGING:
            text.append(self._marks(threat.attackers), style=theme.ENEMY_PIECE)
            text.append(" takes it for free", style=color)
        elif threat.level is Danger.TRADE:
            text.append(self._marks(threat.attackers), style=theme.ENEMY_PIECE)
            text.append(" trades you down %d" % threat.loss, style=color)
        else:
            text.append(self._marks(threat.attackers), style=theme.ENEMY_PIECE)
            text.append(" · held by ", style=theme.DIM)
            text.append(self._marks(threat.defenders), style=theme.TEXT)
        return text

    def _enemy_piece_detail(self, square: chess.Square) -> Optional[Text]:
        chance = self.report.opportunity_at(square)
        text = Text()
        if chance is not None:
            text.append("> ", style=theme.GOLD)
            text.append(self._marks(chance.takers), style=theme.TEXT)
            text.append(" takes it free" if chance.free else " wins %d" % chance.gain,
                        style=theme.GOLD)
            return text

        guards = cover(self.fight.board, square, chess.BLACK)
        if not guards:
            return None
        text.append("guarded by ", style=theme.DIM)
        text.append(self._marks(guards), style=theme.ENEMY_PIECE)
        return text

    def _marks(self, squares, limit: int = 2) -> str:
        """`♞g5 ♝c4 +1` -- the panel is 29 columns, so long lists get counted."""
        head = " ".join(self._mark(square) for square in squares[:limit])
        extra = len(squares) - limit
        return "%s +%d" % (head, extra) if extra > 0 else head

    def _bench_inspect(self) -> Text:
        inventory = self.run.army.inventory
        if self.bench_cursor >= len(inventory):
            return Text("empty bench slot", style=theme.GHOST)
        piece = inventory[self.bench_cursor]
        text = Text()
        text.append("%s " % theme.piece_glyph_for(piece), style=theme.player_color(piece))
        text.append(piece.name, style=theme.TEXT)
        text.append(" · benched · value %d" % piece.value, style=theme.FAINT)
        text.append("\n%s · %d fights survived"
                    % (piece.veterancy_label, piece.fights_survived), style=theme.FAINT)
        return text

    # -- keyboard --------------------------------------------------------

    def action_cursor(self, direction: str) -> None:
        if self.promotion_moves:
            step = 1 if direction in ("right", "down") else -1
            self.promotion_index = (self.promotion_index + step) % len(self.promotion_moves)
            self._refresh_status()
            return
        if self.zone is Zone.BENCH:
            self._move_bench_cursor(direction)
        else:
            self._move_board_cursor(direction)

    def _move_board_cursor(self, direction: str) -> None:
        df, dr = DELTAS[direction]
        file = min(7, max(0, chess.square_file(self.cursor) + df))
        rank = min(7, max(0, chess.square_rank(self.cursor) + dr))
        self.cursor = chess.square(file, rank)
        self.notice = None
        self.refresh_all()

    def _move_bench_cursor(self, direction: str) -> None:
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

    def action_switch_zone(self) -> None:
        if self.promotion_moves:
            return
        self.zone = Zone.BENCH if self.zone is Zone.BOARD else Zone.BOARD
        self.notice = None
        self.refresh_all()

    def action_cancel(self) -> None:
        if self.promotion_moves:
            self.promotion_moves = []
            self.set_status("promotion cancelled", theme.DIM)
            return
        self.selected = None
        self.notice = None
        self.refresh_all()

    def action_select(self) -> None:
        if self.promotion_moves:
            self._commit_promotion()
            return
        if self.zone is Zone.BENCH:
            self.set_status("bench pieces sit out the fight", theme.GHOST)
            return
        self._activate(self.cursor)

    def _activate(self, square: chess.Square) -> None:
        if self.thinking or self.fight.finished:
            return

        if self.selected is not None:
            if square == self.selected:
                self.selected = None
                self.refresh_all()
                return
            if self._attempt(self.selected, square):
                return

        piece = self.fight.board.piece_at(square)
        if piece is not None and piece.color == chess.WHITE:
            if self.fight.moves_from(square):
                self.selected = square
                self.notice = None
                self.refresh_all()
            else:
                self.set_status("that piece has no legal moves", theme.RED)
            return
        self.selected = None
        self.refresh_all()

    def _attempt(self, origin: chess.Square, target: chess.Square) -> bool:
        """Play origin->target, or open the promotion picker if it's ambiguous."""
        moves = [m for m in self.fight.moves_from(origin) if m.to_square == target]
        if not moves:
            return False
        if len(moves) > 1:
            moves.sort(key=lambda m: PROMOTION_ORDER.index(m.promotion))
            self.promotion_moves = moves
            self.promotion_index = 0
            self.selected = None
            self.refresh_all()
            return True
        self._play(moves[0])
        return True

    def _commit_promotion(self) -> None:
        move = self.promotion_moves[self.promotion_index]
        self.promotion_moves = []
        self._play(move)

    def on_key(self, event) -> None:
        """Letter shortcuts for the promotion picker."""
        if not self.promotion_moves:
            return
        wanted = PROMOTION_KEYS.get(event.key)
        if wanted is None:
            return
        for index, move in enumerate(self.promotion_moves):
            if move.promotion == wanted:
                self.promotion_index = index
                event.stop()
                self._commit_promotion()
                return

    # -- diagnostics -----------------------------------------------------

    def action_dev_detail(self) -> None:
        """f1 -- expand the dev bar with FEN, payout breakdown and stake."""
        if not config.DEV_MODE:
            return
        self.query_one("#devbar", DevBar).toggle()
        self.refresh_all()

    def action_dev_gold(self) -> None:
        """f2 -- top up gold, for exercising the shop without playing for it."""
        if not config.DEV_MODE:
            return
        self.run.gold += config.DEV_GOLD_STEP
        self.query_one("#topbar", TopBar).tick_gold_to(self.run.gold)
        self.set_status("dev · +%d gold" % config.DEV_GOLD_STEP, theme.GOLD)
        self.refresh_all()

    def action_dev_win(self) -> None:
        """f3 -- win instantly. Pairs with f3 post-fight to blitz a whole run."""
        self._dev_force(Outcome.PLAYER_WIN)

    def action_dev_lose(self) -> None:
        """f4 -- lose instantly, for reaching the defeat screen."""
        self._dev_force(Outcome.PLAYER_LOSS)

    def _dev_force(self, outcome: Outcome) -> None:
        """End the fight without playing it out.

        Progression is untouched: this routes through the same `_finish` a real
        result does, so payout, casualties and the ladder all behave normally.
        """
        if not config.DEV_MODE or self.fight.finished:
            return
        self.fight.force_outcome(outcome)
        self._finish()

    def action_dev_kill(self) -> None:
        """f5 -- remove the enemy piece under the cursor.

        Kings are refused: removing one leaves a position python-chess rejects
        and Stockfish cannot play. Use f3 to end a fight instead.
        """
        if not config.DEV_MODE or self.fight.finished:
            return
        piece = self.fight.board.piece_at(self.cursor)
        if piece is None or piece.color != chess.BLACK:
            self.set_status("dev · no enemy piece there", theme.GHOST)
            return
        if piece.piece_type == chess.KING:
            self.set_status("dev · use f3 to end the fight", theme.GHOST)
            return
        self.fight.board.remove_piece_at(self.cursor)
        self.fight.resolve()
        self.set_status(
            "dev · removed enemy %s" % PIECE_NAMES[piece.piece_type].lower(), theme.GOLD
        )
        self.refresh_all()
        if self.fight.finished:
            self._finish()

    # -- mouse (drives the same cursor) ----------------------------------

    def on_board_view_square_clicked(self, event: BoardView.SquareClicked) -> None:
        self.zone = Zone.BOARD
        self.cursor = event.square
        self._activate(event.square)

    def on_board_view_cursor_moved(self, event: BoardView.CursorMoved) -> None:
        if event.square is not None and self.zone is Zone.BOARD:
            self.cursor = event.square
            self._refresh_inspect()

    def on_bench_view_slot_clicked(self, event: BenchView.SlotClicked) -> None:
        self.zone = Zone.BENCH
        self.bench_cursor = event.index
        self.refresh_all()

    def on_bench_view_cursor_moved(self, event: BenchView.CursorMoved) -> None:
        if event.index is not None and self.zone is Zone.BENCH:
            self.bench_cursor = event.index
            self._refresh_inspect()

    # -- play ------------------------------------------------------------

    def _play(self, move: chess.Move) -> None:
        capture = self.fight.board.is_capture(move)
        target = move.to_square
        if not self.fight.play_player(move):
            self.set_status("not a legal move", theme.RED)
            return

        self.selected = None
        self.cursor = target
        self.notice = None
        if capture:
            self.query_one("#board", BoardView).flash(target)
        self.refresh_all()

        if self.fight.finished:
            self._finish()
            return

        self.thinking = True
        self._refresh_status()
        self._engine_turn()

    # -- engine ----------------------------------------------------------

    @work(thread=True, exclusive=True)
    def _engine_turn(self) -> None:
        """Blocking engine call, off the UI thread."""
        try:
            move = self.fight.opponent_move()
        except Exception as exc:  # engine died mid-run
            self.app.call_from_thread(self._engine_failed, str(exc))
            return
        if move is not None:
            self.app.call_from_thread(self._apply_engine_move, move)

    def _engine_failed(self, message: str) -> None:
        self.thinking = False
        self.set_status("engine error: %s" % message, theme.RED)

    def _apply_engine_move(self, move: chess.Move) -> None:
        losses_before = len(self.fight.tracker.captured)
        capture = self.fight.board.is_capture(move)
        target = move.to_square

        self.fight.apply_opponent(move)
        self.thinking = False

        if capture:
            self.query_one("#board", BoardView).flash(target)

        self.notice = None
        self.refresh_all()

        lost = self.fight.tracker.captured[losses_before:]
        if lost:
            piece = self._by_id.get(lost[-1])
            if piece is not None:
                self.set_status(
                    "%s takes your %s — gone for good"
                    % (self.fight.enemy_name, piece.name.lower()),
                    theme.RED,
                )

        if self.fight.finished:
            self._finish()

    # -- end -------------------------------------------------------------

    def _finish(self) -> None:
        casualties = self.fight.apply_to_army()
        won = self.fight.outcome is Outcome.PLAYER_WIN
        self.set_status(self._outcome_message(won), theme.GOLD if won else theme.RED)
        # Let the final position sit for a beat before the screen changes.
        self.set_timer(
            1.8,
            lambda: self.app.finish_fight(self.run, self.fight, casualties, won),
        )

    def _outcome_message(self, won: bool) -> str:
        board = self.fight.board
        if self.fight.forced:
            return "dev · fight forced to a %s" % ("win" if won else "loss")
        if board.is_checkmate():
            if won:
                return "checkmate — %s falls in %d moves" % (
                    self.fight.enemy_name, self.fight.player_moves)
            return "checkmate — your king has fallen"
        if board.is_stalemate():
            if won:
                return "stalemate — you had no moves, so the enemy loses"
            return "stalemate — you stalemated %s, and lose for it" % self.fight.enemy_name
        return "the position is dead — you failed to win"

    def action_quit(self) -> None:
        self.app.exit()
