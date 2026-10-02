"""Unit tests for evaluation metrics and alpha-beta bot."""

from __future__ import annotations

import time

import chess

from backend.engine.bot import DEFAULT_DEPTH, Bot
from backend.engine.evaluation import (
    MATE_SCORE,
    PIECE_VALUES,
    Weights,
    attacked_pieces_balance,
    center_control_balance,
    checking_moves_balance,
    compute_metrics,
    controlled_squares_balance,
    evaluate,
    material_balance,
    score_to_bar,
    signed_pow,
)


def test_material_starting_position_is_zero():
    board = chess.Board()
    assert material_balance(board) == 0


def test_material_after_white_up_a_pawn():
    board = chess.Board()
    board.remove_piece_at(chess.A7)
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
    assert checking_moves_balance(board) > 0


def test_evaluate_power_form_uses_metric_scales():
    from backend.engine.evaluation import (
        ATTACK_SCALE,
        CENTER_SCALE,
        CONTROLLED_SCALE,
        KING_SCALE,
    )

    board = chess.Board()
    weights = Weights(
        material=1.0,
        controlled=1.0,
        checking=1.0,
        attacked=1.0,
        center=1.0,
        material_exp=1.0,
        controlled_exp=1.0,
        checking_exp=1.0,
        attacked_exp=1.0,
        center_exp=1.0,
    )
    metrics = compute_metrics(board)
    expected = (
        weights.material * signed_pow(float(metrics.material), 1.0)
        + weights.controlled * signed_pow(metrics.controlled / CONTROLLED_SCALE, 1.0)
        + weights.checking * signed_pow(metrics.checking / KING_SCALE, 1.0)
        + weights.attacked * signed_pow(metrics.attacked / ATTACK_SCALE, 1.0)
        + weights.center * signed_pow(metrics.center / CENTER_SCALE, 1.0)
    )
    assert evaluate(board, weights) == expected


def test_legacy_weights_dict_loads():
    w = Weights.from_dict({"a": 2.0, "b": 0.5, "c": 0.25})
    assert w.material == 2.0
    assert w.controlled == 0.5
    assert w.checking == 0.25
    assert w.attacked == 0.0
    assert w.material_exp == 1.0


def test_attacked_and_center_metrics_nonzero_midgame():
    board = chess.Board()
    board.push_san("e4")
    board.push_san("e5")
    board.push_san("Nf3")
    board.push_san("Nc6")
    assert attacked_pieces_balance(board) != 0 or center_control_balance(board) != 0
    metrics = compute_metrics(board)
    assert isinstance(metrics.attacked, int)
    assert isinstance(metrics.center, int)


def test_shorter_mate_scores_higher():
    # Black to move, checkmated (queen + king).
    board = chess.Board("6k1/6Q1/6K1/8/8/8/8/8 b - - 0 1")
    assert board.is_checkmate()
    short = evaluate(board, Weights(1, 0, 0), ply_from_root=1)
    long = evaluate(board, Weights(1, 0, 0), ply_from_root=5)
    assert short > long > 0
    assert score_to_bar(short)["label"] == "M1"
    assert score_to_bar(long)["label"] == "M3"
    assert short == MATE_SCORE - 1


def test_one_pawn_up_is_about_one_on_bar():
    board = chess.Board()
    board.remove_piece_at(chess.A7)
    data = score_to_bar(evaluate(board, Weights(1.0, 0.0, 0.0)))
    assert abs(data["score"] - 1.0) < 1e-9
    assert data["white_pct"] > 50


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
    result = bot.choose_move(board)
    assert result is not None
    move, score = result
    board.push(move)
    assert board.is_checkmate()
    assert score > 0


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
    result = bot.choose_move(board)
    assert result is not None
    move, score = result
    assert move in board.legal_moves
    assert isinstance(score, float)


def test_depth3_opening_move_is_fast():
    board = chess.Board()
    bot = Bot(
        name="Bench",
        weights=Weights(1.0, 0.2, 0.2),
        depth=3,
        use_parallel=False,
        lane="interactive",
    )
    t0 = time.perf_counter()
    result = bot.choose_move(board)
    elapsed = time.perf_counter() - t0
    assert result is not None
    assert elapsed < 0.45, f"depth-3 move too slow: {elapsed:.2f}s"


def test_score_to_bar_marks_search_source():
    data = score_to_bar(1.5)
    assert data["source"] == "search"
    assert data["white_pct"] > 50
