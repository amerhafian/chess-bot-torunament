"""Weighted board evaluation for tournament bots.

score = a * material + b * controlled_squares + c * king_pressure

Positive scores favor White; negative favor Black.

The third metric (weight c) is a fast king-pressure proxy: how many pieces
attack the enemy king square and the adjacent king-ring squares. This keeps
the "king safety / checking pressure" intent of the original checking-moves
count without generating all legal moves at every leaf.
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


def material_balance(board: chess.Board) -> int:
    """White material minus Black material using fixed piece values."""
    score = 0
    for piece_type, value in PIECE_VALUES.items():
        if value == 0:
            continue
        score += value * (
            bin(board.pieces_mask(piece_type, chess.WHITE)).count("1")
            - bin(board.pieces_mask(piece_type, chess.BLACK)).count("1")
        )
    return score


def controlled_squares_balance(board: chess.Board) -> int:
    """Count attacked squares per side; overlaps count multiple times."""
    white = 0
    black = 0
    occupied = board.occupied
    while occupied:
        square = occupied.bit_length() - 1
        occupied ^= 1 << square
        piece = board.piece_at(square)
        if piece is None:
            continue
        count = bin(int(board.attacks_mask(square))).count("1")
        if piece.color == chess.WHITE:
            white += count
        else:
            black += count
    return white - black


def checking_moves_balance(board: chess.Board) -> int:
    """King-pressure balance: White pressure on Black king minus reverse.

    Pressure = number of pieces attacking the enemy king square plus all
    king-adjacent squares (attackers counted with multiplicity across squares).
    """
    return _king_pressure(board, chess.WHITE) - _king_pressure(board, chess.BLACK)


def _king_pressure(board: chess.Board, color: chess.Color) -> int:
    king = board.king(not color)
    if king is None:
        return 0
    targets = chess.BB_KING_ATTACKS[king] | chess.BB_SQUARES[king]
    total = 0
    # Iterate target squares via bitboard
    bits = int(targets)
    while bits:
        sq = bits.bit_length() - 1
        bits ^= 1 << sq
        total += bin(int(board.attackers_mask(color, sq))).count("1")
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

    # Cheap fifty-move / repetition proxies during search (halfmove clock / no full 3-fold scan)
    if board.halfmove_clock >= 100:
        return 0.0

    metrics = compute_metrics(board)
    return (
        weights.material * metrics.material
        + weights.controlled * metrics.controlled
        + weights.checking * metrics.checking
    )
