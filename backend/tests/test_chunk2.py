"""
test_chunk2.py — v2 WebSocket Infrastructure

Tests:
1. Player WS rejects invalid session token (accept→close 4001)
2. Player WS accepts valid token → CONNECTED
3. ASSIGNED sent individually to each player when both connect
   - Slot 1 player receives problem at position 1
   - Slot 2 player receives problem at position 2
   - Each receives only their own problem (not both)
4. PING → PONG
5. Admin WS rejects invalid key
6. Admin WS accepts valid key → ADMIN_CONNECTED
7. Admin PING → PONG
8. Unknown event → ERROR
9. Chunk 1 REST regression
"""

import pytest
import pytest_asyncio
import os
import aiosqlite
from httpx import AsyncClient, ASGITransport
from starlette.testclient import TestClient

from backend.database import settings, init_db
from backend.problems.problem_loader import load_problems, seed_problems_to_db, get_all_problems
from backend.websocket.manager import manager

settings.database_path = "test_exchange_ws.db"

from backend.main import app  # noqa: E402


# ─── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session", autouse=True)
async def init_test_db():
    """Create DB + seed problems once for all tests in the session."""
    for suffix in ("", "-wal", "-shm"):
        path = settings.database_path + suffix
        if os.path.exists(path):
            try:
                os.remove(path)
            except PermissionError:
                pass

    await init_db()
    load_problems()
    await seed_problems_to_db()
    yield

    for suffix in ("", "-wal", "-shm"):
        path = settings.database_path + suffix
        try:
            if os.path.exists(path):
                os.remove(path)
        except PermissionError:
            pass


@pytest_asyncio.fixture(autouse=True)
async def reset_state():
    """Clear all data tables (keep schema + problems) and reset WS manager between tests."""
    async with aiosqlite.connect(settings.database_path, timeout=15.0) as db:
        await db.execute("DELETE FROM execution_results")
        await db.execute("DELETE FROM submissions")
        await db.execute("DELETE FROM players")
        await db.execute("DELETE FROM group_problems")
        await db.execute("DELETE FROM groups")
        await db.execute("DELETE FROM teams")
        await db.commit()

    await seed_problems_to_db()

    # Reset WS manager in-memory state
    manager._teams.clear()
    manager._admin_ws = None
    manager._assigned_sent.clear()

    yield


@pytest_asyncio.fixture
async def http_client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver"
    ) as c:
        yield c


# ─── Helpers ───────────────────────────────────────────────────────────────────

async def _create_team_with_group(http_client, team_id="WS-TEAM-01", group_id="WS-GROUP-01"):
    """Create team + create group + assign group + join 2 players. Returns (p1, p2) dicts."""
    await http_client.post("/admin/create-team", json={"team_id": team_id})

    pids = list(get_all_problems().keys())
    await http_client.post(
        "/admin/create-group",
        json={"group_id": group_id, "problem_ids": [pids[0], pids[1]]}
    )
    await http_client.post(
        "/admin/assign-group",
        json={"team_id": team_id, "group_id": group_id}
    )

    r1 = await http_client.post("/join", json={"team_id": team_id, "name": "Alice"})
    r2 = await http_client.post("/join", json={"team_id": team_id, "name": "Bob"})
    return r1.json(), r2.json()


# ─── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_player_ws_rejects_invalid_token(http_client):
    """Invalid token → server accepts then closes with code 4001."""
    p1, _ = await _create_team_with_group(http_client)

    with TestClient(app) as tc:
        with tc.websocket_connect(
            f"/ws/{p1['team_id']}/{p1['player_id']}?token=INVALID-TOKEN"
        ) as ws:
            with pytest.raises(Exception):
                ws.receive_json()


@pytest.mark.asyncio
async def test_player_ws_accepts_valid_token(http_client):
    """Valid token → CONNECTED event with correct player/team info."""
    p1, _ = await _create_team_with_group(http_client, "VALID-01", "VGRP-01")

    with TestClient(app) as tc:
        with tc.websocket_connect(
            f"/ws/{p1['team_id']}/{p1['player_id']}?token={p1['session_token']}"
        ) as ws:
            msg = ws.receive_json()
            assert msg["event"] == "CONNECTED"
            assert msg["data"]["player_id"] == p1["player_id"]
            assert msg["data"]["team_id"] == p1["team_id"]


@pytest.mark.asyncio
async def test_assigned_sent_to_both_players_on_connect(http_client):
    """
    When both players WS-connect:
    - Each receives ASSIGNED with their OWN problem
    - Slot 1 player gets position 1 problem
    - Slot 2 player gets position 2 problem
    - Each gets the partner's problem TITLE only (not details)
    """
    p1, p2 = await _create_team_with_group(http_client, "BOTH-01", "BGRP-01")
    pids = list(get_all_problems().keys())
    pos1_id = pids[0]  # assigned to position 1 (player_slot 1)
    pos2_id = pids[1]  # assigned to position 2 (player_slot 2)

    with TestClient(app) as tc:
        with tc.websocket_connect(
            f"/ws/{p1['team_id']}/{p1['player_id']}?token={p1['session_token']}"
        ) as ws1:
            assert ws1.receive_json()["event"] == "CONNECTED"

            with tc.websocket_connect(
                f"/ws/{p2['team_id']}/{p2['player_id']}?token={p2['session_token']}"
            ) as ws2:
                assert ws2.receive_json()["event"] == "CONNECTED"

                # Slot 2 (p2) gets ASSIGNED with position 2 problem
                msg2 = ws2.receive_json()
                assert msg2["event"] == "ASSIGNED"
                assert msg2["data"]["player_slot"] == 2
                assert msg2["data"]["assigned_problem"]["id"] == pos2_id
                assert "part_a_prompt" in msg2["data"]["assigned_problem"]
                # part_b_prompt must NOT be in assigned problem
                assert "part_b_prompt" not in msg2["data"]["assigned_problem"]

                # Slot 1 (p1) also gets ASSIGNED with position 1 problem
                msg1 = ws1.receive_json()
                assert msg1["event"] == "ASSIGNED"
                assert msg1["data"]["player_slot"] == 1
                assert msg1["data"]["assigned_problem"]["id"] == pos1_id

                # Players receive partner's title (not full details)
                assert "partner_problem_title" in msg1["data"]
                assert "partner_problem_title" in msg2["data"]
                
                # p1 should also get a PARTNER_JOINED event because p2 joined
                msg1_partner = ws1.receive_json()
                assert msg1_partner["event"] == "PARTNER_JOINED"


@pytest.mark.asyncio
async def test_assigned_fires_only_once(http_client):
    """ASSIGNED must not be re-sent on reconnect (guarded by _assigned_sent)."""
    p1, p2 = await _create_team_with_group(http_client, "ONCE-01", "OGRP-01")

    # First full connection cycle
    with TestClient(app) as tc:
        with tc.websocket_connect(
            f"/ws/{p1['team_id']}/{p1['player_id']}?token={p1['session_token']}"
        ) as ws1:
            ws1.receive_json()  # CONNECTED

            with tc.websocket_connect(
                f"/ws/{p2['team_id']}/{p2['player_id']}?token={p2['session_token']}"
            ) as ws2:
                ws2.receive_json()  # CONNECTED
                ws2.receive_json()  # ASSIGNED
                ws1.receive_json()  # ASSIGNED
                ws1.receive_json()  # PARTNER_JOINED

                # p1 reconnects WHILE ws2 is still active (this ensures the team is still full)
                with tc.websocket_connect(
                    f"/ws/{p1['team_id']}/{p1['player_id']}?token={p1['session_token']}"
                ) as ws1_again:
                    c_msg = ws1_again.receive_json()
                    assert c_msg["event"] == "CONNECTED"
                    restore_msg = ws1_again.receive_json()
                    assert restore_msg["event"] == "SESSION_RESTORE"
                    
                    # The old ws1 will be disconnected by the server because of duplicate connection
                    with pytest.raises(Exception):
                        ws1.receive_json()


@pytest.mark.asyncio
async def test_ping_pong(http_client):
    """PING → PONG heartbeat."""
    p1, _ = await _create_team_with_group(http_client, "PING-01", "PGRP-01")

    with TestClient(app) as tc:
        with tc.websocket_connect(
            f"/ws/{p1['team_id']}/{p1['player_id']}?token={p1['session_token']}"
        ) as ws:
            ws.receive_json()  # CONNECTED
            ws.send_json({"event": "PING"})
            msg = ws.receive_json()
            assert msg["event"] == "PONG"


@pytest.mark.asyncio
async def test_admin_ws_rejects_invalid_key(http_client):
    """Admin WS with wrong key → rejected."""
    with TestClient(app) as tc:
        with pytest.raises(Exception):
            with tc.websocket_connect("/ws/admin?key=WRONG-KEY"):
                pass


@pytest.mark.asyncio
async def test_admin_ws_accepts_valid_key(http_client):
    """Admin WS with correct key → ADMIN_CONNECTED."""
    with TestClient(app) as tc:
        with tc.websocket_connect(f"/ws/admin?key={settings.admin_key}") as ws:
            msg = ws.receive_json()
            assert msg["event"] == "ADMIN_CONNECTED"
            assert msg["data"]["status"] == "ok"


@pytest.mark.asyncio
async def test_admin_ping_pong(http_client):
    """Admin WS PING → PONG."""
    with TestClient(app) as tc:
        with tc.websocket_connect(f"/ws/admin?key={settings.admin_key}") as ws:
            ws.receive_json()  # ADMIN_CONNECTED
            ws.send_json({"event": "PING"})
            assert ws.receive_json()["event"] == "PONG"


@pytest.mark.asyncio
async def test_unknown_event_returns_error(http_client):
    """Unrecognized event → ERROR."""
    p1, _ = await _create_team_with_group(http_client, "UNK-01", "UGRP-01")

    with TestClient(app) as tc:
        with tc.websocket_connect(
            f"/ws/{p1['team_id']}/{p1['player_id']}?token={p1['session_token']}"
        ) as ws:
            ws.receive_json()  # CONNECTED
            ws.send_json({"event": "SOME_RANDOM_EVENT"})
            msg = ws.receive_json()
            assert msg["event"] == "ERROR"
            assert "not handled" in msg["data"]["message"]


@pytest.mark.asyncio
async def test_chunk1_regression(http_client):
    """Core REST endpoints still work after WS integration."""
    assert (await http_client.get("/health")).status_code == 200

    await http_client.post("/admin/create-team", json={"team_id": "REG-01"})
    pids = list(get_all_problems().keys())
    r_grp = await http_client.post(
        "/admin/create-group",
        json={"group_id": "REG-GRP", "problem_ids": [pids[0], pids[1]]}
    )
    assert r_grp.status_code == 200

    r_assign = await http_client.post(
        "/admin/assign-group",
        json={"team_id": "REG-01", "group_id": "REG-GRP"}
    )
    assert r_assign.status_code == 200

    r_join = await http_client.post("/join", json={"team_id": "REG-01", "name": "Test"})
    assert r_join.status_code == 200
    data = r_join.json()
    assert "session_token" in data
    assert data["player_slot"] == 1
