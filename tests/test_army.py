import chess
import pytest

from chessvania import config
from chessvania.core.army import Army, Piece, army_from_fen, compose_board
from chessvania.core.legality import is_legal_position, position_errors, square_accepts

TEXTBOOK = "8/8/8/8/8/8/PPPPPPPP/RNBQKBNR w - - 0 1"


def test_army_from_fen_takes_only_white():
    army = army_from_fen(TEXTBOOK)
    assert army.deployed_count == 16
    assert army.pawn_count == 8
    assert army.king_square() == chess.E1
    assert army.material() == 39


def test_inventory_cap_is_hard():
    army = Army()
    for _ in range(config.INVENTORY_CAP):
        assert army.add_to_inventory(Piece(chess.PAWN)) is True
    assert army.inventory_full
    assert army.add_to_inventory(Piece(chess.QUEEN)) is False
    assert army.inventory_count == config.INVENTORY_CAP


def test_inventory_is_separate_from_the_board_cap():
    army = army_from_fen(TEXTBOOK)
    for _ in range(config.INVENTORY_CAP):
        army.add_to_inventory(Piece(chess.ROOK))
    assert army.deployed_count == 16
    assert army.inventory_count == 16
    assert army.violations() == []


def test_pawns_may_not_rest_on_the_back_ranks():
    assert square_accepts(chess.PAWN, chess.E4) is True
    assert square_accepts(chess.PAWN, chess.E1) is False
    assert square_accepts(chess.PAWN, chess.E8) is False
    assert square_accepts(chess.ROOK, chess.E1) is True


def test_violations_flags_a_missing_king():
    army = Army(deployment={chess.A1: Piece(chess.ROOK)})
    assert any("king" in v for v in army.violations())


def test_violations_flags_too_many_pawns():
    army = Army(deployment={chess.E1: Piece(chess.KING)})
    for index, square in enumerate(range(chess.A2, chess.A2 + 8)):
        army.deployment[square] = Piece(chess.PAWN)
    army.deployment[chess.A3] = Piece(chess.PAWN)
    assert any("pawns" in v for v in army.violations())


def test_compose_board_merges_both_sides_legally():
    army = army_from_fen(TEXTBOOK)
    board = compose_board(army, "rnbqkbnr/pppppppp/8/8/8/8/8/8 w - - 0 1")
    assert is_legal_position(board), position_errors(board)
    assert board.turn == chess.WHITE
    assert len(board.piece_map()) == 32


def test_the_player_normally_moves_first():
    board = compose_board(army_from_fen(TEXTBOOK), "4k3/8/8/8/8/8/8/8 w - - 0 1")
    assert board.turn == chess.WHITE


def test_castling_rights_follow_placement():
    intact = compose_board(army_from_fen(TEXTBOOK), "4k3/8/8/8/8/8/8/8 w - - 0 1")
    assert intact.has_kingside_castling_rights(chess.WHITE)
    assert intact.has_queenside_castling_rights(chess.WHITE)

    shuffled = army_from_fen(TEXTBOOK)
    shuffled.deployment[chess.D1] = shuffled.deployment.pop(chess.E1)
    moved = compose_board(shuffled, "4k3/8/8/8/8/8/8/8 w - - 0 1")
    assert not moved.has_kingside_castling_rights(chess.WHITE)


def test_veterancy_tiers():
    piece = Piece(chess.ROOK)
    assert piece.veterancy == 0 and piece.veterancy_label == "fresh"
    piece.fights_survived = config.VETERAN_THRESHOLDS[0]
    assert piece.veterancy == 1
    piece.fights_survived = config.VETERAN_THRESHOLDS[1]
    assert piece.veterancy == 2


def test_copy_preserves_identity():
    army = army_from_fen(TEXTBOOK)
    army.add_to_inventory(Piece(chess.QUEEN))
    clone = army.copy()
    assert [p.id for p in clone.deployment.values()] == [
        p.id for p in army.deployment.values()
    ]
    clone.deployment[chess.E1].fights_survived = 9
    assert army.deployment[chess.E1].fights_survived == 0
