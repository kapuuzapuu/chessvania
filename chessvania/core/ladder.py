"""Builds a run's fight sequence and the Elo attached to each fight."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from .. import config


@dataclass(frozen=True)
class Formation:
    """An enemy army, stored as an ordinary FEN."""

    name: str
    tier: str
    fen: str


@dataclass(frozen=True)
class FightSpec:
    """Everything needed to start one fight."""

    ante: int
    index: int
    tier: str
    formation: Formation
    elo: int

    @property
    def label(self) -> str:
        return "%s · %s" % (self.formation.name, self.tier)

    @property
    def is_final(self) -> bool:
        return self.tier == config.TIER_FINAL


def boss_tier(ante: int) -> str:
    """Antes 1-2 end in a mini-boss; ante 3 ends the run."""
    return config.TIER_FINAL if ante == config.ANTES else config.TIER_MINIBOSS


def tier_for_slot(ante: int, index: int) -> str:
    if index == 0:
        return config.TIER_LOW
    if index == 1:
        return config.TIER_MID
    return boss_tier(ante)


def build_ladder(
    pools: Dict[str, Sequence[Formation]],
    stake: config.Stake,
    rng: Optional[random.Random] = None,
) -> List[FightSpec]:
    """Draw one formation per slot and stamp each fight with its Elo.

    Formations are drawn without replacement per tier where the pool allows, so
    a single run does not repeat an enemy unless the library is too small.
    """
    rng = rng or random.Random()
    remaining = {tier: list(entries) for tier, entries in pools.items()}
    specs: List[FightSpec] = []

    for ante in range(1, config.ANTES + 1):
        for index in range(config.FIGHTS_PER_ANTE):
            tier = tier_for_slot(ante, index)
            formation = _draw(remaining, tier)
            elo = config.ELO_RAMP[ante][index] + stake.elo_bonus
            specs.append(
                FightSpec(
                    ante=ante,
                    index=index,
                    tier=tier,
                    formation=formation,
                    elo=elo,
                )
            )
    return specs


def _draw(remaining: Dict[str, List[Formation]], tier: str) -> Formation:
    bucket = remaining.get(tier)
    if not bucket:
        raise ValueError("no formations available for tier %r" % tier)
    choice = bucket.pop(random.randrange(len(bucket)) if len(bucket) > 1 else 0)
    if not bucket:
        # Pool exhausted: allow reuse rather than failing the run.
        remaining[tier] = [choice]
    return choice
