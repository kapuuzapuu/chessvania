"""Enemy formations, stored as ordinary FENs.

Only the BLACK pieces of each FEN are used -- the player's own army supplies
White. Material budgets per tier (the player starts around 24):

    low         16-20   you are up material, you should feel strong
    mid         22-26   roughly even, a real fight
    mini-boss   26-30   slightly outgunned
    final-boss  36-45   overwhelming; the showpiece

A legal side holds at most 16 pieces and 8 pawns, which caps a formation at 39
material with a standard army. The final bosses buy past that by trading pawns
for heavier pieces rather than adding a 17th piece.
"""

from __future__ import annotations

from typing import Dict, List

from .. import config
from ..core.ladder import Formation

LOW: List[Formation] = [
    Formation("the rabble", config.TIER_LOW, "r2k3r/ppp2ppp/8/8/8/8/8/8 w - - 0 1"),
    Formation("the hedge", config.TIER_LOW, "1nbk1bn1/pp4pp/8/8/8/8/8/8 w - - 0 1"),
    Formation("the picket", config.TIER_LOW, "r2k4/pppppppp/2n2n2/8/8/8/8/8 w - - 0 1"),
    Formation("the wedge", config.TIER_LOW, "r1bk1b2/ppp2ppp/8/8/8/8/8/8 w - - 0 1"),
    Formation("the coil", config.TIER_LOW, "1n1k1n1r/pp2pppp/8/8/8/8/8/8 w - - 0 1"),
    Formation("the husk", config.TIER_LOW, "2rk2r1/ppp2ppp/8/8/8/8/8/8 w - - 0 1"),
]

MID: List[Formation] = [
    Formation("the phalanx", config.TIER_MID, "r1bk1bnr/pppp1ppp/8/8/8/8/8/8 w - - 0 1"),
    Formation("the serpent", config.TIER_MID, "3qkbn1/pppp1ppp/8/8/8/8/8/8 w - - 0 1"),
    Formation("the tower", config.TIER_MID, "r2qk2r/pppp1ppp/8/8/8/8/8/8 w - - 0 1"),
    Formation("the fang", config.TIER_MID, "1nbqkb2/pp3ppp/8/8/8/8/8/8 w - - 0 1"),
    Formation("the mire", config.TIER_MID, "r1bqk3/ppp2ppp/8/8/8/8/8/8 w - - 0 1"),
    Formation("the lattice", config.TIER_MID, "rn2kb1r/pp2pppp/8/8/8/8/8/8 w - - 0 1"),
]

MINIBOSS: List[Formation] = [
    Formation("the basilisk", config.TIER_MINIBOSS, "r1bqkb2/pppp1ppp/8/8/8/8/8/8 w - - 0 1"),
    Formation("the gorgon", config.TIER_MINIBOSS, "rn1qkb2/pppp1ppp/8/8/8/8/8/8 w - - 0 1"),
    Formation("the wyrm", config.TIER_MINIBOSS, "r2qkbn1/pp2pppp/8/8/8/8/8/8 w - - 0 1"),
    Formation("the chimera", config.TIER_MINIBOSS, "rnbqk3/pppp1ppp/8/8/8/8/8/8 w - - 0 1"),
    Formation("the hydra", config.TIER_MINIBOSS, "r1bqkbn1/pp3ppp/8/8/8/8/8/8 w - - 0 1"),
]

FINAL: List[Formation] = [
    Formation("the sovereign", config.TIER_FINAL, "rnbqkbnr/pppppppp/8/8/8/8/8/8 w - - 0 1"),
    Formation("the leviathan", config.TIER_FINAL, "rnbqkbnr/pppprppp/8/8/8/8/8/8 w - - 0 1"),
    Formation("the eclipse", config.TIER_FINAL, "rnbqkbnr/pppnpppp/8/8/8/8/8/8 w - - 0 1"),
]

POOLS: Dict[str, List[Formation]] = {
    config.TIER_LOW: LOW,
    config.TIER_MID: MID,
    config.TIER_MINIBOSS: MINIBOSS,
    config.TIER_FINAL: FINAL,
}
