"""The persistent status strip: title, enemy, and run counters."""

from __future__ import annotations

from typing import Optional

from rich.text import Text
from textual.widgets import Static

from ... import config
from ...core.run import RunState
from .. import theme


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

    def _paint(self) -> None:
        """Named to avoid shadowing Textual's internal Widget._render()."""
        run = getattr(self, "_run", None)
        if run is None:
            return
        subtitle = getattr(self, "_subtitle", None) or ""

        line = Text()
        line.append("%s CHESSVANIA" % config.GOLD_GLYPH, style="%s bold" % theme.GOLD)

        right = Text()
        right.append("RUN ", style=theme.DIM)
        right.append("%02d" % run.run_number, style=theme.TEXT)
        right.append("   ANTE ", style=theme.DIM)
        right.append("%d" % run.ante, style=theme.TEXT)
        right.append("/%d" % config.ANTES, style=theme.GHOST)
        right.append("   FIGHT ", style=theme.DIM)
        right.append("%d" % run.fight_in_ante, style=theme.TEXT)
        right.append("/%d" % config.FIGHTS_PER_ANTE, style=theme.GHOST)
        right.append("   ELO ", style=theme.DIM)
        right.append("%d" % run.elo, style=theme.RED)
        right.append("   GOLD ", style=theme.DIM)
        right.append(
            "%s %d" % (config.GOLD_GLYPH, self._displayed_gold), style=theme.GOLD
        )

        # content_size excludes padding; using self.size here overruns and the
        # gold counter gets clipped off the right edge.
        width = self.content_size.width or self.size.width

        # The counters are load-bearing and the enemy's name is flavour, so when
        # the bar is too narrow it is the name that gives way, not the gold.
        room = width - line.cell_len - right.cell_len - 4
        if subtitle and room > 1:
            if len(subtitle) > room:
                subtitle = subtitle[: room - 1] + "…"
            line.append("   ")
            line.append(subtitle, style=theme.DIM)

        pad = max(1, width - line.cell_len - right.cell_len)
        line.append(" " * pad)
        line.append_text(right)
        self.update(line)
