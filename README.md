# Chess Bot Tournament

Breed alpha-beta chess bots with random evaluation weights, run tournaments, watch games live, save the champion’s weights, and play against them in the browser.

## Features

- **python-chess** for rules, legal moves, and attacks
- Alpha-beta search (default depth **5**) with weighted evaluation:
  - material · controlled squares · checking moves  
  - `score = a·x + b·y + c·z`
- Tournaments: **round-robin** or **single elimination**
- Live multi-game watching (≥1s/move when watched; unwatched games run fast)
- Save / import weight presets
- Human vs bot

## Quick start

```bash
pip install -r requirements.txt
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
