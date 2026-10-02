"""Chess Bot Tournament API entrypoint."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.api.routes import router
from backend.api import routes as route_module

app = FastAPI(title="Chess Bot Tournament", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")

app.add_api_websocket_route("/ws/games/{game_id}", route_module.ws_game)
app.add_api_websocket_route("/ws/tournaments/{tournament_id}", route_module.ws_tournament)
app.add_api_websocket_route("/ws/play/{session_id}", route_module.ws_play)

FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"


@app.get("/api")
async def api_root() -> dict[str, str]:
    return {"message": "Chess Bot Tournament API", "docs": "/docs"}


def _mount_frontend() -> None:
    if not FRONTEND_DIST.exists():
        return
    assets = FRONTEND_DIST / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/")
    async def index():
        return FileResponse(FRONTEND_DIST / "index.html")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        candidate = FRONTEND_DIST / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")


_mount_frontend()
