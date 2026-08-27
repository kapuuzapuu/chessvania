"""Run state and the phase machine that drives it.

The app maps phases onto screens; it does not decide what comes next. Keeping
the flow here means "a run is nine fights and then a victory" is a unit test
rather than something you confirm by playing for an hour.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from .. import config
from .army import Army, Piece
from .economy import Payout, compute_payout
from .ladder import FightSpec


class Phase(Enum):
    LOADOUT = "loadout"
    FIGHT = "fight"
    POSTFIGHT = "postfight"
    VICTORY = "victory"
    DEFEAT = "defeat"


@dataclass
class RunState:
    """One run, start to finish. One life."""

    army: Army
    ladder: List[FightSpec]
    stake: config.Stake = field(default_factory=lambda: config.STAKES[0])
    gold: int = 0
    fight_index: int = 0
    banked_skip_bonus: int = 0
    phase: Phase = Phase.FIGHT
    run_number: int = 1
    last_casualties: List[Piece] = field(default_factory=list)

    # -- position in the ladder ------------------------------------------

    @property
    def current(self) -> Optional[FightSpec]:
        if self.fight_index >= len(self.ladder):
            return None
        return self.ladder[self.fight_index]

    @property
    def ante(self) -> int:
        spec = self.current
        return spec.ante if spec else config.ANTES

    @property
    def fight_in_ante(self) -> int:
        spec = self.current
        return (spec.index + 1) if spec else config.FIGHTS_PER_ANTE

    @property
    def elo(self) -> int:
        spec = self.current
        return spec.elo if spec else 0

    @property
    def finished(self) -> bool:
        return self.phase in (Phase.VICTORY, Phase.DEFEAT)

    # -- economy ---------------------------------------------------------

    def preview_payout(self, move_count: int) -> Payout:
        """What a win right now would pay -- drives the live readout."""
        return compute_payout(move_count, self.stake, self.banked_skip_bonus)

    def bank_skip_bonus(self) -> None:
        self.banked_skip_bonus += config.SKIP_BONUS

    def collect(self, payout: Payout) -> None:
        self.gold += payout.total
        self.banked_skip_bonus = 0

    def spend(self, amount: int) -> bool:
        if amount > self.gold:
            return False
        self.gold -= amount
        return True

    # -- phase transitions -----------------------------------------------

    def on_fight_won(self, casualties: List[Piece]) -> Phase:
        self.last_casualties = list(casualties)
        if self.fight_index >= len(self.ladder) - 1:
            self.phase = Phase.VICTORY
        else:
            self.phase = Phase.POSTFIGHT
        return self.phase

    def on_fight_lost(self, casualties: Optional[List[Piece]] = None) -> Phase:
        self.last_casualties = list(casualties or [])
        self.phase = Phase.DEFEAT
        return self.phase

    def on_postfight_done(self) -> Phase:
        self.fight_index += 1
        self.phase = Phase.FIGHT if self.current else Phase.VICTORY
        return self.phase


def new_run(
    army: Army,
    ladder: List[FightSpec],
    stake: Optional[config.Stake] = None,
    run_number: int = 1,
) -> RunState:
    return RunState(
        army=army,
        ladder=ladder,
        stake=stake or config.STAKES[0],
        phase=Phase.FIGHT,
        run_number=run_number,
    )
