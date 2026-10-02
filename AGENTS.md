# Chess Bot Tournament — agent notes

## Agent workflow preferences (owner)

- **Do not** run browser-based manual tests, `computerUse` subagents, screen recordings, or screenshot walkthrough artifacts unless the owner **explicitly** asks for them. They are token-heavy.
- Prefer **pytest**, curl/API smoke checks, and `npm run build` for verification.

## What this project is

A browser-based platform where alpha-beta chess bots compete in tournaments. Bots share the same search algorithm; they differ only by evaluation **weights** `(a, b, c)` over three metrics:

```
score = a * material + b * controlled_squares + c * king_pressure
```

- **material**: P=1, N=3, B=3, R=5, Q=9 (King=0); White − Black
- **controlled_squares**: sum of attacked squares per piece (overlaps count); White − Black
- **king_pressure** (weight `c`): fast proxy for king safety / checking pressure — count attackers on the enemy king square **and** king-adjacent ring squares; White − Black. (Replaces the original “count all legal checking moves” leaf scan, which was too slow.)

Positive scores favor White. Mate uses ±100000 adjusted by depth.

### Search performance

- Default search **depth is 3** (API/UI range 1–8). Depth 5+ is still possible but expensive in pure Python.
- **Do not** parallelize a single `evaluate()` call — too fine-grained; overhead dominates.
- Alpha-beta uses a **per-search transposition table**.
- At depth ≥ 3 with enough root moves, **root-move parallelism** via `ProcessPoolExecutor` (`spawn`) uses multiple CPU cores. Each worker has a private TT.
- **Search lanes (isolation):** human vs bot uses `lane="interactive"` with its own process pool (+ dedicated thread fallback). Tournaments use `lane="background"` with a separate pool. They must not share a pool queue — otherwise tournaments starve live play.
- Tournament games run concurrently via `game_concurrency()` (at least 4).

## Stack

- **Rules / move gen**: [`python-chess`](https://github.com/niklasf/python-chess) (`pip install chess`) — do **not** reimplement chess rules
- **Backend**: FastAPI + Uvicorn, WebSockets for live updates
- **Frontend**: React + Vite + TypeScript + Tailwind + `react-chessboard`
- **Persistence**: JSON files in `data/weights/`
- **License**: GPL-3.0 (matches python-chess)

## Layout

```
backend/
  engine/          # evaluation.py, bot.py (alpha-beta), names.py
  tournament/      # models, formats (RR + elimination), runner
  play/            # human vs bot sessions
  weights/         # JSON store
  api/routes.py    # REST + WS
  main.py          # FastAPI app
frontend/          # Vite SPA
tests/             # pytest
data/weights/      # saved weight presets
```

## How to run

```bash
# Backend (from repo root)
pip install -r requirements.txt
PYTHONPATH=. uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend (dev, proxies /api and /ws)
cd frontend && npm install && npm run dev

# Production UI: build then serve via FastAPI static
cd frontend && npm run build
PYTHONPATH=. uvicorn backend.main:app --host 0.0.0.0 --port 8000

# Tests
PYTHONPATH=. pytest -q
```

## Product rules agents must keep

1. Default search **depth is 3** (configurable 1–8 in UI/API).
2. Tournament formats: **both** round-robin (two games per pair, colors swapped) and single elimination (byes if needed; draws → rematch swapped colors → random if still drawn).
3. Unwatched games run **as fast as possible**. Watched games (WebSocket subscribers on `/ws/games/{id}`) pace at **≥1 second per move**. Multiple games can be watched at once.
4. No chess clocks / time controls unless explicitly requested.
5. Keep the three-metric linear weight formula (`a·x + b·y + c·z`). Metric `z` is king-pressure (see above), not a full checking-move generator. Do not replace with NNUE/Stockfish/etc.
6. Move ordering may use cheap heuristics (captures/checks first); that does not change which move alpha-beta selects at a given depth.

## API sketch

- `POST /api/tournaments` — start tournament
- `GET /api/tournaments/{id}` — status / standings / bracket / games
- `WS /ws/tournaments/{id}` — live tournament updates
- `WS /ws/games/{id}` — subscribe to watch (enables pacing)
- `POST /api/weights`, `GET /api/weights`, `DELETE /api/weights/{id}`
- `POST /api/tournaments/{id}/save-winner`
- `POST /api/play`, `POST /api/play/{id}/move`, `WS /ws/play/{id}`

## Weight JSON schema

```json
{
  "id": "string",
  "name": "string",
  "a": 1.0,
  "b": 0.5,
  "c": 0.5,
  "source": "tournament:… | manual | …",
  "bot_name": "optional",
  "created_at": 0.0
}
```

## Conventions

- Prefer extending existing modules over inventing parallel systems.
- Keep production-minded error handling on API boundaries.
- Frontend visual language: wood/felt chess atmosphere (Fraunces + Source Sans 3); avoid generic purple AI gradients.
- When changing evaluation semantics, update unit tests in `tests/test_evaluation.py`.
