"""Reading and writing save files.

THE ONLY LAYER THAT OWNS DURABLE STATE. Everything the game remembers between
launches is written here and nowhere else, so "what does Chessvania save?" is
answered by reading one package. `core` holds the rules, this holds the JSON.

Stated as a property rather than as "the only layer that touches a filesystem",
which is a claim about a mechanism and stopped being true the moment something
cached. `ui.audio` renders sounds into a temp directory and deletes them when
the process exits -- that is scratch space, not state, and it belongs nowhere
near the user-data directory. `tests/test_architecture.py` enforces the real
rule: nothing outside this package resolves a save path.

Two separate save files with two different lifetimes:

  profile.json   achievements, bestiary, unlocks -- survives every run
  run.json       one run in progress -- deleted when the run ends
"""

from .paths import data_dir, profile_path, run_path
from .profile_store import load_profile, save_profile
from .run_store import clear_run, has_saved_run, load_run, save_run

__all__ = [
    "data_dir",
    "profile_path",
    "run_path",
    "load_profile",
    "save_profile",
    "load_run",
    "save_run",
    "clear_run",
    "has_saved_run",
]
