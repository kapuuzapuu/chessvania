"""Achievements, unlocks and the bestiary record -- all without touching disk."""

import random

import chess

from chessvania import config
from chessvania.core.army import Piece, army_from_fen
from chessvania.core.ladder import build_ladder
from chessvania.core.progress import (
    ACHIEVEMENTS,
    BY_ID,
    Profile,
    ProgressEvent,
    evaluate,
)
from chessvania.core.run import new_run
from chessvania.data.enemies import POOLS
from chessvania.data.loadouts import LOADOUTS

TEXTBOOK = "8/8/8/8/8/8/PPPPPPPP/RNBQKBNR w - - 0 1"


def make_run():
    stake = config.STAKES[0]
    return new_run(army_from_fen(TEXTBOOK), build_ladder(POOLS, stake, random.Random(0)), stake)


def event(profile, **kwargs):
    return ProgressEvent(run=kwargs.pop("run", make_run()), profile=profile, **kwargs)


# -- the catalogue ------------------------------------------------------


def test_achievement_ids_are_unique():
    ids = [a.id for a in ACHIEVEMENTS]
    assert len(ids) == len(set(ids))


def test_every_achievement_has_a_check():
    from chessvania.core.progress import CHECKS

    assert {a.id for a in ACHIEVEMENTS} <= set(CHECKS)


# -- earning ------------------------------------------------------------


def test_first_win_earns_first_blood():
    profile = Profile()
    fresh = evaluate(event(profile, won_fight=True, fight_moves=30, casualties=2))
    assert "first_blood" in {a.id for a in fresh}
    assert profile.has("first_blood")


def test_achievements_are_only_awarded_once():
    profile = Profile()
    evaluate(event(profile, won_fight=True, fight_moves=30, casualties=2))
    again = evaluate(event(profile, won_fight=True, fight_moves=30, casualties=2))
    assert "first_blood" not in {a.id for a in again}


def test_losing_earns_nothing_win_shaped():
    profile = Profile()
    fresh = {a.id for a in evaluate(event(profile, won_fight=False))}
    assert "first_blood" not in fresh
    assert "untouched" not in fresh


def test_blitz_tracks_the_top_payout_tier():
    fastest = config.PAYOUT_TIERS[0][0]
    quick = Profile()
    assert "blitz" in {a.id for a in evaluate(
        event(quick, won_fight=True, fight_moves=fastest, casualties=0))}

    slow = Profile()
    assert "blitz" not in {a.id for a in evaluate(
        event(slow, won_fight=True, fight_moves=fastest + 1, casualties=0))}


def test_untouched_requires_no_casualties():
    clean = Profile()
    assert "untouched" in {a.id for a in evaluate(
        event(clean, won_fight=True, fight_moves=30, casualties=0))}

    bloodied = Profile()
    assert "untouched" not in {a.id for a in evaluate(
        event(bloodied, won_fight=True, fight_moves=30, casualties=1))}


def test_boss_achievement_needs_a_boss():
    profile = Profile()
    assert "first_boss" not in {a.id for a in evaluate(
        event(profile, won_fight=True, tier=config.TIER_LOW))}
    assert "first_boss" in {a.id for a in evaluate(
        event(profile, won_fight=True, tier=config.TIER_MINIBOSS))}


def test_ante_up_fires_on_the_last_fight_of_an_ante():
    run = make_run()
    run.fight_index = config.FIGHTS_PER_ANTE - 1
    profile = Profile()
    assert "ante_up" in {a.id for a in evaluate(
        event(profile, run=run, won_fight=True))}


def test_veteran_reads_the_army():
    run = make_run()
    profile = Profile()
    assert "veteran" not in {a.id for a in evaluate(event(profile, run=run))}

    list(run.army.deployment.values())[0].fights_survived = config.VETERAN_THRESHOLDS[1]
    assert "veteran" in {a.id for a in evaluate(event(profile, run=run))}


def test_miser_counts_skips_within_the_run():
    profile = Profile()
    profile.shop_skips_this_run = 2
    assert "miser" not in {a.id for a in evaluate(event(profile))}
    profile.shop_skips_this_run = 3
    assert "miser" in {a.id for a in evaluate(event(profile))}


def test_champion_is_secret_and_needs_a_won_run():
    assert BY_ID["champion"].secret is True
    profile = Profile()
    assert "champion" not in {a.id for a in evaluate(event(profile, won_fight=True))}
    assert "champion" in {a.id for a in evaluate(event(profile, run_won=True))}


def test_starting_a_run_resets_the_per_run_counter():
    profile = Profile()
    profile.shop_skips_this_run = 3
    profile.start_run()
    assert profile.shop_skips_this_run == 0
    assert profile.runs_played == 1


# -- bestiary and unlocks -----------------------------------------------


def test_defeats_are_recorded_once():
    profile = Profile()
    assert profile.record_defeat("the basilisk") is True
    assert profile.record_defeat("the basilisk") is False
    assert profile.knows("the basilisk")
    assert not profile.knows("the gorgon")


def test_loadouts_without_a_condition_are_always_available():
    profile = Profile()
    always = [lo for lo in LOADOUTS if lo.unlocked_by is None]
    assert always, "expected some unconditional loadouts"
    for loadout in always:
        assert profile.loadout_unlocked(loadout.unlocked_by)


def test_locked_loadouts_open_with_their_achievement():
    locked = [lo for lo in LOADOUTS if lo.unlocked_by]
    assert locked, "expected some locked loadouts"
    loadout = locked[0]

    profile = Profile()
    assert not profile.loadout_unlocked(loadout.unlocked_by)
    profile.earned.add(loadout.unlocked_by)
    assert profile.loadout_unlocked(loadout.unlocked_by)


def test_every_unlock_condition_names_a_real_achievement():
    for loadout in LOADOUTS:
        if loadout.unlocked_by:
            assert loadout.unlocked_by in BY_ID, loadout.name


def test_completion_string():
    profile = Profile()
    assert profile.completion == "0/%d" % len(ACHIEVEMENTS)
    profile.earned.add("first_blood")
    assert profile.completion == "1/%d" % len(ACHIEVEMENTS)
