"""Quick search latency benchmark (not collected by pytest)."""

from __future__ import annotations

import time

import chess

from backend.engine.bot import Bot, game_concurrency, root_worker_count
from backend.engine.evaluation import Weights


def main() -> None:
    print(
        "interactive_workers",
        root_worker_count("interactive"),
        "background_workers",
        root_worker_count("background"),
        "game_concurrency",
        game_concurrency(),
    )
    weights = Weights(1.0, 0.2, 0.2)
    board = chess.Board()
    for depth in (6, 8, 10):
        bot = Bot(
            "bench",
            weights,
            depth=depth,
            use_parallel=False,
            use_native=True,
            lane="interactive",
        )
        t0 = time.perf_counter()
        result = bot.choose_move(board)
        dt = time.perf_counter() - t0
        move = result[0] if result else None
        score = result[1] if result else None
        print(f"native depth={depth}: {move} score={score} in {dt:.3f}s")


if __name__ == "__main__":
    main()
