"""Block-character piece art: well-formed sprites that stay readable on a board."""

import chess

from chessvania.ui import piece_art
from chessvania.ui.widgets.board_view import CELL_LADDER, BoardView

PIECE_TYPES = (chess.PAWN, chess.KNIGHT, chess.BISHOP,
               chess.ROOK, chess.QUEEN, chess.KING)


def test_every_sprite_matches_its_cell_size():
    """A sprite of the wrong shape would shear the whole board row."""
    for (cell_w, cell_h), table in piece_art.PIXELS.items():
        for piece_type, pixels in table.items():
            assert len(pixels) == cell_h * 2, (
                "%dx%d piece %d has %d pixel rows, wants %d" % (
                    cell_w, cell_h, piece_type, len(pixels), cell_h * 2))
            for row in pixels:
                assert len(row) == cell_w, (
                    "%dx%d piece %d: %r is not %d wide" % (
                        cell_w, cell_h, piece_type, row, cell_w))


def test_every_piece_type_has_a_sprite_at_every_art_size():
    for (cell_w, cell_h) in piece_art.PIXELS:
        for piece_type in PIECE_TYPES:
            assert piece_art.art_for(cell_w, cell_h, piece_type) is not None


def test_sprites_keep_a_clear_column_on_each_side():
    """Squares abut, so art touching the edge fuses with its neighbour.

    Without this a back rank renders as one continuous mass rather than eight
    pieces -- it is the single thing that most decides whether the board reads.
    """
    for (cell_w, cell_h), table in piece_art.PIXELS.items():
        for piece_type, pixels in table.items():
            for row in pixels:
                assert row[0] != "#" and row[-1] != "#", (
                    "%dx%d piece %d reaches the cell edge: %r" % (
                        cell_w, cell_h, piece_type, row))


def test_no_two_pieces_look_the_same():
    for (cell_w, cell_h) in piece_art.PIXELS:
        rendered = {}
        for piece_type in PIECE_TYPES:
            key = tuple(piece_art.art_for(cell_w, cell_h, piece_type))
            assert key not in rendered, (
                "%dx%d: piece %d and %d render identically" % (
                    cell_w, cell_h, piece_type, rendered[key]))
            rendered[key] = piece_type


def test_the_smallest_rung_has_no_art_and_keeps_the_glyph():
    """3x1 has no room to draw anything, so it stays a Unicode glyph -- which
    is also what preserves the outlined/solid split at the default size."""
    floor_w, floor_h = CELL_LADDER[0]
    assert not piece_art.has_art(floor_w, floor_h)


def test_every_other_rung_does_have_art():
    for cell_w, cell_h in CELL_LADDER[1:]:
        assert piece_art.has_art(cell_w, cell_h), (
            "cell %dx%d scaled up but still draws a lone glyph" % (cell_w, cell_h))


def test_rendered_rows_are_exactly_the_cell_size():
    for cell_w, cell_h in CELL_LADDER[1:]:
        for piece_type in PIECE_TYPES:
            rows = piece_art.art_for(cell_w, cell_h, piece_type)
            assert len(rows) == cell_h
            for row in rows:
                assert len(row) == cell_w


def test_a_drawn_board_keeps_its_rectangle():
    """The art path must not change the widget's footprint."""
    import asyncio

    from chessvania.ui.widgets.board_view import board_size

    async def scenario():
        from chessvania.app import ChessvaniaApp
        from chessvania.ui.screens.menu import MenuScreen

        app = ChessvaniaApp(seed=1)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("escape")
            await pilot.pause()
            view = BoardView()
            await app.screen.mount(view)
            view.board = chess.Board()
            for cell_w, cell_h in CELL_LADDER:
                view.cell_w, view.cell_h = cell_w, cell_h
                lines = view._render_board().plain.rstrip("\n").split("\n")
                assert (max(len(line) for line in lines), len(lines)) == \
                    board_size(cell_w, cell_h)

    asyncio.run(scenario())
