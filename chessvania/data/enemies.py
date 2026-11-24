"""Enemy formations, stored as ordinary FENs.

Only the BLACK pieces of each FEN are used -- the player's own army supplies
White. Material budgets per tier (the player starts around 24):

    tier I      16-20   you are up material, you should feel strong
    tier II     22-26   roughly even, a real fight
    tier III    26-30   slightly outgunned; the boss of antes 1 and 2
    tier IV     36-45   overwhelming; the showpiece

A legal side holds at most 16 pieces and 8 pawns, which caps a formation at 39
material with a standard army. The final bosses buy past that by trading pawns
for heavier pieces rather than adding a 17th piece.
"""

from __future__ import annotations

from typing import Dict, List

from .. import config
from ..core.ladder import Formation

POOL_I: List[Formation] = [
    Formation("the rabble", config.TIER_I, "r2k3r/ppp2ppp/8/8/8/8/8/8 w - - 0 1"),
    Formation("the hedge", config.TIER_I, "1nbk1bn1/pp4pp/8/8/8/8/8/8 w - - 0 1"),
    Formation("the picket", config.TIER_I, "r2k4/pppppppp/2n2n2/8/8/8/8/8 w - - 0 1"),
    Formation("the wedge", config.TIER_I, "r1bk1b2/ppp2ppp/8/8/8/8/8/8 w - - 0 1"),
    Formation("the coil", config.TIER_I, "1n1k1n1r/pp2pppp/8/8/8/8/8/8 w - - 0 1"),
    Formation("the husk", config.TIER_I, "2rk2r1/ppp2ppp/8/8/8/8/8/8 w - - 0 1"),
]

POOL_II: List[Formation] = [
    Formation("the phalanx", config.TIER_II, "r1bk1bnr/pppp1ppp/8/8/8/8/8/8 w - - 0 1"),
    Formation("the serpent", config.TIER_II, "3qkbn1/pppp1ppp/8/8/8/8/8/8 w - - 0 1"),
    Formation("the tower", config.TIER_II, "r2qk2r/pppp1ppp/8/8/8/8/8/8 w - - 0 1"),
    Formation("the fang", config.TIER_II, "1nbqkb2/pp3ppp/8/8/8/8/8/8 w - - 0 1"),
    Formation("the mire", config.TIER_II, "r1bqk3/ppp2ppp/8/8/8/8/8/8 w - - 0 1"),
    Formation("the lattice", config.TIER_II, "rn2kb1r/pp2pppp/8/8/8/8/8/8 w - - 0 1"),
]

POOL_III: List[Formation] = [
    Formation("the basilisk", config.TIER_III, "r1bqkb2/pppp1ppp/8/8/8/8/8/8 w - - 0 1"),
    Formation("the gorgon", config.TIER_III, "rn1qkb2/pppp1ppp/8/8/8/8/8/8 w - - 0 1"),
    Formation("the wyrm", config.TIER_III, "r2qkbn1/pp2pppp/8/8/8/8/8/8 w - - 0 1"),
    Formation("the chimera", config.TIER_III, "rnbqk3/pppp1ppp/8/8/8/8/8/8 w - - 0 1"),
    Formation("the hydra", config.TIER_III, "r1bqkbn1/pp3ppp/8/8/8/8/8/8 w - - 0 1"),
]

POOL_IV: List[Formation] = [
    Formation("the sovereign", config.TIER_IV, "rnbqkbnr/pppppppp/8/8/8/8/8/8 w - - 0 1"),
    Formation("the leviathan", config.TIER_IV, "rnbqkbnr/pppprppp/8/8/8/8/8/8 w - - 0 1"),
    Formation("the eclipse", config.TIER_IV, "rnbqkbnr/pppnpppp/8/8/8/8/8/8 w - - 0 1"),
]

POOLS: Dict[str, List[Formation]] = {
    config.TIER_I: POOL_I,
    config.TIER_II: POOL_II,
    config.TIER_III: POOL_III,
    config.TIER_IV: POOL_IV,
}
