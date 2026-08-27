"""Enemy placement: the player must always be able to open as White."""

import chess

from chessvania import config
from chessvania.core.army import army_from_fen, compose_board
from chessvania.core.ladder import Formation
from chessvania.core.legality import is_legal_position, position_errors
from chessvania.core.placement import (
    choose_placement,
    formation_variants,
    pairing_is_playable,
)
from chessvania.data.enemies import POOLS

# A rook on d1 with nothing in the way stares straight down the d-file.
SNIPER = "8/8/8/8/8/8/8/3RK3 w - - 0 1"
KING_ON_D8 = Formation("test dummy", config.TIER_LOW, "3k4/8/8/8/8/8/8/8 w - - 0 1")


def test_an_army_aimed_at_the_enemy_king_makes_a_pairing_unplayable():
    """White-to-move with Black in check is illegal, so this placement is out."""
    assert pairing_is_playable(army_from_fen(SNIPER), KING_ON_D8.fen) is False


def test_a_sideways_variant_rescues_an_unplayable_pairing():
    army = army_from_fen(SNIPER)
    playable = [f for f in formation_variants(KING_ON_D8.fen)
                if pairing_is_playable(army, f)]
    assert playable, "no variant avoided the check"

    board = compose_board(army, playable[0])
    assert board.turn == chess.WHITE
    assert is_legal_position(board), position_errors(board)


def test_variants_preserve_the_formation():
    """Mirrors and shifts move files only -- same pieces, same shape."""
    original = "r2k3r/ppp2ppp/8/8/8/8/8/8 w - - 0 1"
    reference = sorted(p.symbol() for p in chess.Board(original).piece_map().values())
    for fen in formation_variants(original):
        pieces = sorted(p.symbol() for p in chess.Board(fen).piece_map().values())
        assert pieces == reference


def test_variants_never_leave_the_board():
    for fen in formation_variants("r2k3r/ppp2ppp/8/8/8/8/8/8 w - - 0 1"):
        assert chess.Board(fen).piece_map()


def test_choose_placement_keeps_the_drawn_formation_when_it_already_works():
    army = army_from_fen("8/8/8/8/8/8/PPPPPPPP/RNBQKBNR w - - 0 1")
    drawn = POOLS[config.TIER_LOW][0]
    chosen = choose_placement(army, drawn, POOLS[config.TIER_LOW])
    assert chosen.fen == drawn.fen
    assert chosen.name == drawn.name


def test_choose_placement_slides_the_enemy_rather_than_swapping_it():
    """The fight you were dealt is still the fight you get -- same name."""
    army = army_from_fen(SNIPER)
    chosen = choose_placement(army, KING_ON_D8, [KING_ON_D8])

    assert chosen.name == KING_ON_D8.name
    assert chosen.fen != KING_ON_D8.fen
    assert pairing_is_playable(army, chosen.fen)


def test_choose_placement_always_yields_white_to_move_across_the_library():
    """Every loadout against every formation, with the real pools."""
    from chessvania.data.loadouts import LOADOUTS

    for loadout in LOADOUTS:
        army = army_from_fen(loadout.fen)
        for tier, pool in POOLS.items():
            for formation in pool:
                chosen = choose_placement(army, formation, pool)
                board = compose_board(army, chosen.fen)
                assert board.turn == chess.WHITE
                assert is_legal_position(board), position_errors(board)
