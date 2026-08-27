"""Save files: round-tripping, and surviving damage.

`conftest.py` points the data directory at a tmp path for every test, so none of
this touches a real profile.
"""

import json
import random

import chess

from chessvania import config
from chessvania.core.army import Piece, army_from_fen, next_piece_id
from chessvania.core.ladder import build_ladder
from chessvania.core.progress import Profile
from chessvania.core.run import new_run
from chessvania.data.enemies import POOLS
from chessvania.persistence import (
    clear_run,
    data_dir,
    has_saved_run,
    load_profile,
    load_run,
    profile_path,
    run_path,
    save_profile,
    save_run,
)

TEXTBOOK = "8/8/8/8/8/8/PPPPPPPP/RNBQKBNR w - - 0 1"


def make_run(gold=7, fight_index=2):
    stake = config.STAKES[2]
    army = army_from_fen(TEXTBOOK)
    army.add_to_inventory(Piece(chess.QUEEN, bought=True))
    run = new_run(army, build_ladder(POOLS, stake, random.Random(3)), stake)
    run.gold = gold
    run.fight_index = fight_index
    run.banked_skip_bonus = 4
    return run


# -- paths ---------------------------------------------------------------


def test_the_data_dir_is_redirected_for_tests(tmp_path):
    assert str(tmp_path) in str(data_dir())


def test_the_data_dir_is_created_on_demand():
    assert data_dir().is_dir()


# -- profile -------------------------------------------------------------


def test_a_missing_profile_loads_as_blank():
    assert not profile_path().exists()
    profile = load_profile()
    assert profile.earned == set()
    assert profile.runs_played == 0


def test_profile_round_trips():
    profile = Profile(
        defeated={"the basilisk", "the husk"},
        earned={"first_blood", "blitz"},
        runs_played=5,
        runs_won=1,
        highest_stake=3,
    )
    assert save_profile(profile)

    loaded = load_profile()
    assert loaded.defeated == profile.defeated
    assert loaded.earned == profile.earned
    assert loaded.runs_played == 5
    assert loaded.runs_won == 1
    assert loaded.highest_stake == 3


def test_unknown_achievement_ids_are_dropped_on_load():
    """Renaming an achievement in code must not leave a phantom in the UI."""
    save_profile(Profile(earned={"first_blood"}))
    payload = json.loads(profile_path().read_text())
    payload["earned"].append("achievement_that_no_longer_exists")
    profile_path().write_text(json.dumps(payload))

    loaded = load_profile()
    assert loaded.earned == {"first_blood"}


def test_a_corrupt_profile_does_not_stop_the_game():
    profile_path().write_text("{ this is not json")
    assert load_profile().earned == set()


# -- run -----------------------------------------------------------------


def test_no_saved_run_initially():
    assert has_saved_run() is False
    assert load_run() is None


def test_run_round_trips():
    run = make_run()
    assert save_run(run)
    assert has_saved_run()

    loaded = load_run()
    assert loaded is not None
    assert loaded.gold == run.gold
    assert loaded.fight_index == run.fight_index
    assert loaded.banked_skip_bonus == run.banked_skip_bonus
    assert loaded.stake.name == run.stake.name
    assert len(loaded.ladder) == len(run.ladder)


def test_the_deployment_survives_square_for_square():
    run = make_run()
    save_run(run)
    loaded = load_run()

    before = {sq: (p.id, p.piece_type) for sq, p in run.army.deployment.items()}
    after = {sq: (p.id, p.piece_type) for sq, p in loaded.army.deployment.items()}
    assert after == before


def test_veterancy_and_provenance_survive():
    run = make_run()
    piece = next(iter(run.army.deployment.values()))
    piece.fights_survived = 4
    save_run(run)

    loaded = load_run()
    restored = loaded.army.find(piece.id)
    assert restored is not None
    assert restored.fights_survived == 4
    assert loaded.army.inventory[0].bought is True


def test_loading_pushes_the_id_counter_past_restored_pieces():
    """Otherwise the next bought piece collides with a loaded one."""
    run = make_run()
    highest = max(p.id for p in run.army.all_pieces())
    save_run(run)

    loaded = load_run()
    fresh = next_piece_id()
    assert fresh > highest
    assert all(p.id != fresh for p in loaded.army.all_pieces())


def test_the_ladder_survives_with_its_elo_ramp():
    run = make_run()
    save_run(run)
    loaded = load_run()

    assert [s.elo for s in loaded.ladder] == [s.elo for s in run.ladder]
    assert [s.tier for s in loaded.ladder] == [s.tier for s in run.ladder]
    assert [s.formation.name for s in loaded.ladder] == [
        s.formation.name for s in run.ladder
    ]


def test_a_corrupt_run_loads_as_nothing():
    run_path().write_text("not json at all")
    assert load_run() is None


def test_a_run_from_a_future_version_is_refused():
    run = make_run()
    save_run(run)
    payload = json.loads(run_path().read_text())
    payload["version"] = 999
    run_path().write_text(json.dumps(payload))
    assert load_run() is None


def test_a_finished_run_is_not_resumable():
    run = make_run()
    run.fight_index = len(run.ladder)
    save_run(run)
    assert load_run() is None


def test_clearing_removes_the_save():
    save_run(make_run())
    assert has_saved_run()
    clear_run()
    assert not has_saved_run()
    assert load_run() is None


def test_clearing_twice_is_harmless():
    clear_run()
    clear_run()


def test_saving_does_not_leave_a_temp_file_behind():
    save_run(make_run())
    leftovers = [p.name for p in data_dir().iterdir() if p.suffix == ".tmp"]
    assert leftovers == []
