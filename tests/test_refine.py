"""Field builder for the tournament weight search."""

from __future__ import annotations

import random

from backend.engine.evaluation import Weights
from backend.weights.refine import COEFFS, coarse_field, fine_field


def _coeff(weights: Weights, name: str) -> float:
    return float(getattr(weights, name))


def test_coarse_field_includes_material_only_and_stays_on_the_grid():
    field = coarse_field(4, random.Random(1))
    assert len(field) == 4
    assert len({weights.as_tuple() for weights in field}) == 4
    assert any(all(_coeff(weights, name) == 0.0 for name in COEFFS) for weights in field)
    for weights in field:
        assert weights.material == 1.0
        assert weights.material_exp == 1.0
        for name in COEFFS:
            assert _coeff(weights, name) in (0.0, 0.5, 1.0, 2.0)


def test_fine_field_keeps_the_champion_and_steps_one_coefficient():
    center = Weights(material=1.0, controlled=0.5, pst=1.0)
    field, offset = fine_field(center, 0.5, 4, 0)
    assert len(field) == 4
    assert field[0].as_tuple() == center.as_tuple()
    assert offset == 3
    for weights in field:
        for name in COEFFS:
            assert _coeff(weights, name) >= 0.0
    for weights in field[1:]:
        changed = [name for name in COEFFS if _coeff(weights, name) != _coeff(center, name)]
        assert len(changed) == 1
        assert abs(_coeff(weights, changed[0]) - _coeff(center, changed[0])) == 0.5


def test_fine_field_rotates_which_coefficients_are_probed():
    center = Weights(material=1.0)
    first, offset = fine_field(center, 0.5, 4, 0)
    second, _ = fine_field(center, 0.5, 4, offset)
    assert {weights.as_tuple() for weights in first[1:]} != {weights.as_tuple() for weights in second[1:]}


def test_negative_step_is_clamped_away():
    center = Weights(material=1.0)
    field, _ = fine_field(center, 0.5, 8, 0)
    for weights in field:
        for name in COEFFS:
            assert _coeff(weights, name) >= 0.0


def test_imported_bot_stays_in_the_coarse_and_fine_fields():
    saved = Weights(material=1.0, pst=0.4, tempo=0.2)
    coarse = coarse_field(4, random.Random(2), [saved])
    assert coarse[0].as_tuple() == saved.as_tuple()
    assert len(coarse) == 4
    assert len({weights.as_tuple() for weights in coarse}) == 4

    center = Weights(material=1.0, controlled=1.0)
    field, offset = fine_field(center, 0.25, 4, 0, [saved])
    assert offset == 2
    assert field[0].as_tuple() == saved.as_tuple()
    assert center.as_tuple() in {weights.as_tuple() for weights in field}
    probes = [weights for weights in field if weights.as_tuple() not in {saved.as_tuple(), center.as_tuple()}]
    assert probes
    for weights in probes:
        changed = [name for name in COEFFS if _coeff(weights, name) != _coeff(center, name)]
        assert len(changed) == 1
        assert abs(_coeff(weights, changed[0]) - _coeff(center, changed[0])) == 0.25


def test_full_field_of_imports_leaves_no_seat_to_search():
    saved = [Weights(material=1.0, pst=0.4), Weights(material=1.0, tempo=0.2)]
    try:
        coarse_field(2, random.Random(0), saved)
    except ValueError as exc:
        assert "seat" in str(exc)
    else:
        raise AssertionError("expected a full import field to be rejected")
