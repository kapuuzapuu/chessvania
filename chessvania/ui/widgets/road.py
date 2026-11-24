"""Where you are in the nine fights, drawn rather than counted.

Three rows, one per ante, each holding two fights and the boss that closes it.
A run is short enough that the whole thing fits in the rail, so the question
"how much is left?" is answered by looking rather than by reading a number --
which is why there is no "4/9" beside the title. The filled nodes already say
it, and saying it twice only invites the two to disagree.

    PROGRESS MAP
    1 ■ ─ □ ─ ◆
    2 □ ─ □ ─ ◆
    3 □ ─ □ ─ ◆

Filled teal is where you are. Dim filled is behind you. Hollow is ahead. The
boss of each ante is a diamond rather than a square, in vermilion once you can
see it coming, so the shape of the climb reads before any of the text does.
"""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from ... import config
from ...core.run import RunState
from .. import theme

# Antes are numbered in ARABIC. Roman numerals belong to the enemy tiers
# (`config.TIER_I`..`TIER_IV`); a screen that used both would make "III" mean
# two different things at once.

FIGHT_DONE = "■"
FIGHT_HERE = "■"
FIGHT_AHEAD = "□"
BOSS = "◆"
BOSS_AHEAD = "◇"
CONNECTOR = " ─ "


class Road(Static):
    """The run's progress map. Reads `RunState`; owns no state of its own."""

    def show(self, run: RunState) -> None:
        self.update(self._build(run))

    def _build(self, run: RunState) -> Text:
        """Named to avoid shadowing Textual's internal `Widget._render()`."""
        text = Text()
        text.append("PROGRESS MAP\n", style=theme.DIM)
        for ante in range(1, config.ANTES + 1):
            text.append_text(self._ante_row(run, ante))
        return text

    def _ante_row(self, run: RunState, ante: int) -> Text:
        here = run.ante == ante and run.current is not None
        text = Text()
        # Flush left, on the same margin as the bench below it. Right-aligning
        # the numeral indented the whole map and left the column looking like
        # two different lists.
        text.append("%-*d " % (len(str(config.ANTES)), ante),
                    style="%s bold" % theme.TEXT if here else theme.GHOST)

        for index in range(config.FIGHTS_PER_ANTE):
            if index:
                text.append(CONNECTOR, style=theme.GHOST)
            text.append_text(self._node(run, ante, index))
        text.append("\n")
        return text

    def _node(self, run: RunState, ante: int, index: int) -> Text:
        """One fight. The last of each ante is its boss."""
        position = (ante - 1) * config.FIGHTS_PER_ANTE + index
        is_boss = index == config.FIGHTS_PER_ANTE - 1
        current = position == run.fight_index
        cleared = position < run.fight_index

        if is_boss:
            glyph = BOSS if cleared or current else BOSS_AHEAD
            if current:
                style = "%s bold" % theme.VERMILION
            elif cleared:
                style = theme.VERMILION_DIM
            else:
                style = theme.VERMILION_DIM
        else:
            glyph = FIGHT_HERE if current else (
                FIGHT_DONE if cleared else FIGHT_AHEAD)
            if current:
                style = "%s bold" % theme.TEAL
            elif cleared:
                style = theme.LABEL
            else:
                style = theme.RULE_STRONG
        return Text(glyph, style=style)
