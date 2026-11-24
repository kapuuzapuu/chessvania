"""What a win pays right now, and how many moves are left at that rate.

Three lines, no sentences:

    PAYOUT
    ◇5 ◇4 ◇3 ◇2 ◇1
    ▏▏▏▏▏▏▏▌▌▌

The LADDER (line 2) is the whole run at a glance. The rung you are on is
lit; the ones behind are ash; the ones ahead dim as they pay less. It is a
fixed row and nothing in it ever moves, so the eye can use position as a
landmark.

Those rungs are stake-adjusted, not the raw tiers: an NG+ payout penalty is
already in the number, so the lit rung is what the board itself owes you and
there is no headline needed to say so. A banked skip bonus is deliberately
NOT folded in -- it is added once, on top, and a ladder that quietly carried
it would read ◇7 with a "+◇2" underneath, which invites you to add them.

The TIER BAR (line 3) is the only thing that moves, and it is exact:

    one tick = one move, always, at every window size.

It covers the tier you are standing in, not the whole ladder, and that is
the trick. The ladder spans 40 moves; one tick per move across all of it
would need 43 columns and the rail is 21, so a whole-ladder bar could only
be drawn at 2.5 moves per cell -- where three moves in five change nothing,
and the scale slides with the window. Scoped to one tier it is always ten
ticks, so every single move spends exactly one and "how many moves until
this drops" is a count rather than an estimate.

Between them the two lines answer the only two questions the economy poses
-- what am I getting, and how long have I got -- with no prose at all. The
bar does not stretch to fill the rail: a bar whose scale depends on the
terminal is a bar you have to re-learn on every resize.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from rich.text import Text
from textual.widgets import Static

from ... import config
from ...core.economy import tier_ladder
from ...core.run import RunState
from .. import theme

LIVE_CELL = "▌"
SPENT_CELL = "▏"
"""HALF BLOCK for a move still in hand, ONE-EIGHTH BLOCK for one already
spent. Both paint only the left of their cell and leave the right as
background, so a run of them is a comb of separate ticks you can count:
▌▌▌ reads as three, where ███ reads as one bar. Each still occupies exactly
one cell, so the scale stays at one tick per move.

Both are FIXED. The marker these replaced was a part-block chosen by the
cursor's sub-cell position, so its width changed as it moved. Here the glyph
means spent or unspent and nothing else, and it says so by thickness as well
as by colour -- the bar still reads on a terminal that mangles the palette."""

SPENT = "#2E2A22"
"""Warm ash for a spent tick: the same bar, visibly dead. Raise it if the
hairlines vanish into the panel in your terminal."""

RUNG_AHEAD = ("#9A7C3A", "#7E6630", "#655228", "#4C3E20", "#3A311D")
"""Rungs you have not fallen to yet, dimming as they pay less."""


class Purse(Static):
    """Reads a `RunState` and a move count; owns no state of its own."""

    def show(self, run: RunState, moves: int) -> None:
        self.update(self._build(run, moves))

    # -- geometry --------------------------------------------------------

    def _rungs(self, run: RunState) -> List[int]:
        """What the board owes at each tier, best first, fallback included.

        Asked of the run rather than read off `config.PAYOUT_TIERS`, so an
        NG+ stake penalty is applied by the one function that owns that
        arithmetic -- the UI does no economy maths.

        `base - stake_penalty` rather than `total`, so the banked skip bonus
        stays out. It is paid once for the fight, not once per tier, and a
        rung that already contained it would be added to the "+ skip bonus"
        line below by anyone reading the panel.
        """
        ladder = tier_ladder()
        probes = [threshold for threshold, _ in ladder] + [ladder[-1][0] + 1]
        quotes = [run.preview_payout(probe) for probe in probes]
        return [quote.base - quote.stake_penalty for quote in quotes]

    def _standing(self, moves: int) -> int:
        """Index into `_rungs()` of the payout a win right now would pay.

        The threshold is inclusive -- on move 10 you are still being paid the
        first tier's rate -- so this is `<=`.
        """
        for index, (threshold, _) in enumerate(tier_ladder()):
            if moves <= threshold:
                return index
        return len(tier_ladder())

    def _tier_span(self, rung: int) -> Optional[Tuple[int, int]]:
        """(first move, last move) of a tier, or None past the ladder."""
        ladder = tier_ladder()
        if rung >= len(ladder):
            return None
        previous = ladder[rung - 1][0] if rung else 0
        return previous, ladder[rung][0]

    def _width(self) -> int:
        return self.content_size.width or 21

    # -- drawing ---------------------------------------------------------

    def _build(self, run: RunState, moves: int) -> Text:
        """Named to avoid shadowing Textual's internal `Widget._render()`."""
        rung = self._standing(moves)

        text = Text()
        text.append("PAYOUT\n", style=theme.DIM)
        text.append_text(self._ladder(run, rung))
        text.append_text(self._bar(moves, rung, self._width()))
        text.append_text(self._skip_bonus(run))
        return text

    def _ladder(self, run: RunState, rung: int) -> Text:
        """The payouts, best to worst.

        Marked by weight and colour rather than by a bracket or a caret: a
        marker that inserts characters shifts every rung after it, and a row
        that reflows every ten moves is a row you cannot use as a landmark.
        """
        text = Text()
        for index, gold in enumerate(self._rungs(run)):
            if index:
                text.append(" ")
            if index == rung:
                style = "%s bold" % theme.GOLD
            elif index < rung:
                style = SPENT
            else:
                style = RUNG_AHEAD[min(index, len(RUNG_AHEAD) - 1)]
            text.append("%s%d" % (config.GOLD_GLYPH, gold), style=style)
        text.append("\n")
        return text

    def _bar(self, moves: int, rung: int, width: int) -> Text:
        """One tick per move of the tier you are standing in, unbroken.

        Past the ladder there is no tier left to spend, so the last one is
        drawn fully drained -- the payout cannot fall any further.
        """
        first, last = self._tier_span(rung) \
            or self._tier_span(len(tier_ladder()) - 1)
        spent = max(0, min(last - first, moves - first))

        text = Text()
        for tick in range(min(last - first, width)):
            if tick < spent:
                text.append(SPENT_CELL, style=SPENT)
            else:
                text.append(LIVE_CELL, style=theme.GOLD)
        text.append("\n")
        return text

    def _skip_bonus(self, run: RunState) -> Text:
        """Carried from a skipped shop, and NOT inside the rungs above.

        It reads as an addition because it is one: lit rung plus this line is
        what you collect. Only drawn when there is one to draw.
        """
        text = Text()
        if run.banked_skip_bonus:
            text.append("+%s%d skip bonus"
                        % (config.GOLD_GLYPH, run.banked_skip_bonus),
                        style=theme.GREEN)
        return text
