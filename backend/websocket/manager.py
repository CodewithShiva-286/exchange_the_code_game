"""
ConnectionManager — team-based WebSocket registry.
Validates session tokens on connect. Provides broadcast-to-team and send-to-player.

Fixes applied:
- Duplicate connections: old WS is closed before new one is accepted
- SHOW_PROBLEMS: tracked per team, fires only once
- Disconnect cleanup: only removes the WS if it matches the stored reference
- Stale connection prevention: replaced connections are force-closed
"""

import logging
import aiosqlite
from fastapi import WebSocket
from ..config import settings

logger = logging.getLogger("ws.manager")


class ConnectionManager:
    """
    Manages active WebSocket connections indexed by team_id → player_id.
    Also tracks the admin connection separately.
    """

    def __init__(self):
        # { team_id: { player_id: WebSocket } }
        self._teams: dict[str, dict[int, WebSocket]] = {}
        self._admin_ws: WebSocket | None = None
        # Track which teams have already received SHOW_PROBLEMS
        self._problems_shown: set[str] = set()

    # ── Session Validation ─────────────────────────────────────────────────

    async def validate_session(self, team_id: str, player_id: int, token: str) -> bool:
        """
        Check that (player_id, team_id, session_token) exist together in the DB.
        Called on every WS connect attempt. Returns False → caller must reject.
        """
        async with aiosqlite.connect(settings.database_path) as db:
            async with db.execute(
                "SELECT id FROM players WHERE id = ? AND team_id = ? AND session_token = ?",
                (player_id, team_id, token)
            ) as cursor:
                return await cursor.fetchone() is not None

    # ── Player Connections ─────────────────────────────────────────────────

    async def connect_player(self, team_id: str, player_id: int, ws: WebSocket) -> bool:
        """
        Accept and register a player WS connection.
        If the player already has an active connection, the OLD one is closed
        gracefully before the new one is stored (prevents ghost connections).
        Returns True if this is a reconnect (old connection existed).
        """
        # Check for existing connection BEFORE accepting the new one
        is_reconnect = False
        if team_id in self._teams and player_id in self._teams[team_id]:
            old_ws = self._teams[team_id][player_id]
            is_reconnect = True
            try:
                await old_ws.close(code=4010, reason="Replaced by new connection")
            except Exception:
                pass  # Old socket may already be dead

        await ws.accept()

        if team_id not in self._teams:
            self._teams[team_id] = {}
        self._teams[team_id][player_id] = ws

        # Update connection status in DB
        async with aiosqlite.connect(settings.database_path) as db:
            await db.execute(
                "UPDATE players SET connection_status = 'online' WHERE id = ? AND team_id = ?",
                (player_id, team_id)
            )
            await db.commit()

        logger.info(f"Player {player_id} {'re' if is_reconnect else ''}connected to team {team_id}")
        return is_reconnect

    async def disconnect_player(self, team_id: str, player_id: int, ws: WebSocket = None):
        """
        Remove a player from the registry.
        If `ws` is provided, only remove if it matches the stored reference
        (prevents a stale/replaced connection from removing the fresh one).
        """
        if team_id in self._teams and player_id in self._teams[team_id]:
            stored_ws = self._teams[team_id][player_id]
            # If ws is given but doesn't match stored → this is a stale disconnect, skip
            if ws is not None and stored_ws is not ws:
                logger.debug(f"Ignoring stale disconnect for player {player_id} in team {team_id}")
                return

            del self._teams[team_id][player_id]
            if not self._teams[team_id]:
                del self._teams[team_id]

        # Update connection status in DB
        async with aiosqlite.connect(settings.database_path) as db:
            await db.execute(
                "UPDATE players SET connection_status = 'offline' WHERE id = ? AND team_id = ?",
                (player_id, team_id)
            )
            await db.commit()

        logger.info(f"Player {player_id} disconnected from team {team_id}")

    # ── Admin Connection ───────────────────────────────────────────────────

    async def connect_admin(self, ws: WebSocket):
        # Close existing admin connection if any
        if self._admin_ws:
            try:
                await self._admin_ws.close(code=4010, reason="Replaced by new admin connection")
            except Exception:
                pass
        await ws.accept()
        self._admin_ws = ws
        logger.info("Admin connected")

    async def disconnect_admin(self):
        self._admin_ws = None
        logger.info("Admin disconnected")

    # ── SHOW_PROBLEMS Tracker ──────────────────────────────────────────────

    def mark_problems_shown(self, team_id: str):
        """Mark that SHOW_PROBLEMS has been sent for this team."""
        self._problems_shown.add(team_id)

    def should_show_problems(self, team_id: str) -> bool:
        """Returns True only if SHOW_PROBLEMS has NOT been sent yet for this team."""
        return team_id not in self._problems_shown

    # ── Queries ────────────────────────────────────────────────────────────

    def get_team_connections(self, team_id: str) -> dict[int, WebSocket]:
        return self._teams.get(team_id, {})

    def get_team_player_count(self, team_id: str) -> int:
        return len(self._teams.get(team_id, {}))

    def is_team_full(self, team_id: str) -> bool:
        """Both players in the team are connected via WS."""
        return self.get_team_player_count(team_id) == 2

    def is_player_connected(self, team_id: str, player_id: int) -> bool:
        return player_id in self._teams.get(team_id, {})

    # ── Sending ────────────────────────────────────────────────────────────

    async def send_to_player(self, team_id: str, player_id: int, message: dict):
        conns = self._teams.get(team_id, {})
        ws = conns.get(player_id)
        if ws:
            try:
                await ws.send_json(message)
            except Exception:
                logger.warning(f"Failed to send to player {player_id} in team {team_id}")

    async def broadcast_to_team(self, team_id: str, message: dict, exclude_player: int = None):
        conns = self._teams.get(team_id, {})
        for pid, ws in conns.items():
            if pid == exclude_player:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                logger.warning(f"Failed to broadcast to player {pid} in team {team_id}")

    async def send_to_admin(self, message: dict):
        if self._admin_ws:
            try:
                await self._admin_ws.send_json(message)
            except Exception:
                logger.warning("Failed to send to admin")


# Singleton instance used across the app
manager = ConnectionManager()
