"""Where save files live.

Resolved lazily rather than at import so the environment can be overridden by
tests, and so importing the package never touches a disk.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

APP_NAME = "chessvania"
ENV_OVERRIDE = "CHESSVANIA_DATA_DIR"


def data_dir() -> Path:
    """The save directory, created on demand.

    Honours CHESSVANIA_DATA_DIR, otherwise the platform's user-data location.
    """
    override = os.environ.get(ENV_OVERRIDE)
    if override:
        path = Path(override).expanduser()
    else:
        try:
            from platformdirs import user_data_dir

            path = Path(user_data_dir(APP_NAME, appauthor=False))
        except ImportError:  # pragma: no cover - platformdirs ships with textual
            path = Path.home() / ".local" / "share" / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def profile_path() -> Path:
    return data_dir() / "profile.json"


def run_path() -> Path:
    return data_dir() / "run.json"


def read_json(path: Path) -> Optional[Any]:
    """Load JSON, or None if it is missing or unreadable.

    A corrupt save should cost you a save, not the ability to launch the game.
    """
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def write_json(path: Path, payload: Any) -> bool:
    """Write atomically, so an interrupted save cannot corrupt the old one."""
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
        temporary.replace(path)
        return True
    except OSError:
        temporary.unlink(missing_ok=True)
        return False
