"""Tests for UI evaluation display helpers."""

from __future__ import annotations

import chess

from backend.engine.evaluation import Weights, display_eval, display_eval_averaged
from backend.play.manager import PlaySession
from backend.tournament.models import BotSpec, GameState


def test_display_eval_starting_near_even():
    board = chess.Board()
    data = display_eval(board, Weights(1, 0.2, 0.2))
    assert 40 <= data["white_pct"] <= 60
    assert data["label"]


def test_display_eval_material_advantage():
    board = chess.Board()
    board.remove_piece_at(chess.A7)
    data = display_eval(board, Weights(1.0, 0.0, 0.0))
    assert data["score"] > 0
    assert data["white_pct"] > 50


def test_game_to_dict_includes_evaluation():
    w = BotSpec(id="w", name="W", weights=Weights(1, 0.2, 0.2))
    b = BotSpec(id="b", name="B", weights=Weights(1.1, 0.3, 0.1))
    game = GameState(id="g1", white=w, black=b)
    payload = game.to_dict()
    assert "evaluation" in payload
    assert "white_pct" in payload["evaluation"]
    assert "label" in payload["evaluation"]


def test_play_session_to_dict_includes_evaluation():
    session = PlaySession(
        id="p1",
        bot_name="Bot",
        weights=Weights(1, 0.2, 0.2),
        depth=3,
        human_color=chess.WHITE,
    )
    payload = session.to_dict()
    assert "evaluation" in payload
    assert 0 <= payload["evaluation"]["white_pct"] <= 100


def test_averaged_eval_is_finite():
    board = chess.Board()
    data = display_eval_averaged(board, Weights(1, 0, 0), Weights(2, 1, 1))
    assert isinstance(data["score"], float)
