"""Block-character piece art for the larger square sizes.

A Unicode chess glyph is one character at one size -- there is no bigger ♜ --
so past the smallest square the pieces are drawn rather than typed.

Each sprite is a pixel grid, and `▀` is what makes the resolution work: it
paints its top half in the foreground colour and its bottom half in the
background. Since "empty" here IS the square's own colour, one character row
carries two pixel rows for free. A 5x2 square is therefore a 5x4 canvas, 7x3 is
7x6, and 9x4 is 9x8.

Sprites are hand-authored per size rather than scaled from one master. At these
resolutions downsampling turns to mush; every pixel has to be placed on purpose,
which is how pixel art is normally done.

ONE DELIBERATE DIFFERENCE FROM THE GLYPH PATH: these sprites are the same for
both armies, so at these sizes the sides are told apart by COLOUR ALONE. The
Unicode path keeps the outlined/solid split and its accessibility guarantee (see
`theme.piece_glyph`); this was a considered trade, not an oversight -- six pieces
have to stay distinct from each other first, and at 5x4 pixels there is not
enough room to also carry a second fill.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import chess

# (cell columns, cell rows) -> piece type -> pixel rows, '#' set and '.' clear.
#
# THE OUTER COLUMN ON EACH SIDE STAYS CLEAR. Squares abut directly, so a
# sprite that reaches the edge fuses with its neighbour and a back rank turns
# into one unreadable mass. `tests/test_piece_art.py` enforces it.
PIXELS: Dict[Tuple[int, int], Dict[int, List[str]]] = {
    (5, 2): {
        chess.PAWN:   [".###.", ".###.", "..#..", ".###."],
        chess.KNIGHT: [".##..", ".###.", "..##.", ".###."],
        chess.BISHOP: ["..#..", ".#.#.", ".###.", ".###."],
        chess.ROOK:   [".#.#.", ".###.", ".###.", ".###."],
        chess.QUEEN:  [".#.#.", "..#..", ".###.", ".###."],
        chess.KING:   ["..#..", ".###.", "..#..", ".###."],
    },
    (7, 3): {
        chess.PAWN:   ["..###..", "..###..", "...#...",
                       "..###..", "..###..", ".#####."],
        chess.KNIGHT: [".##....", ".####..", ".#####.",
                       "...###.", "...###.", ".#####."],
        chess.BISHOP: ["...#...", "..#.#..", "..###..",
                       "..###..", "..###..", ".#####."],
        chess.ROOK:   [".#.#.#.", ".#####.", "..###..",
                       "..###..", "..###..", ".#####."],
        chess.QUEEN:  [".#.#.#.", "..###..", "..###..",
                       "..###..", "..###..", ".#####."],
        chess.KING:   ["..###..", "...#...", "..###..",
                       "..###..", "..###..", ".#####."],
    },
    (9, 4): {
        chess.PAWN:   ["...###...", "..#####..", "..#####..", "...###...",
                       "...###...", "..#####..", ".#######.", ".#######."],
        chess.KNIGHT: ["..##.....", "..####...", ".######..", ".##..###.",
                       ".....###.", "....####.", "...#####.", ".#######."],
        chess.BISHOP: ["....#....", "...#.#...", "..#####..", "..##.##..",
                       "..#####..", "...###...", "..#####..", ".#######."],
        chess.ROOK:   [".##.#.##.", ".#######.", "..#####..", "..#####..",
                       "..#####..", "..#####..", "..#####..", ".#######."],
        chess.QUEEN:  [".#.#.#.#.", ".#######.", "..#####..", "..#####..",
                       "..#####..", "...###...", "..#####..", ".#######."],
        chess.KING:   ["...###...", "....#....", "..#####..", "...###...",
                       "..#####..", "..#####..", "..#####..", ".#######."],
    },
}

_CACHE: Dict[Tuple[int, int], Dict[int, List[str]]] = {}


def _to_rows(pixels: List[str]) -> List[str]:
    """Fold pairs of pixel rows into one character row each."""
    rows = []
    for top, bottom in zip(pixels[0::2], pixels[1::2]):
        row = ""
        for upper, lower in zip(top, bottom):
            on_top, on_bottom = upper == "#", lower == "#"
            if on_top and on_bottom:
                row += "█"
            elif on_top:
                row += "▀"
            elif on_bottom:
                row += "▄"
            else:
                row += " "
        rows.append(row)
    return rows


def has_art(cell_w: int, cell_h: int) -> bool:
    return (cell_w, cell_h) in PIXELS


def art_for(cell_w: int, cell_h: int, piece_type: int) -> Optional[List[str]]:
    """Character rows for one piece, or None if this size has no art."""
    key = (cell_w, cell_h)
    table = PIXELS.get(key)
    if table is None:
        return None
    if key not in _CACHE:
        _CACHE[key] = {kind: _to_rows(rows) for kind, rows in table.items()}
    return _CACHE[key].get(piece_type)
