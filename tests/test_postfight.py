"""The post-fight phase: ordering, the bench-only purchase rule, swap budget."""

import random

import chess
import pytest

from chessvania import config
from chessvania.core.army import Piece, army_from_fen
from chessvania.core.ladder import build_ladder
from chessvania.core.postfight import PostFight, Slot, Step
from chessvania.core.run import new_run
from chessvania.data.enemies import POOLS

TEXTBOOK = "8/8/8/8/8/8/PPPPPPPP/RNBQKBNR w - - 0 1"
SHIELD = "8/8/8/8/8/8/PPPPPPPP/RN2KN1R w - - 0 1"


def make_run(gold=0, army=None, stake=None):
    stake = stake or config.STAKES[0]
    army = army if army is not None else army_from_fen(TEXTBOOK)
    ladder = build_ladder(POOLS, stake, random.Random(0))
    run = new_run(army, ladder, stake)
    run.gold = gold
    return run


def at_shop(run, move_count=5):
    phase = PostFight(run, move_count, [])
    phase.collect_payout()
    return phase


def at_swap(run):
    phase = at_shop(run)
    phase.close_shop()
    phase.close_sell()
    return phase


# -- step 1: payout -----------------------------------------------------


def test_payout_lands_in_the_purse_and_clears_the_bank():
    run = make_run()
    run.banked_skip_bonus = 2
    phase = PostFight(run, 5, [])
    payout = phase.collect_payout()

    assert run.gold == payout.total
    assert payout.skip_bonus == 2
    assert run.banked_skip_bonus == 0
    assert phase.step is Step.SHOP


# -- step 2: shop -------------------------------------------------------


def test_purchases_go_to_the_bench_not_the_board():
    run = make_run(gold=20)
    phase = at_shop(run)
    board_before = dict(run.army.deployment)

    ok, _ = phase.buy(0)
    assert ok
    assert run.army.deployment == board_before
    assert run.army.inventory_count == 1


def test_buying_costs_gold():
    run = make_run(gold=20)
    phase = at_shop(run)
    before = run.gold
    price = phase.stock[0].price

    phase.buy(0)
    assert run.gold == before - price


def test_cannot_buy_what_you_cannot_afford():
    run = make_run(gold=0)
    phase = at_shop(run)
    run.gold = 0
    ok, reason = phase.buy(len(phase.stock) - 1)
    assert not ok and "gold" in reason


def test_a_full_bench_blocks_buying():
    army = army_from_fen(TEXTBOOK)
    for _ in range(config.INVENTORY_CAP):
        army.add_to_inventory(Piece(chess.PAWN))
    run = make_run(gold=99, army=army)
    phase = at_shop(run)

    ok, reason = phase.buy(0)
    assert not ok and reason == "bench full"


def test_the_shop_never_runs_out():
    """Unlimited buys: the same item can be bought over and over."""
    run = make_run(gold=99)
    phase = at_shop(run)
    for _ in range(6):
        ok, reason = phase.buy(0)
        assert ok, reason
    assert run.army.inventory_count == 6


def test_every_piece_type_is_always_in_stock():
    from chessvania.core.economy import buyable_types

    run = make_run(gold=99)
    phase = at_shop(run)
    assert [item.piece_type for item in phase.stock] == buyable_types()


def test_the_catalogue_is_the_same_every_visit():
    first = at_shop(make_run(gold=99))
    second = at_shop(make_run(gold=99))
    assert [i.piece_type for i in first.stock] == [i.piece_type for i in second.stock]


def test_gold_is_the_binding_constraint():
    run = make_run(gold=0)
    phase = at_shop(run)
    run.gold = 4

    queen = next(i for i, item in enumerate(phase.stock)
                 if item.piece_type == chess.QUEEN)
    ok, reason = phase.buy(queen)
    assert not ok and "gold" in reason

    pawn = next(i for i, item in enumerate(phase.stock)
                if item.piece_type == chess.PAWN)
    assert phase.buy(pawn)[0] is True


def test_repeat_purchases_group_in_the_receipt():
    run = make_run(gold=99)
    phase = at_shop(run)
    for _ in range(3):
        phase.buy(0)
    counts = phase.purchase_counts()
    assert list(counts.values()) == [3]


# -- skipping compounds -------------------------------------------------


def test_skipping_without_spending_banks_a_bonus():
    run = make_run(gold=10)
    phase = at_shop(run)
    purse = run.gold

    assert phase.can_skip is True
    ok, _ = phase.skip_shop()
    assert ok
    assert run.banked_skip_bonus == config.SKIP_BONUS
    assert run.gold == purse  # unspent gold stays, so skipping compounds twice over
    assert phase.step is Step.SELL


def test_spending_forfeits_the_skip_bonus():
    run = make_run(gold=99)
    phase = at_shop(run)
    phase.buy(0)

    assert phase.can_skip is False
    ok, _ = phase.skip_shop()
    assert not ok
    assert run.banked_skip_bonus == 0


def test_skip_preview_reports_the_actual_numbers():
    run = make_run(gold=12)
    phase = at_shop(run)
    kept, bonus = phase.skip_preview()
    assert kept == run.gold
    assert bonus == config.SKIP_BONUS


# -- step 3: sell -------------------------------------------------------


def test_selling_is_locked_until_the_shop_closes():
    army = army_from_fen(TEXTBOOK)
    army.add_to_inventory(Piece(chess.ROOK))
    run = make_run(gold=0, army=army)
    phase = at_shop(run)

    ok, reason = phase.sell(0)
    assert not ok and "shop" in reason

    phase.close_shop()
    ok, _ = phase.sell(0)
    assert ok


def test_selling_pays_and_removes_the_piece():
    from chessvania.core.economy import sell_value

    army = army_from_fen(TEXTBOOK)
    army.add_to_inventory(Piece(chess.QUEEN))
    run = make_run(gold=0, army=army)
    phase = at_shop(run)
    phase.close_shop()
    purse = run.gold

    phase.sell(0)
    assert run.gold == purse + sell_value(chess.QUEEN)
    assert run.army.inventory_count == 0


# -- step 4: swap -------------------------------------------------------


def test_swaps_are_capped():
    run = make_run()
    phase = at_swap(run)
    assert phase.swaps_left == config.MAX_SWAPS

    for square, target in ((chess.A2, chess.A3), (chess.B2, chess.B3), (chess.C2, chess.C3)):
        ok, reason = phase.swap(Slot.on_board(square), Slot.on_board(target))
        assert ok, reason

    assert phase.swaps_left == 0
    ok, reason = phase.swap(Slot.on_board(chess.B2), Slot.on_board(chess.B3))
    assert not ok and "swaps left" in reason


def test_swapping_a_board_piece_to_the_bench():
    run = make_run()
    phase = at_swap(run)
    knight_square = chess.B1

    ok, reason = phase.swap(Slot.on_board(knight_square), Slot.on_bench(0))
    assert ok, reason
    assert knight_square not in run.army.deployment
    assert run.army.inventory[0].piece_type == chess.KNIGHT


def test_deploying_from_the_bench_costs_a_swap():
    # SHIELD leaves room on the board; a full 16-piece army legitimately cannot
    # deploy anything, which the next test covers.
    army = army_from_fen(SHIELD)
    army.add_to_inventory(Piece(chess.QUEEN))
    run = make_run(army=army)
    phase = at_swap(run)

    ok, reason = phase.swap(Slot.on_bench(0), Slot.on_board(chess.E4))
    assert ok, reason
    assert run.army.deployment[chess.E4].piece_type == chess.QUEEN
    assert phase.swaps_left == config.MAX_SWAPS - 1


def test_a_full_board_cannot_take_a_deployment():
    army = army_from_fen(TEXTBOOK)  # already 16 pieces
    army.add_to_inventory(Piece(chess.QUEEN))
    run = make_run(army=army)
    phase = at_swap(run)

    ok, reason = phase.swap(Slot.on_bench(0), Slot.on_board(chess.E4))
    assert not ok and "16" in reason


def test_the_king_cannot_leave_the_board():
    run = make_run()
    phase = at_swap(run)
    ok, reason = phase.swap(Slot.on_board(chess.E1), Slot.on_bench(0))
    assert not ok and "king" in reason
    assert phase.swaps_left == config.MAX_SWAPS


def test_a_pawn_cannot_be_swapped_onto_the_back_rank():
    run = make_run()
    phase = at_swap(run)
    ok, reason = phase.swap(Slot.on_board(chess.A2), Slot.on_board(chess.A8))
    assert not ok
    assert "pawn" in reason


def test_swapping_two_empty_slots_does_nothing():
    run = make_run()
    phase = at_swap(run)
    ok, reason = phase.swap(Slot.on_bench(0), Slot.on_bench(1))
    assert not ok and "empty" in reason


def test_a_failed_swap_does_not_spend_the_budget():
    run = make_run()
    phase = at_swap(run)
    phase.swap(Slot.on_board(chess.E1), Slot.on_bench(0))
    assert phase.swaps_left == config.MAX_SWAPS


def test_finishing_advances_the_run():
    run = make_run()
    phase = at_swap(run)
    start_index = run.fight_index
    phase.finish()
    assert phase.done
    assert run.fight_index == start_index + 1
