"""Fight resolution, move counting, and piece identity.

Every test here runs without a Stockfish binary -- the opponent is injected, so
`core` never needs the engine.
"""

import chess
import pytest

from chessvania.core.army import army_from_fen
from chessvania.core.fight import Fight, Outcome


def scripted(*ucis):
    """An opponent that plays a fixed sequence."""
    moves = list(ucis)

    def opponent(board):
        return chess.Move.from_uci(moves.pop(0))

    return opponent


def first_legal(board):
    return next(iter(board.legal_moves))


def make_fight(army_fen, enemy_fen, opponent=first_legal):
    return Fight(
        army=army_from_fen(army_fen),
        enemy_fen=enemy_fen,
        opponent=opponent,
    )


# -- outcomes -----------------------------------------------------------


def test_checkmating_the_enemy_wins():
    fight = make_fight("8/8/8/8/8/8/8/R2QK3 w - - 0 1", "7k/6pp/8/8/8/8/8/8 w - - 0 1")
    assert fight.play_player(chess.Move.from_uci("d1d8")) is True
    assert fight.board.is_checkmate()
    assert fight.outcome is Outcome.PLAYER_WIN
    assert fight.player_moves == 1


def test_being_checkmated_loses():
    fight = make_fight("8/8/8/8/8/8/8/7K w - - 0 1", "7k/1b6/8/8/8/8/6q1/8 w - - 0 1")
    assert fight.board.is_checkmate()
    assert fight.outcome is Outcome.PLAYER_LOSS


def test_delivering_stalemate_loses_the_fight():
    """You have to actually mate -- stalemating the enemy is a loss."""
    fight = make_fight("8/5K2/8/8/8/8/8/6Q1 w - - 0 1", "7k/8/8/8/8/8/8/8 w - - 0 1")
    assert fight.play_player(chess.Move.from_uci("g1g6")) is True
    assert fight.board.is_stalemate()
    assert fight.outcome is Outcome.PLAYER_LOSS


def test_being_stalemated_wins_the_fight():
    """The rule inverts both ways: whoever gets stalemated wins."""
    fight = make_fight("8/8/8/8/8/8/8/7K w - - 0 1", "7k/8/8/8/8/8/5q2/8 w - - 0 1")
    assert fight.board.is_stalemate()
    assert fight.outcome is Outcome.PLAYER_WIN


def test_insufficient_material_is_a_failure_to_win():
    fight = make_fight("8/8/8/8/8/8/8/4K3 w - - 0 1", "4k3/8/8/8/8/8/8/8 w - - 0 1")
    assert fight.outcome is Outcome.PLAYER_LOSS


# -- move counting ------------------------------------------------------


def test_only_player_moves_are_counted():
    fight = make_fight(
        "8/8/8/8/8/8/PPPPPPPP/RNBQKBNR w - - 0 1",
        "rnbqkbnr/pppppppp/8/8/8/8/8/8 w - - 0 1",
    )
    for uci in ("e2e4", "d2d4", "g1f3"):
        fight.play_player(chess.Move.from_uci(uci))
        fight.play_opponent()
    assert fight.player_moves == 3
    assert len(fight.log) == 6


def test_illegal_moves_are_refused_and_not_counted():
    fight = make_fight(
        "8/8/8/8/8/8/PPPPPPPP/RNBQKBNR w - - 0 1",
        "rnbqkbnr/pppppppp/8/8/8/8/8/8 w - - 0 1",
    )
    assert fight.play_player(chess.Move.from_uci("e2e5")) is False
    assert fight.player_moves == 0


def test_parse_accepts_both_san_and_coordinates():
    fight = make_fight(
        "8/8/8/8/8/8/PPPPPPPP/RNBQKBNR w - - 0 1",
        "rnbqkbnr/pppppppp/8/8/8/8/8/8 w - - 0 1",
    )
    assert fight.parse("e2e4") == chess.Move.from_uci("e2e4")
    assert fight.parse("Nf3") == chess.Move.from_uci("g1f3")
    assert fight.parse("zz99") is None


# -- identity -----------------------------------------------------------


def test_captured_pieces_are_named_and_gone_for_good():
    army = army_from_fen("8/8/8/8/3R4/8/8/4K3 w - - 0 1")
    rook_id = next(p.id for p in army.deployment.values() if p.piece_type == chess.ROOK)
    fight = Fight(
        army=army,
        enemy_fen="3q3k/8/8/8/8/8/8/8 w - - 0 1",
        opponent=scripted("d8d4"),
    )
    fight.play_player(chess.Move.from_uci("e1e2"))
    fight.play_opponent()

    casualties = fight.apply_to_army()
    assert [c.name for c in casualties] == ["Rook"]
    assert casualties[0].id == rook_id
    assert all(p.piece_type != chess.ROOK for p in army.deployment.values())


def test_survivors_age_by_one_fight_and_the_bench_does_not():
    from chessvania.core.army import Piece

    army = army_from_fen("8/8/8/8/8/8/8/R2QK3 w - - 0 1")
    benched = Piece(chess.KNIGHT)
    army.add_to_inventory(benched)

    fight = Fight(army=army, enemy_fen="7k/6pp/8/8/8/8/8/8 w - - 0 1", opponent=first_legal)
    fight.play_player(chess.Move.from_uci("d1d8"))
    fight.apply_to_army()

    assert all(p.fights_survived == 1 for p in army.deployment.values())
    assert benched.fights_survived == 0


def test_the_formation_is_not_disturbed_by_a_fight():
    """Where a fight strands your pieces must not become the next setup."""
    army = army_from_fen("8/8/8/8/8/8/PPPPPPPP/RNBQKBNR w - - 0 1")
    before = {square: piece.id for square, piece in army.deployment.items()}

    fight = Fight(
        army=army,
        enemy_fen="rnbqkbnr/pppppppp/8/8/8/8/8/8 w - - 0 1",
        opponent=first_legal,
    )
    for _ in range(6):
        fight.play_player(next(iter(fight.board.legal_moves)))
        fight.play_opponent()
    assert fight.board.piece_map() != {}  # pieces really did move during play

    casualties = fight.apply_to_army()
    dead = {piece.id for piece in casualties}
    expected = {sq: pid for sq, pid in before.items() if pid not in dead}
    after = {square: piece.id for square, piece in army.deployment.items()}
    assert after == expected


def test_promotion_works_inside_a_fight():
    army = army_from_fen("8/6P1/8/8/8/8/8/4K3 w - - 0 1")

    fight = Fight(
        army=army,
        enemy_fen="k7/8/8/8/8/8/8/8 w - - 0 1",
        opponent=scripted("a8a7"),
    )
    fight.play_player(chess.Move.from_uci("g7g8q"))
    assert fight.board.piece_at(chess.G8).piece_type == chess.QUEEN


def test_promotion_does_not_carry_across_fights():
    """Otherwise stalling to queen every pawn is the dominant strategy."""
    army = army_from_fen("8/6P1/8/8/8/8/8/4K3 w - - 0 1")
    pawn = next(p for p in army.deployment.values() if p.piece_type == chess.PAWN)
    home = army.square_of(pawn.id)

    fight = Fight(
        army=army,
        enemy_fen="k7/8/8/8/8/8/8/8 w - - 0 1",
        opponent=scripted("a8a7"),
    )
    fight.play_player(chess.Move.from_uci("g7g8q"))
    fight.play_opponent()
    fight.apply_to_army()

    assert army.deployment[home].id == pawn.id
    assert army.deployment[home].piece_type == chess.PAWN
    assert army.material() == 1  # a pawn's worth, not a queen's


def test_a_promoted_piece_that_dies_costs_you_the_pawn():
    """The queen is temporary; losing it still permanently costs the pawn."""
    army = army_from_fen("8/6P1/8/8/8/8/8/4K3 w - - 0 1")
    pawn_id = next(p.id for p in army.deployment.values() if p.piece_type == chess.PAWN)

    fight = Fight(
        army=army,
        enemy_fen="8/5k2/8/8/8/8/8/8 w - - 0 1",
        opponent=scripted("f7g8"),  # king takes the undefended new queen
    )
    assert fight.play_player(chess.Move.from_uci("g7g8q")) is True
    fight.play_opponent()

    casualties = fight.apply_to_army()
    assert [c.id for c in casualties] == [pawn_id]
    assert [c.name for c in casualties] == ["Pawn"]
    assert army.material() == 0


def test_castling_is_tracked_without_disturbing_the_formation():
    """The tracker follows the rook so a capture names it, but home is home."""
    army = army_from_fen("8/8/8/8/8/8/PPPPPPPP/R3K2R w - - 0 1")
    rook_id = army.deployment[chess.H1].id

    fight = Fight(
        army=army,
        enemy_fen="4k3/8/8/8/8/8/8/8 w - - 0 1",
        opponent=scripted("e8e7"),
    )
    assert fight.play_player(chess.Move.from_uci("e1g1")) is True
    assert fight.tracker.at[chess.F1] == rook_id  # followed mid-fight

    fight.play_opponent()
    fight.apply_to_army()

    assert army.deployment[chess.H1].id == rook_id  # but returns home
    assert chess.F1 not in army.deployment


def test_en_passant_capture_removes_the_right_pawn():
    army = army_from_fen("8/8/8/8/8/8/4P3/4K3 w - - 0 1")
    pawn_id = next(p.id for p in army.deployment.values() if p.piece_type == chess.PAWN)

    fight = Fight(
        army=army,
        enemy_fen="4k3/8/8/8/3p4/8/8/8 w - - 0 1",
        opponent=scripted("d4e3"),
    )
    fight.play_player(chess.Move.from_uci("e2e4"))
    fight.play_opponent()

    casualties = fight.apply_to_army()
    assert [c.id for c in casualties] == [pawn_id]
    assert all(p.piece_type != chess.PAWN for p in army.deployment.values())
