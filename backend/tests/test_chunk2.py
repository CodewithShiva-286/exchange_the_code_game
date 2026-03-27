"""
Chunk 2 tests — WebSocket infrastructure.

Tests:
1. Player WS rejects invalid session token
2. Player WS accepts valid session token and sends CONNECTED
3. SHOW_PROBLEMS auto-triggers when both players connect
4. PING → PONG works
5. Admin WS rejects invalid admin key
6. Admin WS accepts valid admin key
7. Unknown event returns ERROR
8. Chunk 1 REST regression check
"""

import pytest
import pytest_asyncio
import os
from httpx import AsyncClient, ASGITransport
from starlette.testclient import TestClient

from backend.database import settings, init_db
from backend.problems.problem_loader import load_problems, seed_problems_to_db, get_all_problems
from backend.websocket.manager import manager

settings.database_path = "test_exchange_ws.db"

from backend.main import app  # noqa: E402

# ─── Session-scoped DB ────────────────────────────────────────────────────────
# Create DB once, clear tables between tests to avoid Windows file-lock issues.

@pytest_asyncio.fixture(scope="session", autouse=True)
async def init_test_db():
    """Create the DB and seed problems once for all tests."""
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
    """Clean DB rows and manager state between tests."""
    import aiosqlite
    async with aiosqlite.connect(settings.database_path) as db:
        # Clear data tables but keep schema and problems
        await db.execute("DELETE FROM selection_log")
        await db.execute("DELETE FROM execution_results")
        await db.execute("DELETE FROM submissions")
        await db.execute("DELETE FROM players")
        await db.execute("DELETE FROM team_problems")
        await db.execute("DELETE FROM teams")
        await db.commit()

    # Re-seed problems (FK targets)
    await seed_problems_to_db()

    # Reset WS manager
    manager._teams.clear()
    manager._admin_ws = None
    manager._problems_shown.clear()

    yield


@pytest_asyncio.fixture
async def http_client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver"
    ) as c:
        yield c


async def _create_team_and_players(http_client, team_id="WS-TEAM-01"):
    """Helper: create a team, assign problems, join 2 players."""
    await http_client.post("/admin/create-team", json={"team_id": team_id})
    pids = list(get_all_problems().keys())
    await http_client.post(
        "/admin/assign-problems",
        json={"team_id": team_id, "problem_ids": [pids[0], pids[1]]}
    )
    r1 = await http_client.post("/join", json={"team_id": team_id, "name": "Alice"})
    r2 = await http_client.post("/join", json={"team_id": team_id, "name": "Bob"})
    return r1.json(), r2.json()


# ─── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_player_ws_rejects_invalid_token(http_client):
    """WS connection with a bad token → accepted then immediately closed (4001)."""
    p1, _ = await _create_team_and_players(http_client)

    with TestClient(app) as tc:
        with tc.websocket_connect(
            f"/ws/{p1['team_id']}/{p1['player_id']}?token=INVALID-TOKEN"
        ) as ws:
            # The server accepts then immediately closes with code 4001
            # Starlette TestClient surfaces this as a disconnect
            with pytest.raises(Exception):
                ws.receive_json()


@pytest.mark.asyncio
async def test_player_ws_accepts_valid_token(http_client):
    """WS connection with a valid token → CONNECTED event back."""
    p1, _ = await _create_team_and_players(http_client, "VALID-01")

    with TestClient(app) as tc:
        with tc.websocket_connect(
            f"/ws/{p1['team_id']}/{p1['player_id']}?token={p1['session_token']}"
        ) as ws:
            msg = ws.receive_json()
            assert msg["event"] == "CONNECTED"
            assert msg["data"]["player_id"] == p1["player_id"]
            assert msg["data"]["team_id"] == p1["team_id"]


@pytest.mark.asyncio
async def test_show_problems_on_both_connect(http_client):
    """When both players WS-connect, both receive SHOW_PROBLEMS."""
    p1, p2 = await _create_team_and_players(http_client, "BOTH-01")

    with TestClient(app) as tc:
        with tc.websocket_connect(
            f"/ws/{p1['team_id']}/{p1['player_id']}?token={p1['session_token']}"
        ) as ws1:
            msg1 = ws1.receive_json()
            assert msg1["event"] == "CONNECTED"

            with tc.websocket_connect(
                f"/ws/{p2['team_id']}/{p2['player_id']}?token={p2['session_token']}"
            ) as ws2:
                msg2 = ws2.receive_json()
                assert msg2["event"] == "CONNECTED"

                # Player 2 gets SHOW_PROBLEMS
                msg2_show = ws2.receive_json()
                assert msg2_show["event"] == "SHOW_PROBLEMS"
                assert len(msg2_show["data"]["problems"]) == 2

                # Player 1 also gets SHOW_PROBLEMS
                msg1_show = ws1.receive_json()
                assert msg1_show["event"] == "SHOW_PROBLEMS"
                assert len(msg1_show["data"]["problems"]) == 2


@pytest.mark.asyncio
async def test_ping_pong(http_client):
    """Sending PING → receive PONG."""
    p1, _ = await _create_team_and_players(http_client, "PING-01")

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
            msg = ws.receive_json()
            assert msg["event"] == "PONG"


@pytest.mark.asyncio
async def test_unknown_event_returns_error(http_client):
    """Unrecognized event → ERROR response."""
    p1, _ = await _create_team_and_players(http_client, "UNK-01")

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
async def test_chunk1_no_regression(http_client):
    """Chunk 1 REST endpoints still work after WS integration."""
    res = await http_client.get("/health")
    assert res.status_code == 200

    await http_client.post("/admin/create-team", json={"team_id": "REG-01"})
    pids = list(get_all_problems().keys())
    res = await http_client.post(
        "/admin/assign-problems",
        json={"team_id": "REG-01", "problem_ids": [pids[0], pids[1]]}
    )
    assert res.status_code == 200

    res = await http_client.post("/join", json={"team_id": "REG-01", "name": "Test"})
    assert res.status_code == 200
    assert "session_token" in res.json()
