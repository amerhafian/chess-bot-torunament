"""Quick search latency benchmark (not collected by pytest)."""

from __future__ import annotations

import time

import chess

from backend.engine.bot import Bot, game_concurrency, root_worker_count
from backend.engine.evaluation import Weights


def main() -> None:
    print("workers", root_worker_count(), "game_concurrency", game_concurrency())
    weights = Weights(1.0, 0.2, 0.2)
    board = chess.Board()
    for parallel in (False, True):
        for depth in (3, 4, 5):
            bot = Bot("bench", weights, depth=depth, use_parallel=parallel)
            t0 = time.perf_counter()
            move = bot.choose_move(board)
            dt = time.perf_counter() - t0
            print(f"parallel={parallel} depth={depth}: {move} in {dt:.3f}s")


if __name__ == "__main__":
    main()
