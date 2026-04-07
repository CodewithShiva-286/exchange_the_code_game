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
from ..core.team_manager import get_all_teams, get_team_dashboard_data
from ..core.leaderboard import get_leaderboard_data, broadcast_leaderboard_update
from ..core.timer_engine import start_team

router = APIRouter(prefix="/admin", tags=["admin"])


from typing import Optional

@router.post("/create-team", response_model=TeamCreateResponse)
async def create_team(request: Optional[TeamCreateRequest] = None, db: aiosqlite.Connection = Depends(get_db)):
    """Create a new team. Team ID must be unique. Auto-generates if not provided."""
    team_id = request.team_id if request else None

    # Auto-generate if omitted
    if not team_id:
        async with db.execute("SELECT COUNT(*) FROM teams") as cursor:
            row = await cursor.fetchone()
            count = row[0] if row else 0
            
        team_id = f"TEAM-{count + 1}"
        
        # Ensure unique by incrementing until we find an empty slot
        while True:
            async with db.execute("SELECT team_id FROM teams WHERE team_id = ?", (team_id,)) as cursor:
                if not await cursor.fetchone():
                    break
            count += 1
            team_id = f"TEAM-{count + 1}"
    else:
        async with db.execute(
            "SELECT team_id FROM teams WHERE team_id = ?", (team_id,)
        ) as cursor:
            if await cursor.fetchone():
                raise HTTPException(status_code=400, detail="Team ID already exists")

    await db.execute("INSERT INTO teams (team_id) VALUES (?)", (team_id,))
    await db.commit()
    return TeamCreateResponse(status="success", team_id=team_id)


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
    
    # Immediately push ASSIGNED to connected players of this team
    from ..websocket.player_ws import _send_assigned_to_team
    from ..websocket.manager import manager
    if manager.is_team_full(request.team_id):
        await _send_assigned_to_team(request.team_id)
        manager.mark_assigned_sent(request.team_id)

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


@router.get("/groups")
async def get_groups(db: aiosqlite.Connection = Depends(get_db)):
    """
    Returns all available problem groups for the admin dropdown.
    Lightweight: just group_id + problem IDs.
    """
    async with db.execute("SELECT group_id FROM groups ORDER BY group_id") as cursor:
        group_rows = await cursor.fetchall()

    result = []
    for row in group_rows:
        gid = row[0]
        async with db.execute(
            "SELECT problem_id, position FROM group_problems WHERE group_id = ? ORDER BY position",
            (gid,)
        ) as cursor:
            problems = await cursor.fetchall()

        result.append({
            "group_id": gid,
            "problems": [
                {"problem_id": p[0], "position": p[1]}
                for p in problems
            ],
        })

    return result


@router.get("/teams")
async def get_teams():
    """
    Returns full dashboard data for all teams.
    Includes group assignment, player slots, and live WS connection status.
    """
    data = await get_team_dashboard_data()
    return data


@router.get("/leaderboard")
async def get_leaderboard():
    """Return teams ranked by their current cumulative score."""
    return await get_leaderboard_data()

@router.post("/reset-db", response_model=StandardResponse)
async def reset_db(db: aiosqlite.Connection = Depends(get_db)):
    """Safe database cleanup for testing. Removes all teams, players, submissions, and execution results."""
    await db.execute("BEGIN TRANSACTION")
    try:
        await db.execute("DELETE FROM team_scores")
        await db.execute("DELETE FROM execution_results")
        await db.execute("DELETE FROM submissions")
        await db.execute("DELETE FROM players")
        await db.execute("DELETE FROM teams")
        
        # Reset sqlite_sequence to safely restart auto-increment logic if it exists
        await db.execute("DELETE FROM sqlite_sequence WHERE name IN ('teams', 'players', 'submissions', 'execution_results')")
        
        await db.commit()
        await broadcast_leaderboard_update()
        return StandardResponse(status="success", message="Database safely reset. System acts like a fresh start.")
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to reset DB: {str(e)}")

@router.post("/new-round", response_model=StandardResponse)
async def new_round(db: aiosqlite.Connection = Depends(get_db)):
    """Reset round state to allow a new game for the same teams, storing their scores."""
    await db.execute("BEGIN TRANSACTION")
    try:
        await db.execute("DELETE FROM execution_results")
        await db.execute("DELETE FROM submissions")
        
        await db.execute("UPDATE teams SET status = 'waiting', current_phase = 'waiting', group_id = NULL")
        
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to reset round: {str(e)}")

    # Stop all timers and active execution
    from ..core.timer_engine import _active_tasks
    for task in list(_active_tasks):
        if not task.done():
            task.cancel()
    _active_tasks.clear()

    # Reset assignment state tracking and broadcast to players
    teams = await get_all_teams()
    from ..websocket.events import build_event
    for team_id in teams:
        manager._assigned_sent.discard(team_id)
        await manager.broadcast_to_team(team_id, build_event("NEW_ROUND", {}))

    return StandardResponse(status="success", message="Round state successfully reset. Ready for new assignments.")
