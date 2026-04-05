"""
team_manager.py — v2 Core DB utilities for Teams and Players

Provides separation of concerns by pulling DB queries out of the WebSocket layer.
Implements Chunk 3 requirements for tracking team status and resolving problem assignments.
"""

import aiosqlite
from ..config import settings
from ..problems.problem_loader import get_problem


async def get_player_info(player_id: int, team_id: str) -> dict | None:
    """Fetch player info including player_slot."""
    async with aiosqlite.connect(settings.database_path, timeout=15.0) as db:
        async with db.execute(
            "SELECT id, name, team_id, player_slot, connection_status FROM players "
            "WHERE id = ? AND team_id = ?",
            (player_id, team_id)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "name": row[1],
                    "team_id": row[2],
                    "player_slot": row[3],
                    "connection_status": row[4],
                }
    return None


async def get_partner_info(team_id: str, player_id: int) -> dict | None:
    """Fetch the other player in the same team."""
    async with aiosqlite.connect(settings.database_path, timeout=15.0) as db:
        async with db.execute(
            "SELECT id, name, player_slot, connection_status FROM players "
            "WHERE team_id = ? AND id != ?",
            (team_id, player_id)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "name": row[1],
                    "player_slot": row[2],
                    "connection_status": row[3],
                }
    return None


async def get_team_group(team_id: str) -> str | None:
    """Returns the group_id assigned to a team."""
    async with aiosqlite.connect(settings.database_path, timeout=15.0) as db:
        async with db.execute(
            "SELECT group_id FROM teams WHERE team_id = ?", (team_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def get_team_status(team_id: str) -> dict | None:
    """Returns the team's current status and phase."""
    async with aiosqlite.connect(settings.database_path, timeout=15.0) as db:
        async with db.execute(
            "SELECT status, current_phase FROM teams WHERE team_id = ?", (team_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {"status": row[0], "current_phase": row[1]}
    return None


async def get_assigned_problem(team_id: str, player_slot: int) -> dict | None:
    """
    Resolve assigned problem for a player using slot → group_problems.position mapping.
    player_slot 1 → group_problems position 1
    player_slot 2 → group_problems position 2
    """
    async with aiosqlite.connect(settings.database_path, timeout=15.0) as db:
        async with db.execute(
            """
            SELECT gp.problem_id
            FROM group_problems gp
            JOIN teams t ON t.group_id = gp.group_id
            WHERE t.team_id = ? AND gp.position = ?
            """,
            (team_id, player_slot)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            problem_id = row[0]

    problem = get_problem(problem_id)
    if not problem:
        return None

    return {
        "id": problem.id,
        "title": problem.title,
        "description": problem.description,
        "part_a_prompt": problem.part_a_prompt,
        "interface_stub": problem.interface_stub,
        "language": problem.language,
        # part_b_prompt intentionally withheld until swap
    }


async def get_all_teams() -> list[str]:
    """Return a list of all team_ids in the system."""
    async with aiosqlite.connect(settings.database_path, timeout=15.0) as db:
        async with db.execute("SELECT team_id FROM teams") as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


async def get_team_dashboard_data() -> list[dict]:
    """
    Build full dashboard data for the admin UI.

    Returns a list of dicts, each containing:
      - team_id, group_id, status, current_phase
      - players: list of {slot, name, connected}

    Uses the WS ConnectionManager for live connection status.
    """
    from ..websocket.manager import manager  # deferred to avoid circular import

    async with aiosqlite.connect(settings.database_path, timeout=15.0) as db:
        # 1. Fetch all teams
        async with db.execute(
            "SELECT team_id, group_id, status, current_phase FROM teams ORDER BY team_id"
        ) as cursor:
            teams = await cursor.fetchall()

        result = []
        for team_row in teams:
            team_id = team_row[0]
            group_id = team_row[1]
            status = team_row[2]
            phase = team_row[3]

            # 2. Fetch players for this team
            async with db.execute(
                "SELECT id, name, player_slot FROM players WHERE team_id = ? ORDER BY player_slot",
                (team_id,)
            ) as cursor:
                player_rows = await cursor.fetchall()

            players = []
            for p_row in player_rows:
                p_id = p_row[0]
                p_name = p_row[1]
                p_slot = p_row[2]
                # Check live WS connection (not just DB column)
                connected = manager.is_player_connected(team_id, p_id)
                players.append({
                    "slot": p_slot,
                    "name": p_name,
                    "player_id": p_id,
                    "connected": connected,
                })

            result.append({
                "team_id": team_id,
                "group_id": group_id,
                "status": status,
                "current_phase": phase,
                "players": players,
            })

        return result
