"""The bestiary: armies you can field, and enemies you have beaten.

Undefeated enemies show as silhouettes -- you can see how many are out there and
which tier they belong to, but not what they are. Locked loadouts show their
unlock condition rather than being hidden entirely, so there is something to
chase rather than a blank.
"""

from __future__ import annotations

import textwrap

import chess
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

from ... import config
from ...core.army import PIECE_VALUES, army_from_fen
from ...core.progress import BY_ID, Profile
from ...data.enemies import POOLS
from ...data.loadouts import LOADOUTS
from .. import theme

TIER_ORDER = (config.TIER_LOW, config.TIER_MID, config.TIER_MINIBOSS, config.TIER_FINAL)

BLURB_WIDTH = 28
"""Kept under the column's usable width, or the panel re-wraps our wrapped
lines and the hanging indent breaks anyway."""


def _wrap(blurb: str) -> str:
    """Wrap with a hanging indent.

    Letting the panel soft-wrap instead pushes continuation lines back to column
    zero, which breaks the visual grouping of each entry.
    """
    return textwrap.fill(
        blurb, width=BLURB_WIDTH, initial_indent="  ", subsequent_indent="  "
    )


class BestiaryScreen(Screen):
    BINDINGS = [
        ("escape", "back", "Back"),
        ("q", "back", "Back"),
        ("tab", "switch", "Switch column"),
    ]

    def __init__(self, profile: Profile) -> None:
        super().__init__()
        self.profile = profile

    def compose(self) -> ComposeResult:
        yield Static(self._heading(), id="page-heading")
        with Horizontal(id="page-body"):
            with VerticalScroll(classes="page-column"):
                yield Static(self._armies(), id="bestiary-armies")
            with VerticalScroll(classes="page-column"):
                yield Static(self._enemies(), id="bestiary-enemies")
        yield Static(self._foot(), id="page-foot")

    def _heading(self) -> Text:
        text = Text()
        text.append("BESTIARY", style="%s bold" % theme.GOLD)
        known = len(self.profile.defeated)
        total = sum(len(p) for p in POOLS.values())
        text.append("      %d/%d enemies recorded" % (known, total), style=theme.DIM)
        return text

    def _armies(self) -> Text:
        text = Text()
        text.append("YOUR ARMIES\n\n", style=theme.DIM)
        for loadout in LOADOUTS:
            unlocked = self.profile.loadout_unlocked(loadout.unlocked_by)
            army = army_from_fen(loadout.fen)

            if unlocked:
                text.append("%s\n" % loadout.name, style="%s bold" % theme.TEXT)
                counts = {}
                for piece in army.deployment.values():
                    if piece.piece_type != chess.KING:
                        counts[piece.symbol] = counts.get(piece.symbol, 0) + 1
                text.append("  " + "  ".join(
                    "%s×%d" % (g, n) for g, n in counts.items()) + "\n",
                    style=theme.SEASONED)
                text.append("%s\n" % _wrap(loadout.blurb), style=theme.FAINT)
                text.append("  material %d\n\n" % army.material(), style=theme.GHOST)
            else:
                requirement = BY_ID.get(loadout.unlocked_by or "")
                text.append("???\n", style=theme.GHOST)
                text.append("%s\n\n" % _wrap("locked · %s" % (
                    requirement.blurb if requirement else "keep playing")),
                    style=theme.FAINT)
        return text

    def _enemies(self) -> Text:
        text = Text()
        text.append("ENEMIES\n\n", style=theme.DIM)
        for tier in TIER_ORDER:
            pool = POOLS.get(tier, [])
            seen = sum(1 for f in pool if self.profile.knows(f.name))
            text.append("%s " % tier, style=theme.DIM)
            text.append("%d/%d\n" % (seen, len(pool)), style=theme.GHOST)

            for formation in pool:
                if self.profile.knows(formation.name):
                    text.append("  %s" % formation.name, style=theme.TEXT)
                    text.append("  · material %d\n" % self._material(formation.fen),
                                style=theme.FAINT)
                else:
                    text.append("  ???\n", style=theme.GHOST)
            text.append("\n")
        return text

    @staticmethod
    def _material(fen: str) -> int:
        board = chess.Board(fen)
        return sum(PIECE_VALUES[p.piece_type] for p in board.piece_map().values()
                   if p.color == chess.BLACK)

    def _foot(self) -> Text:
        text = Text()
        text.append("esc", style=theme.GREEN)
        text.append(" back to the menu", style=theme.DIM)
        return text

    def action_switch(self) -> None:
        self.focus_next()

    def action_back(self) -> None:
        self.app.open_menu(animate=False)
