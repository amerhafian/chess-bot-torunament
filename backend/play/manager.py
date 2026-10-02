"""Human vs bot and Bot vs Stockfish play sessions."""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

import chess

from backend.engine.bot import Bot
from backend.engine.evaluation import Weights, evaluation_payload, score_to_bar
from backend.engine.names import generate_bot_name
from backend.engine.stockfish import StockfishEngine, StockfishUnavailable, stockfish_available
from backend.tournament.models import WeightRange, new_id
from backend.tournament.runner import MIN_WATCH_MOVE_SECONDS

PlayMode = Literal["human", "stockfish"]


@dataclass
class PlaySession:
    id: str
    bot_name: str
    weights: Weights
    depth: int
    human_color: chess.Color
    mode: PlayMode = "human"
    stockfish_color: Optional[chess.Color] = None
    stockfish_depth: int = 14
    fen: str = chess.STARTING_FEN
    moves: list[str] = field(default_factory=list)
    status: str = "active"  # active | finished
    result: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    bot_thinking: bool = False
    search_score: Optional[float] = None
    eval_history: list[Optional[float]] = field(default_factory=list)
    sf_search_score: Optional[float] = None
    sf_eval_history: list[Optional[float]] = field(default_factory=list)
    sf_thinking: bool = False

    def to_dict(self) -> dict[str, Any]:
        board = chess.Board(self.fen)
        payload: dict[str, Any] = {
            "id": self.id,
            "bot_name": self.bot_name,
            "weights": self.weights.to_dict(),
            "depth": self.depth,
            "mode": self.mode,
            "human_color": "white" if self.human_color == chess.WHITE else "black",
            "fen": self.fen,
            "moves": list(self.moves),
            "status": self.status,
            "result": self.result,
            "created_at": self.created_at,
            "bot_thinking": self.bot_thinking,
            "sf_thinking": self.sf_thinking,
            "turn": "white" if board.turn == chess.WHITE else "black",
            "search_score": self.search_score,
            "eval_history": list(self.eval_history),
            "evaluation": evaluation_payload(
                search_score=self.search_score,
                board=board,
                weights=self.weights,
            ),
            "sf_search_score": self.sf_search_score,
            "sf_eval_history": list(self.sf_eval_history),
            "sf_evaluation": (
                score_to_bar(self.sf_search_score) if self.sf_search_score is not None else None
            ),
        }
        if self.stockfish_color is not None:
            payload["stockfish_color"] = (
                "white" if self.stockfish_color == chess.WHITE else "black"
            )
            payload["stockfish_depth"] = self.stockfish_depth
            payload["bot_color"] = (
                "black" if self.stockfish_color == chess.WHITE else "white"
            )
        return payload


class PlayManager:
    def __init__(self) -> None:
        self.sessions: dict[str, PlaySession] = {}
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        self._boards: dict[str, chess.Board] = {}
        self._sf_tasks: dict[str, asyncio.Task] = {}

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
        mode: PlayMode = "human",
        stockfish_color: str = "white",
        stockfish_depth: int = 14,
    ) -> PlaySession:
        if mode == "stockfish" and not stockfish_available():
            raise StockfishUnavailable(
                "Stockfish binary not found. Install stockfish or set STOCKFISH_PATH."
            )
        color = chess.WHITE if human_color == "white" else chess.BLACK
        sf_color = chess.WHITE if stockfish_color == "white" else chess.BLACK
        session = PlaySession(
            id=new_id("p_"),
            bot_name=bot_name or generate_bot_name(),
            weights=weights,
            depth=depth,
            human_color=color if mode == "human" else (
                chess.BLACK if sf_color == chess.WHITE else chess.WHITE
            ),
            mode=mode,
            stockfish_color=sf_color if mode == "stockfish" else None,
            stockfish_depth=stockfish_depth,
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
        if session.mode == "stockfish":
            await self._run_stockfish_match(session_id)
            return self.sessions[session_id]
        if board.turn != session.human_color:
            await self._bot_move(session, board)
        return session

    async def start_stockfish_match(self, session_id: str) -> PlaySession:
        session = self.sessions[session_id]
        if session.mode != "stockfish":
            raise ValueError("Session is not a Stockfish match")
        if session_id not in self._sf_tasks or self._sf_tasks[session_id].done():
            self._sf_tasks[session_id] = asyncio.create_task(
                self._run_stockfish_match(session_id)
            )
        return session

    async def cancel_session(self, session_id: str) -> None:
        """Stop a Stockfish autoplay task and mark the session finished."""
        task = self._sf_tasks.pop(session_id, None)
        session = self.sessions.get(session_id)
        if session is not None and session.status == "active":
            session.status = "finished"
            session.bot_thinking = False
            session.sf_thinking = False
            if session.result is None:
                session.result = "1/2-1/2"
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def human_move(self, session_id: str, move_uci: str) -> PlaySession:
        session = self.sessions[session_id]
        board = self._boards[session_id]
        if session.mode == "stockfish":
            raise ValueError("This session is Bot vs Stockfish (no human moves)")
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

    async def _run_stockfish_match(self, session_id: str) -> None:
        session = self.sessions[session_id]
        board = self._boards[session_id]
        assert session.stockfish_color is not None
        engine: Optional[StockfishEngine] = None
        try:
            engine = await asyncio.to_thread(
                StockfishEngine, None, session.stockfish_depth
            )
            while session.status == "active":
                if board.turn == session.stockfish_color:
                    await self._stockfish_move(session, board, engine)
                else:
                    await self._bot_move(session, board, pace=True)
                # Yield so WS subscribers can flush between plies.
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            session.bot_thinking = False
            session.sf_thinking = False
            raise
        except Exception:
            session.status = "finished"
            session.result = session.result or "1/2-1/2"
            session.bot_thinking = False
            session.sf_thinking = False
            session.fen = board.fen()
            self._publish(session)
        finally:
            if engine is not None:
                await asyncio.to_thread(engine.close)
            self._sf_tasks.pop(session_id, None)

    async def _stockfish_move(
        self,
        session: PlaySession,
        board: chess.Board,
        engine: StockfishEngine,
    ) -> None:
        session.sf_thinking = True
        self._publish(session)
        t0 = time.perf_counter()
        result = await asyncio.to_thread(engine.choose_move, board)
        elapsed = time.perf_counter() - t0
        remaining = MIN_WATCH_MOVE_SECONDS - elapsed
        if remaining > 0:
            await asyncio.sleep(remaining)

        session.sf_thinking = False
        if result is None:
            self._update_result(session, board)
            self._publish(session)
            return

        san = board.san(result.move)
        board.push(result.move)
        session.moves.append(san)
        session.sf_search_score = result.score_white
        session.sf_eval_history.append(result.score_white)
        # Keep bot bar history aligned by ply (null on SF plies).
        session.eval_history.append(None)
        session.fen = board.fen()
        self._update_result(session, board)
        self._publish(session)

    async def _bot_move(
        self,
        session: PlaySession,
        board: chess.Board,
        *,
        pace: bool = True,
    ) -> None:
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
        if pace:
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
        if session.mode == "stockfish":
            session.sf_eval_history.append(None)
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
    range_d: WeightRange | None = None,
    range_e: WeightRange | None = None,
    range_exp: WeightRange | None = None,
    rng: random.Random | None = None,
) -> Weights:
    rng = rng or random.Random()
    range_d = range_d or WeightRange(0.0, 1.0)
    range_e = range_e or WeightRange(0.0, 1.0)
    range_exp = range_exp or WeightRange(1.0, 1.0)
    return Weights(
        material=rng.uniform(range_a.min, range_a.max),
        controlled=rng.uniform(range_b.min, range_b.max),
        checking=rng.uniform(range_c.min, range_c.max),
        attacked=rng.uniform(range_d.min, range_d.max),
        center=rng.uniform(range_e.min, range_e.max),
        material_exp=rng.uniform(range_exp.min, range_exp.max),
        controlled_exp=rng.uniform(range_exp.min, range_exp.max),
        checking_exp=rng.uniform(range_exp.min, range_exp.max),
        attacked_exp=rng.uniform(range_exp.min, range_exp.max),
        center_exp=rng.uniform(range_exp.min, range_exp.max),
    )
