import contextlib
from fastapi import FastAPI
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

# REST routers
app.include_router(player.router)
app.include_router(admin.router)

# WebSocket routers
app.include_router(player_ws.router)
app.include_router(admin_ws.router)

@app.get("/health")
async def health_check():
    return {"status": "ok"}
