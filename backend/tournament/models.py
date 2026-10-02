"""Shared tournament / game data models."""

from __future__ import annotations

import enum
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from backend.engine.evaluation import Weights


def new_id(prefix: str = "") -> str:
    uid = uuid.uuid4().hex[:12]
    return f"{prefix}{uid}" if prefix else uid


class GameStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    FINISHED = "finished"
    CANCELLED = "cancelled"


class TournamentStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    FINISHED = "finished"
    CANCELLED = "cancelled"


class TournamentFormat(str, enum.Enum):
    ROUND_ROBIN = "round_robin"
    SINGLE_ELIMINATION = "single_elimination"


@dataclass
class WeightRange:
    min: float
    max: float

    def clamp_sample(self, value: float) -> float:
        return max(self.min, min(self.max, value))

    def to_dict(self) -> dict[str, float]:
        return {"min": self.min, "max": self.max}


@dataclass
class BotSpec:
    id: str
    name: str
    weights: Weights
    depth: int = 3

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "weights": self.weights.to_dict(),
            "depth": self.depth,
        }


@dataclass
class GameState:
    id: str
    white: BotSpec
    black: BotSpec
    status: GameStatus = GameStatus.PENDING
    fen: str = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    moves: list[str] = field(default_factory=list)
    result: Optional[str] = None  # "1-0", "0-1", "1/2-1/2"
    winner_bot_id: Optional[str] = None
    round_index: int = 0
    pair_key: Optional[str] = None
    watchers: int = 0
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    last_move_at: Optional[float] = None
    tournament_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        from backend.engine.evaluation import display_eval_averaged
        import chess

        board = chess.Board(self.fen)
        evaluation = display_eval_averaged(board, self.white.weights, self.black.weights)
        return {
            "id": self.id,
            "white": self.white.to_dict(),
            "black": self.black.to_dict(),
            "status": self.status.value,
            "fen": self.fen,
            "moves": list(self.moves),
            "result": self.result,
            "winner_bot_id": self.winner_bot_id,
            "round_index": self.round_index,
            "pair_key": self.pair_key,
            "watchers": self.watchers,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "last_move_at": self.last_move_at,
            "tournament_id": self.tournament_id,
            "evaluation": evaluation,
        }


@dataclass
class Standing:
    bot_id: str
    name: str
    points: float = 0.0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    games: int = 0
    sonneborn_berger: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "bot_id": self.bot_id,
            "name": self.name,
            "points": self.points,
            "wins": self.wins,
            "draws": self.draws,
            "losses": self.losses,
            "games": self.games,
            "sonneborn_berger": self.sonneborn_berger,
        }


@dataclass
class BracketMatch:
    id: str
    round_index: int
    slot: int
    bot_a_id: Optional[str]
    bot_b_id: Optional[str]
    winner_id: Optional[str] = None
    game_ids: list[str] = field(default_factory=list)
    is_bye: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "round_index": self.round_index,
            "slot": self.slot,
            "bot_a_id": self.bot_a_id,
            "bot_b_id": self.bot_b_id,
            "winner_id": self.winner_id,
            "game_ids": list(self.game_ids),
            "is_bye": self.is_bye,
        }


@dataclass
class TournamentConfig:
    bot_count: int
    format: TournamentFormat
    depth: int
    range_a: WeightRange
    range_b: WeightRange
    range_c: WeightRange
    seed: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "bot_count": self.bot_count,
            "format": self.format.value,
            "depth": self.depth,
            "range_a": self.range_a.to_dict(),
            "range_b": self.range_b.to_dict(),
            "range_c": self.range_c.to_dict(),
            "seed": self.seed,
        }


@dataclass
class TournamentState:
    id: str
    config: TournamentConfig
    bots: list[BotSpec]
    games: dict[str, GameState] = field(default_factory=dict)
    status: TournamentStatus = TournamentStatus.PENDING
    standings: dict[str, Standing] = field(default_factory=dict)
    bracket: list[BracketMatch] = field(default_factory=list)
    winner_bot_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "config": self.config.to_dict(),
            "bots": [b.to_dict() for b in self.bots],
            "games": [g.to_dict() for g in self.games.values()],
            "status": self.status.value,
            "standings": [s.to_dict() for s in sorted(
                self.standings.values(),
                key=lambda s: (-s.points, -s.sonneborn_berger, s.name),
            )],
            "bracket": [m.to_dict() for m in self.bracket],
            "winner_bot_id": self.winner_bot_id,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
        }
