"""Reading and writing save files.

The only layer that touches a filesystem. `core` holds the rules, this holds the
JSON. Two separate save files with two different lifetimes:

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
