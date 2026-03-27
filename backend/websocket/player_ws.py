"""
Player WebSocket endpoint: /ws/{team_id}/{player_id}?token={session_token}

Responsibilities:
- Validate session token BEFORE accepting (reject immediately on failure)
- Close duplicate connections (old WS replaced by new)
- Register connection in manager
- SHOW_PROBLEMS auto-trigger ONCE per team when both connect
- SESSION_RESTORE on reconnect
- PING → PONG heartbeat
- Clean disconnect with stale-reference protection
"""

import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
import aiosqlite
from .manager import manager
from .events import (
    build_connected, build_partner_joined, build_show_problems,
    build_session_restore, build_error, build_pong, PING
)
from ..config import settings
from ..problems.problem_loader import get_problem

logger = logging.getLogger("ws.player")
router = APIRouter()


async def _get_player_info(player_id: int, team_id: str) -> dict | None:
    """Fetch player name and basic info from DB."""
    async with aiosqlite.connect(settings.database_path) as db:
        async with db.execute(
            "SELECT id, name, team_id, connection_status, chosen_problem_id FROM players WHERE id = ? AND team_id = ?",
            (player_id, team_id)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "name": row[1],
                    "team_id": row[2],
                    "connection_status": row[3],
                    "chosen_problem_id": row[4],
                }
    return None


async def _get_team_problems_list(team_id: str) -> list:
    """Fetch assigned problems for a team as list of dicts."""
    async with aiosqlite.connect(settings.database_path) as db:
        async with db.execute(
            "SELECT problem_id FROM team_problems WHERE team_id = ?",
            (team_id,)
        ) as cursor:
            rows = await cursor.fetchall()

    problems = []
    for row in rows:
        p = get_problem(row[0])
        if p:
            problems.append({
                "id": p.id,
                "title": p.title,
                "description": p.description,
            })
    return problems


async def _get_partner_info(team_id: str, player_id: int) -> dict | None:
    """Fetch the partner player in the same team."""
    async with aiosqlite.connect(settings.database_path) as db:
        async with db.execute(
            "SELECT id, name, connection_status, chosen_problem_id FROM players WHERE team_id = ? AND id != ?",
            (team_id, player_id)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "name": row[1],
                    "connection_status": row[2],
                    "chosen_problem_id": row[3],
                }
    return None


async def _build_restore_data(team_id: str, player_id: int) -> dict:
    """Build SESSION_RESTORE data from current DB state."""
    player_info = await _get_player_info(player_id, team_id)
    partner_info = await _get_partner_info(team_id, player_id)
    problems = await _get_team_problems_list(team_id)

    # Determine current phase based on state
    # For Chunk 2 we only know: "waiting" or "selection"
    phase = "waiting"
    if partner_info and partner_info["connection_status"] == "online":
        phase = "selection"

    return {
        "player": player_info,
        "partner": partner_info,
        "problems": problems,
        "phase": phase,
    }


@router.websocket("/ws/{team_id}/{player_id}")
async def player_websocket(
    websocket: WebSocket,
    team_id: str,
    player_id: int,
    token: str = Query(...)
):
    # ── 1. Validate session token BEFORE any accept ────────────────────────
    is_valid = await manager.validate_session(team_id, player_id, token)
    if not is_valid:
        # Must accept before we can close with a code on most ASGI servers
        await websocket.accept()
        await websocket.close(code=4001, reason="Invalid session token")
        return

    # ── 2. Connect (handles duplicate detection + old WS close internally) ─
    is_reconnect = await manager.connect_player(team_id, player_id, websocket)

    player_info = await _get_player_info(player_id, team_id)
    if not player_info:
        await websocket.close(code=4002, reason="Player not found")
        return

    try:
        # ── 3. Send CONNECTED confirmation ─────────────────────────────────
        await manager.send_to_player(
            team_id, player_id,
            build_connected(player_id, team_id, player_info["name"])
        )

        # ── 4. Handle reconnect → SESSION_RESTORE ─────────────────────────
        if is_reconnect:
            restore_data = await _build_restore_data(team_id, player_id)
            await manager.send_to_player(
                team_id, player_id,
                build_session_restore(restore_data["phase"], restore_data)
            )
        else:
            # ── 5. First-time connect: check if both players are in ────────
            if manager.is_team_full(team_id):
                # Send SHOW_PROBLEMS only ONCE per team
                if manager.should_show_problems(team_id):
                    problems = await _get_team_problems_list(team_id)
                    if problems:
                        await manager.broadcast_to_team(
                            team_id,
                            build_show_problems(problems)
                        )
                        manager.mark_problems_shown(team_id)

                # Notify the existing partner that new player joined
                for pid in manager.get_team_connections(team_id):
                    if pid != player_id:
                        await manager.send_to_player(
                            team_id, pid,
                            build_partner_joined(player_info["name"])
                        )

        # ── 6. Message loop ────────────────────────────────────────────────
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await manager.send_to_player(
                    team_id, player_id,
                    build_error("INVALID_JSON", "Message must be valid JSON")
                )
                continue

            event_type = message.get("event")

            if event_type == PING:
                await manager.send_to_player(team_id, player_id, build_pong())

            # Other events (CHOOSE_PROBLEM, DRAFT_SAVE, FINAL_SUBMIT)
            # will be routed in Chunk 3 and Chunk 4.
            else:
                await manager.send_to_player(
                    team_id, player_id,
                    build_error("UNKNOWN_EVENT", f"Event '{event_type}' not handled yet")
                )

    except WebSocketDisconnect:
        # Pass `websocket` so manager only removes if it's the CURRENT reference
        await manager.disconnect_player(team_id, player_id, websocket)
    except Exception as e:
        logger.error(f"Player WS error: {e}")
        await manager.disconnect_player(team_id, player_id, websocket)
