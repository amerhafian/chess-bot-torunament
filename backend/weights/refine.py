"""Find weights by playing real round-robin tournaments.

A coarse field plays first. Each later tournament keeps the champion and
fills the other seats with copies that differ by a smaller step on one
coefficient. Material stays at 1 and every exponent stays at 1.
"""

from __future__ import annotations

import asyncio
import random
import threading
from dataclasses import replace
from typing import Any, Optional

from backend.engine.evaluation import Weights
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


def coarse_field(bot_count: int, rng: random.Random) -> list[Weights]:
    """Distinct vectors on the coarse grid, including a material-only bot."""
    field = [Weights(material=1.0)]
    seen = {field[0].as_tuple()}
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


def fine_field(center: Weights, step: float, bot_count: int, offset: int) -> tuple[list[Weights], int]:
    """Champion first, then seats that differ by ``step``, walking the coefficients."""
    options = _single_probes(center, step)
    need = max(0, bot_count - 1)
    field = [center]
    seen = {center.as_tuple()}
    if options:
        for index in range(need):
            weights = options[(offset + index) % len(options)]
            key = weights.as_tuple()
            if key in seen:
                continue
            seen.add(key)
            field.append(weights)
    if len(field) < bot_count:
        for weights in _pair_probes(center, step, seen):
            field.append(weights)
            if len(field) >= bot_count:
                break
    return field[:bot_count], offset + need


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


async def _run_campaign(job_id: str, *, bot_count: int, depth: int) -> None:
    global _running
    try:
        center, name = await _champion_weights(_jobs[job_id]["tournament_id"])
        _update(job_id, leader=name)
        offset = 0
        for index, step in enumerate(FINE_STEPS):
            field, offset = fine_field(center, step, bot_count, offset)
            tournament = manager.start_with_weights(_search_config(bot_count, depth), field)
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


def start_refine(*, bot_count: int = 4, depth: int = 3) -> dict[str, Any]:
    """Start the coarse tournament, then keep going on the running event loop."""
    global _running, _seq
    with _lock:
        if _running:
            raise RuntimeError("a weight search is already running")
        _running = True
        _seq += 1
        job_id = new_id("refine")

    try:
        rng = random.Random()
        field = coarse_field(bot_count, rng)
        tournament = manager.start_with_weights(_search_config(bot_count, depth), field, rng)
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
    asyncio.get_running_loop().create_task(_run_campaign(job_id, bot_count=bot_count, depth=depth))
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
