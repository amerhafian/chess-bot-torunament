#!/usr/bin/env python3
"""Fit power-form coefficients on quiet positions, then check them in a match.

Exponents stay at 1. The loss is Texel's (sigmoid(eval) - game_result)^2.
When Stockfish is on PATH, its centipawn score is an extra teacher term.
The handcrafted eval is what plays; Stockfish only labels positions.

A short round-robin against a material-plus-PST baseline reports whether the
fitted vector wins games, not only the regression.
"""

from __future__ import annotations

import argparse
import math
import random
from typing import Optional

import chess

from backend.engine.bot import Bot
from backend.engine.evaluation import Weights, compute_metrics
from backend.engine.stockfish import StockfishEngine, stockfish_available

SCALES = (1.0, 20.0, 4.0, 2.0, 4.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 4.0)
COEFF_NAMES = (
    "a1",
    "b1",
    "c1",
    "d1",
    "e1",
    "f1",
    "g1",
    "h1",
    "i1",
    "j1",
    "k1",
    "l1",
    "m1",
    "n1",
)


def feature_vector(board: chess.Board) -> list[float]:
    metrics = compute_metrics(board)
    raw = (
        float(metrics.material),
        float(metrics.controlled),
        float(metrics.checking),
        float(metrics.attacked),
        float(metrics.center),
        metrics.pst,
        metrics.passed,
        metrics.structure,
        metrics.shield,
        float(metrics.bishop),
        float(metrics.rook_file),
        metrics.tempo,
        float(metrics.outpost),
        float(metrics.tropism),
    )
    return [value / scale for value, scale in zip(raw, SCALES)]


def is_quiet(board: chess.Board) -> bool:
    """Not in check, and no undefended non-king piece is under attack."""
    if board.is_check():
        return False
    for square, piece in board.piece_map().items():
        if piece.piece_type == chess.KING:
            continue
        if board.attackers(not piece.color, square) and not board.attackers(piece.color, square):
            return False
    return True


def _sigmoid(value: float) -> float:
    if value > 30:
        return 1.0
    if value < -30:
        return 0.0
    return 1.0 / (1.0 + math.exp(-value))


def texel_loss_and_grad(
    coeffs: list[float],
    rows: list[list[float]],
    results: list[float],
    *,
    scale: float,
    teacher: Optional[list[float]] = None,
    teacher_weight: float = 0.15,
) -> tuple[float, list[float]]:
    """Mean squared error of sigmoid(eval/scale) vs result, plus an optional teacher."""
    grad = [0.0] * len(coeffs)
    loss = 0.0
    count = len(rows)
    for index, (features, result) in enumerate(zip(rows, results)):
        eval_score = sum(c * x for c, x in zip(coeffs, features))
        pred = _sigmoid(eval_score / scale)
        err = pred - result
        loss += err * err
        deriv = 2.0 * err * pred * (1.0 - pred) / scale
        for i, feature in enumerate(features):
            grad[i] += deriv * feature
        if teacher is not None:
            target = teacher[index]
            terr = eval_score - target
            loss += teacher_weight * terr * terr
            for i, feature in enumerate(features):
                grad[i] += teacher_weight * 2.0 * terr * feature
    inv = 1.0 / max(1, count)
    return loss * inv, [g * inv for g in grad]


def fit_coefficients(
    rows: list[list[float]],
    results: list[float],
    *,
    steps: int = 80,
    lr: float = 0.05,
    scale: float = 1.5,
    teacher: Optional[list[float]] = None,
    init: Optional[list[float]] = None,
) -> tuple[list[float], float]:
    coeffs = list(init or baseline_coeffs())
    last = 0.0
    for _ in range(steps):
        last, grad = texel_loss_and_grad(coeffs, rows, results, scale=scale, teacher=teacher)
        coeffs = [c - lr * g for c, g in zip(coeffs, grad)]
        coeffs[0] = max(0.2, coeffs[0])
    return coeffs, last


def baseline_coeffs() -> list[float]:
    """Material plus a small piece-square term. Other coefficients stay at 0."""
    coeffs = [0.0] * 14
    coeffs[0] = 1.0
    coeffs[5] = 0.15
    return coeffs


def weights_from_coeffs(coeffs: list[float]) -> Weights:
    return Weights(
        material=coeffs[0],
        controlled=coeffs[1],
        checking=coeffs[2],
        attacked=coeffs[3],
        center=coeffs[4],
        pst=coeffs[5],
        passed=coeffs[6],
        structure=coeffs[7],
        shield=coeffs[8],
        bishop=coeffs[9],
        rook_file=coeffs[10],
        tempo=coeffs[11],
        outpost=coeffs[12],
        tropism=coeffs[13],
    )


def collect_quiet_positions(
    *,
    games: int = 6,
    max_plies: int = 24,
    seed: int = 1,
) -> tuple[list[list[float]], list[float], list[str]]:
    """Random playouts. Each quiet position is labeled with the game result."""
    rng = random.Random(seed)
    rows: list[list[float]] = []
    results: list[float] = []
    fens: list[str] = []
    for _ in range(games):
        board = chess.Board()
        snapshots: list[str] = []
        for ply in range(max_plies):
            if board.is_game_over(claim_draw=True):
                break
            if ply % 2 == 0 and is_quiet(board):
                snapshots.append(board.fen())
            move = rng.choice(list(board.legal_moves))
            board.push(move)
        if board.is_game_over(claim_draw=True):
            outcome = board.outcome(claim_draw=True)
            if outcome is None or outcome.winner is None:
                result = 0.5
            elif outcome.winner == chess.WHITE:
                result = 1.0
            else:
                result = 0.0
        else:
            result = 0.5
        for fen in snapshots:
            rows.append(feature_vector(chess.Board(fen)))
            results.append(result)
            fens.append(fen)
    return rows, results, fens


def teacher_scores(fens: list[str], depth: int = 8) -> Optional[list[float]]:
    """Stockfish centipawns converted to pawns. None when the binary is missing."""
    if not fens or not stockfish_available():
        return None
    engine = StockfishEngine(depth=depth)
    scores: list[float] = []
    try:
        for fen in fens:
            scores.append(engine.analyse_score(chess.Board(fen)))
    finally:
        engine.close()
    return scores


def play_game(
    white: Weights,
    black: Weights,
    *,
    depth: int,
    max_plies: int,
    use_native: bool = True,
) -> float:
    """Return the result from White's point of view (1, 0.5, or 0)."""
    board = chess.Board()
    bots = {
        chess.WHITE: Bot("W", white, depth=depth, use_parallel=False, use_native=use_native, lane="interactive"),
        chess.BLACK: Bot("B", black, depth=depth, use_parallel=False, use_native=use_native, lane="interactive"),
    }
    for _ in range(max_plies):
        if board.is_game_over(claim_draw=True):
            break
        played = bots[board.turn].choose_move(board)
        if played is None:
            break
        board.push(played[0])
    if not board.is_game_over(claim_draw=True):
        return 0.5
    outcome = board.outcome(claim_draw=True)
    if outcome is None or outcome.winner is None:
        return 0.5
    return 1.0 if outcome.winner == chess.WHITE else 0.0


def round_robin(
    candidate: Weights,
    baseline: Weights,
    *,
    pairs: int = 1,
    depth: int = 2,
    max_plies: int = 16,
    use_native: bool = True,
) -> float:
    """Mean score of `candidate` across color-swapped games. 0.5 is even."""
    total = 0.0
    games = 0
    for _ in range(pairs):
        total += play_game(candidate, baseline, depth=depth, max_plies=max_plies, use_native=use_native)
        total += 1.0 - play_game(baseline, candidate, depth=depth, max_plies=max_plies, use_native=use_native)
        games += 2
    return total / games


def main() -> None:
    parser = argparse.ArgumentParser(description="Texel-tune evaluation coefficients")
    parser.add_argument("--games", type=int, default=6)
    parser.add_argument("--steps", type=int, default=60)
    parser.add_argument("--depth", type=int, default=2)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--no-stockfish", action="store_true")
    args = parser.parse_args()

    rows, results, fens = collect_quiet_positions(games=args.games, seed=args.seed)
    if len(rows) < 4:
        raise SystemExit("not enough quiet positions; increase --games")
    teacher = None if args.no_stockfish else teacher_scores(fens)
    init = baseline_coeffs()
    before, _ = texel_loss_and_grad(init, rows, results, scale=1.5, teacher=teacher)
    fitted, after = fit_coefficients(
        rows, results, steps=args.steps, teacher=teacher, init=init
    )
    candidate = weights_from_coeffs(fitted)
    baseline = weights_from_coeffs(init)
    match = round_robin(candidate, baseline, depth=args.depth, max_plies=12)
    print(f"quiet positions: {len(rows)}")
    print(f"stockfish labels: {teacher is not None}")
    print(f"loss {before:.4f} -> {after:.4f}")
    named = ", ".join(f"{name}={value:.3f}" for name, value in zip(COEFF_NAMES, fitted))
    print(f"coefficients: {named}")
    print(f"round-robin score vs material+PST baseline: {match:.2f} (candidate's point of view)")


if __name__ == "__main__":
    main()
