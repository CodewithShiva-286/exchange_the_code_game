"""
test_chunk7_strict.py
Strict validation tests for Chunk 7: Admin Dashboard & Team Creation lifecycle.
"""

import pytest
import pytest_asyncio
import os
import asyncio
from httpx import AsyncClient, ASGITransport

from backend.database import settings, init_db
from backend.problems.problem_loader import load_problems, seed_problems_to_db, get_all_problems
from backend.websocket.manager import manager

# Override DB path BEFORE importing app
settings.database_path = "test_exchange_chunk7.db"

from backend.main import app  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
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
    # Reset manager connection state to avoid pollution
    manager._teams.clear()
    manager._assigned_sent.clear()
    yield

    for suffix in ("", "-wal", "-shm"):
        path = settings.database_path + suffix
        if os.path.exists(path):
            try:
                os.remove(path)
            except PermissionError:
                pass


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver"
    ) as c:
        yield c

async def _create_group(client, group_id="GROUP-A"):
    pids = list(get_all_problems().keys())
    return await client.post(
        "/admin/create-group",
        json={"group_id": group_id, "problem_ids": [pids[0], pids[1]]}
    )

# ─── 1. TEAM CREATION TESTS ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_team_sequential_ids(client):
    team_ids = []
    for _ in range(5):
        res = await client.post("/admin/create-team", json={})
        assert res.status_code == 200
        team_ids.append(res.json()["team_id"])
    
    assert team_ids == ["TEAM-1", "TEAM-2", "TEAM-3", "TEAM-4", "TEAM-5"]

@pytest.mark.asyncio
async def test_create_team_empty_payload(client):
    res = await client.post("/admin/create-team", json={})
    assert res.status_code == 200
    assert res.json()["team_id"] == "TEAM-1"

@pytest.mark.asyncio
async def test_create_team_concurrent_requests(client):
    tasks = [client.post("/admin/create-team", json={}) for _ in range(10)]
    responses = await asyncio.gather(*tasks)
    
    team_ids = set()
    for res in responses:
        assert res.status_code == 200
        team_ids.add(res.json()["team_id"])
        
    assert len(team_ids) == 10
    expected_ids = {f"TEAM-{i}" for i in range(1, 11)}
    assert team_ids == expected_ids

# ─── 2. GET /admin/teams VALIDATION ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_admin_teams_structure(client):
    # Create team
    await client.post("/admin/create-team", json={})
    # Join 1 player to verify players array
    await client.post("/join", json={"team_id": "TEAM-1", "name": "Bob"})
    
    res = await client.get("/admin/teams")
    assert res.status_code == 200
    data = res.json()
    
    assert len(data) == 1
    team = data[0]
    assert team["team_id"] == "TEAM-1"
    assert "group_id" in team
    assert "players" in team
    assert len(team["players"]) == 1
    
    player = team["players"][0]
    assert player["slot"] == 1
    assert "connected" in player
    assert player["name"] == "Bob"

@pytest.mark.asyncio
async def test_empty_teams_state(client):
    res = await client.get("/admin/teams")
    assert res.status_code == 200
    assert res.json() == []

# ─── 3. PLAYER JOIN -> SLOT MAPPING ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_player_join_slot_assignment(client):
    await client.post("/admin/create-team", json={})
    
    res1 = await client.post("/join", json={"team_id": "TEAM-1", "name": "Alice"})
    res2 = await client.post("/join", json={"team_id": "TEAM-1", "name": "Bob"})
    
    assert res1.json()["player_slot"] == 1
    assert res2.json()["player_slot"] == 2

@pytest.mark.asyncio
async def test_player_join_overflow(client):
    await client.post("/admin/create-team", json={})
    await client.post("/join", json={"team_id": "TEAM-1", "name": "P1"})
    await client.post("/join", json={"team_id": "TEAM-1", "name": "P2"})
    
    res = await client.post("/join", json={"team_id": "TEAM-1", "name": "P3"})
    assert res.status_code == 400

@pytest.mark.asyncio
async def test_player_reflected_in_admin_teams(client):
    await client.post("/admin/create-team", json={})
    await client.post("/join", json={"team_id": "TEAM-1", "name": "Alice"})
    
    res = await client.get("/admin/teams")
    team = res.json()[0]
    assert len(team["players"]) == 1
    assert team["players"][0]["name"] == "Alice"
    assert team["players"][0]["slot"] == 1

# ─── 4. CONNECTION STATUS TESTS ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_connection_status_updates(client):
    await client.post("/admin/create-team", json={})
    join_res = await client.post("/join", json={"team_id": "TEAM-1", "name": "Alice"})
    token = join_res.json()["session_token"]
    p_id = join_res.json()["player_id"]
    
    # Check disconnected state
    res1 = await client.get("/admin/teams")
    assert res1.json()[0]["players"][0]["connected"] is False
    
    # Establish WS connection
    from fastapi.testclient import TestClient
    from backend.main import app as sync_app
    sync_client = TestClient(sync_app)
    
    with sync_client.websocket_connect(f"/ws/player/{p_id}?token={token}") as websocket:
        # Check connected state
        res2 = await client.get("/admin/teams")
        assert res2.json()[0]["players"][0]["connected"] is True
        
    # Check disconnected state again
    res3 = await client.get("/admin/teams")
    assert res3.json()[0]["players"][0]["connected"] is False

# ─── 5. GROUP ASSIGNMENT TESTS ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_assign_group_to_team(client):
    await client.post("/admin/create-team", json={})
    await _create_group(client, "GROUP-A")
    
    res = await client.post("/admin/assign-group", json={"team_id": "TEAM-1", "group_id": "GROUP-A"})
    assert res.status_code == 200
    
    teams = await client.get("/admin/teams")
    assert teams.json()[0]["group_id"] == "GROUP-A"

@pytest.mark.asyncio
async def test_reassign_group(client):
    await client.post("/admin/create-team", json={})
    await _create_group(client, "GROUP-A")
    await client.post("/admin/create-group", json={"group_id": "GROUP-B", "problem_ids": ["p002", "p003"]})
    
    res1 = await client.post("/admin/assign-group", json={"team_id": "TEAM-1", "group_id": "GROUP-A"})
    assert res1.status_code == 200
    res2 = await client.post("/admin/assign-group", json={"team_id": "TEAM-1", "group_id": "GROUP-B"})
    
    # If the backend fails to reassign, this assertion will catch that it returned non-200
    if res2.status_code != 200:
        pytest.fail(f"Reassignment failed: {res2.json()}")
    
    teams = await client.get("/admin/teams")
    assert teams.json()[0]["group_id"] == "GROUP-B"

@pytest.mark.asyncio
async def test_assign_group_before_players(client):
    await client.post("/admin/create-team", json={})
    await _create_group(client, "GROUP-A")
    
    res = await client.post("/admin/assign-group", json={"team_id": "TEAM-1", "group_id": "GROUP-A"})
    assert res.status_code == 200

# ─── 6. START FLOW VALIDATION ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_start_without_ready_teams(client):
    await client.post("/admin/create-team", json={})
    res = await client.post("/admin/start")
    assert res.status_code == 400
    assert "Following teams not ready: TEAM-1" in res.json()["detail"]

@pytest.mark.asyncio
async def test_start_with_ready_team(client):
    await client.post("/admin/create-team", json={})
    await _create_group(client, "GROUP-A")
    await client.post("/admin/assign-group", json={"team_id": "TEAM-1", "group_id": "GROUP-A"})
    
    j1 = await client.post("/join", json={"team_id": "TEAM-1", "name": "P1"})
    j2 = await client.post("/join", json={"team_id": "TEAM-1", "name": "P2"})
    t1 = j1.json()["session_token"]
    t2 = j2.json()["session_token"]
    pid1 = j1.json()["player_id"]
    pid2 = j2.json()["player_id"]
    
    from fastapi.testclient import TestClient
    from backend.main import app as sync_app
    sync_client = TestClient(sync_app)
    
    with sync_client.websocket_connect(f"/ws/player/{pid1}?token={t1}") as ws1:
        with sync_client.websocket_connect(f"/ws/player/{pid2}?token={t2}") as ws2:
            res = await client.post("/admin/start")
            if res.status_code != 200:
                pytest.fail(f"Start failed: {res.json()}")
            assert res.status_code == 200

# ─── 7. EDGE CASES ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_duplicate_team_creation_race(client):
    await test_create_team_concurrent_requests(client)

@pytest.mark.asyncio
async def test_invalid_team_join(client):
    res = await client.post("/join", json={"team_id": "NON_EXISTENT", "name": "P1"})
    assert res.status_code == 404

@pytest.mark.asyncio
async def test_api_resilience(client):
    # Invalid payloads should not crash the server but return 422
    res1 = await client.post("/admin/assign-group", json={})
    assert res1.status_code == 422
