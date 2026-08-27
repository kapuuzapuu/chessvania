"""run.json -- one run in progress, so a session can be resumed.

Piece identity is part of the save. Veterancy and the casualty report are both
keyed on piece ids, so ids have to survive a reload intact -- and the id
generator has to be pushed past anything restored, or a newly bought piece would
collide with a loaded one.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import chess

from .. import config
from ..core.army import Army, Piece, reserve_piece_ids
from ..core.ladder import FightSpec, Formation
from ..core.run import Phase, RunState
from .paths import read_json, run_path, write_json

VERSION = 1


# -- encode -------------------------------------------------------------


def _piece_to_json(piece: Piece) -> Dict[str, Any]:
    return {
        "id": piece.id,
        "type": piece.piece_type,
        "fights": piece.fights_survived,
        "bought": piece.bought,
    }


def _army_to_json(army: Army) -> Dict[str, Any]:
    return {
        "deployment": {
            chess.square_name(square): _piece_to_json(piece)
            for square, piece in army.deployment.items()
        },
        "inventory": [_piece_to_json(p) for p in army.inventory],
    }


def _spec_to_json(spec: FightSpec) -> Dict[str, Any]:
    return {
        "ante": spec.ante,
        "index": spec.index,
        "tier": spec.tier,
        "elo": spec.elo,
        "name": spec.formation.name,
        "fen": spec.formation.fen,
    }


def save_run(run: RunState) -> bool:
    return write_json(
        run_path(),
        {
            "version": VERSION,
            "army": _army_to_json(run.army),
            "ladder": [_spec_to_json(s) for s in run.ladder],
            "stake": _stake_index(run.stake),
            "gold": run.gold,
            "fight_index": run.fight_index,
            "banked_skip_bonus": run.banked_skip_bonus,
            "run_number": run.run_number,
        },
    )


def _stake_index(stake: config.Stake) -> int:
    for index, candidate in enumerate(config.STAKES):
        if candidate.name == stake.name:
            return index
    return 0


# -- decode -------------------------------------------------------------


def _piece_from_json(payload: Dict[str, Any]) -> Piece:
    return Piece(
        piece_type=int(payload["type"]),
        id=int(payload["id"]),
        fights_survived=int(payload.get("fights", 0)),
        bought=bool(payload.get("bought", False)),
    )


def load_run() -> Optional[RunState]:
    """Restore a saved run, or None if there isn't a usable one."""
    payload = read_json(run_path())
    if not isinstance(payload, dict) or payload.get("version") != VERSION:
        return None

    try:
        army_payload = payload["army"]
        deployment = {
            chess.parse_square(name): _piece_from_json(p)
            for name, p in army_payload["deployment"].items()
        }
        inventory = [_piece_from_json(p) for p in army_payload["inventory"]]
        army = Army(deployment=deployment, inventory=inventory)

        ladder = [
            FightSpec(
                ante=int(s["ante"]),
                index=int(s["index"]),
                tier=s["tier"],
                formation=Formation(s["name"], s["tier"], s["fen"]),
                elo=int(s["elo"]),
            )
            for s in payload["ladder"]
        ]
        if not ladder:
            return None

        stake_index = int(payload.get("stake", 0))
        stake = config.STAKES[stake_index % len(config.STAKES)]

        run = RunState(
            army=army,
            ladder=ladder,
            stake=stake,
            gold=int(payload.get("gold", 0)),
            fight_index=int(payload.get("fight_index", 0)),
            banked_skip_bonus=int(payload.get("banked_skip_bonus", 0)),
            phase=Phase.FIGHT,
            run_number=int(payload.get("run_number", 1)),
        )
    except (KeyError, TypeError, ValueError):
        return None

    if run.current is None:  # finished or out of range
        return None

    # Push the id generator past everything restored.
    highest = max((p.id for p in army.all_pieces()), default=0)
    reserve_piece_ids(highest)
    return run


def has_saved_run() -> bool:
    return run_path().exists()


def clear_run() -> None:
    run_path().unlink(missing_ok=True)
