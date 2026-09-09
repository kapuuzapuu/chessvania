"""profile.json -- achievements, bestiary, unlocks and settings, across all runs."""

from __future__ import annotations

from typing import Any, Dict

from ..core.progress import BY_ID, Profile, Settings
from .paths import profile_path, read_json, write_json

VERSION = 1


def _read_settings(payload: Dict[str, Any]) -> Settings:
    """Rebuild settings, falling back to the default for anything unusable.

    Settings are cosmetic, so a malformed or half-written block is never worth
    failing a load over: an unreadable preference costs you that preference, not
    your achievements. Unknown keys are ignored, which is what lets an older
    build read a profile written by a newer one.
    """
    raw = payload.get("settings")
    if not isinstance(raw, dict):
        return Settings()

    defaults = Settings()
    return Settings(
        filled_player_pieces=bool(
            raw.get("filled_player_pieces", defaults.filled_player_pieces)
        ),
        boot_animation=bool(raw.get("boot_animation", defaults.boot_animation)),
    )


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
        settings=_read_settings(payload),
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
            "settings": {
                "filled_player_pieces": profile.settings.filled_player_pieces,
                "boot_animation": profile.settings.boot_animation,
            },
        },
    )
