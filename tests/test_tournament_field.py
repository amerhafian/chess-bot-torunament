"""Saved bots occupy tournament seats; the rest are random."""

from __future__ import annotations

import random

import pytest

from backend.engine.evaluation import Weights
from backend.tournament.models import TournamentConfig, TournamentFormat, WeightRange
from backend.tournament.runner import mix_field


def _config(bot_count: int = 4) -> TournamentConfig:
    span = WeightRange(0.0, 1.0)
    return TournamentConfig(
        bot_count=bot_count,
        format=TournamentFormat.ROUND_ROBIN,
        depth=3,
        range_a=WeightRange(1.0, 1.0),
        range_b=span,
        range_c=span,
        range_d=span,
        range_e=span,
        range_exp=WeightRange(1.0, 1.0),
        seed=1,
    )


def test_saved_bot_keeps_its_name_and_weights():
    saved = Weights(material=1.0, pst=0.4, tempo=0.2)
    field = mix_field(_config(), [("Find weights", saved)], random.Random(0))
    assert len(field) == 4
    assert field[0] == ("Find weights", saved)
    assert len({name for name, _ in field}) == 4


def test_duplicate_saved_names_get_a_suffix():
    field = mix_field(
        _config(2),
        [("Bold", Weights(material=1.0)), ("Bold", Weights(material=1.0, pst=1.0))],
        random.Random(0),
    )
    assert [name for name, _ in field] == ["Bold", "Bold 2"]
    assert field[1][1].pst == 1.0


def test_too_many_saved_bots_is_rejected():
    pinned = [("A", Weights(material=1.0)), ("B", Weights(material=1.0)), ("C", Weights(material=1.0))]
    with pytest.raises(ValueError, match="bot_count"):
        mix_field(_config(2), pinned, random.Random(0))
