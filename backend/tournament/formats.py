"""Tournament schedule builders: round-robin and single elimination."""

from __future__ import annotations

import math
from typing import Optional

from backend.tournament.models import BotSpec, BracketMatch, GameState, new_id


def build_round_robin_games(bots: list[BotSpec], tournament_id: str) -> list[GameState]:
    """Two games per pair with swapped colors."""
    games: list[GameState] = []
    for i, a in enumerate(bots):
        for b in bots[i + 1 :]:
            pair_key = f"{a.id}:{b.id}"
            games.append(
                GameState(
                    id=new_id("g_"),
                    white=a,
                    black=b,
                    round_index=0,
                    pair_key=pair_key,
                    tournament_id=tournament_id,
                )
            )
            games.append(
                GameState(
                    id=new_id("g_"),
                    white=b,
                    black=a,
                    round_index=0,
                    pair_key=pair_key,
                    tournament_id=tournament_id,
                )
            )
    return games


def next_power_of_two(n: int) -> int:
    if n <= 1:
        return 1
    return 1 << (n - 1).bit_length()


def build_elimination_bracket(bots: list[BotSpec]) -> list[BracketMatch]:
    """Build a single-elimination bracket with byes for non-power-of-two counts."""
    if not bots:
        return []

    size = next_power_of_two(len(bots))
    # Seed order: as provided (already shuffled/random). Byes go to earliest seeds.
    slots: list[Optional[str]] = [None] * size
    for i, bot in enumerate(bots):
        slots[i] = bot.id

    matches: list[BracketMatch] = []
    # Round 0 pairings
    round0: list[BracketMatch] = []
    for slot in range(size // 2):
        a = slots[slot * 2]
        b = slots[slot * 2 + 1]
        is_bye = a is None or b is None
        winner = None
        if is_bye:
            winner = a or b
        match = BracketMatch(
            id=new_id("m_"),
            round_index=0,
            slot=slot,
            bot_a_id=a,
            bot_b_id=b,
            winner_id=winner,
            is_bye=is_bye,
        )
        round0.append(match)
        matches.append(match)

    rounds = int(math.log2(size))
    prev = round0
    for r in range(1, rounds):
        current: list[BracketMatch] = []
        for slot in range(len(prev) // 2):
            # Winners advance; may already be known if both prior were byes
            left = prev[slot * 2]
            right = prev[slot * 2 + 1]
            a = left.winner_id if left.is_bye else None
            b = right.winner_id if right.is_bye else None
            # Only pre-fill if both sides already decided via bye chain
            winner = None
            is_bye = False
            match = BracketMatch(
                id=new_id("m_"),
                round_index=r,
                slot=slot,
                bot_a_id=a if left.winner_id else None,
                bot_b_id=b if right.winner_id else None,
                winner_id=winner,
                is_bye=is_bye,
            )
            # If both prior winners known (bye chain), leave bots filled for scheduling
            if left.winner_id and right.winner_id:
                match.bot_a_id = left.winner_id
                match.bot_b_id = right.winner_id
            elif left.winner_id and not right.winner_id:
                match.bot_a_id = left.winner_id
            elif right.winner_id and not left.winner_id:
                match.bot_b_id = right.winner_id
            current.append(match)
            matches.append(match)
        prev = current

    return matches


def pending_elimination_games(
    bots_by_id: dict[str, BotSpec],
    bracket: list[BracketMatch],
    tournament_id: str,
) -> list[GameState]:
    """Create games for bracket matches that have both bots and no winner yet."""
    games: list[GameState] = []
    for match in bracket:
        if match.winner_id or match.is_bye:
            continue
        if not match.bot_a_id or not match.bot_b_id:
            continue
        if match.game_ids:
            continue
        a = bots_by_id[match.bot_a_id]
        b = bots_by_id[match.bot_b_id]
        game = GameState(
            id=new_id("g_"),
            white=a,
            black=b,
            round_index=match.round_index,
            pair_key=match.id,
            tournament_id=tournament_id,
        )
        match.game_ids.append(game.id)
        games.append(game)
    return games


def advance_bracket_after_win(
    bracket: list[BracketMatch],
    match_id: str,
    winner_id: str,
) -> None:
    """Set match winner and propagate into the next round slot."""
    match = next(m for m in bracket if m.id == match_id)
    match.winner_id = winner_id

    next_round = match.round_index + 1
    next_slot = match.slot // 2
    nxt = next((m for m in bracket if m.round_index == next_round and m.slot == next_slot), None)
    if nxt is None:
        return
    if match.slot % 2 == 0:
        nxt.bot_a_id = winner_id
    else:
        nxt.bot_b_id = winner_id
