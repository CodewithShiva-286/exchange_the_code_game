"""
submission_handler.py — v2 Submission Handler (Chunk 4)

Handles storing drafts (in-memory) and final submissions (DB).
"""

import hashlib
import aiosqlite
import logging
from ..config import settings

logger = logging.getLogger("core.submission")

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
