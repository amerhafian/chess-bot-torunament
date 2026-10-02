# Chess Bot Tournament

Breed alpha-beta chess bots with random evaluation weights, run tournaments, watch games live, save the champion’s weights, and play against them (or watch them vs Stockfish) in the browser.

## Features

- **python-chess** for rules, legal moves, and attacks
- Alpha-beta search (default depth **3 plies**, TT + root-parallel on multi-core) with power-form evaluation over five metrics:
  - material · controlled squares · king pressure · attacked pieces · center control
  - `score = a1·x^a2 + b1·y^b2 + …` (signed power; exponents default to 1)
- Mate labels on the eval bar as `Mn` / `-Mn` (moves). Depth stays in plies (depth 4 ≈ M2; M4 needs ~7–8 plies).
- Tournaments: **round-robin** or **single elimination**
- Live multi-game watching (≥1s/move when watched; unwatched games run fast)
- Save / import weight presets (legacy `{a,b,c}` still loads)
- Human vs bot, and **Bot vs Stockfish** (user picks Stockfish’s color; dual eval bars)

## Quick start

```bash
pip install -r requirements.txt
# Optional — needed for Bot vs Stockfish
sudo apt-get install -y stockfish
# or: export STOCKFISH_PATH=/path/to/stockfish

cd frontend && npm install && npm run build && cd ..
PYTHONPATH=. uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Open http://127.0.0.1:8000

### Development

```bash
# terminal 1
PYTHONPATH=. uvicorn backend.main:app --reload --port 8000

# terminal 2
cd frontend && npm run dev
```

Vite proxies `/api` and `/ws` to the backend.

### Tests

```bash
PYTHONPATH=. pytest -q
```

## License

GPL-3.0 (see [LICENSE](LICENSE)).
