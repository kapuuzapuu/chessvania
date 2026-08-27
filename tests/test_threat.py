"""The threat read: what is hanging, what is held, and what you can take."""

import chess

from chessvania.core.threat import Danger, cover, read

# Every position below is a bare, legal, White-to-move board built for one
# question. FENs beat fixtures here: the position IS the test case.


def board(fen):
    return chess.Board(fen)


# -- danger levels ------------------------------------------------------


def test_an_unattacked_piece_is_not_reported():
    report = read(board("4k3/8/8/8/8/8/8/R3K3 w - - 0 1"))
    assert report.threats == ()
    assert report.at(chess.A1) is None
    assert report.material_at_risk == 0


def test_an_undefended_attacked_piece_hangs():
    # Black bishop on f6 eyes the rook on a1 down the long diagonal.
    report = read(board("4k3/8/5b2/8/8/8/8/R3K3 w - - 0 1"))
    threat = report.at(chess.A1)
    assert threat.level is Danger.HANGING
    assert threat.loss == 5  # the whole rook, gone for the run
    assert threat.cheapest_attacker == chess.F6


def test_a_defended_piece_attacked_by_something_cheaper_is_a_losing_trade():
    # Pawn on b6 hits the rook on c5; the rook on c1 defends it.
    report = read(board("4k3/8/1p6/2R5/8/8/8/2R1K3 w - - 0 1"))
    threat = report.at(chess.C5)
    assert threat.level is Danger.TRADE
    assert threat.loss == 4  # rook 5 for pawn 1
    assert chess.C1 in threat.defenders


def test_a_defended_piece_attacked_by_an_equal_is_held():
    # Rook takes rook, rook takes back. Nobody is up.
    report = read(board("4k3/8/8/2r5/8/8/8/1RR1K3 w - - 0 1"))
    threat = report.at(chess.C1)
    assert threat.level is Danger.HELD
    assert threat.loss == 0
    assert report.material_at_risk == 0


def test_a_pinned_defender_does_not_count_as_a_defender():
    """A knight pinned to the king cannot recapture, so the piece it 'defends'
    is really hanging. Reporting it as held would cost a piece for good."""
    # Black rook on e8 pins the knight on e2 to the white king on e1.
    # That knight is the only thing covering the bishop on d4, which a black
    # bishop on a7 attacks.
    held = board("4r2k/b7/8/8/3B4/8/4N3/4K3 w - - 0 1")
    assert chess.E2 in held.attackers(chess.WHITE, chess.D4)
    assert held.is_pinned(chess.WHITE, chess.E2)

    threat = read(held).at(chess.D4)
    assert threat.level is Danger.HANGING
    assert threat.defenders == ()


def test_the_enemy_king_is_never_the_cheap_attacker():
    """Priced at zero it would report every defended piece as a losing trade,
    even though a king can only capture what nobody defends."""
    # Black king on c6 touches the rook on c5; the rook on c1 defends it.
    report = read(board("8/8/2k5/2R5/8/8/8/2R1K3 w - - 0 1"))
    threat = report.at(chess.C5)
    assert threat.level is Danger.HELD
    assert threat.loss == 0


# -- check --------------------------------------------------------------


def test_check_is_its_own_level_and_names_the_checker():
    report = read(board("4k3/8/8/8/8/8/8/r3K3 w - - 0 1"))
    assert report.in_check
    assert report.checkers == (chess.A1,)
    assert report.at(chess.E1).level is Danger.CHECK
    assert report.worst is Danger.CHECK


def test_check_counts_the_ways_out():
    report = read(board("4k3/8/8/8/8/8/8/r3K3 w - - 0 1"))
    assert report.escapes == len(list(chess.Board("4k3/8/8/8/8/8/8/r3K3 w - - 0 1").legal_moves))
    assert report.escapes > 0


def test_a_king_that_is_not_attacked_reports_no_check():
    report = read(board("4k3/8/8/8/8/8/8/4K3 w - - 0 1"))
    assert not report.in_check
    assert report.checkers == ()
    assert report.escapes == 0


# -- ordering and totals ------------------------------------------------


def test_threats_are_sorted_worst_first():
    # In check from the rook on a1, and the queen on d5 hangs to the bishop.
    report = read(board("4k3/5b2/8/3Q4/8/8/8/r3K3 w - - 0 1"))
    levels = [threat.level for threat in report.threats]
    assert levels == sorted(levels, reverse=True)
    assert levels[0] is Danger.CHECK


def test_material_at_risk_sums_only_real_losses():
    # A hanging rook (5) plus a held rook (0).
    report = read(board("4k3/8/5b2/8/8/8/8/R3K1r1 w - - 0 1"))
    assert report.material_at_risk == 5


# -- opportunities ------------------------------------------------------


def test_an_undefended_enemy_piece_is_a_free_capture():
    # White rook on a1 sees the black rook on a8; nothing guards it.
    report = read(board("r3k3/8/8/8/8/8/8/R3K3 w - - 0 1"))
    chance = report.opportunity_at(chess.A8)
    assert chance.free is True
    assert chance.gain == 5
    assert chess.A1 in chance.takers


def test_a_guarded_enemy_piece_is_only_worth_the_difference():
    # Rook takes the queen on a8, the king on b8 recaptures: +9 for -5.
    report = read(board("qk6/8/8/8/8/8/8/R3K3 w - - 0 1"))
    chance = report.opportunity_at(chess.A8)
    assert chance.free is False
    assert chance.gain == 4


def test_a_losing_capture_is_not_offered():
    # Rook takes the pawn on a7, the rook on a8 recaptures: -4 for the trouble.
    report = read(board("r3k3/p7/8/8/8/8/8/R3K3 w - - 0 1"))
    assert report.opportunity_at(chess.A7) is None


def test_opportunities_come_from_legal_moves_so_pins_are_respected():
    """A pinned rook cannot take, so its target is not an opportunity."""
    # White rook on e4 is pinned to the king on e1 by the black rook on e8.
    # It "attacks" the knight on a4 geometrically but cannot legally take it.
    position = board("4r3/8/8/8/n3R3/8/8/4K3 w - - 0 1")
    assert chess.A4 in [m.to_square for m in position.pseudo_legal_moves]
    assert chess.A4 not in [m.to_square for m in position.legal_moves]
    assert read(position).opportunity_at(chess.A4) is None


def test_free_captures_outrank_bigger_guarded_ones():
    """A free bishop beats a guarded queen: the gain is certain either way, but
    the free one does not put your own piece into the exchange."""
    # Free bishop on h8; queen on a8 guarded by the king next to it on b8.
    report = read(board("qk5b/8/8/8/8/8/8/R3K2R w - - 0 1"))
    assert report.opportunities[0].square == chess.H8
    assert report.opportunities[0].free is True


def test_no_opportunities_while_it_is_the_enemys_move():
    report = read(board("r3k3/8/8/8/8/8/8/R3K3 b - - 0 1"))
    assert report.opportunities == ()


# -- the cover helper ---------------------------------------------------


def test_cover_lists_attackers_cheapest_first():
    # The black rook on d8 and pawn on c7 both hit d7.
    covered = cover(board("3rk3/2p5/8/8/8/8/8/4K3 w - - 0 1"), chess.D6, chess.BLACK)
    assert covered[0] == chess.C7  # pawn before rook
    assert set(covered) == {chess.C7, chess.D8}


def test_cover_of_an_empty_uncontested_square_is_empty():
    assert cover(board("4k3/8/8/8/8/8/8/4K3 w - - 0 1"), chess.D5, chess.BLACK) == ()
