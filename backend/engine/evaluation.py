"""Weighted board evaluation for tournament bots.

score = a * material + b * controlled_squares + c * checking_moves

Positive scores favor White; negative favor Black.
"""

from __future__ import annotations

from dataclasses import dataclass

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


@dataclass(frozen=True, slots=True)
class Weights:
    """Evaluation weight triple (a, b, c)."""

    material: float  # a
    controlled: float  # b
    checking: float  # c

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
    checking: int


def material_balance(board: chess.Board) -> int:
    """White material minus Black material using fixed piece values."""
    score = 0
    for piece_type, value in PIECE_VALUES.items():
        if value == 0:
            continue
        score += value * len(board.pieces(piece_type, chess.WHITE))
        score -= value * len(board.pieces(piece_type, chess.BLACK))
    return score


def controlled_squares_balance(board: chess.Board) -> int:
    """Count attacked squares per side; overlaps count multiple times."""
    white = 0
    black = 0
    for square in chess.SQUARES:
        piece = board.piece_at(square)
        if piece is None:
            continue
        attacks = board.attacks(square)
        count = len(attacks)
        if piece.color == chess.WHITE:
            white += count
        else:
            black += count
    return white - black


def checking_moves_balance(board: chess.Board) -> int:
    """Count legal checking moves for each side; return White - Black."""
    white = _count_checking_moves(board, chess.WHITE)
    black = _count_checking_moves(board, chess.BLACK)
    return white - black


def _count_checking_moves(board: chess.Board, color: chess.Color) -> int:
    """Count legal moves by *color* that give check."""
    if board.turn == color:
        probe = board
    else:
        # Copy so we can force the side to move without mutating caller state.
        probe = board.copy(stack=False)
        probe.turn = color
    count = 0
    for move in probe.legal_moves:
        if probe.gives_check(move):
            count += 1
    return count


def compute_metrics(board: chess.Board) -> Metrics:
    return Metrics(
        material=material_balance(board),
        controlled=controlled_squares_balance(board),
        checking=checking_moves_balance(board),
    )


def evaluate(board: chess.Board, weights: Weights, depth_remaining: int = 0) -> float:
    """Evaluate position. Mate scores include depth so shorter mates score higher."""
    if board.is_checkmate():
        # Side to move is checkmated — bad for them.
        if board.turn == chess.WHITE:
            return -MATE_SCORE + depth_remaining
        return MATE_SCORE - depth_remaining

    if (
        board.is_stalemate()
        or board.is_insufficient_material()
        or board.can_claim_fifty_moves()
        or board.is_repetition(3)
    ):
        return 0.0

    metrics = compute_metrics(board)
    return (
        weights.material * metrics.material
        + weights.controlled * metrics.controlled
        + weights.checking * metrics.checking
    )
