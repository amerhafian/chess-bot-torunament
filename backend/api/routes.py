"""FastAPI routes for tournaments, play, and weights."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from backend.engine.evaluation import Weights
from backend.play.manager import play_manager, random_weights
from backend.tournament.models import TournamentFormat, WeightRange
from backend.tournament.runner import manager, parse_config
from backend.weights import store as weight_store

router = APIRouter()


class WeightRangeIn(BaseModel):
    min: float
    max: float


class TournamentCreateIn(BaseModel):
    bot_count: int = Field(default=4, ge=2, le=32)
    format: TournamentFormat = TournamentFormat.ROUND_ROBIN
    depth: int = Field(default=5, ge=1, le=6)
    range_a: WeightRangeIn = Field(default_factory=lambda: WeightRangeIn(min=0.5, max=2.0))
    range_b: WeightRangeIn = Field(default_factory=lambda: WeightRangeIn(min=0.0, max=1.0))
    range_c: WeightRangeIn = Field(default_factory=lambda: WeightRangeIn(min=0.0, max=1.0))
    seed: Optional[int] = None


class SaveWeightsIn(BaseModel):
    name: str
    a: float
    b: float
    c: float
    source: Optional[str] = None
    bot_name: Optional[str] = None


class SaveWinnerIn(BaseModel):
    name: Optional[str] = None


class PlayCreateIn(BaseModel):
    depth: int = Field(default=5, ge=1, le=6)
    human_color: str = Field(default="white", pattern="^(white|black)$")
    weight_id: Optional[str] = None
    a: Optional[float] = None
    b: Optional[float] = None
    c: Optional[float] = None
    randomize: bool = False
    range_a: WeightRangeIn = Field(default_factory=lambda: WeightRangeIn(min=0.5, max=2.0))
    range_b: WeightRangeIn = Field(default_factory=lambda: WeightRangeIn(min=0.0, max=1.0))
    range_c: WeightRangeIn = Field(default_factory=lambda: WeightRangeIn(min=0.0, max=1.0))
    bot_name: Optional[str] = None


class HumanMoveIn(BaseModel):
    move: str


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/tournaments")
async def create_tournament(body: TournamentCreateIn) -> dict[str, Any]:
    try:
        config = parse_config(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    tournament = await manager.create_tournament(config)
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
    weights = Weights(material=body.a, controlled=body.b, checking=body.c)
    return weight_store.save_weights(
        body.name,
        weights,
        source=body.source,
        bot_name=body.bot_name,
    )


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


@router.post("/play")
async def create_play(body: PlayCreateIn) -> dict[str, Any]:
    bot_name = body.bot_name
    if body.weight_id:
        saved = weight_store.get_weights(body.weight_id)
        if saved is None:
            raise HTTPException(status_code=404, detail="Weights not found")
        weights = Weights(material=saved["a"], controlled=saved["b"], checking=saved["c"])
        bot_name = bot_name or saved.get("bot_name") or saved.get("name")
    elif body.randomize or body.a is None or body.b is None or body.c is None:
        weights = random_weights(
            WeightRange(body.range_a.min, body.range_a.max),
            WeightRange(body.range_b.min, body.range_b.max),
            WeightRange(body.range_c.min, body.range_c.max),
        )
    else:
        weights = Weights(material=body.a, controlled=body.b, checking=body.c)

    session = play_manager.create_session(
        weights=weights,
        depth=body.depth,
        human_color=body.human_color,
        bot_name=bot_name,
    )
    # If human is black, bot should move first — kick off async
    if body.human_color == "black":
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


async def _ws_pump(websocket: WebSocket, queue) -> None:
    while True:
        payload = await queue.get()
        await websocket.send_json(payload)


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
            # Also accept client pings / ignore inbound
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
