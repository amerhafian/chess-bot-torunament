"""Unique bot name generator."""

from __future__ import annotations

import random
from typing import Iterable

_ADJECTIVES = (
    "Swift",
    "Silent",
    "Iron",
    "Clever",
    "Bold",
    "Quiet",
    "Fierce",
    "Steady",
    "Sharp",
    "Lucky",
    "Noble",
    "Wild",
    "Calm",
    "Bright",
    "Dark",
    "Grand",
    "Nimble",
    "Stoic",
    "Vivid",
    "Cunning",
)

_NOUNS = (
    "Knight",
    "Rook",
    "Bishop",
    "Pawn",
    "Queen",
    "Castle",
    "Gambit",
    "Shield",
    "Blade",
    "Falcon",
    "Tiger",
    "Owl",
    "Fox",
    "Drake",
    "Viper",
    "Hawk",
    "Lynx",
    "Wolf",
    "Spark",
    "Crown",
)


def generate_bot_name(existing: Iterable[str] | None = None, rng: random.Random | None = None) -> str:
    """Return a unique AdjectiveNoun name not present in *existing*."""
    used = set(existing or ())
    rng = rng or random.Random()
    for _ in range(500):
        name = f"{rng.choice(_ADJECTIVES)}{rng.choice(_NOUNS)}"
        if name not in used:
            return name
    # Extremely unlikely fallback
    suffix = rng.randint(1000, 9999)
    return f"{rng.choice(_ADJECTIVES)}{rng.choice(_NOUNS)}{suffix}"
