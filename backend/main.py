import contextlib
from fastapi import FastAPI, Request
from starlette.responses import Response
from .database import init_db
from .problems.problem_loader import load_problems, seed_problems_to_db
from .routers import admin, player
from .websocket import player_ws, admin_ws


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    load_problems()
    await init_db()
    await seed_problems_to_db()
    yield


app = FastAPI(title="Exchange The Code", lifespan=lifespan)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store"
    return response


# REST routers
app.include_router(player.router)
app.include_router(admin.router)

# WebSocket routers
app.include_router(player_ws.router)
app.include_router(admin_ws.router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
