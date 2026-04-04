"""
timer_engine.py — v2 Core Timer Engine (Chunk 4)

Handles the full game flow state machine for a team:
PART_A (900s) -> BUFFER (10s) -> SWAP -> PART_B (900s) -> END
"""

import asyncio
import logging
import aiosqlite
from ..config import settings
from ..websocket.manager import manager
from ..websocket.events import (
    build_start_part_a, build_timer_tick, build_lock_and_submit,
    build_wait_for_swap, build_end_game
)
from .team_manager import get_assigned_problem
from .submission_handler import auto_submit_draft
from .swap_engine import perform_swap

logger = logging.getLogger("core.timer")

# Keep references to prevent GC
_active_tasks = set()


async def _set_team_phase(team_id: str, phase: str):
    """Updates the team's current_phase in the database."""
    async with aiosqlite.connect(settings.database_path, timeout=15.0) as db:
        await db.execute(
            "UPDATE teams SET current_phase = ? WHERE team_id = ?",
            (phase, team_id)
        )
        await db.commit()


async def force_team_submissions(team_id: str, phase: str):
    """Force drafts into final submissions for all players in a team."""
    async with aiosqlite.connect(settings.database_path, timeout=15.0) as db:
        async with db.execute(
            "SELECT id, player_slot FROM players WHERE team_id = ?",
            (team_id,)
        ) as cursor:
            players = await cursor.fetchall()
            
    for row in players:
        player_id = row[0]
        slot = row[1]
        if not slot: 
            continue
        
        # In Part A, player writes on their own slot's problem.
        # In Part B, player writes on the partner's slot problem.
        target_slot = slot if phase == "part_a" else (3 - slot)
        assigned_problem = await get_assigned_problem(team_id, target_slot)
        
        if assigned_problem:
            await auto_submit_draft(player_id, assigned_problem["id"], phase)


async def _run_team_timer(team_id: str):
    try:
        # ── 1. Part A ────────────────────────────────────────────────────────
        await _set_team_phase(team_id, "part_a")
        await manager.broadcast_to_team(team_id, build_start_part_a(settings.part_a_duration))
        
        for remaining in range(settings.part_a_duration, 0, -1):
            if remaining % 5 == 0:
                await manager.broadcast_to_team(team_id, build_timer_tick(remaining, "part_a"))
            await asyncio.sleep(1)
            
        # ── 2. Lock Part A ───────────────────────────────────────────────────
        await manager.broadcast_to_team(team_id, build_lock_and_submit())
        await force_team_submissions(team_id, "part_a")
        
        # ── 3. Wait Buffer ───────────────────────────────────────────────────
        await _set_team_phase(team_id, "buffer")
        for remaining in range(settings.buffer_duration, 0, -1):
            await manager.broadcast_to_team(team_id, build_wait_for_swap(remaining))
            await asyncio.sleep(1)
            
        # ── 4. Setup Part B (Swap) ───────────────────────────────────────────
        await _set_team_phase(team_id, "part_b")
        await perform_swap(team_id)
        
        # ── 5. Part B ────────────────────────────────────────────────────────
        for remaining in range(settings.part_b_duration, 0, -1):
            if remaining % 5 == 0:
                await manager.broadcast_to_team(team_id, build_timer_tick(remaining, "part_b"))
            await asyncio.sleep(1)
            
        # ── 6. End Game ──────────────────────────────────────────────────────
        await _set_team_phase(team_id, "ended")
        await manager.broadcast_to_team(team_id, build_lock_and_submit())
        await force_team_submissions(team_id, "part_b")
        await manager.broadcast_to_team(team_id, build_end_game())
        
    except asyncio.CancelledError:
        logger.info(f"Timer task cancelled for team {team_id}")
    except Exception as e:
        logger.error(f"Error in timer task for team {team_id}: {e}")


def start_team(team_id: str):
    """Schedules the timer task for a specific team in the background."""
    task = asyncio.create_task(_run_team_timer(team_id))
    _active_tasks.add(task)
    task.add_done_callback(_active_tasks.discard)
    logger.info(f"Started team timer for {team_id}")
