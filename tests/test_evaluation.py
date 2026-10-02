"""Unit tests for evaluation metrics and alpha-beta bot."""

from __future__ import annotations

import chess

from backend.engine.bot import Bot
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
    # Two white rooks on open file both attack e4-like squares; use simple position.
    board = chess.Board(None)
    board.set_piece_at(chess.A1, chess.Piece.from_symbol("R"))
    board.set_piece_at(chess.A2, chess.Piece.from_symbol("R"))
    board.set_piece_at(chess.E8, chess.Piece.from_symbol("k"))
    board.set_piece_at(chess.E1, chess.Piece.from_symbol("K"))
    # Attacked squares include overlap on the a-file between them.
    white_only = controlled_squares_balance(board)
    assert white_only > 0
    # Removing second rook should reduce control count.
    board.remove_piece_at(chess.A2)
    assert controlled_squares_balance(board) < white_only


def test_checking_moves_scholars_mate_threat():
    # After 1.e4 e5 2.Qh5 Nc6 3.Bc4 — White has Qxf7# available among checks.
    board = chess.Board()
    board.push_san("e4")
    board.push_san("e5")
    board.push_san("Qh5")
    board.push_san("Nc6")
    board.push_san("Bc4")
    board.push_san("Nf6")
    # White to move with Qxf7#
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
    )
    move = bot.choose_move(board)
    assert move is not None
    board.push(move)
    assert board.is_checkmate()


def test_default_depth_is_five():
    bot = Bot(name="Deep", weights=Weights(1, 1, 1))
    assert bot.depth == 5
