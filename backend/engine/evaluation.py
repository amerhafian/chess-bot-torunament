"""Weighted board evaluation for tournament bots.

score = sum over metrics of coeff * signed_pow(scaled_metric, exp)

Positive scores favor White; negative favor Black.
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

# Pawn-comparable metric scales: raw_metric / SCALE ≈ roughly one pawn of influence.
CONTROLLED_SCALE = 20.0
KING_SCALE = 4.0
ATTACK_SCALE = 2.0
CENTER_SCALE = 4.0
# Eval-bar tanh saturates near ±BAR_SCALE pawns.
BAR_SCALE = 3.0

_CENTER_BB = chess.BB_D4 | chess.BB_D5 | chess.BB_E4 | chess.BB_E5
_PIECE_TYPES_SCORED = (chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)
_WEIGHT_KEYS = ("a1", "a2", "b1", "b2", "c1", "c2", "d1", "d2", "e1", "e2")


@dataclass(frozen=True, slots=True)
class Weights:
    """Power-form evaluation weights: five (coeff, exp) pairs."""

    material: float = 1.0  # a1
    controlled: float = 0.0  # b1
    checking: float = 0.0  # c1 — king-pressure coeff
    attacked: float = 0.0  # d1
    center: float = 0.0  # e1
    material_exp: float = 1.0  # a2
    controlled_exp: float = 1.0  # b2
    checking_exp: float = 1.0  # c2
    attacked_exp: float = 1.0  # d2
    center_exp: float = 1.0  # e2

    def as_tuple(self) -> tuple[float, ...]:
        return (
            self.material,
            self.controlled,
            self.checking,
            self.attacked,
            self.center,
            self.material_exp,
            self.controlled_exp,
            self.checking_exp,
            self.attacked_exp,
            self.center_exp,
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "a1": self.material,
            "a2": self.material_exp,
            "b1": self.controlled,
            "b2": self.controlled_exp,
            "c1": self.checking,
            "c2": self.checking_exp,
            "d1": self.attacked,
            "d2": self.attacked_exp,
            "e1": self.center,
            "e2": self.center_exp,
            # Legacy aliases (coeff only) for older clients / saved files.
            "a": self.material,
            "b": self.controlled,
            "c": self.checking,
        }

    @classmethod
    def from_tuple(cls, values: tuple[float, ...] | list[float]) -> Weights:
        if len(values) == 3:
            return cls(material=values[0], controlled=values[1], checking=values[2])
        if len(values) != 10:
            raise ValueError(f"expected 3 or 10 weight values, got {len(values)}")
        return cls(
            material=values[0],
            controlled=values[1],
            checking=values[2],
            attacked=values[3],
            center=values[4],
            material_exp=values[5],
            controlled_exp=values[6],
            checking_exp=values[7],
            attacked_exp=values[8],
            center_exp=values[9],
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Weights:
        """Load power weights; legacy {a,b,c} → coeffs with exp 1 and d1=e1=0."""
        if "a1" in data or "b1" in data or "c1" in data or "d1" in data or "e1" in data:
            return cls(
                material=float(data.get("a1", data.get("a", 0.0))),
                controlled=float(data.get("b1", data.get("b", 0.0))),
                checking=float(data.get("c1", data.get("c", 0.0))),
                attacked=float(data.get("d1", 0.0)),
                center=float(data.get("e1", 0.0)),
                material_exp=float(data.get("a2", 1.0)),
                controlled_exp=float(data.get("b2", 1.0)),
                checking_exp=float(data.get("c2", 1.0)),
                attacked_exp=float(data.get("d2", 1.0)),
                center_exp=float(data.get("e2", 1.0)),
            )
        return cls(
            material=float(data.get("a", 0.0)),
            controlled=float(data.get("b", 0.0)),
            checking=float(data.get("c", 0.0)),
            attacked=0.0,
            center=0.0,
            material_exp=1.0,
            controlled_exp=1.0,
            checking_exp=1.0,
            attacked_exp=1.0,
            center_exp=1.0,
        )


@dataclass(frozen=True, slots=True)
class Metrics:
    material: int
    controlled: int
    checking: int  # king-pressure balance
    attacked: int
    center: int


def _popcount(bb: int) -> int:
    return bb.bit_count()


def signed_pow(value: float, exp: float) -> float:
    """sign(x) * |x|^exp; 0 stays 0."""
    if value == 0.0:
        return 0.0
    if value > 0.0:
        return float(abs(value) ** exp)
    return -float(abs(value) ** exp)


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


def attacked_pieces_balance(board: chess.Board) -> int:
    """Count of enemy pieces currently attacked; White − Black."""
    return _attacked_pieces(board, chess.WHITE) - _attacked_pieces(board, chess.BLACK)


def _attacked_pieces(board: chess.Board, color: chess.Color) -> int:
    enemy = not color
    total = 0
    for piece_type in chess.PIECE_TYPES:
        bb = board.pieces_mask(piece_type, enemy)
        while bb:
            sq = bb.bit_length() - 1
            bb ^= 1 << sq
            if board.attackers_mask(color, sq):
                total += 1
    return total


def center_control_balance(board: chess.Board) -> int:
    """Attacks on d4/d5/e4/e5; White − Black."""
    return _center_attacks(board, chess.WHITE) - _center_attacks(board, chess.BLACK)


def _center_attacks(board: chess.Board, color: chess.Color) -> int:
    total = 0
    bits = int(_CENTER_BB)
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
        attacked=attacked_pieces_balance(board),
        center=center_control_balance(board),
    )


def evaluate(board: chess.Board, weights: Weights, ply_from_root: int = 0) -> float:
    """Evaluate position. Mate scores encode distance so shorter mates score higher."""
    if board.is_checkmate():
        # Side to move is mated; plies_to_mate is the path length from the search root.
        plies = max(0, int(ply_from_root))
        if board.turn == chess.WHITE:
            return -(MATE_SCORE - plies)
        return float(MATE_SCORE - plies)

    if board.is_stalemate() or board.is_insufficient_material():
        return 0.0

    if board.halfmove_clock >= 100:
        return 0.0

    # Match search terminals: threefold (is_repetition(2) == third occurrence).
    if board.halfmove_clock >= 4 and board.is_repetition(2):
        return 0.0

    metrics = compute_metrics(board)
    score = 0.0
    if weights.material != 0.0:
        score += weights.material * signed_pow(float(metrics.material), weights.material_exp)
    if weights.controlled != 0.0:
        score += weights.controlled * signed_pow(
            metrics.controlled / CONTROLLED_SCALE, weights.controlled_exp
        )
    if weights.checking != 0.0:
        score += weights.checking * signed_pow(
            metrics.checking / KING_SCALE, weights.checking_exp
        )
    if weights.attacked != 0.0:
        score += weights.attacked * signed_pow(
            metrics.attacked / ATTACK_SCALE, weights.attacked_exp
        )
    if weights.center != 0.0:
        score += weights.center * signed_pow(
            metrics.center / CENTER_SCALE, weights.center_exp
        )
    return score


def mate_moves_from_score(score: float) -> Optional[int]:
    """Return mate-in-N (moves) from a White-perspective mate score, or None."""
    if abs(score) < MATE_SCORE / 2:
        return None
    plies = int(round(MATE_SCORE - abs(score)))
    plies = max(0, plies)
    return max(1, (plies + 1) // 2)


def score_to_bar(score: float, *, scale: float = BAR_SCALE) -> dict[str, Any]:
    """Convert a White-perspective pawn-ish score into eval-bar fields."""
    moves = mate_moves_from_score(score)
    if moves is not None:
        if score > 0:
            white_pct = 100.0
            label = f"M{moves}"
        else:
            white_pct = 0.0
            label = f"-M{moves}"
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


def display_eval(board: chess.Board, weights: Weights, *, scale: float = BAR_SCALE) -> dict[str, Any]:
    """Static eval for UI bars when no search score is available yet."""
    data = score_to_bar(evaluate(board, weights), scale=scale)
    data["source"] = "static"
    return data


def display_eval_averaged(
    board: chess.Board,
    weights_a: Weights,
    weights_b: Weights,
    *,
    scale: float = BAR_SCALE,
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
