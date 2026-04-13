import contextlib
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .database import init_db
from .problems.problem_loader import load_problems, seed_problems_to_db
from .routers import admin, player
from .websocket import player_ws, admin_ws
from .runner.execution_queue import start_worker, stop_worker

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    load_problems()
    await init_db()
    await seed_problems_to_db()
    start_worker()
    yield
    stop_worker()

app = FastAPI(title="Exchange The Code", lifespan=lifespan)

# CORS — allow admin dashboard (served from file:// or different port) to hit the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# REST routers
app.include_router(player.router)
app.include_router(admin.router)

# WebSocket routers
app.include_router(player_ws.router)
app.include_router(admin_ws.router)

# Serve frontend static files (admin dashboard)
_frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.isdir(_frontend_dir):
    app.mount("/frontend", StaticFiles(directory=_frontend_dir, html=True), name="frontend")

@app.get("/health")
async def health_check():
    return {"status": "ok"}
