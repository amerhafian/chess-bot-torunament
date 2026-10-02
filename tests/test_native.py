"""Native engine: perft, eval agreement, and shared tactical moves."""

from __future__ import annotations

import chess
import pytest

from backend.engine.bot import Bot
from backend.engine.evaluation import Weights, static_eval

native = pytest.importorskip("backend.engine.native")


def test_perft_start_position():
    fen = chess.STARTING_FEN
    assert native.perft(fen, 1) == 20
    assert native.perft(fen, 2) == 400
    assert native.perft(fen, 3) == 8902


def test_static_eval_matches_python():
    weights = Weights(
        material=1.0,
        controlled=0.2,
        checking=0.15,
        attacked=0.1,
        center=0.1,
        pst=0.2,
        passed=0.25,
        structure=0.1,
        shield=0.1,
        bishop=0.2,
        rook_file=0.1,
        tempo=0.1,
        outpost=0.2,
        tropism=0.15,
    )
    board = chess.Board()
    board.push_san("e4")
    board.push_san("c5")
    board.push_san("Nf3")
    python_score = static_eval(board, weights)
    native_score = native.evaluate_fen(board.fen(), list(weights.as_tuple()))
    assert python_score == pytest.approx(native_score, abs=1e-6)


def test_native_and_python_agree_on_tactical_depth_two():
    weights = Weights(material=1.0)
    scholar = chess.Board()
    for san in ("e4", "e5", "Qh5", "Nc6", "Bc4", "Nf6"):
        scholar.push_san(san)
    hanging = chess.Board(None)
    hanging.set_piece_at(chess.B3, chess.Piece.from_symbol("N"))
    hanging.set_piece_at(chess.E1, chess.Piece.from_symbol("K"))
    hanging.set_piece_at(chess.A5, chess.Piece.from_symbol("q"))
    hanging.set_piece_at(chess.E8, chess.Piece.from_symbol("k"))
    for board in (scholar, hanging):
        python_bot = Bot("py", weights, depth=2, use_parallel=False, use_native=False, lane="interactive")
        native_bot = Bot("cpp", weights, depth=2, use_parallel=False, use_native=True, lane="interactive")
        py_move = python_bot.choose_move(board)
        cpp_move = native_bot.choose_move(board)
        assert py_move is not None and cpp_move is not None
        assert py_move[0] == cpp_move[0]
