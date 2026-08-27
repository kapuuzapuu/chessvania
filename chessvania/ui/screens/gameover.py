"""Victory and defeat."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Center, Middle
from textual.screen import Screen
from textual.widgets import Static

from ... import config
from ...core.run import RunState
from .. import theme


class GameOverScreen(Screen):
    BINDINGS = [
        ("enter", "again", "New run"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, run: RunState, won: bool) -> None:
        super().__init__()
        self.run = run
        self.won = won

    def compose(self) -> ComposeResult:
        with Middle():
            with Center():
                yield Static(self._headline(), id="over-headline")
            with Center():
                yield Static(self._summary(), id="over-summary")

    def _headline(self) -> Text:
        if self.won:
            return Text("THE RUN IS YOURS", style="%s bold" % theme.GOLD)
        return Text("YOUR KING HAS FALLEN", style="%s bold" % theme.RED)

    def _summary(self) -> Text:
        army = self.run.army
        fights = self.run.fight_index + (1 if self.won else 0)
        veterans = [p for p in army.all_pieces() if p.veterancy > 0]

        text = Text()
        if self.won:
            text.append("you cleared all %d fights on stake %s.\n\n"
                        % (len(self.run.ladder), self.run.stake.name), style=theme.TEXT)
        else:
            spec = self.run.current
            enemy = spec.formation.name if spec else "the enemy"
            text.append("felled by %s at ante %d, fight %d.\n\n"
                        % (enemy, self.run.ante, self.run.fight_in_ante), style=theme.TEXT)

        text.append("fights survived   ", style=theme.DIM)
        text.append("%d\n" % fights, style=theme.TEXT)
        text.append("gold unspent      ", style=theme.DIM)
        text.append("%s %d\n" % (config.GOLD_GLYPH, self.run.gold), style=theme.GOLD)
        text.append("army remaining    ", style=theme.DIM)
        text.append("%d on board · %d benched\n" % (army.deployed_count, army.inventory_count),
                    style=theme.TEXT)

        if veterans:
            text.append("\nveterans\n", style=theme.DIM)
            for piece in sorted(veterans, key=lambda p: -p.fights_survived)[:6]:
                text.append("  %s %-7s " % (piece.symbol, piece.name.lower()),
                            style=theme.player_color(piece))
                text.append("%d fights\n" % piece.fights_survived, style=theme.FAINT)

        text.append("\npress ", style=theme.DIM)
        text.append("ENTER", style=theme.GREEN)
        text.append(" for a new run  ·  ", style=theme.DIM)
        text.append("Q", style=theme.GREEN)
        text.append(" to quit", style=theme.DIM)
        return text

    def action_again(self) -> None:
        self.app.open_menu(animate=False)

    def action_quit(self) -> None:
        self.app.exit()
