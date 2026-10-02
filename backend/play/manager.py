"""Human vs bot play sessions."""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import chess

from backend.engine.bot import Bot
from backend.engine.evaluation import Weights, evaluation_payload
from backend.engine.names import generate_bot_name
from backend.tournament.models import WeightRange, new_id
from backend.tournament.runner import MIN_WATCH_MOVE_SECONDS


@dataclass
class PlaySession:
    id: str
    bot_name: str
    weights: Weights
    depth: int
    human_color: chess.Color
    fen: str = chess.STARTING_FEN
    moves: list[str] = field(default_factory=list)
    status: str = "active"  # active | finished
    result: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    bot_thinking: bool = False
    search_score: Optional[float] = None
    eval_history: list[Optional[float]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        board = chess.Board(self.fen)
        return {
            "id": self.id,
            "bot_name": self.bot_name,
            "weights": self.weights.to_dict(),
            "depth": self.depth,
            "human_color": "white" if self.human_color == chess.WHITE else "black",
            "fen": self.fen,
            "moves": list(self.moves),
            "status": self.status,
            "result": self.result,
            "created_at": self.created_at,
            "bot_thinking": self.bot_thinking,
            "turn": "white" if board.turn == chess.WHITE else "black",
            "search_score": self.search_score,
            "eval_history": list(self.eval_history),
            "evaluation": evaluation_payload(
                search_score=self.search_score,
                board=board,
                weights=self.weights,
            ),
        }


class PlayManager:
    def __init__(self) -> None:
        self.sessions: dict[str, PlaySession] = {}
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        self._boards: dict[str, chess.Board] = {}

    def subscribe(self, session_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._subscribers.setdefault(session_id, set()).add(queue)
        return queue

    def unsubscribe(self, session_id: str, queue: asyncio.Queue) -> None:
        subs = self._subscribers.get(session_id)
        if not subs:
            return
        subs.discard(queue)
        if not subs:
            self._subscribers.pop(session_id, None)

    def _publish(self, session: PlaySession) -> None:
        payload = {"type": "play", "session": session.to_dict()}
        for queue in list(self._subscribers.get(session.id, ())):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    queue.put_nowait(payload)
                except asyncio.QueueFull:
                    pass

    def create_session(
        self,
        *,
        weights: Weights,
        depth: int = 3,
        human_color: str = "white",
        bot_name: Optional[str] = None,
    ) -> PlaySession:
        color = chess.WHITE if human_color == "white" else chess.BLACK
        session = PlaySession(
            id=new_id("p_"),
            bot_name=bot_name or generate_bot_name(),
            weights=weights,
            depth=depth,
            human_color=color,
        )
        self.sessions[session.id] = session
        self._boards[session.id] = chess.Board()
        return session

    def get(self, session_id: str) -> Optional[PlaySession]:
        return self.sessions.get(session_id)

    async def maybe_bot_opening_move(self, session_id: str) -> PlaySession:
        session = self.sessions[session_id]
        board = self._boards[session_id]
        if session.status != "active":
            return session
        if board.turn != session.human_color:
            await self._bot_move(session, board)
        return session

    async def human_move(self, session_id: str, move_uci: str) -> PlaySession:
        session = self.sessions[session_id]
        board = self._boards[session_id]
        if session.status != "active":
            raise ValueError("Game is finished")
        if board.turn != session.human_color:
            raise ValueError("Not your turn")

        try:
            move = chess.Move.from_uci(move_uci)
        except ValueError as exc:
            raise ValueError("Invalid move format") from exc
        if move not in board.legal_moves:
            raise ValueError("Illegal move")

        san = board.san(move)
        board.push(move)
        session.moves.append(san)
        # Human ply: no search score yet — keep prior search_score for bar until bot replies.
        session.eval_history.append(None)
        session.fen = board.fen()
        self._update_result(session, board)
        self._publish(session)

        if session.status == "active" and board.turn != session.human_color:
            await self._bot_move(session, board)
        return session

    async def _bot_move(self, session: PlaySession, board: chess.Board) -> None:
        session.bot_thinking = True
        self._publish(session)
        bot = Bot(
            session.bot_name,
            session.weights,
            session.depth,
            lane="interactive",
        )
        t0 = time.perf_counter()
        result = await asyncio.to_thread(bot.choose_move, board)
        elapsed = time.perf_counter() - t0
        remaining = MIN_WATCH_MOVE_SECONDS - elapsed
        if remaining > 0:
            await asyncio.sleep(remaining)

        session.bot_thinking = False
        if result is None:
            self._update_result(session, board)
            self._publish(session)
            return

        move, score = result
        san = board.san(move)
        board.push(move)
        session.moves.append(san)
        session.search_score = score
        session.eval_history.append(score)
        session.fen = board.fen()
        self._update_result(session, board)
        self._publish(session)

    def _update_result(self, session: PlaySession, board: chess.Board) -> None:
        if not board.is_game_over(claim_draw=True):
            return
        session.status = "finished"
        outcome = board.outcome(claim_draw=True)
        if outcome is None or outcome.winner is None:
            session.result = "1/2-1/2"
        elif outcome.winner == chess.WHITE:
            session.result = "1-0"
        else:
            session.result = "0-1"


play_manager = PlayManager()


def random_weights(
    range_a: WeightRange,
    range_b: WeightRange,
    range_c: WeightRange,
    rng: random.Random | None = None,
) -> Weights:
    rng = rng or random.Random()
    return Weights(
        material=rng.uniform(range_a.min, range_a.max),
        controlled=rng.uniform(range_b.min, range_b.max),
        checking=rng.uniform(range_c.min, range_c.max),
    )
