"""Texel fitter: loss drops, and a tiny match returns a score."""

from __future__ import annotations

from scripts.tune_weights import (
    baseline_coeffs,
    feature_vector,
    fit_coefficients,
    round_robin,
    texel_loss_and_grad,
    weights_from_coeffs,
)

import chess


def test_feature_vector_has_fourteen_terms():
    assert len(feature_vector(chess.Board())) == 14


def test_texel_fit_reduces_loss():
    # White is up material in the winning sample and down in the losing one.
    winning = chess.Board()
    winning.remove_piece_at(chess.A7)
    losing = chess.Board()
    losing.remove_piece_at(chess.A2)
    rows = [feature_vector(winning), feature_vector(losing), feature_vector(chess.Board())]
    results = [1.0, 0.0, 0.5]
    init = [0.1] * 14
    before, _ = texel_loss_and_grad(init, rows, results, scale=1.5)
    fitted, after = fit_coefficients(rows, results, steps=40, lr=0.2, init=init)
    assert after < before
    assert fitted[0] > 0.2


def test_round_robin_score_is_a_fraction():
    baseline = weights_from_coeffs(baseline_coeffs())
    candidate = weights_from_coeffs(baseline_coeffs())
    score = round_robin(candidate, baseline, pairs=1, depth=1, max_plies=4, use_native=True)
    assert 0.0 <= score <= 1.0
