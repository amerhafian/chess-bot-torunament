# Chess Bot Tournament — agent notes

## Agent workflow preferences (owner)

- **Do not** run browser-based manual tests, `computerUse` subagents, screen recordings, or screenshot walkthrough artifacts unless the owner **explicitly** asks for them. They are token-heavy.
- Prefer **pytest**, curl/API smoke checks, and `npm run build` for verification.

## What this project is

A browser-based platform where alpha-beta chess bots compete in tournaments. Bots share the same search algorithm; they differ by evaluation **power-form weights** over five metrics:

```
score = a1·mat^a2 + b1·(ctrl/20)^b2 + c1·(king/4)^c2
 + d1·(attacked/2)^d2 + e1·(center/4)^e2
 + f1·pst^f2 + g1·passed^g2 + h1·structure^h2
 + i1·shield^i2 + j1·bishop^j2 + k1·rook^k2
 + l1·tempo^l2 + m1·outpost^m2 + n1·(tropism/4)^n2
```

with `signed_pow(x,p) = sign(x)·|x|^p`. Coefficients f–n default to 0 so older weight files keep the five-metric eval. `pst` is a phased piece-square table in pawns; `passed` grows as material comes off; `structure` is isolated/doubled pawns (positive when White has fewer defects); `shield` is the king pawn shield minus heavy-piece pressure; `bishop` is the bishop pair; `rook` is open/semi-open files; `tempo` is the side to move (+1 White, −1 Black); `outpost` counts knights on the fourth through sixth rank (third through fifth for Black) that a friendly pawn defends and no enemy pawn attacks; `tropism` is how close queens, rooks, and knights are to the enemy king (7 − chebyshev distance, White − Black, divided by 4).

- **material (a)**: P=1, N=3, B=3, R=5, Q=9 (King=0); White − Black
- **controlled_squares (b)**: sum of attacked squares per piece (overlaps count); White − Black
- **king_pressure (c)**: attackers on enemy king square and king-adjacent ring; White − Black
- **attacked_pieces (d)**: count of enemy pieces currently attacked; White − Black
- **center_control (e)**: attacks on d4/d5/e4/e5; White − Black

Positive scores favor White. Mate uses `±(100000 − plies_to_mate)` so shorter mates score higher. Eval bar shows `Mn` / `-Mn` in **moves** (`n = (plies+1)//2`). Search **depth is in plies** (depth 4 ≈ M2; M4 needs ~7–8 plies).

Legacy weight JSON `{a,b,c}` loads as coeffs with exponents `1` and `d1=e1=0`.

### Search performance

- Default search **depth is 3**. There is no upper cap. Depth 5+ is still expensive in pure Python; the native engine finishes a depth-10 opening search in well under a second.
- **Do not** parallelize a single `evaluate()` call — too fine-grained; overhead dominates.
- Alpha-beta uses a **per-search transposition table**. The native engine shares one depth-preferred lock-free table across root threads; the Python pool gives each worker a private table.
- Quiescence searches captures that do not lose the first exchange, plus quiet queen promotions. Null-move and late-move reductions use a narrow window and re-search if the score beats the bound. Checks extend the line by at most two extra plies.
- At depth ≥ 3 with enough root moves, **root-move parallelism** via `ProcessPoolExecutor` (`spawn`) uses multiple CPU cores. Each worker has a private TT.
- **Search lanes (isolation):** human vs bot uses `lane="interactive"` (inline search inside `asyncio.to_thread`). Tournaments use `lane="background"` with a separate process pool. They must not share a pool queue — otherwise tournaments starve live play.
- Tournament games run concurrently via `game_concurrency()` (25 at a time). Each game searches on one thread so they run together; a live game still uses every core.
- **Eval bar:** shows the **search score** of the last bot think (`choose_move` → `(move, score)`), Stockfish-style — not the static leaf eval of the current FEN. `eval_history` stores per-ply scores for scrubbing; human plies may be `null` until the bot replies. Static eval is only a fallback before any search exists. Live bar EMA-smooths `white_pct`; scrubbing is exact.
- In-search terminals: mate/stalemate/insufficient/50-move, plus **threefold** via `is_repetition(2)` when `halfmove_clock >= 4`. Game loop still uses full `claim_draw=True`. Move ordering prefers captures only (no `gives_check` sort).

### Stockfish

- Stockfish is an **optional opponent** for Bot vs Stockfish play (`mode=stockfish`), not a replacement for bot evaluation.
- Binary via `STOCKFISH_PATH` or `PATH` (`stockfish`). Missing binary → HTTP 503 on create.
- User picks Stockfish’s color; dual eval bars show bot search score and SF analysis score.

## Stack

- **Rules / move gen**: [`python-chess`](https://github.com/niklasf/python-chess) (`pip install chess`) — do **not** reimplement chess rules
- **Backend**: FastAPI + Uvicorn, WebSockets for live updates
- **Frontend**: React + Vite + TypeScript + Tailwind + `react-chessboard`
- **Persistence**: JSON files in `data/weights/`
- **License**: GPL-3.0 (matches python-chess)

## Layout

```
backend/
  engine/          # evaluation.py, bot.py (alpha-beta), stockfish.py, names.py
  tournament/      # models, formats (RR + elimination), runner
  play/            # human vs bot + bot vs Stockfish sessions
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
# Optional: Stockfish for Bot vs SF play
#   sudo apt-get install -y stockfish
#   # or: export STOCKFISH_PATH=/path/to/stockfish
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

1. Default search **depth is 3** (any integer ≥ 1 in the UI/API). Depth is **plies**; mate labels are **moves** (`Mn`).
2. Tournament formats: **both** round-robin (two games per pair, colors swapped) and single elimination (byes if needed; draws → rematch swapped colors → random if still drawn).
3. Unwatched games run **as fast as possible**. Watched games (WebSocket subscribers on `/ws/games/{id}`) pace at **≥1 second per move**. Multiple games can be watched at once.
4. No chess clocks / time controls unless explicitly requested.
5. Keep the **five-metric power-form** weight formula (`coeff · signed_pow(scaled_metric, exp)`). Do **not** replace bot evaluation with NNUE/Stockfish. Stockfish may be used only as an **opponent** in play mode.
6. Move ordering may use cheap heuristics (captures/checks first); that does not change which move alpha-beta selects at a given depth.

## API sketch

- `POST /api/tournaments` — start tournament. Optional `weight_ids` pin saved bots into the field; the remaining seats are random.
- `GET /api/tournaments/{id}` — status / standings / bracket / games
- `WS /ws/tournaments/{id}` — live tournament updates
- `WS /ws/games/{id}` — subscribe to watch (enables pacing)
- `POST /api/weights`, `GET /api/weights`, `DELETE /api/weights/{id}`
- `POST /api/weights/refine`, `GET /api/weights/refine` — five round-robin tournaments (material fixed at 1). A coarse field plays first, then each later field is the champion plus bots that differ by a smaller step.
- `POST /api/tournaments/{id}/save-winner`
- `POST /api/play` — human vs bot or `mode=stockfish` (Bot vs SF)
- `POST /api/play/{id}/move`, `WS /ws/play/{id}`
- `GET /api/stockfish` — `{available: bool}`

## Weight JSON schema

```json
{
  "id": "string",
  "name": "string",
  "a1": 1.0,
  "a2": 1.0,
  "b1": 0.5,
  "b2": 1.0,
  "c1": 0.5,
  "c2": 1.0,
  "d1": 0.0,
  "d2": 1.0,
 "e1": 0.0,
 "e2": 1.0,
 "f1": 0.0,
 "f2": 1.0,
 "g1": 0.0,
 "g2": 1.0,
 "h1": 0.0,
 "h2": 1.0,
 "i1": 0.0,
 "i2": 1.0,
 "j1": 0.0,
 "j2": 1.0,
 "k1": 0.0,
 "k2": 1.0,
 "l1": 0.0,
 "l2": 1.0,
 "m1": 0.0,
 "m2": 1.0,
 "n1": 0.0,
 "n2": 1.0,
 "a": 1.0,
  "b": 0.5,
  "c": 0.5,
  "source": "tournament:… | manual | …",
  "bot_name": "optional",
  "created_at": 0.0
}
```

Legacy files with only `a,b,c` are still loadable.

## Conventions

- Prefer extending existing modules over inventing parallel systems.
- Keep production-minded error handling on API boundaries.
- Frontend visual language: wood/felt chess atmosphere (Fraunces + Source Sans 3); avoid generic purple AI gradients.
- When changing evaluation semantics, update unit tests in `tests/test_evaluation.py`.
