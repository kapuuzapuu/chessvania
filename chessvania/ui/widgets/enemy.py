"""Who you are fighting, in the top right.

Three facts and no prose: the name, the tier it belongs to, and the Elo the
engine is actually playing at. The name leads because it is the thing you
remember a fight by; the other two qualify it.

    THE SOVEREIGN
    TIER IV · ELO 2200

Tier is vermilion because vermilion means THEM, and it is the only word on
screen that says how hard this is about to be. The Elo is the real number
handed to Stockfish, not a label -- see `config.strength_for`.
"""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from ...core.fight import Fight
from .. import theme


class EnemyCard(Static):
    """Reads a `Fight`; owns no state of its own."""

    def show(self, fight: Fight) -> None:
        self.update(self._build(fight))

    def _build(self, fight: Fight) -> Text:
        """Named to avoid shadowing Textual's internal `Widget._render()`."""
        text = Text()
        text.append("%s\n" % fight.enemy_name.upper(), style="%s bold" % theme.TEXT)
        text.append("TIER %s" % fight.tier, style=theme.VERMILION)
        text.append(" · ", style=theme.GHOST)
        text.append("ELO ", style=theme.DIM)
        text.append("%d" % fight.elo, style=theme.TEXT)
        return text
