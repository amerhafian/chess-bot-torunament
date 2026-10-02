"""Stockfish UCI helper for Bot vs Stockfish play sessions."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from typing import Optional

import chess
import chess.engine

MATE_SCORE = 100_000


class StockfishUnavailable(RuntimeError):
    """Raised when no Stockfish binary can be resolved."""


_COMMON_STOCKFISH_PATHS = (
    "/usr/games/stockfish",
    "/usr/local/bin/stockfish",
    "/usr/bin/stockfish",
)


def resolve_stockfish_path() -> Optional[str]:
    env = os.environ.get("STOCKFISH_PATH")
    if env and os.path.isfile(env) and os.access(env, os.X_OK):
        return env
    found = shutil.which("stockfish")
    if found:
        return found
    for path in _COMMON_STOCKFISH_PATHS:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def stockfish_available() -> bool:
    return resolve_stockfish_path() is not None


@dataclass
class StockfishMove:
    move: chess.Move
    score_white: float  # White-perspective pawns / mate encoding


def score_from_pov(score: chess.engine.PovScore) -> float:
    """Convert engine score to White-perspective float (pawns or mate encoding)."""
    white = score.white()
    if white.is_mate():
        mate = white.mate()
        assert mate is not None
        # Mate in N moves → approx plies 2N-1 for the winning side.
        plies = max(1, abs(mate) * 2 - 1)
        signed = MATE_SCORE - plies
        return float(signed if mate > 0 else -signed)
    cp = white.score(mate_score=None)
    if cp is None:
        return 0.0
    return cp / 100.0


class StockfishEngine:
    """Thin sync wrapper around a SimpleEngine instance."""

    def __init__(self, path: Optional[str] = None, depth: int = 14) -> None:
        binary = path or resolve_stockfish_path()
        if not binary:
            raise StockfishUnavailable(
                "Stockfish binary not found. Install stockfish or set STOCKFISH_PATH."
            )
        self.path = binary
        self.depth = depth
        self._engine = chess.engine.SimpleEngine.popen_uci(binary)

    def close(self) -> None:
        try:
            self._engine.quit()
        except Exception:
            pass

    def analyse_score(self, board: chess.Board) -> float:
        info = self._engine.analyse(board, chess.engine.Limit(depth=self.depth))
        score = info.get("score")
        if score is None:
            return 0.0
        return score_from_pov(score)

    def choose_move(self, board: chess.Board) -> Optional[StockfishMove]:
        if board.is_game_over(claim_draw=True):
            return None
        result = self._engine.play(board, chess.engine.Limit(depth=self.depth))
        if result.move is None:
            return None
        # Analyse the position after the move for a stable White-perspective score.
        board.push(result.move)
        try:
            score = self.analyse_score(board)
        finally:
            board.pop()
        return StockfishMove(move=result.move, score_white=score)
