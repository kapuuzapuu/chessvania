"""Locate and drive a user-installed Stockfish binary.

Stockfish is GPL-3.0 and multi-megabyte per platform, so it is deliberately not
bundled -- the app finds one the player installed. python-chess speaks UCI to it
directly; there is no need for the separate `stockfish` pip wrapper.
"""

from __future__ import annotations

import os
import shutil
from typing import Optional

import chess
import chess.engine

from .. import config

INSTALL_MESSAGE = """\
Stockfish engine not found. Install it, then re-run:
  macOS:   brew install stockfish
  Debian:  sudo apt install stockfish
  Windows/other: download from https://stockfishchess.org/download/
Or set STOCKFISH_PATH=/path/to/stockfish\
"""


class EngineNotFound(RuntimeError):
    """Raised when no Stockfish binary can be located."""

    def __init__(self) -> None:
        super().__init__(INSTALL_MESSAGE)


def locate_binary(explicit: Optional[str] = None) -> str:
    """Resolve a Stockfish path: explicit -> STOCKFISH_PATH -> system PATH."""
    for candidate in (explicit, os.environ.get("STOCKFISH_PATH")):
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    found = shutil.which("stockfish")
    if found:
        return found
    raise EngineNotFound()


class StockfishOpponent:
    """An `Opponent` callable backed by Stockfish at a configurable strength.

    Below Stockfish's UCI_Elo floor (1320) this falls back to `Skill Level` plus
    a shallow search, which is the only way to get genuinely weak play.
    """

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = locate_binary(path)
        self._engine = chess.engine.SimpleEngine.popen_uci(self.path)
        self._limit = chess.engine.Limit(depth=config.STRONG_DEPTH)
        self.strength: Optional[config.Strength] = None

    def configure(self, target_elo: int) -> config.Strength:
        strength = config.strength_for(target_elo)
        if strength.skill_level is not None:
            options = {
                "UCI_LimitStrength": False,
                "Skill Level": strength.skill_level,
            }
        else:
            options = {
                "Skill Level": 20,
                "UCI_LimitStrength": True,
                "UCI_Elo": strength.uci_elo,
            }
        self._engine.configure(options)
        self._limit = chess.engine.Limit(depth=strength.depth)
        self.strength = strength
        return strength

    def __call__(self, board: chess.Board) -> chess.Move:
        result = self._engine.play(
            board, self._limit, game=object(), info=chess.engine.INFO_NONE
        )
        if result.move is None:
            raise RuntimeError("Stockfish returned no move")
        return result.move

    def close(self) -> None:
        try:
            self._engine.quit()
        except Exception:
            self._engine.close()

    def __enter__(self) -> "StockfishOpponent":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
