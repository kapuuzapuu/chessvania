import chess

from chessvania import config
from chessvania.core.economy import (
    base_payout,
    compute_payout,
    price_of,
    sell_value,
    tier_for,
)


def test_payout_decreases_as_moves_increase():
    payouts = [base_payout(n) for n in (5, 15, 25, 40, 90)]
    assert payouts == sorted(payouts, reverse=True)
    assert payouts[0] > payouts[-1]


def test_tier_boundaries_are_inclusive():
    first_threshold, first_gold = config.PAYOUT_TIERS[0]
    assert base_payout(first_threshold) == first_gold
    assert base_payout(first_threshold + 1) < first_gold


def test_past_the_last_tier_pays_the_fallback():
    last_threshold = config.PAYOUT_TIERS[-1][0]
    assert tier_for(last_threshold + 1) is None
    assert base_payout(last_threshold + 1) == config.PAYOUT_FALLBACK


def test_stake_penalty_never_pushes_below_the_floor():
    brutal = config.Stake("Test", payout_penalty=99)
    payout = compute_payout(5, brutal)
    assert payout.total == config.MIN_PAYOUT


def test_banked_skip_bonus_adds_on_top():
    plain = compute_payout(5, config.STAKES[0])
    banked = compute_payout(5, config.STAKES[0], skip_bonus=2)
    assert banked.total == plain.total + 2
    assert banked.skip_bonus == 2


def test_payout_itemises_its_working():
    stake = config.Stake("Lean", payout_penalty=1)
    payout = compute_payout(5, stake, skip_bonus=3)
    assert payout.base == 5
    assert payout.stake_penalty == 1
    assert payout.total == payout.base - payout.stake_penalty + payout.skip_bonus


def test_sell_is_half_price_with_a_floor():
    assert sell_value(chess.QUEEN) == price_of(chess.QUEEN) // 2
    assert sell_value(chess.PAWN) >= config.MIN_SELL


def test_kings_are_not_for_sale():
    from chessvania.core.economy import buyable_types

    assert chess.KING not in buyable_types()
