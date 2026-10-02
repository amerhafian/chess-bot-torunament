"""Alpha-beta chess bot with TT and root-move parallelism."""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from multiprocessing import get_context
from typing import Optional

import chess

from backend.engine.evaluation import Weights, evaluate

BOUND_EXACT = 0
BOUND_LOWER = 1
BOUND_UPPER = 2

DEFAULT_DEPTH = 3
MAX_ROOT_WORKERS = 8
MIN_DEPTH_FOR_POOL = 3
MIN_MOVES_FOR_POOL = 4

# Shared pool for the process (lazy). Avoids spawn-per-move overhead.
_POOL: ProcessPoolExecutor | None = None
_POOL_WORKERS: int = 0


def root_worker_count() -> int:
    """Size of the shared root-move process pool."""
    cpus = os.cpu_count() or 2
    return max(1, min(MAX_ROOT_WORKERS, cpus))


def game_concurrency() -> int:
    """How many tournament games may run at once (shared search pool)."""
    cpus = os.cpu_count() or 2
    return max(4, min(8, cpus))


def _get_pool() -> ProcessPoolExecutor:
    global _POOL, _POOL_WORKERS
    workers = root_worker_count()
    if _POOL is None or _POOL_WORKERS != workers:
        if _POOL is not None:
            _POOL.shutdown(wait=False, cancel_futures=True)
        # spawn avoids forking an already-running asyncio/uvicorn process
        _POOL = ProcessPoolExecutor(
            max_workers=workers,
            mp_context=get_context("spawn"),
        )
        _POOL_WORKERS = workers
    return _POOL


@dataclass
class Bot:
    """A named alpha-beta player with fixed evaluation weights."""

    name: str
    weights: Weights
    depth: int = DEFAULT_DEPTH
    use_parallel: bool = True

    def choose_move(self, board: chess.Board) -> Optional[chess.Move]:
        """Return the best move for the side to move, or None if no legal moves."""
        legal = list(board.legal_moves)
        if not legal:
            return None

        ordered = _order_moves(board, legal)
        use_pool = (
            self.use_parallel
            and self.depth >= MIN_DEPTH_FOR_POOL
            and len(ordered) >= MIN_MOVES_FOR_POOL
            and root_worker_count() > 1
        )
        if use_pool:
            try:
                return _choose_move_parallel(board, ordered, self.weights, self.depth)
            except Exception:
                # Pool can break under some launch contexts; fall back cleanly.
                global _POOL, _POOL_WORKERS
                if _POOL is not None:
                    try:
                        _POOL.shutdown(wait=False, cancel_futures=True)
                    except Exception:
                        pass
                _POOL = None
                _POOL_WORKERS = 0
        return _choose_move_serial(board, ordered, self.weights, self.depth)


def _choose_move_serial(
    board: chess.Board,
    ordered: list[chess.Move],
    weights: Weights,
    depth: int,
) -> chess.Move:
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
    return best_move


def _choose_move_parallel(
    board: chess.Board,
    ordered: list[chess.Move],
    weights: Weights,
    depth: int,
) -> chess.Move:
    fen = board.fen()
    maximizing = board.turn == chess.WHITE
    weight_tuple = weights.as_tuple()
    args = [(fen, move.uci(), depth - 1, weight_tuple) for move in ordered]

    pool = _get_pool()
    results = list(pool.map(_score_root_move, args, chunksize=1))

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
    return chess.Move.from_uci(best_move_uci)


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


def _order_moves(board: chess.Board, moves: list[chess.Move]) -> list[chess.Move]:
    """Prefer captures / checks for better alpha-beta pruning."""

    def key(move: chess.Move) -> tuple[int, int]:
        capture = 1 if board.is_capture(move) else 0
        check = 1 if board.gives_check(move) else 0
        return (capture, check)

    return sorted(moves, key=key, reverse=True)


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

    if depth == 0 or board.is_game_over(claim_draw=True):
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
