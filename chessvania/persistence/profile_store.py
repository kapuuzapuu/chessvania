"""profile.json -- achievements, bestiary and unlocks, across all runs."""

from __future__ import annotations

from ..core.progress import BY_ID, Profile
from .paths import profile_path, read_json, write_json

VERSION = 1


def load_profile() -> Profile:
    """Load the profile, or a blank one if there isn't a usable file yet."""
    payload = read_json(profile_path())
    if not isinstance(payload, dict):
        return Profile()

    # Drop achievement ids we no longer recognise, so renaming one in code
    # cannot resurrect it as a phantom entry in the UI.
    earned = {a for a in payload.get("earned", []) if a in BY_ID}

    return Profile(
        defeated=set(payload.get("defeated", [])),
        earned=earned,
        runs_played=int(payload.get("runs_played", 0)),
        runs_won=int(payload.get("runs_won", 0)),
        highest_stake=int(payload.get("highest_stake", 1)),
    )


def save_profile(profile: Profile) -> bool:
    return write_json(
        profile_path(),
        {
            "version": VERSION,
            "defeated": sorted(profile.defeated),
            "earned": sorted(profile.earned),
            "runs_played": profile.runs_played,
            "runs_won": profile.runs_won,
            "highest_stake": profile.highest_stake,
        },
    )
