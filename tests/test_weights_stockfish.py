"""Tests for power-form weight persistence and Stockfish helpers."""

from __future__ import annotations

import chess
import chess.engine
import pytest

from backend.engine.evaluation import Weights
from backend.engine.stockfish import (
    StockfishUnavailable,
    resolve_stockfish_path,
    score_from_pov,
    stockfish_available,
)
from backend.weights import store as weight_store


def test_save_and_load_power_weights(tmp_path, monkeypatch):
    monkeypatch.setattr(weight_store, "WEIGHTS_DIR", tmp_path)
    w = Weights(
        material=1.5,
        controlled=0.4,
        checking=0.3,
        attacked=0.2,
        center=0.1,
        material_exp=1.2,
        controlled_exp=0.8,
        checking_exp=1.0,
        attacked_exp=1.1,
        center_exp=0.9,
    )
    saved = weight_store.save_weights("Power", w, source="test")
    assert saved["a1"] == 1.5
    assert saved["a2"] == 1.2
    assert saved["d1"] == 0.2
    loaded = weight_store.get_weights(saved["id"])
    assert loaded is not None
    again = Weights.from_dict(loaded)
    assert again.material == 1.5
    assert again.material_exp == 1.2
    assert again.attacked == 0.2


def test_legacy_abc_file_normalizes(tmp_path, monkeypatch):
    monkeypatch.setattr(weight_store, "WEIGHTS_DIR", tmp_path)
    path = tmp_path / "legacy.json"
    path.write_text(
        '{"id":"legacy","name":"Old","a":2.0,"b":0.5,"c":0.25,"created_at":1}',
        encoding="utf-8",
    )
    loaded = weight_store.get_weights("legacy")
    assert loaded is not None
    assert loaded["a1"] == 2.0
    assert loaded["a2"] == 1.0
    assert loaded["d1"] == 0.0
    assert loaded["a"] == 2.0


def test_score_from_pov_cp_and_mate():
    cp = chess.engine.PovScore(chess.engine.Cp(150), chess.WHITE)
    assert abs(score_from_pov(cp) - 1.5) < 1e-9
    mate = chess.engine.PovScore(chess.engine.Mate(2), chess.WHITE)
    score = score_from_pov(mate)
    assert score > 50000
    assert score_from_pov(chess.engine.PovScore(chess.engine.Mate(-1), chess.WHITE)) < -50000


def test_stockfish_availability_is_bool():
    assert isinstance(stockfish_available(), bool)
    path = resolve_stockfish_path()
    assert path is None or isinstance(path, str)


@pytest.mark.asyncio
async def test_create_stockfish_play_or_503():
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.play.manager import play_manager

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/play",
            json={
                "mode": "stockfish",
                "stockfish_color": "black",
                "depth": 2,
                "stockfish_depth": 5,
                "a1": 1.0,
                "b1": 0.1,
                "c1": 0.1,
            },
        )
        try:
            if stockfish_available():
                assert resp.status_code == 200
                data = resp.json()
                assert data["mode"] == "stockfish"
                assert data["stockfish_color"] == "black"
                assert data["bot_color"] == "white"
            else:
                assert resp.status_code == 503
                assert "Stockfish" in resp.json()["detail"]
        finally:
            if resp.status_code == 200:
                await play_manager.cancel_session(resp.json()["id"])


def test_stockfish_unavailable_message():
    err = StockfishUnavailable("missing")
    assert "missing" in str(err)
