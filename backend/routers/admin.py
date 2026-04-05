"""
routers/admin.py — v2 Admin REST endpoints

Endpoints:
  POST /admin/create-team    — create a new team
  POST /admin/create-group   — create a problem group (2 problems at fixed positions)
  POST /admin/assign-group   — assign a group to a team

Removed from v1:
  POST /admin/assign-problems (replaced by create-group + assign-group flow)
"""

from fastapi import APIRouter, Depends, HTTPException
import aiosqlite
from ..database import get_db
from ..models import (
    TeamCreateRequest, TeamCreateResponse,
    GroupCreateRequest, GroupCreateResponse,
    GroupAssignRequest, StandardResponse,
    ReadyCheckResponse, TeamReadyStatus
)
from ..problems.problem_loader import get_problem
from ..websocket.manager import manager
from ..core.team_manager import get_all_teams
from ..core.timer_engine import start_team

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/create-team", response_model=TeamCreateResponse)
async def create_team(request: TeamCreateRequest, db: aiosqlite.Connection = Depends(get_db)):
    """Create a new team. Team ID must be unique."""
    async with db.execute(
        "SELECT team_id FROM teams WHERE team_id = ?", (request.team_id,)
    ) as cursor:
        if await cursor.fetchone():
            raise HTTPException(status_code=400, detail="Team ID already exists")

    await db.execute("INSERT INTO teams (team_id) VALUES (?)", (request.team_id,))
    await db.commit()
    return TeamCreateResponse(status="success", team_id=request.team_id)


@router.post("/create-group", response_model=GroupCreateResponse)
async def create_group(request: GroupCreateRequest, db: aiosqlite.Connection = Depends(get_db)):
    """
    Create a reusable problem group with exactly 2 problems at fixed positions.
    problem_ids[0] → position 1 (assigned to player_slot 1)
    problem_ids[1] → position 2 (assigned to player_slot 2)
    """
    # Enforce unique problem IDs
    if len(set(request.problem_ids)) != 2:
        raise HTTPException(status_code=400, detail="Problem IDs in a group must be unique")

    # Validate both problems exist in the loaded problem cache
    for p_id in request.problem_ids:
        if get_problem(p_id) is None:
            raise HTTPException(status_code=400, detail=f"Problem '{p_id}' not found")

    # Check group_id is not already taken
    async with db.execute(
        "SELECT group_id FROM groups WHERE group_id = ?", (request.group_id,)
    ) as cursor:
        if await cursor.fetchone():
            raise HTTPException(status_code=400, detail="Group ID already exists")

    # Insert group
    await db.execute("INSERT INTO groups (group_id) VALUES (?)", (request.group_id,))

    # Insert exactly 2 problems at positions 1 and 2
    await db.execute(
        "INSERT INTO group_problems (group_id, problem_id, position) VALUES (?, ?, ?)",
        (request.group_id, request.problem_ids[0], 1)
    )
    await db.execute(
        "INSERT INTO group_problems (group_id, problem_id, position) VALUES (?, ?, ?)",
        (request.group_id, request.problem_ids[1], 2)
    )
    await db.commit()

    return GroupCreateResponse(status="success", group_id=request.group_id)


@router.post("/assign-group", response_model=StandardResponse)
async def assign_group(request: GroupAssignRequest, db: aiosqlite.Connection = Depends(get_db)):
    """Assign an existing group to a team. A team can only have one group assigned."""
    # Validate team exists
    async with db.execute(
        "SELECT team_id, group_id FROM teams WHERE team_id = ?", (request.team_id,)
    ) as cursor:
        team_row = await cursor.fetchone()
        if not team_row:
            raise HTTPException(status_code=404, detail="Team not found")
        if team_row[1] is not None:
            raise HTTPException(status_code=400, detail="Team already has a group assigned")

    # Validate group exists and has exactly 2 problems
    async with db.execute(
        "SELECT group_id FROM groups WHERE group_id = ?", (request.group_id,)
    ) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Group not found")

    async with db.execute(
        "SELECT COUNT(*) FROM group_problems WHERE group_id = ?", (request.group_id,)
    ) as cursor:
        row = await cursor.fetchone()
        if row[0] != 2:
            raise HTTPException(
                status_code=400,
                detail="Group must have exactly 2 problems before assignment"
            )

    # Assign group to team
    await db.execute(
        "UPDATE teams SET group_id = ? WHERE team_id = ?",
        (request.group_id, request.team_id)
    )
    await db.commit()

    return StandardResponse(status="success", message=f"Group '{request.group_id}' assigned to team '{request.team_id}'")


@router.get("/ready-check", response_model=ReadyCheckResponse)
async def ready_check():
    """
    Returns the ready status of all teams.
    A team is ready if it has exactly 2 connected players.
    """
    teams = await get_all_teams()
    response = []
    for team_id in teams:
        conns = manager.get_team_connections(team_id)
        connected_count = len(conns)
        response.append(
            TeamReadyStatus(
                team_id=team_id,
                connected_players=connected_count,
                ready=connected_count == 2
            )
        )
    return ReadyCheckResponse(teams=response)


@router.post("/start", response_model=StandardResponse)
async def start_round(db: aiosqlite.Connection = Depends(get_db)):
    """
    Validates all teams are ready (both players connected),
    then starts the core timer engine for all teams.
    """
    teams = await get_all_teams()
    
    if not teams:
        raise HTTPException(status_code=400, detail="Cannot start: No teams exist.")
    
    not_ready = []
    for team_id in teams:
        if len(manager.get_team_connections(team_id)) != 2:
            not_ready.append(team_id)
            
    if not_ready:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot start. Following teams not ready: {', '.join(not_ready)}"
        )
        
    for team_id in teams:
        await db.execute("UPDATE teams SET status = 'active' WHERE team_id = ?", (team_id,))
    
    await db.commit()
        
    for team_id in teams:
        start_team(team_id)
    
    return StandardResponse(status="success", message="Game started for all teams.")
