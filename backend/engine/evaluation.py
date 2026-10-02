"""Weighted board evaluation for tournament bots.

score = a * material + b * controlled_squares + c * king_pressure

Positive scores favor White; negative favor Black.

The third metric (weight c) is a fast king-pressure proxy: how many pieces
attack the enemy king square and the adjacent king-ring squares.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional

import chess

PIECE_VALUES: dict[chess.PieceType, int] = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}

MATE_SCORE = 100_000

_PIECE_TYPES_SCORED = (chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)


@dataclass(frozen=True, slots=True)
class Weights:
    """Evaluation weight triple (a, b, c)."""

    material: float  # a
    controlled: float  # b
    checking: float  # c — king-pressure weight

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.material, self.controlled, self.checking)

    def to_dict(self) -> dict[str, float]:
        return {
            "a": self.material,
            "b": self.controlled,
            "c": self.checking,
        }

    @classmethod
    def from_dict(cls, data: dict[str, float]) -> Weights:
        return cls(
            material=float(data["a"]),
            controlled=float(data["b"]),
            checking=float(data["c"]),
        )


@dataclass(frozen=True, slots=True)
class Metrics:
    material: int
    controlled: int
    checking: int  # king-pressure balance


def _popcount(bb: int) -> int:
    return bb.bit_count()


def material_balance(board: chess.Board) -> int:
    """White material minus Black material using fixed piece values."""
    score = 0
    for piece_type in _PIECE_TYPES_SCORED:
        value = PIECE_VALUES[piece_type]
        score += value * (
            _popcount(board.pieces_mask(piece_type, chess.WHITE))
            - _popcount(board.pieces_mask(piece_type, chess.BLACK))
        )
    return score


def controlled_squares_balance(board: chess.Board) -> int:
    """Count attacked squares per side; overlaps count multiple times."""
    white = _controlled_for_color(board, chess.WHITE)
    black = _controlled_for_color(board, chess.BLACK)
    return white - black


def _controlled_for_color(board: chess.Board, color: chess.Color) -> int:
    total = 0
    for piece_type in chess.PIECE_TYPES:
        bb = board.pieces_mask(piece_type, color)
        while bb:
            sq = bb.bit_length() - 1
            bb ^= 1 << sq
            total += _popcount(board.attacks_mask(sq))
    return total


def checking_moves_balance(board: chess.Board) -> int:
    """King-pressure balance: White pressure on Black king minus reverse."""
    return _king_pressure(board, chess.WHITE) - _king_pressure(board, chess.BLACK)


def _king_pressure(board: chess.Board, color: chess.Color) -> int:
    king = board.king(not color)
    if king is None:
        return 0
    targets = chess.BB_KING_ATTACKS[king] | chess.BB_SQUARES[king]
    total = 0
    bits = int(targets)
    while bits:
        sq = bits.bit_length() - 1
        bits ^= 1 << sq
        total += _popcount(board.attackers_mask(color, sq))
    return total


def compute_metrics(board: chess.Board) -> Metrics:
    return Metrics(
        material=material_balance(board),
        controlled=controlled_squares_balance(board),
        checking=checking_moves_balance(board),
    )


def evaluate(board: chess.Board, weights: Weights, depth_remaining: int = 0) -> float:
    """Evaluate position. Mate scores include depth so shorter mates score higher."""
    if board.is_checkmate():
        if board.turn == chess.WHITE:
            return -MATE_SCORE + depth_remaining
        return MATE_SCORE - depth_remaining

    if board.is_stalemate() or board.is_insufficient_material():
        return 0.0

    if board.halfmove_clock >= 100:
        return 0.0

    score = 0.0
    if weights.material != 0.0:
        score += weights.material * material_balance(board)
    if weights.controlled != 0.0:
        score += weights.controlled * controlled_squares_balance(board)
    if weights.checking != 0.0:
        score += weights.checking * checking_moves_balance(board)
    return score


def score_to_bar(score: float, *, scale: float = 8.0) -> dict[str, Any]:
    """Convert a White-perspective score into eval-bar fields."""
    if score >= MATE_SCORE / 2:
        white_pct = 100.0
        label = "M"
    elif score <= -MATE_SCORE / 2:
        white_pct = 0.0
        label = "-M"
    else:
        white_pct = 50.0 + 50.0 * math.tanh(score / scale)
        white_pct = max(0.0, min(100.0, white_pct))
        label = f"{score:+.1f}"
    return {
        "score": float(score),
        "white_pct": float(white_pct),
        "label": label,
        "source": "search",
    }


def display_eval(board: chess.Board, weights: Weights, *, scale: float = 8.0) -> dict[str, Any]:
    """Static eval for UI bars when no search score is available yet."""
    data = score_to_bar(evaluate(board, weights), scale=scale)
    data["source"] = "static"
    return data


def display_eval_averaged(
    board: chess.Board,
    weights_a: Weights,
    weights_b: Weights,
    *,
    scale: float = 8.0,
) -> dict[str, Any]:
    """Average of two static weight sets (fallback only)."""
    score = 0.5 * (evaluate(board, weights_a) + evaluate(board, weights_b))
    data = score_to_bar(score, scale=scale)
    data["source"] = "static"
    return data


def evaluation_payload(
    *,
    search_score: Optional[float],
    board: chess.Board,
    weights: Weights,
    weights2: Optional[Weights] = None,
) -> dict[str, Any]:
    """Prefer search score; otherwise static (optionally averaged)."""
    if search_score is not None:
        return score_to_bar(search_score)
    if weights2 is not None:
        return display_eval_averaged(board, weights, weights2)
    return display_eval(board, weights)
