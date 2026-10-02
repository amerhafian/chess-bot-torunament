"""Tests for tournament format builders."""

from __future__ import annotations

from backend.engine.evaluation import Weights
from backend.tournament.formats import (
    advance_bracket_after_win,
    build_elimination_bracket,
    build_round_robin_games,
    next_power_of_two,
    pending_elimination_games,
)
from backend.tournament.models import BotSpec


def _bots(n: int) -> list[BotSpec]:
    return [
        BotSpec(id=f"b{i}", name=f"Bot{i}", weights=Weights(1, 0.5, 0.5), depth=5)
        for i in range(n)
    ]


def test_round_robin_two_games_per_pair():
    bots = _bots(4)
    games = build_round_robin_games(bots, "t1")
    # C(4,2) = 6 pairs * 2 = 12 games
    assert len(games) == 12


def test_next_power_of_two():
    assert next_power_of_two(3) == 4
    assert next_power_of_two(4) == 4
    assert next_power_of_two(5) == 8


def test_elimination_byes():
    bots = _bots(3)
    bracket = build_elimination_bracket(bots)
    round0 = [m for m in bracket if m.round_index == 0]
    assert len(round0) == 2
    byes = [m for m in round0 if m.is_bye]
    assert len(byes) == 1
    assert byes[0].winner_id is not None


def test_elimination_advance():
    bots = _bots(4)
    bracket = build_elimination_bracket(bots)
    bots_by_id = {b.id: b for b in bots}
    games = pending_elimination_games(bots_by_id, bracket, "t1")
    assert len(games) == 2
    match = next(m for m in bracket if m.id == games[0].pair_key)
    advance_bracket_after_win(bracket, match.id, games[0].white.id)
    assert match.winner_id == games[0].white.id
