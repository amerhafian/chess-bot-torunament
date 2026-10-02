"""Tournament orchestration with watcher-aware move pacing."""

from __future__ import annotations

import asyncio
import random
import time
from typing import Any, Callable, Optional

import chess

from backend.engine.bot import Bot
from backend.engine.evaluation import Weights
from backend.engine.names import generate_bot_name
from backend.tournament.formats import (
    advance_bracket_after_win,
    build_elimination_bracket,
    build_round_robin_games,
    pending_elimination_games,
)
from backend.tournament.models import (
    BotSpec,
    GameState,
    GameStatus,
    Standing,
    TournamentConfig,
    TournamentFormat,
    TournamentState,
    TournamentStatus,
    WeightRange,
    new_id,
)

WatchCallback = Callable[[GameState], Any]
TournamentCallback = Callable[[TournamentState], Any]

MIN_WATCH_MOVE_SECONDS = 1.0


class TournamentManager:
    """In-memory store and runner for tournaments and live games."""

    def __init__(self) -> None:
        self.tournaments: dict[str, TournamentState] = {}
        self.games: dict[str, GameState] = {}
        self._game_subscribers: dict[str, set[asyncio.Queue]] = {}
        self._tournament_subscribers: dict[str, set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()
        self._tasks: dict[str, asyncio.Task] = {}

    # ---- subscriptions ----

    def subscribe_game(self, game_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._game_subscribers.setdefault(game_id, set()).add(queue)
        game = self.games.get(game_id)
        if game is not None:
            game.watchers = len(self._game_subscribers[game_id])
        return queue

    def unsubscribe_game(self, game_id: str, queue: asyncio.Queue) -> None:
        subs = self._game_subscribers.get(game_id)
        if not subs:
            return
        subs.discard(queue)
        game = self.games.get(game_id)
        if game is not None:
            game.watchers = len(subs)
        if not subs:
            self._game_subscribers.pop(game_id, None)

    def subscribe_tournament(self, tournament_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._tournament_subscribers.setdefault(tournament_id, set()).add(queue)
        return queue

    def unsubscribe_tournament(self, tournament_id: str, queue: asyncio.Queue) -> None:
        subs = self._tournament_subscribers.get(tournament_id)
        if not subs:
            return
        subs.discard(queue)
        if not subs:
            self._tournament_subscribers.pop(tournament_id, None)

    def _publish_game(self, game: GameState) -> None:
        payload = {"type": "game", "game": game.to_dict()}
        for queue in list(self._game_subscribers.get(game.id, ())):
            self._put_nowait(queue, payload)
        if game.tournament_id:
            self._publish_tournament_event(game.tournament_id, {"type": "game_update", "game": game.to_dict()})

    def _publish_tournament(self, tournament: TournamentState) -> None:
        self._publish_tournament_event(tournament.id, {"type": "tournament", "tournament": tournament.to_dict()})

    def _publish_tournament_event(self, tournament_id: str, payload: dict[str, Any]) -> None:
        for queue in list(self._tournament_subscribers.get(tournament_id, ())):
            self._put_nowait(queue, payload)

    @staticmethod
    def _put_nowait(queue: asyncio.Queue, payload: Any) -> None:
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    # ---- creation ----

    async def create_tournament(self, config: TournamentConfig) -> TournamentState:
        rng = random.Random(config.seed)
        names: set[str] = set()
        bots: list[BotSpec] = []
        for _ in range(config.bot_count):
            name = generate_bot_name(names, rng)
            names.add(name)
            weights = Weights(
                material=rng.uniform(config.range_a.min, config.range_a.max),
                controlled=rng.uniform(config.range_b.min, config.range_b.max),
                checking=rng.uniform(config.range_c.min, config.range_c.max),
            )
            bots.append(
                BotSpec(
                    id=new_id("b_"),
                    name=name,
                    weights=weights,
                    depth=config.depth,
                )
            )

        tournament = TournamentState(
            id=new_id("t_"),
            config=config,
            bots=bots,
            standings={
                b.id: Standing(bot_id=b.id, name=b.name) for b in bots
            },
            status=TournamentStatus.RUNNING,
        )

        if config.format == TournamentFormat.ROUND_ROBIN:
            games = build_round_robin_games(bots, tournament.id)
            for g in games:
                tournament.games[g.id] = g
                self.games[g.id] = g
        else:
            tournament.bracket = build_elimination_bracket(bots)
            bots_by_id = {b.id: b for b in bots}
            games = pending_elimination_games(bots_by_id, tournament.bracket, tournament.id)
            for g in games:
                tournament.games[g.id] = g
                self.games[g.id] = g

        self.tournaments[tournament.id] = tournament
        self._publish_tournament(tournament)
        self._tasks[tournament.id] = asyncio.create_task(self._run_tournament(tournament.id))
        return tournament

    async def _run_tournament(self, tournament_id: str) -> None:
        tournament = self.tournaments[tournament_id]
        try:
            if tournament.config.format == TournamentFormat.ROUND_ROBIN:
                await self._run_round_robin(tournament)
            else:
                await self._run_elimination(tournament)
            self._finalize_tournament(tournament)
        except Exception as exc:  # noqa: BLE001
            tournament.status = TournamentStatus.CANCELLED
            tournament.finished_at = time.time()
            self._publish_tournament(tournament)
            raise exc

    async def _run_round_robin(self, tournament: TournamentState) -> None:
        pending = [g for g in tournament.games.values() if g.status == GameStatus.PENDING]
        from backend.engine.bot import game_concurrency

        # Leave headroom for per-move root process pools
        sem = asyncio.Semaphore(game_concurrency())

        async def run_one(game: GameState) -> None:
            async with sem:
                await self._play_game(game)
                self._apply_round_robin_result(tournament, game)
                self._publish_tournament(tournament)

        await asyncio.gather(*(run_one(g) for g in pending))

    async def _run_elimination(self, tournament: TournamentState) -> None:
        bots_by_id = {b.id: b for b in tournament.bots}
        while True:
            # Resolve byes already marked
            if all(m.winner_id for m in tournament.bracket):
                break

            new_games = pending_elimination_games(bots_by_id, tournament.bracket, tournament.id)
            for g in new_games:
                tournament.games[g.id] = g
                self.games[g.id] = g
            self._publish_tournament(tournament)

            runnable = [
                g
                for g in tournament.games.values()
                if g.status == GameStatus.PENDING and g.pair_key
            ]
            if not runnable:
                # Fill any matches that got both bots mid-round
                new_games = pending_elimination_games(bots_by_id, tournament.bracket, tournament.id)
                for g in new_games:
                    tournament.games[g.id] = g
                    self.games[g.id] = g
                runnable = [
                    g
                    for g in tournament.games.values()
                    if g.status == GameStatus.PENDING
                ]
                if not runnable:
                    # Check if tournament complete
                    final = max(tournament.bracket, key=lambda m: m.round_index)
                    if final.winner_id:
                        break
                    await asyncio.sleep(0.05)
                    continue

            from backend.engine.bot import game_concurrency

            sem = asyncio.Semaphore(game_concurrency())

            async def run_match_game(game: GameState) -> None:
                async with sem:
                    await self._play_elimination_match(tournament, game)

            await asyncio.gather(*(run_match_game(g) for g in runnable))

    async def _play_elimination_match(self, tournament: TournamentState, game: GameState) -> None:
        match_id = game.pair_key
        assert match_id is not None
        await self._play_game(game)

        winner_id = game.winner_bot_id
        if winner_id is None:
            # Draw: rematch with colors swapped
            rematch = GameState(
                id=new_id("g_"),
                white=game.black,
                black=game.white,
                round_index=game.round_index,
                pair_key=match_id,
                tournament_id=tournament.id,
            )
            match = next(m for m in tournament.bracket if m.id == match_id)
            match.game_ids.append(rematch.id)
            tournament.games[rematch.id] = rematch
            self.games[rematch.id] = rematch
            self._publish_tournament(tournament)
            await self._play_game(rematch)
            winner_id = rematch.winner_bot_id
            if winner_id is None:
                # Still drawn — random winner
                winner_id = random.choice([game.white.id, game.black.id])

        advance_bracket_after_win(tournament.bracket, match_id, winner_id)
        self._publish_tournament(tournament)

    async def _play_game(self, game: GameState) -> None:
        board = chess.Board()
        white_bot = Bot(
            game.white.name,
            game.white.weights,
            game.white.depth,
            lane="background",
        )
        black_bot = Bot(
            game.black.name,
            game.black.weights,
            game.black.depth,
            lane="background",
        )

        game.status = GameStatus.RUNNING
        game.started_at = time.time()
        game.fen = board.fen()
        self._publish_game(game)

        move_count = 0
        max_plies = 300  # safety against endless games

        while not board.is_game_over(claim_draw=True) and move_count < max_plies:
            watcher_count = len(self._game_subscribers.get(game.id, ()))
            game.watchers = watcher_count
            pace = watcher_count > 0

            t0 = time.perf_counter()
            player = white_bot if board.turn == chess.WHITE else black_bot
            result = await asyncio.to_thread(player.choose_move, board)
            if result is None:
                break

            move, score = result
            san = board.san(move)
            board.push(move)
            game.moves.append(san)
            game.search_score = score
            game.eval_history.append(score)
            game.fen = board.fen()
            game.last_move_at = time.time()
            move_count += 1

            if pace:
                elapsed = time.perf_counter() - t0
                remaining = MIN_WATCH_MOVE_SECONDS - elapsed
                if remaining > 0:
                    await asyncio.sleep(remaining)
                # Re-check: if watchers left mid-sleep, still ok to continue fast next move

            self._publish_game(game)

        game.fen = board.fen()
        game.status = GameStatus.FINISHED
        game.finished_at = time.time()
        outcome = board.outcome(claim_draw=True)
        if outcome is None or outcome.winner is None:
            if move_count >= max_plies:
                game.result = "1/2-1/2"
            else:
                game.result = "1/2-1/2"
            game.winner_bot_id = None
        elif outcome.winner == chess.WHITE:
            game.result = "1-0"
            game.winner_bot_id = game.white.id
        else:
            game.result = "0-1"
            game.winner_bot_id = game.black.id
        self._publish_game(game)

    def _apply_round_robin_result(self, tournament: TournamentState, game: GameState) -> None:
        white_s = tournament.standings[game.white.id]
        black_s = tournament.standings[game.black.id]
        white_s.games += 1
        black_s.games += 1
        if game.result == "1-0":
            white_s.points += 1
            white_s.wins += 1
            black_s.losses += 1
        elif game.result == "0-1":
            black_s.points += 1
            black_s.wins += 1
            white_s.losses += 1
        else:
            white_s.points += 0.5
            black_s.points += 0.5
            white_s.draws += 1
            black_s.draws += 1
        self._recompute_sonneborn_berger(tournament)

    def _recompute_sonneborn_berger(self, tournament: TournamentState) -> None:
        """Sonneborn–Berger: sum of defeated opponents' points + half of draw opponents'."""
        # Reset
        for s in tournament.standings.values():
            s.sonneborn_berger = 0.0

        finished = [g for g in tournament.games.values() if g.status == GameStatus.FINISHED]
        points = {sid: st.points for sid, st in tournament.standings.items()}

        for game in finished:
            if game.result == "1-0":
                tournament.standings[game.white.id].sonneborn_berger += points[game.black.id]
            elif game.result == "0-1":
                tournament.standings[game.black.id].sonneborn_berger += points[game.white.id]
            else:
                tournament.standings[game.white.id].sonneborn_berger += 0.5 * points[game.black.id]
                tournament.standings[game.black.id].sonneborn_berger += 0.5 * points[game.white.id]

    def _finalize_tournament(self, tournament: TournamentState) -> None:
        if tournament.config.format == TournamentFormat.ROUND_ROBIN:
            ranked = sorted(
                tournament.standings.values(),
                key=lambda s: (-s.points, -s.sonneborn_berger, s.name),
            )
            tournament.winner_bot_id = ranked[0].bot_id if ranked else None
        else:
            if tournament.bracket:
                final = max(tournament.bracket, key=lambda m: (m.round_index, -m.slot))
                # true final is highest round_index, slot 0
                finals = [m for m in tournament.bracket if m.round_index == max(m.round_index for m in tournament.bracket)]
                final = finals[0]
                tournament.winner_bot_id = final.winner_id
        tournament.status = TournamentStatus.FINISHED
        tournament.finished_at = time.time()
        self._publish_tournament(tournament)

    def get_tournament(self, tournament_id: str) -> Optional[TournamentState]:
        return self.tournaments.get(tournament_id)

    def get_game(self, game_id: str) -> Optional[GameState]:
        return self.games.get(game_id)

    def list_tournaments(self) -> list[TournamentState]:
        return sorted(self.tournaments.values(), key=lambda t: t.created_at, reverse=True)


manager = TournamentManager()


def parse_config(data: dict[str, Any]) -> TournamentConfig:
    def rng(key: str, default_min: float, default_max: float) -> WeightRange:
        block = data.get(key) or {}
        return WeightRange(
            min=float(block.get("min", default_min)),
            max=float(block.get("max", default_max)),
        )

    fmt = TournamentFormat(data.get("format", TournamentFormat.ROUND_ROBIN.value))
    bot_count = int(data.get("bot_count", 4))
    if bot_count < 2:
        raise ValueError("bot_count must be at least 2")
    if bot_count > 32:
        raise ValueError("bot_count must be at most 32")
    depth = int(data.get("depth", 3))
    if depth < 1 or depth > 8:
        raise ValueError("depth must be between 1 and 8")

    range_a = rng("range_a", 0.5, 2.0)
    range_b = rng("range_b", 0.0, 1.0)
    range_c = rng("range_c", 0.0, 1.0)
    for label, r in (("a", range_a), ("b", range_b), ("c", range_c)):
        if r.min > r.max:
            raise ValueError(f"range_{label} min must be <= max")

    seed = data.get("seed")
    return TournamentConfig(
        bot_count=bot_count,
        format=fmt,
        depth=depth,
        range_a=range_a,
        range_b=range_b,
        range_c=range_c,
        seed=int(seed) if seed is not None else None,
    )
