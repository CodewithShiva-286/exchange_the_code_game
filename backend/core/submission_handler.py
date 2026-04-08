"""
submission_handler.py — v2 Submission Handler (Chunk 4)

Handles storing drafts (in-memory) and final submissions (DB).
"""

import hashlib
import aiosqlite
import logging
from ..config import settings

logger = logging.getLogger("core.submission")


async def check_both_submitted(team_id: str, phase: str) -> dict | None:
    """
    Check whether BOTH players in the team have a final submission
    for the given phase (each for their own assigned problem).

    Returns a dict {player_id: code} for both players if both submitted,
    or None if any player hasn't submitted yet.
    
    Key insight: Player 1 submits for p001, Player 2 submits for p002.
    They submit for DIFFERENT problem_ids — so we use team_id as the
    common key and check each player individually.
    """
    async with aiosqlite.connect(settings.database_path, timeout=15.0) as db:
        # Fetch all players in this team (ordered by slot)
        async with db.execute(
            "SELECT id, player_slot FROM players WHERE team_id = ? ORDER BY player_slot",
            (team_id,)
        ) as cursor:
            player_rows = await cursor.fetchall()

        if len(player_rows) < 2:
            logger.info(f"[SWAP] Team {team_id}: less than 2 players, cannot swap")
            return None

        pid1, pid2 = player_rows[0][0], player_rows[1][0]

        # Check if EACH player has submitted ANY final submission for this phase
        async with db.execute(
            """
            SELECT player_id, code, problem_id FROM submissions
            WHERE player_id IN (?, ?) AND phase = ? AND is_final = 1
            """,
            (pid1, pid2, phase)
        ) as cursor:
            rows = await cursor.fetchall()

    # Build map: player_id -> code
    submissions = {}
    for row in rows:
        submissions[row[0]] = row[1]

    submitted_A = pid1 in submissions
    submitted_B = pid2 in submissions

    # Debug logs (MANDATORY per user request)
    logger.info(f"[SWAP] Team: {team_id}")
    logger.info(f"[SWAP] Player {pid1} (slot 1) submitted: {submitted_A}")
    logger.info(f"[SWAP] Player {pid2} (slot 2) submitted: {submitted_B}")

    if not (submitted_A and submitted_B):
        logger.info(f"[SWAP] Team {team_id}: NOT ready (waiting for {'slot 2' if submitted_A else 'slot 1'})")
        return None

    logger.info(f"[SWAP] Team {team_id}: BOTH submitted! Ready to swap.")
    return submissions

# In-memory draft store
# Key: (player_id, problem_id) -> code
_DRAFTS: dict[tuple[int, str], str] = {}


def receive_draft(player_id: int, problem_id: str, code: str):
    """Store code in memory as the latest draft."""
    _DRAFTS[(player_id, problem_id)] = code


async def receive_final(player_id: int, problem_id: str, code: str, phase: str = "part_a") -> bool:
    """Store final code in DB with SHA-256 hash. Returns True if successful."""
    sha256_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
    try:
        async with aiosqlite.connect(settings.database_path, timeout=15.0) as db:
            await db.execute(
                """
                INSERT INTO submissions (player_id, problem_id, code, sha256_hash, phase, is_final)
                VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(player_id, problem_id, phase) DO UPDATE SET 
                    code=excluded.code,
                    sha256_hash=excluded.sha256_hash,
                    is_final=1
                """,
                (player_id, problem_id, code, sha256_hash, phase)
            )
            await db.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to save final submission for player {player_id}: {e}")
        return False


async def auto_submit_draft(player_id: int, problem_id: str, phase: str = "part_a") -> bool:
    """Fallback when timer locks and no final submit was received."""
    code = _DRAFTS.get((player_id, problem_id), "")
    return await receive_final(player_id, problem_id, code, phase)
