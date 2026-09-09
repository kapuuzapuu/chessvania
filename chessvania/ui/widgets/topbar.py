"""The persistent status strip: title, enemy, and run counters."""

from __future__ import annotations

from typing import Optional

from rich.text import Text
from textual.widgets import Static

from ... import config
from ...core.run import RunState
from .. import theme


COUNTER_TIERS = ((False, 3), (False, 1), (True, 1))
"""(short labels?, gutter width), roomiest first.

The bar walks down this list until the enemy's name fits whole. Full words with
generous gutters when there is space; single letters packed tight when there is
not. The counters themselves are never cut -- losing half of "GOLD" tells you
less than nothing.
"""

SUBTITLE_GAP = 3
"""Columns between the game title and the enemy's name."""

MIN_PAD = 1
"""Columns kept between the name and the counters so they never touch.

Reserved when working out how much room the name has, not added afterwards --
adding it afterwards is what made the bar one column too wide at some widths."""


class TopBar(Static):
    """Left: game + current enemy. Right: RUN / ANTE / FIGHT / ELO / GOLD.

    No HP -- you lose by being checkmated, not by a health bar.
    """

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._displayed_gold = 0
        self._target_gold = 0

    def show(self, run: RunState, subtitle: Optional[str] = None) -> None:
        self._target_gold = run.gold
        if self._displayed_gold != run.gold and not self._ticking():
            self._displayed_gold = run.gold
        self._run = run
        self._subtitle = subtitle
        self._paint()

    def _ticking(self) -> bool:
        return getattr(self, "_tick_timer", None) is not None

    def tick_gold_to(self, target: int, step_seconds: float = 0.06) -> None:
        """Count the gold counter up rather than snapping. It is the reward beat."""
        self._target_gold = target
        if self._displayed_gold == target:
            return
        if self._ticking():
            return
        self._tick_timer = self.set_interval(step_seconds, self._advance_gold)

    def _advance_gold(self) -> None:
        if self._displayed_gold < self._target_gold:
            self._displayed_gold += 1
        elif self._displayed_gold > self._target_gold:
            self._displayed_gold -= 1
        else:
            timer = getattr(self, "_tick_timer", None)
            if timer is not None:
                timer.stop()
                self._tick_timer = None
            return
        self._paint()

    def on_resize(self, event=None) -> None:
        """Re-lay out once the real width is known (and whenever it changes)."""
        self._paint()

    def _counter_groups(self, run: RunState, short: bool) -> list:
        """The five counters, each as its own Text so they can be spaced apart.

        `short` swaps the words for single letters. Gold drops its label
        entirely -- the coin glyph already says what the number is.
        """
        groups = []

        group = Text()
        group.append("R" if short else "RUN ", style=theme.DIM)
        group.append("%02d" % run.run_number, style=theme.TEXT)
        groups.append(group)

        group = Text()
        group.append("A" if short else "ANTE ", style=theme.DIM)
        group.append("%d" % run.ante, style=theme.TEXT)
        group.append("/%d" % config.ANTES, style=theme.GHOST)
        groups.append(group)

        group = Text()
        group.append("F" if short else "FIGHT ", style=theme.DIM)
        group.append("%d" % run.fight_in_ante, style=theme.TEXT)
        group.append("/%d" % config.FIGHTS_PER_ANTE, style=theme.GHOST)
        groups.append(group)

        group = Text()
        group.append("E" if short else "ELO ", style=theme.DIM)
        group.append("%d" % run.elo, style=theme.RED)
        groups.append(group)

        group = Text()
        if not short:
            group.append("GOLD ", style=theme.DIM)
        group.append(
            "%s%s%d" % (config.GOLD_GLYPH, "" if short else " ", self._displayed_gold),
            style=theme.GOLD,
        )
        groups.append(group)

        return groups

    def _counters(self, run: RunState, short: bool, gutter: int) -> Text:
        text = Text()
        for index, group in enumerate(self._counter_groups(run, short)):
            if index:
                text.append(" " * gutter)
            text.append_text(group)
        return text

    def _paint(self) -> None:
        """Named to avoid shadowing Textual's internal Widget._render()."""
        run = getattr(self, "_run", None)
        if run is None:
            return
        subtitle = getattr(self, "_subtitle", None) or ""

        title = Text()
        title.append("%s CHESSVANIA" % config.GOLD_GLYPH, style="%s bold" % theme.GOLD)

        # content_size excludes padding; using self.size here overruns and the
        # gold counter gets clipped off the right edge.
        width = self.content_size.width or self.size.width

        # Step down through the tiers and take the first that leaves the enemy's
        # name room to be written out in full. The counters are load-bearing, so
        # they are never truncated -- but they are allowed to get terser, which
        # is what stops the name from being the only thing that ever gives way.
        # If even the tightest tier cannot fit the name, the name still yields.
        right = None
        room = 0
        for short, gutter in COUNTER_TIERS:
            right = self._counters(run, short, gutter)
            room = (width - title.cell_len - right.cell_len
                    - SUBTITLE_GAP - MIN_PAD)
            if not subtitle or room >= len(subtitle):
                break

        line = Text()
        line.append_text(title)
        if subtitle and room > 1:
            if len(subtitle) > room:
                subtitle = subtitle[: room - 1] + "…"
            line.append(" " * SUBTITLE_GAP)
            line.append(subtitle, style=theme.DIM)

        # Never negative: at a width where even the tightest tier does not
        # fit, the counters run on and the terminal clips them.
        pad = max(0, width - line.cell_len - right.cell_len)
        line.append(" " * pad)
        line.append_text(right)
        self.update(line)
