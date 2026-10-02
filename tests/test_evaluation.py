"""Unit tests for evaluation metrics and alpha-beta bot."""

from __future__ import annotations

import time

import chess

from backend.engine.bot import DEFAULT_DEPTH, Bot
from backend.engine.evaluation import (
    PIECE_VALUES,
    Weights,
    checking_moves_balance,
    compute_metrics,
    controlled_squares_balance,
    evaluate,
    material_balance,
)


def test_material_starting_position_is_zero():
    board = chess.Board()
    assert material_balance(board) == 0


def test_material_after_white_up_a_pawn():
    board = chess.Board()
    board.remove_piece_at(chess.A7)  # black pawn removed
    assert material_balance(board) == 1


def test_piece_values():
    assert PIECE_VALUES[chess.PAWN] == 1
    assert PIECE_VALUES[chess.KNIGHT] == 3
    assert PIECE_VALUES[chess.BISHOP] == 3
    assert PIECE_VALUES[chess.ROOK] == 5
    assert PIECE_VALUES[chess.QUEEN] == 9
    assert PIECE_VALUES[chess.KING] == 0


def test_controlled_squares_overlap_counts():
    board = chess.Board(None)
    board.set_piece_at(chess.A1, chess.Piece.from_symbol("R"))
    board.set_piece_at(chess.A2, chess.Piece.from_symbol("R"))
    board.set_piece_at(chess.E8, chess.Piece.from_symbol("k"))
    board.set_piece_at(chess.E1, chess.Piece.from_symbol("K"))
    white_only = controlled_squares_balance(board)
    assert white_only > 0
    board.remove_piece_at(chess.A2)
    assert controlled_squares_balance(board) < white_only


def test_king_pressure_scholars_mate_threat():
    board = chess.Board()
    board.push_san("e4")
    board.push_san("e5")
    board.push_san("Qh5")
    board.push_san("Nc6")
    board.push_san("Bc4")
    board.push_san("Nf6")
    # White queen/bishop pressure the black king ring / f7
    assert checking_moves_balance(board) > 0


def test_evaluate_weighted_sum():
    board = chess.Board()
    weights = Weights(material=1.0, controlled=0.0, checking=0.0)
    metrics = compute_metrics(board)
    assert evaluate(board, weights) == (
        weights.material * metrics.material
        + weights.controlled * metrics.controlled
        + weights.checking * metrics.checking
    )


def test_bot_finds_mate_in_one():
    board = chess.Board()
    board.push_san("e4")
    board.push_san("e5")
    board.push_san("Qh5")
    board.push_san("Nc6")
    board.push_san("Bc4")
    board.push_san("Nf6")
    bot = Bot(
        name="Tester",
        weights=Weights(material=1.0, controlled=0.1, checking=0.1),
        depth=2,
        use_parallel=False,
    )
    move = bot.choose_move(board)
    assert move is not None
    board.push(move)
    assert board.is_checkmate()


def test_default_depth_is_three():
    bot = Bot(name="Deep", weights=Weights(1, 1, 1))
    assert bot.depth == DEFAULT_DEPTH == 3


def test_parallel_choose_move_returns_legal():
    board = chess.Board()
    bot = Bot(
        name="Parallel",
        weights=Weights(1.0, 0.2, 0.2),
        depth=3,
        use_parallel=True,
    )
    move = bot.choose_move(board)
    assert move is not None
    assert move in board.legal_moves


def test_depth3_opening_move_is_fast():
    board = chess.Board()
    bot = Bot(
        name="Bench",
        weights=Weights(1.0, 0.2, 0.2),
        depth=3,
        use_parallel=True,
    )
    t0 = time.perf_counter()
    move = bot.choose_move(board)
    elapsed = time.perf_counter() - t0
    assert move is not None
    # After optimizations, depth-3 opening should be well under a few seconds.
    assert elapsed < 5.0, f"depth-3 move too slow: {elapsed:.2f}s"
