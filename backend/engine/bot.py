"""Alpha-beta chess bot with TT and lane-isolated root parallelism.

Interactive (human vs bot) and background (tournaments) use separate
ProcessPoolExecutors so tournament root searches cannot queue-starve live play.
"""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from multiprocessing import get_context
from typing import Literal, Optional

import chess

from backend.engine.evaluation import Weights, evaluate

BOUND_EXACT = 0
BOUND_LOWER = 1
BOUND_UPPER = 2

DEFAULT_DEPTH = 3
MAX_ROOT_WORKERS = 8
MIN_DEPTH_FOR_POOL = 3
MIN_MOVES_FOR_POOL = 4

SearchLane = Literal["interactive", "background"]
MoveResult = tuple[chess.Move, float]

# Lane-isolated process pools (lazy).
_POOLS: dict[SearchLane, ProcessPoolExecutor | None] = {
    "interactive": None,
    "background": None,
}
_POOL_WORKERS: dict[SearchLane, int] = {
    "interactive": 0,
    "background": 0,
}


def interactive_worker_count() -> int:
    cpus = os.cpu_count() or 2
    return max(1, min(2, cpus))


def background_worker_count() -> int:
    cpus = os.cpu_count() or 2
    reserved = interactive_worker_count()
    return max(1, min(MAX_ROOT_WORKERS, cpus - reserved if cpus > reserved else 1))


def root_worker_count(lane: SearchLane = "background") -> int:
    """Workers for a search lane's process pool."""
    if lane == "interactive":
        return interactive_worker_count()
    return background_worker_count()


def game_concurrency() -> int:
    """How many tournament games may run at once."""
    cpus = os.cpu_count() or 2
    return max(4, min(8, cpus))


def _reset_pool(lane: SearchLane) -> None:
    pool = _POOLS.get(lane)
    if pool is not None:
        try:
            pool.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
    _POOLS[lane] = None
    _POOL_WORKERS[lane] = 0


def _get_pool(lane: SearchLane) -> ProcessPoolExecutor:
    workers = root_worker_count(lane)
    pool = _POOLS[lane]
    if pool is None or _POOL_WORKERS[lane] != workers:
        _reset_pool(lane)
        _POOLS[lane] = ProcessPoolExecutor(
            max_workers=workers,
            mp_context=get_context("spawn"),
        )
        _POOL_WORKERS[lane] = workers
    assert _POOLS[lane] is not None
    return _POOLS[lane]


@dataclass
class Bot:
    """A named alpha-beta player with fixed evaluation weights."""

    name: str
    weights: Weights
    depth: int = DEFAULT_DEPTH
    use_parallel: bool = True
    lane: SearchLane = "background"

    def choose_move(self, board: chess.Board) -> Optional[MoveResult]:
        """Return (best_move, white_perspective_score), or None if no legal moves."""
        legal = list(board.legal_moves)
        if not legal:
            return None

        ordered = _order_moves(board, legal)
        workers = root_worker_count(self.lane)
        use_pool = (
            self.use_parallel
            and self.depth >= MIN_DEPTH_FOR_POOL
            and len(ordered) >= MIN_MOVES_FOR_POOL
            and workers > 1
        )
        if use_pool:
            try:
                return _choose_move_parallel(
                    board, ordered, self.weights, self.depth, self.lane
                )
            except Exception:
                _reset_pool(self.lane)

        # Background serial in a worker process (keeps GIL off the API process).
        # Skip if parallel already preferred and failed — still try once.
        if self.lane == "background" and workers >= 1:
            try:
                return _choose_move_serial_in_process(
                    board, ordered, self.weights, self.depth, self.lane
                )
            except Exception:
                _reset_pool(self.lane)

        # Interactive: run inline (caller already uses asyncio.to_thread).
        return _choose_move_serial(board, ordered, self.weights, self.depth)


def _choose_move_serial(
    board: chess.Board,
    ordered: list[chess.Move],
    weights: Weights,
    depth: int,
) -> MoveResult:
    maximizing = board.turn == chess.WHITE
    best_move = ordered[0]
    best_score = float("-inf") if maximizing else float("inf")
    tt: dict = {}

    for move in ordered:
        board.push(move)
        score = _alphabeta(
            board,
            depth - 1,
            float("-inf"),
            float("inf"),
            board.turn == chess.WHITE,
            weights,
            tt,
        )
        board.pop()
        if maximizing:
            if score > best_score:
                best_score = score
                best_move = move
        elif score < best_score:
            best_score = score
            best_move = move
    return best_move, best_score


def _choose_move_parallel(
    board: chess.Board,
    ordered: list[chess.Move],
    weights: Weights,
    depth: int,
    lane: SearchLane,
) -> MoveResult:
    fen = board.fen()
    maximizing = board.turn == chess.WHITE
    weight_tuple = weights.as_tuple()
    args = [(fen, move.uci(), depth - 1, weight_tuple) for move in ordered]

    pool = _get_pool(lane)
    results = list(pool.map(_score_root_move, args, chunksize=2))

    best_move_uci = results[0][0]
    best_score = results[0][1]
    for move_uci, score in results[1:]:
        if maximizing:
            if score > best_score:
                best_score = score
                best_move_uci = move_uci
        elif score < best_score:
            best_score = score
            best_move_uci = move_uci
    return chess.Move.from_uci(best_move_uci), best_score


def _choose_move_serial_in_process(
    board: chess.Board,
    ordered: list[chess.Move],
    weights: Weights,
    depth: int,
    lane: SearchLane,
) -> MoveResult:
    payload = (
        board.fen(),
        [m.uci() for m in ordered],
        depth,
        weights.as_tuple(),
    )
    pool = _get_pool(lane)
    move_uci, score = pool.submit(_serial_search_worker, payload).result()
    return chess.Move.from_uci(move_uci), score


def _score_root_move(payload: tuple[str, str, int, tuple[float, float, float]]) -> tuple[str, float]:
    """Worker entry: score one root move. Must be top-level for pickling."""
    fen, move_uci, depth, weight_tuple = payload
    board = chess.Board(fen)
    move = chess.Move.from_uci(move_uci)
    weights = Weights(*weight_tuple)
    board.push(move)
    tt: dict = {}
    score = _alphabeta(
        board,
        depth,
        float("-inf"),
        float("inf"),
        board.turn == chess.WHITE,
        weights,
        tt,
    )
    return move_uci, score


def _serial_search_worker(
    payload: tuple[str, list[str], int, tuple[float, float, float]],
) -> tuple[str, float]:
    """Worker entry: full serial root search in a background process."""
    fen, move_ucis, depth, weight_tuple = payload
    board = chess.Board(fen)
    ordered = [chess.Move.from_uci(u) for u in move_ucis]
    weights = Weights(*weight_tuple)
    move, score = _choose_move_serial(board, ordered, weights, depth)
    return move.uci(), score


def _order_moves(board: chess.Board, moves: list[chess.Move]) -> list[chess.Move]:
    """Prefer captures for better alpha-beta pruning (no gives_check — too costly)."""
    return sorted(moves, key=board.is_capture, reverse=True)


def _is_cheap_terminal(board: chess.Board) -> bool:
    """Fast terminal detection for search — skips expensive threefold scans."""
    if board.is_insufficient_material():
        return True
    if board.halfmove_clock >= 100:
        return True
    # Checkmate / stalemate: no legal moves
    try:
        next(board.generate_legal_moves())
        return False
    except StopIteration:
        return True


def _alphabeta(
    board: chess.Board,
    depth: int,
    alpha: float,
    beta: float,
    maximizing: bool,
    weights: Weights,
    tt: dict,
) -> float:
    alpha_orig = alpha
    key = board._transposition_key()
    entry = tt.get(key)
    if entry is not None:
        e_depth, e_score, e_bound = entry
        if e_depth >= depth:
            if e_bound == BOUND_EXACT:
                return e_score
            if e_bound == BOUND_LOWER:
                alpha = max(alpha, e_score)
            elif e_bound == BOUND_UPPER:
                beta = min(beta, e_score)
            if alpha >= beta:
                return e_score

    if depth == 0 or _is_cheap_terminal(board):
        return evaluate(board, weights, depth_remaining=depth)

    moves = _order_moves(board, list(board.legal_moves))
    if not moves:
        return evaluate(board, weights, depth_remaining=depth)

    if maximizing:
        value = float("-inf")
        for move in moves:
            board.push(move)
            value = max(
                value,
                _alphabeta(board, depth - 1, alpha, beta, False, weights, tt),
            )
            board.pop()
            alpha = max(alpha, value)
            if alpha >= beta:
                break
    else:
        value = float("inf")
        for move in moves:
            board.push(move)
            value = min(
                value,
                _alphabeta(board, depth - 1, alpha, beta, True, weights, tt),
            )
            board.pop()
            beta = min(beta, value)
            if alpha >= beta:
                break

    bound = BOUND_EXACT
    if value <= alpha_orig:
        bound = BOUND_UPPER
    elif value >= beta:
        bound = BOUND_LOWER
    tt[key] = (depth, value, bound)
    return value
