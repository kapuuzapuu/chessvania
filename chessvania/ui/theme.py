"""Palette and glyph helpers.

Colours are specified as truecolor hex; Textual downgrades to 256/16/mono on
weaker terminals automatically, so there is only one version to author.

Colour never carries meaning alone. Sides are distinguishable by glyph shape --
one army draws with the outlined chess symbols and the other with the solid
ones -- so the board stays readable with every colour stripped out.

`piece_glyph` is the only place glyphs come from, so that invariant holds
everywhere by construction rather than by everyone remembering it.
"""

from __future__ import annotations

from typing import Optional

import chess

from ..core.army import Piece
from ..core.threat import Danger

# surfaces
BG = "#0b0d12"
PANEL = "#12151c"
BORDER = "#1c1f27"
BORDER_SOFT = "#23262e"

# squares
SQ_LIGHT = "#262a33"
SQ_DARK = "#161920"
SQ_MOVE = "#3a3320"
SQ_CAPTURE_DARK = "#552924"
SQ_CAPTURE_LIGHT = "#62362e"
"""Same split for capture squares -- see `SQ_TARGET_DARK`."""

SQ_CAPTURE = SQ_CAPTURE_DARK
SQ_SELECT = "#2b3a34"
SQ_TARGET_DARK = "#293d35"
SQ_TARGET_LIGHT = "#324a40"
"""Two shades, matching the two square colours underneath.

A single tint flattens the board the moment a piece is picked up: the
checkerboard is how you read ranks and files, and it should survive being
highlighted.

BOTH SHADES SIT ABOVE A PLAIN LIGHT SQUARE, which is the constraint that
matters and the one the first attempt missed -- its dark variant was actually
dimmer than an unlit light square, so a highlighted dark square and a plain
light one read the same. The darker of the pair now clears a plain light
square by about a tenth of the brightness range.

The step BETWEEN the two is deliberately smaller than the checkerboard's own,
so they read as one highlight in two tones rather than as two different
states.
"""

SQ_TARGET = SQ_TARGET_DARK
"""The bench has no checkerboard to match, so it takes the darker one."""
SQ_CURSOR = "#3d4a63"
"""Cursor tint, used only at the sizes that draw block art.

The 3x1 square brackets its cursor because there is no room for anything
else; an art square is filled edge to edge, so a bracket would have to be
painted over the piece itself. Tinting the square is the honest option."""
SQ_CHECK = "#5c1d20"
"""Deeper and redder than SQ_CAPTURE, which marks a capture you are considering.
This one marks a fact about the position."""

# text
TEXT = "#c3c8d2"
DIM = "#5a5f6b"
FAINT = "#4a4e58"
GHOST = "#3a3d45"

# accents
GOLD = "#e0b24c"
GREEN = "#5dcaa5"
RED = "#e2655f"

# player pieces, tinted by veterancy -- stays inside the pale "yours" family so
# it never reads as a change of side
KING = "#e8eaf0"
FRESH = "#b8bdc9"
SEASONED = "#dde2ee"
VETERAN = "#f5e9c8"
VETERANCY_COLORS = (FRESH, SEASONED, VETERAN)

# enemy pieces
ENEMY_ROYAL = "#e2655f"
ENEMY_PIECE = "#c77b76"
ENEMY_PAWN = "#b08a86"

# threat overlay
DANGER = "#ff6b6b"
"""A piece you are about to lose for the rest of the run."""
CAUTION = "#d9a441"
"""A trade you come out behind on. Worth knowing, not worth panicking about."""

_THREAT_MARKERS = {
    Danger.CHECK: "+",
    Danger.HANGING: "!",
    Danger.TRADE: "-",
}
"""One column each, because a board cell is three wide and two are already spent
on the glyph and its padding.

SAFE and HELD deliberately get nothing. A board that annotates every contested
square annotates nothing, and "attacked but the recapture is fine" is the normal
state of most of a chess position.

These exist so the warnings survive a monochrome terminal: colour reinforces the
marker, it never carries the meaning alone.
"""

_THREAT_COLORS = {
    Danger.CHECK: DANGER,
    Danger.HANGING: DANGER,
    Danger.TRADE: CAUTION,
}


def threat_marker(level: Danger) -> Optional[str]:
    return _THREAT_MARKERS.get(level)


def threat_color(level: Danger) -> Optional[str]:
    return _THREAT_COLORS.get(level)


def player_color(piece: Piece) -> str:
    if piece.piece_type == chess.KING:
        return KING
    return VETERANCY_COLORS[piece.veterancy]


def player_color_for(veterancy: int, piece_type: int) -> str:
    if piece_type == chess.KING:
        return KING
    return VETERANCY_COLORS[max(0, min(2, veterancy))]


def enemy_color(piece_type: int) -> str:
    if piece_type in (chess.KING, chess.QUEEN):
        return ENEMY_ROYAL
    if piece_type == chess.PAWN:
        return ENEMY_PAWN
    return ENEMY_PIECE


def gold(amount: int) -> str:
    from .. import config

    return "%s %d" % (config.GOLD_GLYPH, amount)


# --------------------------------------------------------------------------
# Piece glyphs
# --------------------------------------------------------------------------
#
# The BOARD draws sprites now (see `ui.piece_art`), so these dress the places a
# sprite will not fit: the bench, the shop rows, the loadout and bestiary
# summaries, the inspect panel. White is outlined and Black solid, the printed
# diagram convention.


def piece_glyph(piece_type: int, color: bool = chess.WHITE) -> str:
    """The Unicode glyph for a piece."""
    return chess.Piece(piece_type, color).unicode_symbol()


def piece_glyph_for(piece: Piece) -> str:
    """Glyph for one of the player's own pieces."""
    return piece_glyph(piece.piece_type, chess.WHITE)
