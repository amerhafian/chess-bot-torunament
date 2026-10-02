"""Find weights by playing real round-robin tournaments.

A coarse field plays first. Each later tournament keeps every imported bot and
the champion, and fills the other seats with copies that differ by a smaller
step on one coefficient. Material stays at 1 and every exponent stays at 1.
"""

from __future__ import annotations

import asyncio
import random
import threading
from dataclasses import replace
from typing import Any, Optional

from backend.engine.evaluation import Weights
from backend.engine.names import generate_bot_name
from backend.tournament.models import TournamentConfig, TournamentFormat, TournamentStatus, WeightRange, new_id
from backend.tournament.runner import manager
from backend.weights import store as weight_store

COEFFS: tuple[str, ...] = (
    "controlled",
    "checking",
    "attacked",
    "center",
    "pst",
    "passed",
    "structure",
    "shield",
    "bishop",
    "rook_file",
    "tempo",
    "outpost",
    "tropism",
)
COARSE_VALUES = (0.0, 0.5, 1.0, 2.0)
FINE_STEPS = (0.5, 0.25, 0.125, 0.0625)
GENERATIONS = 1 + len(FINE_STEPS)

_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}
_running = False
_seq = 0


def coarse_field(bot_count: int, rng: random.Random, pinned: list[Weights] | None = None) -> list[Weights]:
    """Saved bots first, then distinct coarse vectors, including a material-only bot."""
    pinned = list(pinned or [])
    if len(pinned) >= bot_count:
        raise ValueError("leave a seat open so the search can try new weights")
    field = list(pinned)
    seen = {weights.as_tuple() for weights in field}
    material = Weights(material=1.0)
    if material.as_tuple() not in seen:
        field.append(material)
        seen.add(material.as_tuple())
    while len(field) < bot_count:
        chosen = {name: rng.choice(COARSE_VALUES) for name in COEFFS}
        weights = replace(Weights(material=1.0), **chosen)
        key = weights.as_tuple()
        if key in seen:
            continue
        seen.add(key)
        field.append(weights)
    return field


def _single_probes(center: Weights, step: float) -> list[Weights]:
    probes: list[Weights] = []
    seen = {center.as_tuple()}
    for name in COEFFS:
        base = float(getattr(center, name))
        for delta in (step, -step):
            value = max(0.0, base + delta)
            if value == base:
                continue
            weights = replace(center, **{name: value})
            key = weights.as_tuple()
            if key in seen:
                continue
            seen.add(key)
            probes.append(weights)
    return probes


def _pair_probes(center: Weights, step: float, seen: set[tuple[float, ...]]) -> list[Weights]:
    probes: list[Weights] = []
    for index, left in enumerate(COEFFS):
        left_base = float(getattr(center, left))
        for right in COEFFS[index + 1 :]:
            right_base = float(getattr(center, right))
            for left_delta in (step, -step):
                for right_delta in (step, -step):
                    left_value = max(0.0, left_base + left_delta)
                    right_value = max(0.0, right_base + right_delta)
                    if left_value == left_base or right_value == right_base:
                        continue
                    weights = replace(center, **{left: left_value, right: right_value})
                    key = weights.as_tuple()
                    if key in seen:
                        continue
                    seen.add(key)
                    probes.append(weights)
    return probes


def fine_field(
    center: Weights,
    step: float,
    bot_count: int,
    offset: int,
    pinned: list[Weights] | None = None,
) -> tuple[list[Weights], int]:
    """Saved bots and the champion stay. Other seats differ from the champion by ``step``."""
    pinned = list(pinned or [])
    if len(pinned) >= bot_count:
        raise ValueError("leave a seat open so the search can try new weights")
    field: list[Weights] = []
    seen: set[tuple[float, ...]] = set()

    def add(weights: Weights) -> None:
        key = weights.as_tuple()
        if key in seen or len(field) >= bot_count:
            return
        seen.add(key)
        field.append(weights)

    for weights in pinned:
        add(weights)
    if not pinned:
        field = [center]
        seen = {center.as_tuple()}
    else:
        add(center)
    probe_slots = bot_count - len(field)
    options = _single_probes(center, step)
    if options and probe_slots > 0:
        for index in range(probe_slots):
            add(options[(offset + index) % len(options)])
    if len(field) < bot_count:
        for weights in _pair_probes(center, step, seen):
            field.append(weights)
            if len(field) >= bot_count:
                break
    return field[:bot_count], offset + probe_slots


def _names_for(field: list[Weights], pinned: list[tuple[str, Weights]], rng: random.Random) -> list[str]:
    """Keep a saved bot's name when its weights are still in the field."""
    remaining = list(pinned)
    used: set[str] = set()
    names: list[str] = []
    for weights in field:
        match = next((index for index, (_, saved) in enumerate(remaining) if saved.as_tuple() == weights.as_tuple()), None)
        if match is None:
            name = generate_bot_name(used, rng)
        else:
            raw = remaining.pop(match)[0].strip() or "Saved bot"
            name = raw
            suffix = 2
            while name in used:
                name = f"{raw} {suffix}"
                suffix += 1
        used.add(name)
        names.append(name)
    return names


def _search_config(bot_count: int, depth: int) -> TournamentConfig:
    fixed = WeightRange(1.0, 1.0)
    unused = WeightRange(0.0, 0.0)
    return TournamentConfig(
        bot_count=bot_count,
        format=TournamentFormat.ROUND_ROBIN,
        depth=depth,
        range_a=fixed,
        range_b=unused,
        range_c=unused,
        range_d=unused,
        range_e=unused,
        range_exp=fixed,
    )


def _start_field(
    field: list[Weights],
    pinned: list[tuple[str, Weights]],
    *,
    bot_count: int,
    depth: int,
    rng: random.Random,
):
    return manager.start_with_weights(
        _search_config(bot_count, depth),
        field,
        rng,
        names=_names_for(field, pinned, rng),
    )


def _snapshot(job_id: str) -> dict[str, Any]:
    with _lock:
        job = dict(_jobs[job_id])
        job["tournament_ids"] = list(job["tournament_ids"])
    return job


def _update(job_id: str, **kwargs: Any) -> None:
    with _lock:
        extra_id = kwargs.pop("append_tournament_id", None)
        _jobs[job_id].update(kwargs)
        if extra_id:
            _jobs[job_id]["tournament_ids"].append(extra_id)
            _jobs[job_id]["tournament_id"] = extra_id


async def _champion_weights(tournament_id: str) -> tuple[Weights, str]:
    task = manager._tasks.get(tournament_id)
    if task is None:
        raise RuntimeError("tournament task is missing")
    await task
    tournament = manager.get_tournament(tournament_id)
    if tournament is None or tournament.status != TournamentStatus.FINISHED or not tournament.winner_bot_id:
        raise RuntimeError("tournament finished without a champion")
    winner = next(bot for bot in tournament.bots if bot.id == tournament.winner_bot_id)
    return winner.weights, winner.name


async def _run_campaign(
    job_id: str,
    *,
    bot_count: int,
    depth: int,
    pinned: list[tuple[str, Weights]],
    rng: random.Random,
) -> None:
    global _running
    pinned_weights = [weights for _, weights in pinned]
    try:
        center, name = await _champion_weights(_jobs[job_id]["tournament_id"])
        _update(job_id, leader=name)
        offset = 0
        for index, step in enumerate(FINE_STEPS):
            field, offset = fine_field(center, step, bot_count, offset, pinned_weights)
            held = list(pinned)
            if not any(weights.as_tuple() == center.as_tuple() for _, weights in held):
                held.append((name, center))
            tournament = _start_field(field, held, bot_count=bot_count, depth=depth, rng=rng)
            _update(
                job_id,
                generation=index + 2,
                phase="fine",
                step=step,
                leader=name,
                append_tournament_id=tournament.id,
            )
            center, name = await _champion_weights(tournament.id)
            _update(job_id, leader=name)
        saved = weight_store.save_weights(name="Find weights", weights=center, source="refine")
        _update(job_id, status="finished", phase="done", saved_id=saved["id"], weights=center.to_dict())
    except Exception as exc:
        _update(job_id, status="error", error=str(exc))
    finally:
        with _lock:
            _running = False


def start_refine(
    *,
    bot_count: int = 4,
    depth: int = 3,
    pinned: list[tuple[str, Weights]] | None = None,
) -> dict[str, Any]:
    """Start the coarse tournament, then keep going on the running event loop."""
    global _running, _seq
    pinned = list(pinned or [])
    with _lock:
        if _running:
            raise RuntimeError("a weight search is already running")
        _running = True
        _seq += 1
        job_id = new_id("refine")

    rng = random.Random()
    try:
        field = coarse_field(bot_count, rng, [weights for _, weights in pinned])
        tournament = _start_field(field, pinned, bot_count=bot_count, depth=depth, rng=rng)
    except Exception:
        with _lock:
            _running = False
        raise

    with _lock:
        _jobs[job_id] = {
            "id": job_id,
            "seq": _seq,
            "status": "running",
            "generation": 1,
            "generations": GENERATIONS,
            "phase": "coarse",
            "step": None,
            "leader": None,
            "tournament_id": tournament.id,
            "tournament_ids": [tournament.id],
            "bot_count": bot_count,
            "depth": depth,
            "weights": None,
            "saved_id": None,
            "error": None,
        }
    asyncio.get_running_loop().create_task(
        _run_campaign(job_id, bot_count=bot_count, depth=depth, pinned=pinned, rng=rng)
    )
    return _snapshot(job_id)


def current_refine() -> dict[str, Any]:
    with _lock:
        if not _jobs:
            return {"status": "idle"}
        latest = max(_jobs.values(), key=lambda job: job["seq"])
        snapshot = dict(latest)
        snapshot["tournament_ids"] = list(latest["tournament_ids"])
        return snapshot


def get_refine(job_id: str) -> Optional[dict[str, Any]]:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        snapshot = dict(job)
        snapshot["tournament_ids"] = list(job["tournament_ids"])
        return snapshot
