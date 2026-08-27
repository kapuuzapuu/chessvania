"""The dev-mode diagnostics strip.

Only mounted when `config.DEV_MODE` is on. Compact by default -- one line of
live state, one of shortcuts -- and F1 expands it with the detail you want when
something looks wrong: the FEN, the exact engine lever, the payout breakdown.
"""

from __future__ import annotations

from typing import Optional

import chess
from rich.text import Text
from textual.widgets import Static

from ... import config
from ...core.army import PIECE_VALUES
from ...core.fight import Fight
from ...core.run import RunState
from .. import theme

FIGHT_KEYS = "f1 detail · f2 +gold · f3 win · f4 lose · f5 kill under cursor"
"""Shortcut legend for the fight screen. The keys themselves are declared in
that screen's BINDINGS -- this is only the caption, so keep the two in step."""

POSTFIGHT_KEYS = "f1 detail · f2 +gold · f3 skip phase · f5 refill swaps"
"""Shortcut legend for the post-fight screen. See FIGHT_KEYS."""


class DevBar(Static):
    """Live diagnostics. Never reachable from a menu -- see config.DEV_MODE.

    The owning screen decides whether this is mounted at all and calls `show`
    on every refresh; the widget holds no game state of its own beyond whether
    the detail lines are expanded.
    """

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.expanded = False

    def toggle(self) -> None:
        """Flip between the one-line summary and the full detail block.

        The caller is responsible for redrawing afterwards.
        """
        self.expanded = not self.expanded

    def show(
        self,
        run: RunState,
        fight: Optional[Fight] = None,
        keys: str = FIGHT_KEYS,
        extra: Optional[str] = None,
    ) -> None:
        """Redraw the bar.

        Args:
            run: the live run -- supplies ante, Elo, gold and army totals.
            fight: the fight in progress, if any. Omit on the post-fight screen
                and the fight-specific columns are dropped.
            keys: the shortcut legend to print (FIGHT_KEYS / POSTFIGHT_KEYS).
            extra: one more line of screen-specific detail, shown only while
                expanded. The post-fight screen passes its phase state here.
        """
        text = Text()
        text.append(" DEV ", style="black on %s" % theme.GOLD)
        text.append("  ")
        text.append_text(self._state(run, fight))
        if self.expanded:
            detail = self._detail(run, fight, extra)
            detail.rstrip()  # rich's rstrip mutates in place and returns None
            text.append("\n")
            text.append_text(detail)
        text.append("\n")
        text.append(keys, style=theme.GHOST)
        self.update(text)

    # -- lines -----------------------------------------------------------

    def _state(self, run: RunState, fight: Optional[Fight]) -> Text:
        text = Text()
        text.append("ante %d/%d f%d" % (run.ante, config.ANTES, run.fight_in_ante),
                    style=theme.DIM)
        text.append("  elo ", style=theme.GHOST)
        text.append("%d" % run.elo, style=theme.RED)
        text.append(" (%s)" % self._lever(run.elo), style=theme.GHOST)
        text.append("  gold ", style=theme.GHOST)
        text.append("%d" % run.gold, style=theme.GOLD)
        text.append("  mat ", style=theme.GHOST)
        text.append("%d" % run.army.material(), style=theme.TEXT)
        if fight is not None:
            text.append("v%d" % self._enemy_material(fight), style=theme.RED)
            text.append("  mv ", style=theme.GHOST)
            text.append("%d" % fight.player_moves, style=theme.TEXT)
        return text

    def _detail(self, run: RunState, fight: Optional[Fight], extra: Optional[str]) -> Text:
        text = Text()
        payout = run.preview_payout(fight.player_moves if fight else 0)
        text.append("stake %s" % run.stake.name, style=theme.DIM)
        text.append("  payout %d(base %d, stake -%d, banked +%d)"
                    % (payout.total, payout.base, payout.stake_penalty, payout.skip_bonus),
                    style=theme.GHOST)
        text.append("  board %d bench %d" % (run.army.deployed_count, run.army.inventory_count),
                    style=theme.GHOST)
        text.append("\n")
        if fight is not None:
            text.append("%s  turn=%s\n" % (fight.enemy_name,
                                           "white" if fight.board.turn else "black"),
                        style=theme.DIM)
            text.append("%s\n" % fight.board.fen(), style=theme.FAINT)
        if extra:
            text.append("%s\n" % extra, style=theme.GHOST)
        return text

    @staticmethod
    def _lever(elo: int) -> str:
        strength = config.strength_for(elo)
        if strength.skill_level is not None:
            return "skill %d d%d" % (strength.skill_level, strength.depth)
        return "uci %d d%d" % (strength.uci_elo, strength.depth)

    @staticmethod
    def _enemy_material(fight: Fight) -> int:
        return sum(
            PIECE_VALUES[piece.piece_type]
            for piece in fight.board.piece_map().values()
            if piece.color == chess.BLACK
        )
