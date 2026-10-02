"""Threefold / repetition handling inside search."""

from __future__ import annotations

import chess
import pytest

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
    assert board.is_repetition(3)
    assert _is_cheap_terminal(board)


def test_second_visit_is_not_a_draw():
    board = chess.Board()
    for san in ("Nf3", "Nf6", "Ng1", "Ng8"):
        board.push_san(san)
    assert board.is_repetition(2)
    assert not board.is_repetition(3)
    assert not _is_cheap_terminal(board)
    assert evaluate(board, Weights(material=1.0, tempo=1.0)) != 0.0


def _winning_side_about_to_repeat() -> tuple[chess.Board, chess.Move]:
    """White is up a rook. a3a2 would be the third visit; other moves are not."""
    board = chess.Board("4k3/8/8/8/8/8/8/R3K3 w - - 0 1")
    for uci in ("a1a2", "e8e7", "a2a3", "e7e8", "a3a2", "e8d8", "a2a3", "d8e8"):
        board.push_uci(uci)
    drawing = chess.Move.from_uci("a3a2")
    assert drawing in board.legal_moves
    probe = board.copy(stack=True)
    probe.push(drawing)
    assert probe.is_repetition(3)
    assert not board.is_repetition(3)
    return board, drawing


@pytest.mark.parametrize("use_native", [True, False])
def test_winning_bot_refuses_the_threefold_move(use_native: bool):
    if use_native:
        pytest.importorskip("backend.engine.native")
    board, drawing = _winning_side_about_to_repeat()
    bot = Bot(
        "Ahead",
        Weights(material=1.0),
        depth=2,
        use_parallel=False,
        use_native=use_native,
        lane="interactive",
    )
    result = bot.choose_move(board)
    assert result is not None
    move, score = result
    assert move != drawing
    assert score > 1.0


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
