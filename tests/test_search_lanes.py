"""Search lane isolation: interactive vs background pools."""

from __future__ import annotations

import chess

from backend.engine import bot as bot_mod
from backend.engine.bot import (
    Bot,
    background_worker_count,
    interactive_worker_count,
    root_worker_count,
)
from backend.engine.evaluation import Weights


def test_lane_worker_counts_are_positive_and_split():
    assert interactive_worker_count() >= 1
    assert background_worker_count() >= 1
    assert root_worker_count("interactive") == interactive_worker_count()
    assert root_worker_count("background") == background_worker_count()


def test_pools_are_distinct_objects():
    # Force pool creation
    p_i = bot_mod._get_pool("interactive")
    p_b = bot_mod._get_pool("background")
    assert p_i is not p_b
    assert bot_mod._POOLS["interactive"] is p_i
    assert bot_mod._POOLS["background"] is p_b


def test_interactive_and_background_bots_return_legal_moves():
    board = chess.Board()
    weights = Weights(1.0, 0.2, 0.2)
    interactive = Bot("I", weights, depth=2, use_parallel=False, lane="interactive")
    background = Bot("B", weights, depth=2, use_parallel=False, lane="background")
    mi = interactive.choose_move(board)
    mb = background.choose_move(board)
    assert mi is not None and mi[0] in board.legal_moves
    assert mb is not None and mb[0] in board.legal_moves
    assert isinstance(mi[1], float) and isinstance(mb[1], float)


def test_default_lane_is_background():
    bot = Bot("D", Weights(1, 1, 1))
    assert bot.lane == "background"
