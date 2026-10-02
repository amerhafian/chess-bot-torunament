"""FastAPI routes for tournaments, play, and weights."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

import chess

from backend.engine.evaluation import Weights, display_eval, display_eval_averaged
from backend.engine.stockfish import StockfishUnavailable, stockfish_available
from backend.play.manager import play_manager, random_weights
from backend.tournament.models import TournamentFormat, WeightRange
from backend.tournament.runner import manager, parse_config
from backend.weights import refine as weight_refine
from backend.weights import store as weight_store

router = APIRouter()


def _load_pinned(weight_ids: list[str]) -> list[tuple[str, Weights]]:
    pinned: list[tuple[str, Weights]] = []
    seen: set[str] = set()
    for weight_id in weight_ids:
        if not weight_id or weight_id in seen:
            continue
        seen.add(weight_id)
        saved = weight_store.get_weights(weight_id)
        if saved is None:
            raise HTTPException(status_code=404, detail=f"Saved weights not found: {weight_id}")
        label = str(saved.get("bot_name") or saved.get("name") or weight_id)
        pinned.append((label, Weights.from_dict(saved)))
    return pinned


class WeightRangeIn(BaseModel):
    min: float
    max: float


class WeightsFields(BaseModel):
    """Power-form weights with legacy a/b/c aliases."""

    a1: Optional[float] = None
    a2: Optional[float] = None
    b1: Optional[float] = None
    b2: Optional[float] = None
    c1: Optional[float] = None
    c2: Optional[float] = None
    d1: Optional[float] = None
    d2: Optional[float] = None
    e1: Optional[float] = None
    e2: Optional[float] = None
    f1: Optional[float] = None
    f2: Optional[float] = None
    g1: Optional[float] = None
    g2: Optional[float] = None
    h1: Optional[float] = None
    h2: Optional[float] = None
    i1: Optional[float] = None
    i2: Optional[float] = None
    j1: Optional[float] = None
    j2: Optional[float] = None
    k1: Optional[float] = None
    k2: Optional[float] = None
    l1: Optional[float] = None
    l2: Optional[float] = None
    m1: Optional[float] = None
    m2: Optional[float] = None
    n1: Optional[float] = None
    n2: Optional[float] = None
    a: Optional[float] = None
    b: Optional[float] = None
    c: Optional[float] = None


def weights_from_fields(body: WeightsFields) -> Weights:
    return Weights.from_dict(body.model_dump(exclude_none=True))


class TournamentCreateIn(BaseModel):
    bot_count: int = Field(default=4, ge=2, le=32)
    format: TournamentFormat = TournamentFormat.ROUND_ROBIN
    depth: int = Field(default=3, ge=1)
    range_a: WeightRangeIn = Field(default_factory=lambda: WeightRangeIn(min=0.5, max=2.0))
    range_b: WeightRangeIn = Field(default_factory=lambda: WeightRangeIn(min=0.0, max=1.0))
    range_c: WeightRangeIn = Field(default_factory=lambda: WeightRangeIn(min=0.0, max=1.0))
    range_d: WeightRangeIn = Field(default_factory=lambda: WeightRangeIn(min=0.0, max=1.0))
    range_e: WeightRangeIn = Field(default_factory=lambda: WeightRangeIn(min=0.0, max=1.0))
    range_exp: WeightRangeIn = Field(default_factory=lambda: WeightRangeIn(min=0.5, max=1.5))
    seed: Optional[int] = None
    weight_ids: list[str] = Field(default_factory=list)


class SaveWeightsIn(WeightsFields):
    name: str
    source: Optional[str] = None
    bot_name: Optional[str] = None


class SaveWinnerIn(BaseModel):
    name: Optional[str] = None


class PlayCreateIn(WeightsFields):
    depth: int = Field(default=3, ge=1)
    human_color: str = Field(default="white", pattern="^(white|black)$")
    mode: str = Field(default="human", pattern="^(human|stockfish)$")
    stockfish_color: str = Field(default="white", pattern="^(white|black)$")
    stockfish_depth: int = Field(default=14, ge=1)
    weight_id: Optional[str] = None
    randomize: bool = False
    range_a: WeightRangeIn = Field(default_factory=lambda: WeightRangeIn(min=0.5, max=2.0))
    range_b: WeightRangeIn = Field(default_factory=lambda: WeightRangeIn(min=0.0, max=1.0))
    range_c: WeightRangeIn = Field(default_factory=lambda: WeightRangeIn(min=0.0, max=1.0))
    range_d: WeightRangeIn = Field(default_factory=lambda: WeightRangeIn(min=0.0, max=1.0))
    range_e: WeightRangeIn = Field(default_factory=lambda: WeightRangeIn(min=0.0, max=1.0))
    range_exp: WeightRangeIn = Field(default_factory=lambda: WeightRangeIn(min=0.5, max=1.5))
    bot_name: Optional[str] = None


class HumanMoveIn(BaseModel):
    move: str


class EvaluateIn(WeightsFields):
    fen: str
    # Optional second weight set for averaged static eval (tournament review).
    weights2: Optional[dict[str, float]] = None


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/stockfish")
async def stockfish_status() -> dict[str, Any]:
    return {"available": stockfish_available()}


@router.post("/evaluate")
async def evaluate_position(body: EvaluateIn) -> dict[str, Any]:
    try:
        board = chess.Board(body.fen)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid FEN") from exc

    primary = body.model_dump(
        exclude_none=True,
        exclude={"fen", "weights2", "name", "source", "bot_name"},
    )
    w1 = Weights.from_dict(primary)
    if body.weights2:
        w2 = Weights.from_dict(body.weights2)
        return display_eval_averaged(board, w1, w2)
    return display_eval(board, w1)


@router.post("/tournaments")
async def create_tournament(body: TournamentCreateIn) -> dict[str, Any]:
    pinned = _load_pinned(body.weight_ids)
    try:
        config = parse_config(body.model_dump())
        tournament = await manager.create_tournament(config, pinned)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return tournament.to_dict()


@router.get("/tournaments")
async def list_tournaments() -> list[dict[str, Any]]:
    return [t.to_dict() for t in manager.list_tournaments()]


@router.get("/tournaments/{tournament_id}")
async def get_tournament(tournament_id: str) -> dict[str, Any]:
    tournament = manager.get_tournament(tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    return tournament.to_dict()


@router.get("/tournaments/{tournament_id}/games")
async def list_tournament_games(tournament_id: str) -> list[dict[str, Any]]:
    tournament = manager.get_tournament(tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    return [g.to_dict() for g in tournament.games.values()]


@router.get("/games/{game_id}")
async def get_game(game_id: str) -> dict[str, Any]:
    game = manager.get_game(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return game.to_dict()


@router.post("/tournaments/{tournament_id}/save-winner")
async def save_tournament_winner(tournament_id: str, body: SaveWinnerIn) -> dict[str, Any]:
    tournament = manager.get_tournament(tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if not tournament.winner_bot_id:
        raise HTTPException(status_code=400, detail="Tournament has no winner yet")
    winner = next(b for b in tournament.bots if b.id == tournament.winner_bot_id)
    name = body.name or f"{winner.name} (tournament winner)"
    return weight_store.save_weights(
        name,
        winner.weights,
        source=f"tournament:{tournament_id}",
        bot_name=winner.name,
    )


@router.get("/weights")
async def list_weights() -> list[dict[str, Any]]:
    return weight_store.list_weights()


@router.post("/weights")
async def save_weights(body: SaveWeightsIn) -> dict[str, Any]:
    weights = weights_from_fields(body)
    return weight_store.save_weights(
        body.name,
        weights,
        source=body.source,
        bot_name=body.bot_name,
    )


class RefineIn(BaseModel):
    bot_count: int = Field(default=4, ge=2, le=32)
    depth: int = Field(default=3, ge=1)
    weight_ids: list[str] = Field(default_factory=list)


@router.post("/weights/refine")
async def start_weight_refine(body: RefineIn) -> dict[str, Any]:
    pinned = _load_pinned(body.weight_ids)
    try:
        return weight_refine.start_refine(bot_count=body.bot_count, depth=body.depth, pinned=pinned)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/weights/refine")
async def refine_status() -> dict[str, Any]:
    return weight_refine.current_refine()


@router.get("/weights/refine/{job_id}")
async def refine_job(job_id: str) -> dict[str, Any]:
    job = weight_refine.get_refine(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Weight search not found")
    return job


@router.get("/weights/{weight_id}")
async def get_weights(weight_id: str) -> dict[str, Any]:
    data = weight_store.get_weights(weight_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Weights not found")
    return data


@router.delete("/weights/{weight_id}")
async def delete_weights(weight_id: str) -> dict[str, bool]:
    ok = weight_store.delete_weights(weight_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Weights not found")
    return {"deleted": True}


def _resolve_play_weights(body: PlayCreateIn) -> tuple[Weights, Optional[str]]:
    bot_name = body.bot_name
    if body.weight_id:
        saved = weight_store.get_weights(body.weight_id)
        if saved is None:
            raise HTTPException(status_code=404, detail="Weights not found")
        return Weights.from_dict(saved), bot_name or saved.get("bot_name") or saved.get("name")

    has_explicit = any(
        v is not None
        for v in (
            body.a1,
            body.b1,
            body.c1,
            body.d1,
            body.e1,
            body.a,
            body.b,
            body.c,
        )
    )
    if body.randomize or not has_explicit:
        return (
            random_weights(
                WeightRange(body.range_a.min, body.range_a.max),
                WeightRange(body.range_b.min, body.range_b.max),
                WeightRange(body.range_c.min, body.range_c.max),
                WeightRange(body.range_d.min, body.range_d.max),
                WeightRange(body.range_e.min, body.range_e.max),
                WeightRange(body.range_exp.min, body.range_exp.max),
            ),
            bot_name,
        )
    return weights_from_fields(body), bot_name


@router.post("/play")
async def create_play(body: PlayCreateIn) -> dict[str, Any]:
    weights, bot_name = _resolve_play_weights(body)
    try:
        session = play_manager.create_session(
            weights=weights,
            depth=body.depth,
            human_color=body.human_color,
            bot_name=bot_name,
            mode=body.mode,  # type: ignore[arg-type]
            stockfish_color=body.stockfish_color,
            stockfish_depth=body.stockfish_depth,
        )
    except StockfishUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if body.mode == "stockfish":
        await play_manager.start_stockfish_match(session.id)
        session = play_manager.get(session.id) or session
    elif body.human_color == "black":
        await play_manager.maybe_bot_opening_move(session.id)
        session = play_manager.get(session.id) or session
    return session.to_dict()


@router.get("/play/{session_id}")
async def get_play(session_id: str) -> dict[str, Any]:
    session = play_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Play session not found")
    return session.to_dict()


@router.post("/play/{session_id}/move")
async def play_move(session_id: str, body: HumanMoveIn) -> dict[str, Any]:
    session = play_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Play session not found")
    try:
        session = await play_manager.human_move(session_id, body.move)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return session.to_dict()


@router.websocket("/ws/games/{game_id}")
async def ws_game(websocket: WebSocket, game_id: str) -> None:
    game = manager.get_game(game_id)
    if game is None:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    queue = manager.subscribe_game(game_id)
    await websocket.send_json({"type": "game", "game": game.to_dict()})
    try:
        while True:
            import asyncio

            recv_task = asyncio.create_task(websocket.receive_text())
            queue_task = asyncio.create_task(queue.get())
            done, pending = await asyncio.wait(
                {recv_task, queue_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            if queue_task in done:
                payload = queue_task.result()
                await websocket.send_json(payload)
            if recv_task in done:
                try:
                    recv_task.result()
                except WebSocketDisconnect:
                    break
    except WebSocketDisconnect:
        pass
    finally:
        manager.unsubscribe_game(game_id, queue)


@router.websocket("/ws/tournaments/{tournament_id}")
async def ws_tournament(websocket: WebSocket, tournament_id: str) -> None:
    tournament = manager.get_tournament(tournament_id)
    if tournament is None:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    queue = manager.subscribe_tournament(tournament_id)
    await websocket.send_json({"type": "tournament", "tournament": tournament.to_dict()})
    try:
        import asyncio

        while True:
            recv_task = asyncio.create_task(websocket.receive_text())
            queue_task = asyncio.create_task(queue.get())
            done, pending = await asyncio.wait(
                {recv_task, queue_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            if queue_task in done:
                await websocket.send_json(queue_task.result())
            if recv_task in done:
                try:
                    recv_task.result()
                except WebSocketDisconnect:
                    break
    except WebSocketDisconnect:
        pass
    finally:
        manager.unsubscribe_tournament(tournament_id, queue)


@router.websocket("/ws/play/{session_id}")
async def ws_play(websocket: WebSocket, session_id: str) -> None:
    session = play_manager.get(session_id)
    if session is None:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    queue = play_manager.subscribe(session_id)
    await websocket.send_json({"type": "play", "session": session.to_dict()})
    try:
        import asyncio

        while True:
            recv_task = asyncio.create_task(websocket.receive_text())
            queue_task = asyncio.create_task(queue.get())
            done, pending = await asyncio.wait(
                {recv_task, queue_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            if queue_task in done:
                await websocket.send_json(queue_task.result())
            if recv_task in done:
                try:
                    recv_task.result()
                except WebSocketDisconnect:
                    break
    except WebSocketDisconnect:
        pass
    finally:
        play_manager.unsubscribe(session_id, queue)
