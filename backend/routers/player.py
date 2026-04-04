"""
routers/player.py — v2 Player REST endpoints

Changes from v1:
- POST /join: atomically assigns player_slot (1 or 2) using DB transaction
- POST /join: returns player_slot in response
- GET /team/{team_id}/problems: REMOVED (players don't browse all problems;
  assignment is delivered via WS ASSIGNED event)
- GET /problem/{problem_id}: kept for problem detail lookups
"""

from fastapi import APIRouter, Depends, HTTPException
import aiosqlite
import uuid
from ..database import get_db
from ..models import JoinRequest, JoinResponse, ProblemDetail
from ..problems.problem_loader import get_problem

router = APIRouter(tags=["player"])


@router.post("/join", response_model=JoinResponse)
async def join_team(request: JoinRequest, db: aiosqlite.Connection = Depends(get_db)):
    """
    Join a team. Atomically assigns player_slot (1 = first joiner, 2 = second joiner).
    Rejects if team is full (2 players already).
    Race condition safe: slot is read and written inside a single transaction.
    """
    # Validate team exists
    async with db.execute(
        "SELECT team_id FROM teams WHERE team_id = ?", (request.team_id,)
    ) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Team not found")

    # ── Atomic slot assignment ─────────────────────────────────────────────
    # Read current player count + assign slot inside one serialised transaction.
    # aiosqlite is single-threaded per connection so this is safe under async.
    await db.execute("BEGIN")
    try:
        async with db.execute(
            "SELECT COUNT(*) FROM players WHERE team_id = ?", (request.team_id,)
        ) as cursor:
            row = await cursor.fetchone()
            current_count = row[0]

        if current_count >= 2:
            await db.execute("ROLLBACK")
            raise HTTPException(status_code=400, detail="Team is already full (2 players max)")

        player_slot = current_count + 1   # 0 → slot 1, 1 → slot 2
        session_token = str(uuid.uuid4())

        await db.execute(
            "INSERT INTO players (team_id, name, session_token, player_slot) VALUES (?, ?, ?, ?)",
            (request.team_id, request.name, session_token, player_slot)
        )
        await db.execute("COMMIT")
    except HTTPException:
        raise
    except Exception:
        await db.execute("ROLLBACK")
        raise

    # Retrieve the auto-generated player ID
    async with db.execute(
        "SELECT id FROM players WHERE session_token = ?", (session_token,)
    ) as cursor:
        player_row = await cursor.fetchone()
        player_id = player_row[0]

    return JoinResponse(
        status="success",
        session_token=session_token,
        team_id=request.team_id,
        player_id=player_id,
        player_slot=player_slot,
    )


@router.get("/problem/{problem_id}", response_model=ProblemDetail)
async def get_problem_details(problem_id: str):
    """Fetch full details of a problem by ID."""
    problem = get_problem(problem_id)
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")
    return problem
