"""Alpha-beta chess bot with quiescence, iterative deepening, and a native engine.

Interactive (human vs bot) and background (tournaments) use separate
ProcessPoolExecutors so tournament root searches cannot queue-starve live play.
When the C++ extension is built, ``choose_move`` uses it. The Python search
remains the fallback and the low-depth reference.
"""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from multiprocessing import get_context
from typing import Literal, Optional

import chess

from backend.engine.evaluation import MATE_SCORE, PIECE_VALUES, Weights, static_eval

BOUND_EXACT = 0
BOUND_LOWER = 1
BOUND_UPPER = 2

DEFAULT_DEPTH = 3
MAX_ROOT_WORKERS = 8
MIN_DEPTH_FOR_POOL = 3
MIN_MOVES_FOR_POOL = 4
MAX_Q_PLY = 8
NULL_REDUCTION = 2
MATE_BOUND = MATE_SCORE / 2
MAX_PLY = 128
MAX_CHECK_EXT = 2
NULL_WINDOW = 0.01

SearchLane = Literal["interactive", "background"]
MoveResult = tuple[chess.Move, float]

_POOLS: dict[SearchLane, ProcessPoolExecutor | None] = {
    "interactive": None,
    "background": None,
}
_POOL_WORKERS: dict[SearchLane, int] = {
    "interactive": 0,
    "background": 0,
}
_NATIVE = None
_NATIVE_TRIED = False


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
    """How many tournament games may run at once.

    Each tournament search uses one thread, so the games themselves are the
    parallelism. Live play still uses every core for a single search.
    """
    return 25


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


def _native_module():
    global _NATIVE, _NATIVE_TRIED
    if _NATIVE_TRIED:
        return _NATIVE
    _NATIVE_TRIED = True
    try:
        from backend.engine import native as native_mod

        _NATIVE = native_mod
    except ImportError:
        _NATIVE = None
    return _NATIVE


@dataclass
class Bot:
    """A named alpha-beta player with fixed evaluation weights."""

    name: str
    weights: Weights
    depth: int = DEFAULT_DEPTH
    use_parallel: bool = True
    lane: SearchLane = "background"
    use_native: bool = True

    def choose_move(self, board: chess.Board) -> Optional[MoveResult]:
        """Return (best_move, white_perspective_score), or None if no legal moves."""
        legal = list(board.legal_moves)
        if not legal:
            return None

        if self.use_native:
            threads = 0 if self.use_parallel else 1
            native = _native_choose(board, self.weights, self.depth, threads)
            if native is not None:
                return native

        ordered = _order_moves(board, legal, None, 0, _empty_killers(), [0] * (2 * 64 * 64))
        workers = root_worker_count(self.lane)
        use_pool = (
            self.use_parallel
            and self.depth >= MIN_DEPTH_FOR_POOL
            and len(ordered) >= MIN_MOVES_FOR_POOL
            and workers > 1
        )
        try:
            return _iterative_search(board, ordered, self.weights, self.depth, use_pool, self.lane)
        except Exception:
            if use_pool:
                _reset_pool(self.lane)
            return _iterative_search(board, ordered, self.weights, self.depth, False, self.lane)


def _reversible_history(board: chess.Board) -> tuple[str, list[str]]:
    """FEN at the last irreversible move, and the UCI moves back to ``board``.

    A FEN has no repetition stack. Replays cannot cross a capture or pawn move,
    which is exactly the halfmove window.
    """
    scratch = board.copy(stack=True)
    moves: list[str] = []
    steps = min(board.halfmove_clock, len(scratch.move_stack))
    for _ in range(steps):
        moves.append(scratch.pop().uci())
    moves.reverse()
    return scratch.fen(), moves


def _native_choose(board: chess.Board, weights: Weights, depth: int, threads: int) -> Optional[MoveResult]:
    mod = _native_module()
    if mod is None:
        return None
    try:
        fen, history = _reversible_history(board)
        uci, score = mod.choose_move(fen, list(weights.as_tuple()), int(depth), int(threads), history)
        move = chess.Move.from_uci(uci)
    except Exception:
        return None
    if move not in board.legal_moves:
        return None
    return move, float(score)


def _empty_killers() -> list[list[Optional[chess.Move]]]:
    return [[None, None] for _ in range(MAX_PLY)]


@dataclass
class _Search:
    weights: Weights
    tt: dict = field(default_factory=dict)
    killers: list = field(default_factory=_empty_killers)
    history: list = field(default_factory=lambda: [0] * (2 * 64 * 64))


def _iterative_search(
    board: chess.Board,
    ordered: list[chess.Move],
    weights: Weights,
    depth: int,
    use_pool: bool,
    lane: SearchLane,
) -> MoveResult:
    ctx = _Search(weights)
    best_move = ordered[0]
    score = 0.0
    for current in range(1, depth + 1):
        if current >= 4:
            alpha = score - 1.25
            beta = score + 1.25
        else:
            alpha = float("-inf")
            beta = float("inf")
        move = best_move
        val = score
        for _attempt in range(3):
            move, val = _search_root(
                board,
                current,
                alpha,
                beta,
                ctx,
                best_move,
                use_pool and current == depth,
                lane,
            )
            if val <= alpha:
                alpha = float("-inf")
            elif val >= beta:
                beta = float("inf")
            else:
                break
        best_move, score = move, val
    return best_move, score


def _search_root(
    board: chess.Board,
    depth: int,
    alpha: float,
    beta: float,
    ctx: _Search,
    pv: Optional[chess.Move],
    use_pool: bool,
    lane: SearchLane,
) -> MoveResult:
    maximizing = board.turn == chess.WHITE
    alpha_orig = alpha
    beta_orig = beta
    moves = _order_moves(board, list(board.legal_moves), pv, 0, ctx.killers, ctx.history)
    if not moves:
        raise RuntimeError("root search called with no legal moves")

    best_move = moves[0]
    if maximizing:
        best_score = float("-inf")
    else:
        best_score = float("inf")

    def consider(move: chess.Move, score: float) -> None:
        nonlocal best_move, best_score, alpha, beta
        if maximizing:
            if score > best_score:
                best_score = score
                best_move = move
            alpha = max(alpha, best_score)
        else:
            if score < best_score:
                best_score = score
                best_move = move
            beta = min(beta, best_score)

    board.push(moves[0])
    first = _alphabeta(board, depth - 1, alpha, beta, ctx, ply=1, qply=0)
    board.pop()
    consider(moves[0], first)

    rest = moves[1:]
    if use_pool and rest and alpha < beta:
        try:
            pool = _get_pool(lane)
            ancestor, history = _reversible_history(board)
            payloads = [
                (ancestor, history, move.uci(), depth - 1, ctx.weights.as_tuple(), alpha, beta)
                for move in rest
            ]
            for move_uci, score in pool.map(_score_root_move, payloads, chunksize=1):
                consider(chess.Move.from_uci(move_uci), score)
            _store_tt(ctx, board, depth, best_score, alpha_orig, beta_orig, best_move, 0)
            return best_move, best_score
        except Exception:
            _reset_pool(lane)

    for move in rest:
        if alpha >= beta:
            break
        board.push(move)
        score = _alphabeta(board, depth - 1, alpha, beta, ctx, ply=1, qply=0)
        board.pop()
        consider(move, score)
    _store_tt(ctx, board, depth, best_score, alpha_orig, beta_orig, best_move, 0)
    return best_move, best_score


def _score_root_move(payload: tuple) -> tuple[str, float]:
    """Worker entry: score one root move inside a fixed window."""
    fen, history, move_uci, depth, weight_tuple, alpha, beta = payload
    board = chess.Board(fen)
    for uci in history:
        board.push_uci(uci)
    board.push(chess.Move.from_uci(move_uci))
    weights = Weights.from_tuple(weight_tuple)
    ctx = _Search(weights)
    score = _alphabeta(board, depth, alpha, beta, ctx, ply=1, qply=0)
    return move_uci, score


def _is_draw(board: chess.Board) -> bool:
    if board.is_insufficient_material():
        return True
    if board.halfmove_clock >= 100:
        return True
    if board.halfmove_clock >= 4 and board.is_repetition(3):
        return True
    return False


def _is_cheap_terminal(board: chess.Board) -> bool:
    """Fast terminal detection for search.

    Includes a gated threefold check (cheap enough when halfmove_clock >= 4)
    so the tree treats repetitions as draws. Full claim_draw stays in the game loop.
    """
    if _is_draw(board):
        return True
    try:
        next(board.generate_legal_moves())
        return False
    except StopIteration:
        return True


def _mate_score(board: chess.Board, ply: int) -> float:
    plies = max(0, ply)
    if board.turn == chess.WHITE:
        return -(MATE_SCORE - plies)
    return float(MATE_SCORE - plies)


def _tt_pack(score: float, ply: int) -> float:
    if score > MATE_BOUND:
        return score + ply
    if score < -MATE_BOUND:
        return score - ply
    return score


def _tt_unpack(score: float, ply: int) -> float:
    if score > MATE_BOUND:
        return score - ply
    if score < -MATE_BOUND:
        return score + ply
    return score


def _probe_tt(ctx: _Search, board: chess.Board, depth: int, alpha: float, beta: float, ply: int):
    entry = ctx.tt.get(board._transposition_key())
    if entry is None:
        return alpha, beta, None, None
    e_depth, e_score, e_bound, e_move = entry
    tt_move = e_move
    if e_depth < depth:
        return alpha, beta, tt_move, None
    score = _tt_unpack(e_score, ply)
    if e_bound == BOUND_EXACT:
        return alpha, beta, tt_move, score
    if e_bound == BOUND_LOWER:
        alpha = max(alpha, score)
    elif e_bound == BOUND_UPPER:
        beta = min(beta, score)
    if alpha >= beta:
        return alpha, beta, tt_move, score
    return alpha, beta, tt_move, None


def _store_tt(
    ctx: _Search,
    board: chess.Board,
    depth: int,
    value: float,
    alpha_orig: float,
    beta: float,
    best_move: Optional[chess.Move],
    ply: int,
) -> None:
    bound = BOUND_EXACT
    if value <= alpha_orig:
        bound = BOUND_UPPER
    elif value >= beta:
        bound = BOUND_LOWER
    ctx.tt[board._transposition_key()] = (depth, _tt_pack(value, ply), bound, best_move)


def _mvv_lva(board: chess.Board, move: chess.Move) -> int:
    if board.is_en_passant(move):
        victim = PIECE_VALUES[chess.PAWN]
    else:
        victim_type = board.piece_type_at(move.to_square)
        victim = PIECE_VALUES.get(victim_type, 0) if victim_type is not None else 0
    attacker_type = board.piece_type_at(move.from_square)
    attacker = PIECE_VALUES.get(attacker_type, 0) if attacker_type is not None else 0
    promo = 0
    if move.promotion:
        promo = PIECE_VALUES.get(move.promotion, 0) * 4
    return victim * 16 - attacker + promo


def _history_index(board: chess.Board, move: chess.Move) -> int:
    side = 0 if board.turn == chess.WHITE else 1
    return side * 4096 + move.from_square * 64 + move.to_square


def _order_moves(
    board: chess.Board,
    moves: list[chess.Move],
    tt_move: Optional[chess.Move],
    ply: int,
    killers: list,
    history: list,
) -> list[chess.Move]:
    """TT move, then MVV-LVA captures, then killers, then history."""
    killer_pair = killers[ply] if ply < len(killers) else [None, None]

    def key(move: chess.Move) -> int:
        if tt_move is not None and move == tt_move:
            return 2_000_000
        if board.is_capture(move) or move.promotion:
            return 1_000_000 + _mvv_lva(board, move)
        if move == killer_pair[0]:
            return 800_000
        if move == killer_pair[1]:
            return 700_000
        return history[_history_index(board, move)]

    return sorted(moves, key=key, reverse=True)


def _victim_value(board: chess.Board, move: chess.Move) -> int:
    if board.is_en_passant(move):
        victim = PIECE_VALUES[chess.PAWN]
    else:
        piece_type = board.piece_type_at(move.to_square)
        victim = PIECE_VALUES.get(piece_type, 0) if piece_type is not None else 0
    if move.promotion:
        victim += PIECE_VALUES.get(move.promotion, 0) - PIECE_VALUES[chess.PAWN]
    return victim


def _see_non_negative(board: chess.Board, move: chess.Move) -> bool:
    """Keep captures whose first-exchange lower bound is not a loss."""
    victim = _victim_value(board, move)
    attacker_type = board.piece_type_at(move.from_square)
    attacker = PIECE_VALUES.get(attacker_type, 0) if attacker_type is not None else 0
    if not board.is_attacked_by(not board.turn, move.to_square):
        return True
    return victim >= attacker


def _noisy_moves(board: chess.Board) -> list[chess.Move]:
    """Captures that do not lose material, plus quiet queen promotions."""
    moves = [move for move in board.generate_legal_captures() if _see_non_negative(board, move)]
    rank = 6 if board.turn == chess.WHITE else 1
    from_mask = chess.BB_RANKS[rank] & board.pieces_mask(chess.PAWN, board.turn)
    if from_mask:
        moves.extend(
            move
            for move in board.generate_legal_moves(from_mask)
            if move.promotion == chess.QUEEN and not board.is_capture(move)
        )
    return moves


def _has_non_pawn(board: chess.Board, color: chess.Color) -> bool:
    for piece_type in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN):
        if board.pieces_mask(piece_type, color):
            return True
    return False


def _remember_cutoff(ctx: _Search, board: chess.Board, move: chess.Move, ply: int, depth: int) -> None:
    if board.is_capture(move) or move.promotion:
        return
    pair = ctx.killers[ply]
    if move != pair[0]:
        pair[1] = pair[0]
        pair[0] = move
    ctx.history[_history_index(board, move)] += depth * depth


def _alphabeta(
    board: chess.Board,
    depth: int,
    alpha: float,
    beta: float,
    ctx: _Search,
    ply: int,
    qply: int,
    extensions: int = 0,
) -> float:
    if _is_draw(board):
        return 0.0

    alpha_orig = alpha
    alpha, beta, tt_move, tt_hit = _probe_tt(ctx, board, depth, alpha, beta, ply)
    if tt_hit is not None:
        return tt_hit
    beta_orig = beta

    if depth <= 0:
        return _quiescence(board, alpha, beta, ctx, ply, qply)

    in_check = board.is_check()
    moves = _order_moves(board, list(board.legal_moves), tt_move, ply, ctx.killers, ctx.history)
    if not moves:
        if in_check:
            return _mate_score(board, ply)
        return 0.0

    maximizing = board.turn == chess.WHITE
    if (
        depth >= 3
        and not in_check
        and _has_non_pawn(board, board.turn)
        and not (board.move_stack and board.peek() == chess.Move.null())
    ):
        board.push(chess.Move.null())
        if maximizing and beta < MATE_BOUND:
            null_score = _alphabeta(
                board, depth - 1 - NULL_REDUCTION, beta - NULL_WINDOW, beta, ctx, ply + 1, qply, extensions
            )
            board.pop()
            if null_score >= beta:
                return null_score
        elif (not maximizing) and alpha > -MATE_BOUND:
            null_score = _alphabeta(
                board, depth - 1 - NULL_REDUCTION, alpha, alpha + NULL_WINDOW, ctx, ply + 1, qply, extensions
            )
            board.pop()
            if null_score <= alpha:
                return null_score
        else:
            board.pop()

    extension = 1 if in_check and extensions < MAX_CHECK_EXT else 0
    child_depth = depth - 1 + extension
    next_ext = extensions + extension

    if maximizing:
        value = float("-inf")
    else:
        value = float("inf")
    best_move: Optional[chess.Move] = None

    for index, move in enumerate(moves):
        noisy = board.is_capture(move) or bool(move.promotion)
        reduction = 1 if depth >= 3 and index >= 3 and not noisy and not in_check else 0
        board.push(move)
        if reduction and maximizing and alpha > -MATE_BOUND:
            score = _alphabeta(
                board, child_depth - reduction, alpha, alpha + NULL_WINDOW, ctx, ply + 1, qply, next_ext
            )
            if score > alpha:
                score = _alphabeta(board, child_depth, alpha, beta, ctx, ply + 1, qply, next_ext)
        elif reduction and (not maximizing) and beta < MATE_BOUND:
            score = _alphabeta(
                board, child_depth - reduction, beta - NULL_WINDOW, beta, ctx, ply + 1, qply, next_ext
            )
            if score < beta:
                score = _alphabeta(board, child_depth, alpha, beta, ctx, ply + 1, qply, next_ext)
        else:
            score = _alphabeta(board, child_depth, alpha, beta, ctx, ply + 1, qply, next_ext)
        board.pop()

        if maximizing:
            if score > value:
                value = score
                best_move = move
            alpha = max(alpha, value)
        else:
            if score < value:
                value = score
                best_move = move
            beta = min(beta, value)
        if alpha >= beta:
            _remember_cutoff(ctx, board, move, ply, depth)
            break

    _store_tt(ctx, board, depth, value, alpha_orig, beta_orig, best_move, ply)
    return value


def _quiescence(
    board: chess.Board,
    alpha: float,
    beta: float,
    ctx: _Search,
    ply: int,
    qply: int,
) -> float:
    if _is_draw(board):
        return 0.0
    in_check = board.is_check()
    stand = None
    if not in_check:
        stand = static_eval(board, ctx.weights)
        if board.turn == chess.WHITE:
            if stand >= beta:
                return stand
            if stand > alpha:
                alpha = stand
        else:
            if stand <= alpha:
                return stand
            if stand < beta:
                beta = stand
    if qply >= MAX_Q_PLY:
        return stand if stand is not None else static_eval(board, ctx.weights)

    if in_check:
        moves = _order_moves(board, list(board.legal_moves), None, ply, ctx.killers, ctx.history)
    else:
        moves = _order_moves(board, _noisy_moves(board), None, ply, ctx.killers, ctx.history)
    if not moves:
        if in_check:
            return _mate_score(board, ply)
        return stand if stand is not None else 0.0

    maximizing = board.turn == chess.WHITE
    if maximizing:
        value = float("-inf") if stand is None else stand
    else:
        value = float("inf") if stand is None else stand

    for move in moves:
        if stand is not None and not in_check:
            victim = float(_victim_value(board, move))
            if board.turn == chess.WHITE and stand + victim + 1.0 < alpha:
                continue
            if board.turn == chess.BLACK and stand - victim - 1.0 > beta:
                continue
        board.push(move)
        score = _quiescence(board, alpha, beta, ctx, ply + 1, qply + 1)
        board.pop()
        if maximizing:
            if score > value:
                value = score
            alpha = max(alpha, value)
        else:
            if score < value:
                value = score
            beta = min(beta, value)
        if alpha >= beta:
            break
    return value
