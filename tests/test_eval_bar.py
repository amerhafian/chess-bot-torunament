"""Tests for UI evaluation display helpers and search-score payloads."""

from __future__ import annotations

import chess

from backend.engine.evaluation import (
    MATE_SCORE,
    Weights,
    display_eval,
    display_eval_averaged,
    score_to_bar,
)
from backend.play.manager import PlaySession
from backend.tournament.models import BotSpec, GameState


def test_display_eval_starting_near_even():
    board = chess.Board()
    data = display_eval(board, Weights(1, 0.2, 0.2))
    assert 40 <= data["white_pct"] <= 60
    assert data["source"] == "static"


def test_display_eval_material_advantage():
    board = chess.Board()
    board.remove_piece_at(chess.A7)
    data = display_eval(board, Weights(1.0, 0.0, 0.0))
    assert data["score"] > 0
    assert data["white_pct"] > 50


def test_game_to_dict_prefers_search_score():
    w = BotSpec(id="w", name="W", weights=Weights(1, 0.2, 0.2))
    b = BotSpec(id="b", name="B", weights=Weights(1.1, 0.3, 0.1))
    game = GameState(id="g1", white=w, black=b, search_score=12.5, eval_history=[12.5])
    payload = game.to_dict()
    assert payload["evaluation"]["source"] == "search"
    assert payload["evaluation"]["score"] == 12.5
    assert payload["eval_history"] == [12.5]


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
    assert payload["evaluation"]["source"] == "static"


def test_averaged_eval_is_finite():
    board = chess.Board()
    data = display_eval_averaged(board, Weights(1, 0, 0), Weights(2, 1, 1))
    assert isinstance(data["score"], float)


def test_score_to_bar_mate_labels():
    # Mate in 1 ply → M1
    assert score_to_bar(MATE_SCORE - 1)["label"] == "M1"
    assert score_to_bar(-(MATE_SCORE - 1))["label"] == "-M1"
    # Mate in 3 plies → M2
    assert score_to_bar(MATE_SCORE - 3)["label"] == "M2"
    assert score_to_bar(-(MATE_SCORE - 3))["label"] == "-M2"
