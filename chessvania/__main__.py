"""Entry point: `python -m chessvania`."""

from __future__ import annotations

import os
import sys

from . import config
from .engine import EngineNotFound, locate_binary


def main() -> int:
    # The entry point is where the environment gets read; config.py stays a
    # module of plain constants.
    if os.environ.get("CHESSVANIA_DEV"):
        config.DEV_MODE = True

    # Resolve Stockfish BEFORE the TUI starts, so a missing engine produces a
    # readable install message rather than a stack trace behind a cleared screen.
    try:
        locate_binary()
    except EngineNotFound as exc:
        print(str(exc), file=sys.stderr)
        return 1

    from .app import ChessvaniaApp

    ChessvaniaApp().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
