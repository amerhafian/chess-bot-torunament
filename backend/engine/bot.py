"""Alpha-beta chess bot with weighted evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import chess

from backend.engine.evaluation import Weights, evaluate


@dataclass
class Bot:
    """A named alpha-beta player with fixed evaluation weights."""

    name: str
    weights: Weights
    depth: int = 5

    def choose_move(self, board: chess.Board) -> Optional[chess.Move]:
        """Return the best move for the side to move, or None if no legal moves."""
        legal = list(board.legal_moves)
        if not legal:
            return None

        maximizing = board.turn == chess.WHITE
        best_move: Optional[chess.Move] = None
        best_score = float("-inf") if maximizing else float("inf")

        ordered = _order_moves(board, legal)
        for move in ordered:
            board.push(move)
            score = _alphabeta(
                board,
                self.depth - 1,
                float("-inf"),
                float("inf"),
                board.turn == chess.WHITE,
                self.weights,
            )
            board.pop()

            if maximizing:
                if score > best_score or best_move is None:
                    best_score = score
                    best_move = move
            else:
                if score < best_score or best_move is None:
                    best_score = score
                    best_move = move

        return best_move


def _order_moves(board: chess.Board, moves: list[chess.Move]) -> list[chess.Move]:
    """Prefer captures for better alpha-beta pruning."""

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
) -> float:
    if depth == 0 or board.is_game_over(claim_draw=True):
        return evaluate(board, weights, depth_remaining=depth)

    moves = _order_moves(board, list(board.legal_moves))
    if not moves:
        return evaluate(board, weights, depth_remaining=depth)

    if maximizing:
        value = float("-inf")
        for move in moves:
            board.push(move)
            value = max(value, _alphabeta(board, depth - 1, alpha, beta, False, weights))
            board.pop()
            alpha = max(alpha, value)
            if alpha >= beta:
                break
        return value

    value = float("inf")
    for move in moves:
        board.push(move)
        value = min(value, _alphabeta(board, depth - 1, alpha, beta, True, weights))
        board.pop()
        beta = min(beta, value)
        if alpha >= beta:
            break
    return value
