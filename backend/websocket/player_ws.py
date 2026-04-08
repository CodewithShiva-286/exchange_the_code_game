"""
websocket/player_ws.py — v2 Player WebSocket endpoint

/ws/{team_id}/{player_id}?token={session_token}

Responsibilities:
- Validate session token BEFORE accepting (reject immediately on failure)
- Close duplicate connections (old WS replaced with new)
- Register connection in manager
- Send ASSIGNED (individually per player) ONCE when both players connect
- SESSION_RESTORE on reconnect (includes assignment, not selection state)
- PING → PONG heartbeat
- Clean disconnect with stale-reference protection

v2 changes:
- REMOVED: SHOW_PROBLEMS broadcast
- REMOVED: all chosen_problem_id references
- ADDED: ASSIGNED sent individually using player_slot → group_problems.position
- ADDED: assignment included in SESSION_RESTORE
"""

import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
import aiosqlite
from .manager import manager
from .events import (
    build_connected, build_partner_joined, build_assigned,
    build_session_restore, build_error, build_pong, build_start_part_b,
    PING, DRAFT_SAVE, FINAL_SUBMIT, RUN_CODE
)
from ..config import settings
from ..problems.problem_loader import get_problem

logger = logging.getLogger("ws.player")
router = APIRouter()

from ..core.team_manager import get_player_info, get_partner_info, get_assigned_problem, get_team_status
from ..core.submission_handler import receive_draft, receive_final, check_both_submitted
from ..runner.execution_queue import submit_task, ExecutionTask


async def _send_assigned_to_team(team_id: str):
    """
    Send ASSIGNED individually to each connected player in the team.
    Slot 1 → problem at position 1; Slot 2 → problem at position 2.
    Each player receives ONLY their own assigned problem + partner's title.
    Called exactly once per team (guarded by manager.should_send_assigned).
    """
    conns = manager.get_team_connections(team_id)
    for pid in conns:
        player_info = await get_player_info(pid, team_id)
        if not player_info:
            continue

        slot = player_info["player_slot"]
        partner_slot = 3 - slot  # slot 1 → partner slot 2, slot 2 → partner slot 1

        assigned_problem = await get_assigned_problem(team_id, slot)
        partner_problem = await get_assigned_problem(team_id, partner_slot)

        if not assigned_problem:
            logger.warning(f"No assigned problem found for player {pid} (slot {slot}) in team {team_id}")
            continue

        partner_title = partner_problem["title"] if partner_problem else "Unknown"

        await manager.send_to_player(
            team_id, pid,
            build_assigned(slot, assigned_problem, partner_title)
        )


async def _build_restore_data(team_id: str, player_id: int) -> dict:
    """Build SESSION_RESTORE payload from DB state (v2: includes assignment, not selection)."""
    player_info = await get_player_info(player_id, team_id)
    partner_info = await get_partner_info(team_id, player_id)

    team_status = await get_team_status(team_id)
    phase = team_status["current_phase"] if team_status else "waiting"

    if phase == "waiting" and partner_info and partner_info["connection_status"] == "online":
        phase = "assigned"

    assigned_problem = None
    if player_info and player_info["player_slot"]:
        # In Part B and Ended, UI must restore the partner's problem as the main assignment
        target_slot = player_info["player_slot"] if phase not in ("part_b", "ended") else (3 - player_info["player_slot"])
        assigned_problem = await get_assigned_problem(team_id, target_slot)

    return {
        "player": player_info,
        "partner": partner_info,
        "assigned_problem": assigned_problem,
        "phase": phase,
    }


# ── WebSocket endpoint ─────────────────────────────────────────────────────────

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
        await websocket.accept()
        await websocket.close(code=4001, reason="Invalid session token")
        return

    # ── 2. Connect (handles duplicate: old WS force-closed before new accepted)
    is_reconnect = await manager.connect_player(team_id, player_id, websocket)

    player_info = await get_player_info(player_id, team_id)
    if not player_info:
        await websocket.close(code=4002, reason="Player not found")
        return

    try:
        # ── 3. Send CONNECTED confirmation ─────────────────────────────────
        await manager.send_to_player(
            team_id, player_id,
            build_connected(player_id, team_id, player_info["name"])
        )

        # ── 4. Reconnect → SESSION_RESTORE  ───────────────────────────────
        if is_reconnect:
            restore_data = await _build_restore_data(team_id, player_id)
            await manager.send_to_player(
                team_id, player_id,
                build_session_restore(restore_data["phase"], restore_data)
            )
        else:
            # ── 5. First-time connect ──────────────────────────────────────
            # Always notify the connecting player if their partner is already connected
            partner_info = await get_partner_info(team_id, player_id)
            if partner_info and partner_info.get("connection_status") == "online":
                await manager.send_to_player(
                    team_id, player_id,
                    build_partner_joined(partner_info["name"])
                )

            if manager.is_team_full(team_id):
                # Both players now connected → send ASSIGNED once per team
                if manager.should_send_assigned(team_id):
                    await _send_assigned_to_team(team_id)
                    manager.mark_assigned_sent(team_id)

                # Notify existing partner of new connection
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

            elif event_type == DRAFT_SAVE:
                data = message.get("data", {})
                problem_id = data.get("problem_id")
                code = data.get("code", "")
                if problem_id:
                    receive_draft(player_id, problem_id, code)

            elif event_type == FINAL_SUBMIT:
                data = message.get("data", {})
                problem_id = data.get("problem_id")
                code = data.get("code", "")
                team_status = await get_team_status(team_id)
                
                if not team_status or team_status["current_phase"] not in ("part_a", "part_b"):
                    await manager.send_to_player(
                        team_id, player_id, 
                        build_error("INVALID_PHASE", "Cannot submit outside of active timer phases.")
                    )
                    continue
                    
                if problem_id:
                    success = await receive_final(player_id, problem_id, code, team_status["current_phase"])
                    if not success:
                        await manager.send_to_player(
                            team_id, player_id, 
                            build_error("SUBMIT_FAILED", "Failed to save final submission.")
                        )
                    else:
                        # ── Auto-swap: check if both players have submitted ────
                        phase = team_status["current_phase"]
                        logger.info(f"[SWAP] Player {player_id} (team {team_id}) submitted. Checking partner...")
                        both_codes = await check_both_submitted(team_id, phase)
                        if both_codes is not None and phase == "part_a":
                            # Both submitted Part A → swap code and start Part B
                            logger.info(f"[SWAP] Team {team_id}: BOTH submitted! Triggering auto-swap.")
                            conns = manager.get_team_connections(team_id)
                            for pid in list(conns.keys()):
                                p_info = await get_player_info(pid, team_id)
                                if not p_info:
                                    continue
                                p_slot = p_info["player_slot"]
                                partner_slot = 3 - p_slot  # slot 1↔slot 2

                                # Get partner's code: the OTHER player's submission
                                partner_code = both_codes.get(
                                    next((k for k in both_codes if k != pid), None), ""
                                ) or ""
                                logger.info(f"[SWAP] Sending to player {pid} (slot {p_slot}): partner_code length={len(partner_code)}")

                                # Full problem for the partner's slot (they will work on it in Part B)
                                partner_problem = await get_assigned_problem(team_id, partner_slot)
                                if not partner_problem:
                                    partner_problem = {}

                                part_b_prompt = partner_problem.get("part_b_prompt", "Complete Part B!")

                                await manager.send_to_player(
                                    team_id, pid,
                                    build_start_part_b(
                                        duration_seconds=1800,
                                        partner_code=partner_code,
                                        part_b_prompt=part_b_prompt,
                                        full_problem=partner_problem,
                                    )
                                )
                        elif both_codes is None and phase == "part_a":
                            logger.info(f"[SWAP] Team {team_id}: Waiting for partner to submit.")

            elif event_type == RUN_CODE:
                data = message.get("data", {})
                print("RUN_CODE RECEIVED:", data)
                code = data.get("code", "")
                language = data.get("language", "python")
                problem_id = data.get("problem_id", "")

                # Fetch only visible (sample) test cases for this problem
                import aiosqlite as _aiosqlite
                test_cases = []
                async with _aiosqlite.connect(settings.database_path, timeout=15.0) as db:
                    async with db.execute(
                        "SELECT id, input_data, expected_output FROM test_cases "
                        "WHERE problem_id = ? AND is_visible = 1",
                        (problem_id,)
                    ) as cursor:
                        async for row in cursor:
                            test_cases.append({
                                "id": row[0],
                                "input_data": row[1],
                                "expected_output": row[2],
                            })

                if not test_cases:
                    # No sample test cases → just run with empty stdin for quick feedback
                    test_cases = [{"id": 0, "input_data": "", "expected_output": ""}]

                task = ExecutionTask(
                    task_type="run",
                    team_id=team_id,
                    player_id=player_id,
                    code=code,
                    language=language,
                    test_cases=test_cases,
                    problem_id=problem_id,
                )
                # Fire-and-forget: don't block the WS loop
                import asyncio as _asyncio
                _asyncio.create_task(submit_task(task))

            else:
                await manager.send_to_player(
                    team_id, player_id,
                    build_error("UNKNOWN_EVENT", f"Event '{event_type}' not handled yet")
                )

    except WebSocketDisconnect:
        await manager.disconnect_player(team_id, player_id, websocket)
    except Exception as e:
        logger.error(f"Player WS error: {e}")
        await manager.disconnect_player(team_id, player_id, websocket)
