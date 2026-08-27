"""Progression that outlives a single run: achievements, unlocks, the bestiary.

A `Profile` is everything the player keeps when a run ends. It is plain data
with plain rules -- reading and writing it to disk is `persistence`'s job, not
this module's, so all of this is testable without touching a filesystem.

Run state and profile state are deliberately separate. A run is one life and
dies with you; a profile accumulates across every run you ever play.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set

from .. import config
from .run import RunState


@dataclass(frozen=True)
class Achievement:
    id: str
    name: str
    blurb: str
    secret: bool = False
    """Secret achievements show as '???' until earned."""


ACHIEVEMENTS: List[Achievement] = [
    Achievement("first_blood", "First Blood", "win your first fight"),
    Achievement("blitz", "Blitz", "win a fight in 10 moves or fewer"),
    Achievement("untouched", "Untouched", "win a fight without losing a piece"),
    Achievement("ante_up", "Ante Up", "clear an entire ante"),
    Achievement("first_boss", "Trophy Hunter", "defeat a mini-boss"),
    Achievement("veteran", "Old Guard", "keep a piece alive for six fights"),
    Achievement("miser", "Miser", "skip the shop three times in one run"),
    Achievement("full_bench", "Hoarder", "fill all sixteen bench slots"),
    Achievement("bare_bones", "Bare Bones", "win a fight with five pieces or fewer"),
    Achievement("champion", "Champion", "win a run", secret=True),
]

BY_ID: Dict[str, Achievement] = {a.id: a for a in ACHIEVEMENTS}


@dataclass
class Profile:
    """Everything that survives a run ending."""

    defeated: Set[str] = field(default_factory=set)
    """Enemy formation names the player has beaten -- drives the bestiary."""

    earned: Set[str] = field(default_factory=set)
    """Achievement ids."""

    runs_played: int = 0
    runs_won: int = 0
    highest_stake: int = 1
    shop_skips_this_run: int = 0
    """Reset when a run starts; the Miser achievement reads it."""

    # -- queries ---------------------------------------------------------

    def has(self, achievement_id: str) -> bool:
        return achievement_id in self.earned

    def knows(self, enemy_name: str) -> bool:
        return enemy_name in self.defeated

    def loadout_unlocked(self, unlocked_by: Optional[str]) -> bool:
        """Loadouts with no condition are always available."""
        return unlocked_by is None or self.has(unlocked_by)

    @property
    def completion(self) -> str:
        return "%d/%d" % (len(self.earned), len(ACHIEVEMENTS))

    # -- mutation --------------------------------------------------------

    def start_run(self) -> None:
        self.runs_played += 1
        self.shop_skips_this_run = 0

    def record_defeat(self, enemy_name: str) -> bool:
        """Returns True the first time this enemy is beaten."""
        if enemy_name in self.defeated:
            return False
        self.defeated.add(enemy_name)
        return True


@dataclass
class ProgressEvent:
    """What just happened, for the achievement checks to read."""

    run: RunState
    profile: Profile
    won_fight: bool = False
    fight_moves: int = 0
    casualties: int = 0
    enemy: Optional[str] = None
    tier: Optional[str] = None
    run_won: bool = False


def _cleared_an_ante(event: ProgressEvent) -> bool:
    """True on winning the last fight of any ante."""
    spec = event.run.current
    if spec is None:
        return event.won_fight
    return event.won_fight and spec.index == config.FIGHTS_PER_ANTE - 1


CHECKS: Dict[str, Callable[[ProgressEvent], bool]] = {
    "first_blood": lambda e: e.won_fight,
    "blitz": lambda e: e.won_fight and e.fight_moves <= config.PAYOUT_TIERS[0][0],
    "untouched": lambda e: e.won_fight and e.casualties == 0,
    "ante_up": _cleared_an_ante,
    "first_boss": lambda e: e.won_fight and e.tier in (
        config.TIER_MINIBOSS, config.TIER_FINAL),
    "veteran": lambda e: any(
        p.fights_survived >= config.VETERAN_THRESHOLDS[1]
        for p in e.run.army.all_pieces()
    ),
    "miser": lambda e: e.profile.shop_skips_this_run >= 3,
    "full_bench": lambda e: e.run.army.inventory_full,
    "bare_bones": lambda e: e.won_fight and e.run.army.deployed_count <= 5,
    "champion": lambda e: e.run_won,
}


def evaluate(event: ProgressEvent) -> List[Achievement]:
    """Award anything newly earned, and return it so the UI can announce it."""
    fresh: List[Achievement] = []
    for achievement in ACHIEVEMENTS:
        if event.profile.has(achievement.id):
            continue
        check = CHECKS.get(achievement.id)
        if check and check(event):
            event.profile.earned.add(achievement.id)
            fresh.append(achievement)
    return fresh
