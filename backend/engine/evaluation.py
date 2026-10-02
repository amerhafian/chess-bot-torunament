"""Weighted board evaluation for tournament bots.

score = sum over metrics of coeff * signed_pow(scaled_metric, exp)

Positive scores favor White; negative favor Black.

Legacy five-metric files still load. Extra terms (PST, passed pawns, pawn
structure, king shield, bishop pair, rook files, tempo, knight outposts,
king tropism) default to coefficient 0.
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
PST_SCALE = 1.0
PASSED_SCALE = 1.0
STRUCTURE_SCALE = 1.0
SHIELD_SCALE = 1.0
BISHOP_SCALE = 1.0
ROOK_SCALE = 1.0
TEMPO_SCALE = 1.0
OUTPOST_SCALE = 1.0
TROPISM_SCALE = 4.0
# Eval-bar tanh saturates near ±BAR_SCALE pawns.
BAR_SCALE = 3.0

_CENTER_BB = chess.BB_D4 | chess.BB_D5 | chess.BB_E4 | chess.BB_E5
_PIECE_TYPES_SCORED = (chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)
_PHASE_WEIGHT = {
    chess.KNIGHT: 1,
    chess.BISHOP: 1,
    chess.ROOK: 2,
    chess.QUEEN: 4,
}
_PHASE_TOTAL = 24.0
# Advance bonus by steps from the back rank (0 = home rank, 6 = one step from promotion).
_PASSED_BY_ADVANCE = (0.0, 0.05, 0.10, 0.20, 0.35, 0.60, 1.00, 1.50)

# Piece-square tables in centipawns, rank 8 → rank 1, file a → h.
# White indexes with square ^ 56; black indexes with the square itself.
_PST_MG: dict[chess.PieceType, tuple[int, ...]] = {
    chess.PAWN: (
        0, 0, 0, 0, 0, 0, 0, 0,
        50, 50, 50, 50, 50, 50, 50, 50,
        10, 10, 20, 30, 30, 20, 10, 10,
        5, 5, 10, 25, 25, 10, 5, 5,
        0, 0, 0, 20, 20, 0, 0, 0,
        5, -5, -10, 0, 0, -10, -5, 5,
        5, 10, 10, -20, -20, 10, 10, 5,
        0, 0, 0, 0, 0, 0, 0, 0,
    ),
    chess.KNIGHT: (
        -50, -40, -30, -30, -30, -30, -40, -50,
        -40, -20, 0, 0, 0, 0, -20, -40,
        -30, 0, 10, 15, 15, 10, 0, -30,
        -30, 5, 15, 20, 20, 15, 5, -30,
        -30, 0, 15, 20, 20, 15, 0, -30,
        -30, 5, 10, 15, 15, 10, 5, -30,
        -40, -20, 0, 5, 5, 0, -20, -40,
        -50, -40, -30, -30, -30, -30, -40, -50,
    ),
    chess.BISHOP: (
        -20, -10, -10, -10, -10, -10, -10, -20,
        -10, 0, 0, 0, 0, 0, 0, -10,
        -10, 0, 5, 10, 10, 5, 0, -10,
        -10, 5, 5, 10, 10, 5, 5, -10,
        -10, 0, 10, 10, 10, 10, 0, -10,
        -10, 10, 10, 10, 10, 10, 10, -10,
        -10, 5, 0, 0, 0, 0, 5, -10,
        -20, -10, -10, -10, -10, -10, -10, -20,
    ),
    chess.ROOK: (
        0, 0, 0, 0, 0, 0, 0, 0,
        5, 10, 10, 10, 10, 10, 10, 5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        0, 0, 0, 5, 5, 0, 0, 0,
    ),
    chess.QUEEN: (
        -20, -10, -10, -5, -5, -10, -10, -20,
        -10, 0, 0, 0, 0, 0, 0, -10,
        -10, 0, 5, 5, 5, 5, 0, -10,
        -5, 0, 5, 5, 5, 5, 0, -5,
        0, 0, 5, 5, 5, 5, 0, -5,
        -10, 5, 5, 5, 5, 5, 0, -10,
        -10, 0, 5, 0, 0, 0, 0, -10,
        -20, -10, -10, -5, -5, -10, -10, -20,
    ),
    chess.KING: (
        -30, -40, -40, -50, -50, -40, -40, -30,
        -30, -40, -40, -50, -50, -40, -40, -30,
        -30, -40, -40, -50, -50, -40, -40, -30,
        -30, -40, -40, -50, -50, -40, -40, -30,
        -20, -30, -30, -40, -40, -30, -30, -20,
        -10, -20, -20, -20, -20, -20, -20, -10,
        20, 20, 0, 0, 0, 0, 20, 20,
        20, 30, 10, 0, 0, 10, 30, 20,
    ),
}
_PST_EG: dict[chess.PieceType, tuple[int, ...]] = {
    chess.PAWN: (
        0, 0, 0, 0, 0, 0, 0, 0,
        80, 80, 80, 80, 80, 80, 80, 80,
        50, 50, 50, 50, 50, 50, 50, 50,
        30, 30, 30, 30, 30, 30, 30, 30,
        20, 20, 20, 20, 20, 20, 20, 20,
        10, 10, 10, 10, 10, 10, 10, 10,
        10, 10, 10, 10, 10, 10, 10, 10,
        0, 0, 0, 0, 0, 0, 0, 0,
    ),
    chess.KNIGHT: _PST_MG[chess.KNIGHT],
    chess.BISHOP: _PST_MG[chess.BISHOP],
    chess.ROOK: _PST_MG[chess.ROOK],
    chess.QUEEN: (
        -20, -10, -10, -5, -5, -10, -10, -20,
        -10, 0, 5, 0, 0, 0, 0, -10,
        -10, 0, 5, 5, 5, 5, 0, -10,
        -5, 0, 5, 5, 5, 5, 0, -5,
        -5, 0, 5, 5, 5, 5, 0, -5,
        -10, 0, 5, 5, 5, 5, 0, -10,
        -10, 0, 0, 0, 0, 0, 0, -10,
        -20, -10, -10, -5, -5, -10, -10, -20,
    ),
    chess.KING: (
        -50, -40, -30, -20, -20, -30, -40, -50,
        -30, -20, -10, 0, 0, -10, -20, -30,
        -30, -10, 20, 30, 30, 20, -10, -30,
        -30, -10, 30, 40, 40, 30, -10, -30,
        -30, -10, 30, 40, 40, 30, -10, -30,
        -30, -10, 20, 30, 30, 20, -10, -30,
        -30, -30, 0, 0, 0, 0, -30, -30,
        -50, -30, -30, -30, -30, -30, -30, -50,
    ),
}


def _popcount(bb: int) -> int:
    return bb.bit_count()


@dataclass(frozen=True, slots=True)
class Weights:
    """Power-form evaluation weights.

    a–e are the original five metrics. f–n extend the same formula:
    pst, passed pawns, pawn structure, king shield, bishop pair, rook files,
    tempo, knight outposts, and king tropism.
    """

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
    pst: float = 0.0  # f1
    passed: float = 0.0  # g1
    structure: float = 0.0  # h1
    shield: float = 0.0  # i1
    bishop: float = 0.0  # j1
    rook_file: float = 0.0  # k1
    tempo: float = 0.0  # l1
    outpost: float = 0.0  # m1
    tropism: float = 0.0  # n1
    pst_exp: float = 1.0  # f2
    passed_exp: float = 1.0  # g2
    structure_exp: float = 1.0  # h2
    shield_exp: float = 1.0  # i2
    bishop_exp: float = 1.0  # j2
    rook_file_exp: float = 1.0  # k2
    tempo_exp: float = 1.0  # l2
    outpost_exp: float = 1.0  # m2
    tropism_exp: float = 1.0  # n2

    def as_tuple(self) -> tuple[float, ...]:
        """Flat vector: five legacy pairs, six extension pairs, then l/m/n.

        Length 28. ``from_tuple`` still accepts legacy length 3, 10, and 22.
        """
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
            self.pst,
            self.passed,
            self.structure,
            self.shield,
            self.bishop,
            self.rook_file,
            self.pst_exp,
            self.passed_exp,
            self.structure_exp,
            self.shield_exp,
            self.bishop_exp,
            self.rook_file_exp,
            self.tempo,
            self.outpost,
            self.tropism,
            self.tempo_exp,
            self.outpost_exp,
            self.tropism_exp,
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
            "f1": self.pst,
            "f2": self.pst_exp,
            "g1": self.passed,
            "g2": self.passed_exp,
            "h1": self.structure,
            "h2": self.structure_exp,
            "i1": self.shield,
            "i2": self.shield_exp,
            "j1": self.bishop,
            "j2": self.bishop_exp,
            "k1": self.rook_file,
            "k2": self.rook_file_exp,
            "l1": self.tempo,
            "l2": self.tempo_exp,
            "m1": self.outpost,
            "m2": self.outpost_exp,
            "n1": self.tropism,
            "n2": self.tropism_exp,
            "a": self.material,
            "b": self.controlled,
            "c": self.checking,
        }

    @classmethod
    def from_tuple(cls, values: tuple[float, ...] | list[float]) -> Weights:
        if len(values) == 3:
            return cls(material=values[0], controlled=values[1], checking=values[2])
        if len(values) == 10:
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
        if len(values) == 22:
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
                pst=values[10],
                passed=values[11],
                structure=values[12],
                shield=values[13],
                bishop=values[14],
                rook_file=values[15],
                pst_exp=values[16],
                passed_exp=values[17],
                structure_exp=values[18],
                shield_exp=values[19],
                bishop_exp=values[20],
                rook_file_exp=values[21],
            )
        if len(values) != 28:
            raise ValueError(f"expected 3, 10, 22, or 28 weight values, got {len(values)}")
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
            pst=values[10],
            passed=values[11],
            structure=values[12],
            shield=values[13],
            bishop=values[14],
            rook_file=values[15],
            pst_exp=values[16],
            passed_exp=values[17],
            structure_exp=values[18],
            shield_exp=values[19],
            bishop_exp=values[20],
            rook_file_exp=values[21],
            tempo=values[22],
            outpost=values[23],
            tropism=values[24],
            tempo_exp=values[25],
            outpost_exp=values[26],
            tropism_exp=values[27],
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Weights:
        """Load power weights; legacy {a,b,c} → coeffs with exp 1 and other coeffs 0."""
        extended = any(
            key in data
            for key in ("a1", "b1", "c1", "d1", "e1", "f1", "g1", "h1", "i1", "j1", "k1", "l1", "m1", "n1")
        )
        if extended:
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
                pst=float(data.get("f1", 0.0)),
                passed=float(data.get("g1", 0.0)),
                structure=float(data.get("h1", 0.0)),
                shield=float(data.get("i1", 0.0)),
                bishop=float(data.get("j1", 0.0)),
                rook_file=float(data.get("k1", 0.0)),
                tempo=float(data.get("l1", 0.0)),
                outpost=float(data.get("m1", 0.0)),
                tropism=float(data.get("n1", 0.0)),
                pst_exp=float(data.get("f2", 1.0)),
                passed_exp=float(data.get("g2", 1.0)),
                structure_exp=float(data.get("h2", 1.0)),
                shield_exp=float(data.get("i2", 1.0)),
                bishop_exp=float(data.get("j2", 1.0)),
                rook_file_exp=float(data.get("k2", 1.0)),
                tempo_exp=float(data.get("l2", 1.0)),
                outpost_exp=float(data.get("m2", 1.0)),
                tropism_exp=float(data.get("n2", 1.0)),
            )
        return cls(
            material=float(data.get("a", 0.0)),
            controlled=float(data.get("b", 0.0)),
            checking=float(data.get("c", 0.0)),
        )


@dataclass(frozen=True, slots=True)
class Metrics:
    material: int
    controlled: int
    checking: int  # king-pressure balance
    attacked: int
    center: int
    pst: float
    passed: float
    structure: float
    shield: float
    bishop: int
    rook_file: int
    tempo: float
    outpost: int
    tropism: int


def signed_pow(value: float, exp: float) -> float:
    """sign(x) * |x|^exp; 0 stays 0."""
    if value == 0.0:
        return 0.0
    if exp == 1.0:
        return value
    if value > 0.0:
        return float(abs(value) ** exp)
    return -float(abs(value) ** exp)


def _term(coeff: float, exp: float, scaled: float) -> float:
    if coeff == 0.0 or scaled == 0.0:
        return 0.0
    if exp == 1.0:
        return coeff * scaled
    return coeff * signed_pow(scaled, exp)


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


def _side_attack_metrics(board: chess.Board, color: chess.Color) -> tuple[int, int, int, int]:
    """One attack-map pass: controlled, king pressure, attacked pieces, center hits."""
    enemy = not color
    king_sq = board.king(enemy)
    ring = 0 if king_sq is None else (chess.BB_KING_ATTACKS[king_sq] | chess.BB_SQUARES[king_sq])
    enemy_occ = board.occupied_co[enemy]
    controlled = 0
    king_pressure = 0
    attack_union = 0
    center = 0
    occ = board.occupied_co[color]
    while occ:
        sq = (occ & -occ).bit_length() - 1
        occ &= occ - 1
        attacks = board.attacks_mask(sq)
        controlled += _popcount(attacks)
        if ring:
            king_pressure += _popcount(attacks & ring)
        attack_union |= attacks
        center += _popcount(attacks & _CENTER_BB)
    attacked = _popcount(attack_union & enemy_occ)
    return controlled, king_pressure, attacked, center


def controlled_squares_balance(board: chess.Board) -> int:
    """Count attacked squares per side; overlaps count multiple times."""
    white, _, _, _ = _side_attack_metrics(board, chess.WHITE)
    black, _, _, _ = _side_attack_metrics(board, chess.BLACK)
    return white - black


def checking_moves_balance(board: chess.Board) -> int:
    """King-pressure balance: White pressure on Black king minus reverse."""
    _, white, _, _ = _side_attack_metrics(board, chess.WHITE)
    _, black, _, _ = _side_attack_metrics(board, chess.BLACK)
    return white - black


def attacked_pieces_balance(board: chess.Board) -> int:
    """Count of enemy pieces currently attacked; White − Black."""
    _, _, white, _ = _side_attack_metrics(board, chess.WHITE)
    _, _, black, _ = _side_attack_metrics(board, chess.BLACK)
    return white - black


def center_control_balance(board: chess.Board) -> int:
    """Attacks on d4/d5/e4/e5; White − Black."""
    _, _, _, white = _side_attack_metrics(board, chess.WHITE)
    _, _, _, black = _side_attack_metrics(board, chess.BLACK)
    return white - black


def game_phase(board: chess.Board) -> float:
    """1.0 at the start, 0.0 when only kings and pawns remain."""
    units = 0
    for piece_type, weight in _PHASE_WEIGHT.items():
        units += weight * (
            _popcount(board.pieces_mask(piece_type, chess.WHITE))
            + _popcount(board.pieces_mask(piece_type, chess.BLACK))
        )
    if units >= _PHASE_TOTAL:
        return 1.0
    return units / _PHASE_TOTAL


def pst_balance(board: chess.Board, phase: Optional[float] = None) -> float:
    """Phased piece-square tables, in pawns. White − Black."""
    if phase is None:
        phase = game_phase(board)
    endgame = 1.0 - phase
    score = 0.0
    for color, sign in ((chess.WHITE, 1.0), (chess.BLACK, -1.0)):
        for piece_type in chess.PIECE_TYPES:
            mg = _PST_MG[piece_type]
            eg = _PST_EG[piece_type]
            bb = board.pieces_mask(piece_type, color)
            while bb:
                sq = (bb & -bb).bit_length() - 1
                bb &= bb - 1
                idx = (sq ^ 56) if color == chess.WHITE else sq
                score += sign * (phase * mg[idx] + endgame * eg[idx])
    return score / 100.0


def _is_passed_pawn(board: chess.Board, sq: int, color: chess.Color) -> bool:
    file = chess.square_file(sq)
    rank = chess.square_rank(sq)
    enemy = not color
    files = (file - 1, file, file + 1)
    if color == chess.WHITE:
        ranks = range(rank + 1, 8)
    else:
        ranks = range(rank - 1, -1, -1)
    for f in files:
        if f < 0 or f > 7:
            continue
        for r in ranks:
            piece = board.piece_at(chess.square(f, r))
            if piece is not None and piece.piece_type == chess.PAWN and piece.color == enemy:
                return False
    return True


def passed_pawn_balance(board: chess.Board, phase: Optional[float] = None) -> float:
    """Passed-pawn score in pawns, larger as material comes off the board."""
    if phase is None:
        phase = game_phase(board)
    scale = 0.5 + 1.5 * (1.0 - phase)
    total = 0.0
    for color, sign in ((chess.WHITE, 1.0), (chess.BLACK, -1.0)):
        bb = board.pieces_mask(chess.PAWN, color)
        while bb:
            sq = (bb & -bb).bit_length() - 1
            bb &= bb - 1
            if not _is_passed_pawn(board, sq, color):
                continue
            rank = chess.square_rank(sq)
            advance = rank if color == chess.WHITE else 7 - rank
            total += sign * _PASSED_BY_ADVANCE[advance] * scale
    return total


def pawn_structure_balance(board: chess.Board) -> float:
    """Black defects minus White defects (doubled + isolated). Positive favors White."""

    def penalty(color: chess.Color) -> int:
        files = [0] * 8
        bb = board.pieces_mask(chess.PAWN, color)
        while bb:
            sq = (bb & -bb).bit_length() - 1
            bb &= bb - 1
            files[chess.square_file(sq)] += 1
        doubled = sum(count - 1 for count in files if count >= 2)
        isolated = 0
        for file, count in enumerate(files):
            if count == 0:
                continue
            left = files[file - 1] if file > 0 else 0
            right = files[file + 1] if file < 7 else 0
            if left == 0 and right == 0:
                isolated += count
        return doubled + isolated

    return float(penalty(chess.BLACK) - penalty(chess.WHITE))


def king_shield_balance(board: chess.Board) -> float:
    """Pawn shield minus heavy-piece pressure on the king ring. White − Black."""

    def score(color: chess.Color) -> float:
        king = board.king(color)
        if king is None:
            return 0.0
        kfile = chess.square_file(king)
        krank = chess.square_rank(king)
        direction = 1 if color == chess.WHITE else -1
        pawns = 0
        for df in (-1, 0, 1):
            file = kfile + df
            if file < 0 or file > 7:
                continue
            for step in (1, 2):
                rank = krank + direction * step
                if rank < 0 or rank > 7:
                    continue
                piece = board.piece_at(chess.square(file, rank))
                if piece is not None and piece.piece_type == chess.PAWN and piece.color == color:
                    pawns += 1
        ring = chess.BB_KING_ATTACKS[king] | chess.BB_SQUARES[king]
        heavies = 0
        enemy = not color
        for piece_type in (chess.QUEEN, chess.ROOK):
            bb = board.pieces_mask(piece_type, enemy)
            while bb:
                sq = (bb & -bb).bit_length() - 1
                bb &= bb - 1
                if board.attacks_mask(sq) & ring:
                    heavies += 1
        return float(pawns) - 0.75 * heavies

    return score(chess.WHITE) - score(chess.BLACK)


def bishop_pair_balance(board: chess.Board) -> int:
    white = 1 if _popcount(board.pieces_mask(chess.BISHOP, chess.WHITE)) >= 2 else 0
    black = 1 if _popcount(board.pieces_mask(chess.BISHOP, chess.BLACK)) >= 2 else 0
    return white - black


def rook_file_balance(board: chess.Board) -> int:
    """Open file = 2, semi-open = 1, per rook. White − Black."""
    all_pawns = board.pawns

    def score(color: chess.Color) -> int:
        friendly = board.pieces_mask(chess.PAWN, color)
        total = 0
        bb = board.pieces_mask(chess.ROOK, color)
        while bb:
            sq = (bb & -bb).bit_length() - 1
            bb &= bb - 1
            mask = chess.BB_FILES[chess.square_file(sq)]
            if friendly & mask:
                continue
            total += 2 if (all_pawns & mask) == 0 else 1
        return total

    return score(chess.WHITE) - score(chess.BLACK)


def tempo_balance(board: chess.Board) -> float:
    """Side to move, from White's point of view. +1 White, −1 Black."""
    return 1.0 if board.turn == chess.WHITE else -1.0


def knight_outpost_balance(board: chess.Board) -> int:
    """Knights on an advanced rank, defended by a friendly pawn, safe from enemy pawns."""

    def count(color: chess.Color) -> int:
        total = 0
        enemy = not color
        bb = board.pieces_mask(chess.KNIGHT, color)
        while bb:
            sq = (bb & -bb).bit_length() - 1
            bb &= bb - 1
            rank = chess.square_rank(sq)
            if color == chess.WHITE and rank not in (3, 4, 5):
                continue
            if color == chess.BLACK and rank not in (2, 3, 4):
                continue
            friendly_pawns = board.pieces_mask(chess.PAWN, color)
            enemy_pawns = board.pieces_mask(chess.PAWN, enemy)
            if not (board.attackers(color, sq) & friendly_pawns):
                continue
            if board.attackers(enemy, sq) & enemy_pawns:
                continue
            total += 1
        return total

    return count(chess.WHITE) - count(chess.BLACK)


def king_tropism_balance(board: chess.Board) -> int:
    """Closeness of queens, rooks, and knights to the enemy king. White − Black."""

    def score(color: chess.Color) -> int:
        king = board.king(not color)
        if king is None:
            return 0
        kfile = chess.square_file(king)
        krank = chess.square_rank(king)
        total = 0
        for piece_type in (chess.QUEEN, chess.ROOK, chess.KNIGHT):
            bb = board.pieces_mask(piece_type, color)
            while bb:
                sq = (bb & -bb).bit_length() - 1
                bb &= bb - 1
                dist = max(abs(chess.square_file(sq) - kfile), abs(chess.square_rank(sq) - krank))
                total += 7 - dist
        return total

    return score(chess.WHITE) - score(chess.BLACK)


def compute_metrics(board: chess.Board) -> Metrics:
    white = _side_attack_metrics(board, chess.WHITE)
    black = _side_attack_metrics(board, chess.BLACK)
    phase = game_phase(board)
    return Metrics(
        material=material_balance(board),
        controlled=white[0] - black[0],
        checking=white[1] - black[1],
        attacked=white[2] - black[2],
        center=white[3] - black[3],
        pst=pst_balance(board, phase),
        passed=passed_pawn_balance(board, phase),
        structure=pawn_structure_balance(board),
        shield=king_shield_balance(board),
        bishop=bishop_pair_balance(board),
        rook_file=rook_file_balance(board),
        tempo=tempo_balance(board),
        outpost=knight_outpost_balance(board),
        tropism=king_tropism_balance(board),
    )


def static_eval(board: chess.Board, weights: Weights) -> float:
    """Positional score only. Search handles mate, stalemate, and draws."""
    score = _term(weights.material, weights.material_exp, float(material_balance(board)))
    if (
        weights.controlled != 0.0
        or weights.checking != 0.0
        or weights.attacked != 0.0
        or weights.center != 0.0
    ):
        white = _side_attack_metrics(board, chess.WHITE)
        black = _side_attack_metrics(board, chess.BLACK)
        score += _term(weights.controlled, weights.controlled_exp, (white[0] - black[0]) / CONTROLLED_SCALE)
        score += _term(weights.checking, weights.checking_exp, (white[1] - black[1]) / KING_SCALE)
        score += _term(weights.attacked, weights.attacked_exp, (white[2] - black[2]) / ATTACK_SCALE)
        score += _term(weights.center, weights.center_exp, (white[3] - black[3]) / CENTER_SCALE)
    if (
        weights.pst != 0.0
        or weights.passed != 0.0
        or weights.structure != 0.0
        or weights.shield != 0.0
        or weights.bishop != 0.0
        or weights.rook_file != 0.0
    ):
        phase = game_phase(board)
        score += _term(weights.pst, weights.pst_exp, pst_balance(board, phase) / PST_SCALE)
        score += _term(weights.passed, weights.passed_exp, passed_pawn_balance(board, phase) / PASSED_SCALE)
        score += _term(weights.structure, weights.structure_exp, pawn_structure_balance(board) / STRUCTURE_SCALE)
        score += _term(weights.shield, weights.shield_exp, king_shield_balance(board) / SHIELD_SCALE)
        score += _term(weights.bishop, weights.bishop_exp, float(bishop_pair_balance(board)) / BISHOP_SCALE)
        score += _term(weights.rook_file, weights.rook_file_exp, float(rook_file_balance(board)) / ROOK_SCALE)
    if weights.tempo != 0.0 or weights.outpost != 0.0 or weights.tropism != 0.0:
        score += _term(weights.tempo, weights.tempo_exp, tempo_balance(board) / TEMPO_SCALE)
        score += _term(weights.outpost, weights.outpost_exp, float(knight_outpost_balance(board)) / OUTPOST_SCALE)
        score += _term(weights.tropism, weights.tropism_exp, float(king_tropism_balance(board)) / TROPISM_SCALE)
    return score


def evaluate(board: chess.Board, weights: Weights, ply_from_root: int = 0) -> float:
    """Evaluate position. Mate scores encode distance so shorter mates score higher."""
    if board.is_checkmate():
        plies = max(0, int(ply_from_root))
        if board.turn == chess.WHITE:
            return -(MATE_SCORE - plies)
        return float(MATE_SCORE - plies)

    if board.is_stalemate() or board.is_insufficient_material():
        return 0.0

    if board.halfmove_clock >= 100:
        return 0.0

    if board.halfmove_clock >= 4 and board.is_repetition(3):
        return 0.0

    return static_eval(board, weights)


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
