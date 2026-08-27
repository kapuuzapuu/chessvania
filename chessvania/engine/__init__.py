"""Stockfish integration. Nothing in `core` imports this package."""

from .stockfish import EngineNotFound, StockfishOpponent, locate_binary

__all__ = ["EngineNotFound", "StockfishOpponent", "locate_binary"]
