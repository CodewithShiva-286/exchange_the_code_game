"""
swap_engine.py — v2 Swap System (Chunk 4)

Handles exchanging code between player slots after Part A concludes.
"""

import aiosqlite
import logging
from ..config import settings
from .team_manager import get_assigned_problem, get_player_info
from ..problems.problem_loader import get_problem
from ..websocket.manager import manager
from ..websocket.events import build_start_part_b

logger = logging.getLogger("core.swap")

async def perform_swap(team_id: str):
    """
    Swap rule (v2): player_slot 1 ↔ player_slot 2
    After swap:
      - Player 1 (slot 1) gets Problem 2 Part A code + Problem 2 Part B prompt
      - Player 2 (slot 2) gets Problem 1 Part A code + Problem 1 Part B prompt
    """
    conns = manager.get_team_connections(team_id)
    
    # 1. Gather submission from DB for both slots
    slot_submissions = {}
    async with aiosqlite.connect(settings.database_path, timeout=15.0) as db:
        async with db.execute(
            """
            SELECT p.player_slot, s.code, s.problem_id
            FROM players p
            JOIN submissions s ON s.player_id = p.id
            WHERE p.team_id = ? AND s.phase = 'part_a'
            """,
            (team_id,)
        ) as cursor:
            async for row in cursor:
                slot_submissions[row[0]] = {"code": row[1], "problem_id": row[2]}

    # For safety, ensure both slots have empty string if missing (e.g. they disconnected)
    if 1 not in slot_submissions:
        slot_submissions[1] = {"code": "", "problem_id": None}
    if 2 not in slot_submissions:
        slot_submissions[2] = {"code": "", "problem_id": None}

    # 2. Iterate connected players and send payload
    part_b_duration = settings.part_b_duration

    for pid in conns:
        player_info = await get_player_info(pid, team_id)
        if not player_info:
            continue
            
        slot = player_info["player_slot"]
        partner_slot = 3 - slot  # 1 -> 2, 2 -> 1
        
        partner_code = slot_submissions[partner_slot]["code"]
        
        part_b_prompt = "Missing Part B prompt."
        full_problem_data = {}
        partner_prob_info = await get_assigned_problem(team_id, partner_slot)
        if partner_prob_info:
            full_problem_data = partner_prob_info
            full_prob = get_problem(partner_prob_info["id"])
            if full_prob:
                part_b_prompt = full_prob.part_b_prompt
        
        print(f"[{team_id}] SWAP DEBUG for player {pid} (target slot {partner_slot}):", full_problem_data)

        payload = build_start_part_b(part_b_duration, partner_code, part_b_prompt, full_problem_data)
        print(f"[{team_id}] WS START_PART_B PAYLOAD:", payload)

        await manager.send_to_player(team_id, pid, payload)
