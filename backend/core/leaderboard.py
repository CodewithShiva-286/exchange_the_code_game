"""
leaderboard.py — leaderboard helpers built on top of existing team_scores data.

`team_scores.total_score` is already cumulative per round, so the leaderboard
uses the latest/highest cumulative total for each team rather than summing
historical rows again.
"""

import aiosqlite

from ..config import settings
from ..websocket.events import build_leaderboard_update
from ..websocket.manager import manager


async def get_leaderboard_data() -> list[dict]:
    """Return leaderboard rows sorted by current total score descending."""
    async with aiosqlite.connect(settings.database_path, timeout=15.0) as db:
        async with db.execute(
            """
            SELECT team_id, SUM(total_score) AS total_score
            FROM team_scores
            GROUP BY team_id
            ORDER BY total_score DESC, team_id ASC
            """
        ) as cursor:
            rows = await cursor.fetchall()

    return [
        {
            "team_id": row[0],
            "total_score": int(row[1] or 0),
        }
        for row in rows
    ]


async def broadcast_leaderboard_update() -> list[dict]:
    """Push the current leaderboard to the connected admin client, if any."""
    leaderboard = await get_leaderboard_data()
    await manager.send_to_admin(build_leaderboard_update(leaderboard))
    return leaderboard
