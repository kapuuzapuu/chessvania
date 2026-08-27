"""Ladder construction and the run phase machine."""

import random

from chessvania import config
from chessvania.core.army import army_from_fen
from chessvania.core.ladder import build_ladder, tier_for_slot
from chessvania.core.run import Phase, new_run
from chessvania.data.enemies import POOLS

TEXTBOOK = "8/8/8/8/8/8/PPPPPPPP/RNBQKBNR w - - 0 1"

TOTAL_FIGHTS = config.ANTES * config.FIGHTS_PER_ANTE


def make_ladder(stake=None, seed=0):
    return build_ladder(POOLS, stake or config.STAKES[0], random.Random(seed))


def make_run(stake=None, seed=0):
    stake = stake or config.STAKES[0]
    return new_run(army_from_fen(TEXTBOOK), make_ladder(stake, seed), stake)


# -- the ladder ---------------------------------------------------------


def test_a_run_is_nine_fights():
    assert len(make_ladder()) == TOTAL_FIGHTS


def test_difficulty_never_regresses():
    elos = [spec.elo for spec in make_ladder()]
    assert elos == sorted(elos)
    assert len(set(elos)) == len(elos)


def test_each_ante_floor_beats_the_previous_ceiling():
    for ante in range(1, config.ANTES):
        assert config.ELO_RAMP[ante + 1][0] > config.ELO_RAMP[ante][2]


def test_tier_shape_within_each_ante():
    ladder = make_ladder()
    for ante in range(1, config.ANTES + 1):
        slice_ = [s for s in ladder if s.ante == ante]
        assert [s.tier for s in slice_] == [
            tier_for_slot(ante, i) for i in range(config.FIGHTS_PER_ANTE)
        ]


def test_the_run_ends_on_a_final_boss():
    ladder = make_ladder()
    assert ladder[-1].tier == config.TIER_FINAL
    assert ladder[-1].is_final
    assert sum(1 for s in ladder if s.tier == config.TIER_MINIBOSS) == config.ANTES - 1


def test_formations_match_their_tier():
    for spec in make_ladder():
        assert spec.formation.tier == spec.tier


def test_stake_elo_bonus_shifts_the_whole_ramp():
    base = [s.elo for s in make_ladder(config.STAKES[0])]
    sharpened = config.STAKES[1]
    raised = [s.elo for s in make_ladder(sharpened)]
    assert raised == [e + sharpened.elo_bonus for e in base]


# -- the phase machine --------------------------------------------------


def test_winning_a_mid_ladder_fight_opens_the_post_fight_phase():
    run = make_run()
    assert run.on_fight_won([]) is Phase.POSTFIGHT


def test_winning_the_last_fight_ends_the_run():
    run = make_run()
    run.fight_index = TOTAL_FIGHTS - 1
    assert run.on_fight_won([]) is Phase.VICTORY


def test_losing_ends_the_run_immediately():
    run = make_run()
    assert run.on_fight_lost([]) is Phase.DEFEAT
    assert run.finished


def test_a_full_run_is_eight_post_fight_phases_then_victory():
    run = make_run()
    postfights = 0
    for _ in range(TOTAL_FIGHTS):
        phase = run.on_fight_won([])
        if phase is Phase.VICTORY:
            break
        postfights += 1
        run.on_postfight_done()

    assert postfights == TOTAL_FIGHTS - 1
    assert run.phase is Phase.VICTORY


def test_counters_track_position_in_the_ladder():
    run = make_run()
    seen = []
    for _ in range(TOTAL_FIGHTS):
        seen.append((run.ante, run.fight_in_ante))
        run.on_fight_won([])
        run.on_postfight_done()

    assert seen[0] == (1, 1)
    assert seen[3] == (2, 1)
    assert seen[-1] == (config.ANTES, config.FIGHTS_PER_ANTE)


def test_gold_cannot_be_overspent():
    run = make_run()
    run.gold = 3
    assert run.spend(5) is False
    assert run.gold == 3
    assert run.spend(3) is True
    assert run.gold == 0
