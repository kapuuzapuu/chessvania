"""Pick a starting army and a stake, then start the run."""

from __future__ import annotations

import chess
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Center, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Select, Static

from ... import config
from ...core.army import army_from_fen
from ...data.loadouts import LOADOUTS
from .. import theme


class LoadoutScreen(Screen):
    BINDINGS = [("escape", "back", "Back")]

    def __init__(self, profile=None) -> None:
        super().__init__()
        from ...core.progress import Profile

        self.profile = profile if profile is not None else Profile()
        self.available = [
            loadout for loadout in LOADOUTS
            if self.profile.loadout_unlocked(loadout.unlocked_by)
        ]

    def compose(self) -> ComposeResult:
        yield Static(self._heading(), id="loadout-heading")
        with Horizontal(id="loadout-row"):
            for index, loadout in enumerate(self.available):
                with Vertical(classes="loadout-card"):
                    yield Static(self._card(loadout), classes="loadout-body")
                    yield Button("take %s" % loadout.name, id="pick-%d" % index)
        with Center():
            yield Select(
                [(s.name, i) for i, s in enumerate(config.STAKES)],
                value=0,
                allow_blank=False,
                id="stake",
            )
        yield Static(self._stake_note(config.STAKES[0]), id="stake-note")

    def _heading(self) -> Text:
        text = Text()
        text.append("CHOOSE YOUR ARMY\n", style="%s bold" % theme.GOLD)
        text.append(
            "it persists for the whole run. what dies, stays dead.",
            style=theme.DIM,
        )
        return text

    def _card(self, loadout) -> Text:
        army = army_from_fen(loadout.fen)
        counts = {}
        for piece in army.deployment.values():
            if piece.piece_type != chess.KING:
                counts[piece.symbol] = counts.get(piece.symbol, 0) + 1

        text = Text()
        text.append("%s\n" % loadout.name.upper(), style="%s bold" % theme.TEXT)
        text.append("%s\n\n" % loadout.blurb, style=theme.DIM)
        text.append("  ".join("%s×%d" % (g, n) for g, n in counts.items()) + "\n",
                    style=theme.SEASONED)
        text.append("material %d · %d pieces" % (army.material(), army.deployed_count),
                    style=theme.FAINT)
        return text

    def _stake_note(self, stake: config.Stake) -> Text:
        text = Text()
        text.append("stake: ", style=theme.DIM)
        text.append(stake.name, style=theme.GOLD)
        parts = []
        if stake.elo_bonus:
            parts.append("every fight +%d elo" % stake.elo_bonus)
        if stake.payout_penalty:
            parts.append("payouts −%d" % stake.payout_penalty)
        text.append("  " + (" · ".join(parts) if parts else "the base ladder"),
                    style=theme.FAINT)
        return text

    def on_select_changed(self, event: Select.Changed) -> None:
        stake = config.STAKES[int(event.value)]
        self.query_one("#stake-note", Static).update(self._stake_note(stake))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if not event.button.id or not event.button.id.startswith("pick-"):
            return
        index = int(event.button.id.split("-")[1])
        stake_index = int(self.query_one("#stake", Select).value)
        self.app.start_run(self.available[index], config.STAKES[stake_index])

    def action_back(self) -> None:
        self.app.open_menu(animate=False)
