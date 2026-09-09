"""Palette and glyph helpers.

Colours are specified as truecolor hex; Textual downgrades to 256/16/mono on
weaker terminals automatically, so there is only one version to author.

Colour never carries meaning alone. Sides are distinguishable by glyph shape --
one army draws with the outlined chess symbols and the other with the solid
ones -- so the board stays readable with every colour stripped out.

WHICH army gets which fill is a setting (`Settings.filled_player_pieces`), but
that the two always differ is not. `piece_glyph` is the only place glyphs come
from, so the invariant holds everywhere by construction rather than by everyone
remembering it.
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
SQ_CAPTURE = "#4a2420"
SQ_SELECT = "#2b3a34"
SQ_TARGET = "#22322c"
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
# Deliberately module-level state. The fill is a display mode that applies
# uniformly to every glyph the app draws -- board, bench, shop, loadout,
# bestiary, game over -- so threading a boolean through ten render call sites
# would buy nothing over setting it once. `ChessvaniaApp.apply_settings` is the
# only caller of `set_piece_fill`; tests reset it via an autouse fixture.

_PLAYER_FILLED = False


def set_piece_fill(player_filled: bool) -> None:
    """Choose which army draws with the solid glyphs."""
    global _PLAYER_FILLED
    _PLAYER_FILLED = player_filled


def player_filled() -> bool:
    return _PLAYER_FILLED


def piece_glyph(piece_type: int, color: bool = chess.WHITE) -> str:
    """The glyph for a piece, honouring the fill preference.

    python-chess's `invert_color` swaps a piece's glyph for its opposite number,
    so applying it to BOTH sides exchanges the two armies' fills rather than
    making them match. That is what keeps the sides distinguishable without
    colour whichever way the setting is pointed.
    """
    return chess.Piece(piece_type, color).unicode_symbol(invert_color=_PLAYER_FILLED)


def piece_glyph_for(piece: Piece) -> str:
    """Glyph for one of the player's own pieces."""
    return piece_glyph(piece.piece_type, chess.WHITE)
