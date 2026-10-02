"""Threefold / repetition handling inside search."""

from __future__ import annotations

import chess

from backend.engine.bot import Bot, _is_cheap_terminal
from backend.engine.evaluation import Weights, evaluate


def _play_repetition_line() -> chess.Board:
    """Reach a position that is a threefold repetition (knights out and back twice)."""
    board = chess.Board()
    # 1.Nf3 Nf6 2.Ng1 Ng8 3.Nf3 Nf6 4.Ng1 Ng8 — starting position appears thrice
    for san in ("Nf3", "Nf6", "Ng1", "Ng8", "Nf3", "Nf6", "Ng1", "Ng8"):
        board.push_san(san)
    return board


def test_repetition_is_cheap_terminal():
    board = _play_repetition_line()
    assert board.is_repetition(2)
    assert _is_cheap_terminal(board)


def test_evaluate_repetition_is_draw_score():
    board = _play_repetition_line()
    assert evaluate(board, Weights(1.0, 0.5, 0.5)) == 0.0


def test_bot_still_finds_mate_with_repetition_terminals():
    board = chess.Board()
    board.push_san("e4")
    board.push_san("e5")
    board.push_san("Qh5")
    board.push_san("Nc6")
    board.push_san("Bc4")
    board.push_san("Nf6")
    bot = Bot("M", Weights(1, 0.1, 0.1), depth=2, use_parallel=False, lane="interactive")
    result = bot.choose_move(board)
    assert result is not None
    board.push(result[0])
    assert board.is_checkmate()
