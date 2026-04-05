"""
test_chunk1.py — v2 Backend Foundation

Tests the REST API endpoints with the new group-based schema:
- Team creation
- Group creation (2 problems at positions 1 and 2)
- Group assignment to team
- Player join with atomic slot assignment
- 3rd player rejected
- Unique session tokens
- Problem detail endpoint

REMOVED from v1:
- test_assign_exactly_two_problems (assign-problems endpoint gone)
- test_fetch_team_problems (GET /team/{team_id}/problems removed)
"""

import pytest
import pytest_asyncio
import os
import asyncio
from httpx import AsyncClient, ASGITransport
from backend.database import settings, init_db
from backend.problems.problem_loader import load_problems, seed_problems_to_db, get_all_problems

# Override DB path — must happen before app import
settings.database_path = "test_exchange.db"

from backend.main import app  # noqa: E402


# ─── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Fresh DB + problem cache for every test."""
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


# ─── Helpers ───────────────────────────────────────────────────────────────────

async def _create_group(client, group_id="GROUP-A"):
    """Helper: create a group with the first 2 loaded problems."""
    pids = list(get_all_problems().keys())
    return await client.post(
        "/admin/create-group",
        json={"group_id": group_id, "problem_ids": [pids[0], pids[1]]}
    )


async def _setup_team_with_group(client, team_id="T-01", group_id="GROUP-A"):
    """Helper: create team + create group + assign group."""
    await client.post("/admin/create-team", json={"team_id": team_id})
    await _create_group(client, group_id)
    await client.post(
        "/admin/assign-group",
        json={"team_id": team_id, "group_id": group_id}
    )


# ─── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_check(client):
    res = await client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_create_team_success(client):
    res = await client.post("/admin/create-team", json={"team_id": "ALPHA-01"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["team_id"] == "ALPHA-01"


@pytest.mark.asyncio
async def test_create_team_duplicate_rejected(client):
    await client.post("/admin/create-team", json={"team_id": "DUP-01"})
    res = await client.post("/admin/create-team", json={"team_id": "DUP-01"})
    assert res.status_code == 400
    assert "already exists" in res.json()["detail"]


@pytest.mark.asyncio
async def test_create_group_success(client):
    res = await _create_group(client, "GROUP-B")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["group_id"] == "GROUP-B"


@pytest.mark.asyncio
async def test_create_group_rejects_duplicate_problems(client):
    """Both positions must have different problems."""
    pids = list(get_all_problems().keys())
    res = await client.post(
        "/admin/create-group",
        json={"group_id": "GROUP-C", "problem_ids": [pids[0], pids[0]]}
    )
    assert res.status_code == 400
    assert "unique" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_group_rejects_duplicate_group_id(client):
    await _create_group(client, "GROUP-D")
    res = await _create_group(client, "GROUP-D")
    assert res.status_code == 400
    assert "already exists" in res.json()["detail"]


@pytest.mark.asyncio
async def test_create_group_rejects_single_problem(client):
    """Pydantic min_length=2 enforces exactly 2 problem IDs."""
    pids = list(get_all_problems().keys())
    res = await client.post(
        "/admin/create-group",
        json={"group_id": "GROUP-E", "problem_ids": [pids[0]]}
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_assign_group_success(client):
    await client.post("/admin/create-team", json={"team_id": "T-ASSIGN-01"})
    await _create_group(client, "GROUP-F")
    res = await client.post(
        "/admin/assign-group",
        json={"team_id": "T-ASSIGN-01", "group_id": "GROUP-F"}
    )
    assert res.status_code == 200
    assert res.json()["status"] == "success"


@pytest.mark.asyncio
async def test_assign_group_rejects_unknown_team(client):
    await _create_group(client, "GROUP-G")
    res = await client.post(
        "/admin/assign-group",
        json={"team_id": "NO-SUCH-TEAM", "group_id": "GROUP-G"}
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_assign_group_rejects_unknown_group(client):
    await client.post("/admin/create-team", json={"team_id": "T-ASSIGN-02"})
    res = await client.post(
        "/admin/assign-group",
        json={"team_id": "T-ASSIGN-02", "group_id": "NO-SUCH-GROUP"}
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_assign_group_rejects_reassignment(client):
    """A team cannot have its group reassigned once set."""
    await client.post("/admin/create-team", json={"team_id": "T-REASSIGN"})
    await _create_group(client, "GROUP-H")
    await client.post(
        "/admin/assign-group",
        json={"team_id": "T-REASSIGN", "group_id": "GROUP-H"}
    )
    pids = list(get_all_problems().keys())
    await client.post(
        "/admin/create-group",
        json={"group_id": "GROUP-I", "problem_ids": [pids[1], pids[0]]}
    )
    res = await client.post(
        "/admin/assign-group",
        json={"team_id": "T-REASSIGN", "group_id": "GROUP-I"}
    )
    assert res.status_code == 400
    assert "already has a group" in res.json()["detail"]


@pytest.mark.asyncio
async def test_player_join_success_slot_1(client):
    """First player to join gets slot 1."""
    await client.post("/admin/create-team", json={"team_id": "JOIN-01"})
    res = await client.post("/join", json={"team_id": "JOIN-01", "name": "Alice"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["player_slot"] == 1
    assert "session_token" in data
    assert isinstance(data["player_id"], int)


@pytest.mark.asyncio
async def test_player_join_success_slot_2(client):
    """Second player to join gets slot 2."""
    await client.post("/admin/create-team", json={"team_id": "JOIN-02"})
    await client.post("/join", json={"team_id": "JOIN-02", "name": "Alice"})
    res = await client.post("/join", json={"team_id": "JOIN-02", "name": "Bob"})
    assert res.status_code == 200
    assert res.json()["player_slot"] == 2


@pytest.mark.asyncio
async def test_player_join_invalid_team_rejected(client):
    res = await client.post("/join", json={"team_id": "NO-TEAM", "name": "Ghost"})
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_player_join_max_two_per_team(client):
    """3rd join attempt must be rejected."""
    await client.post("/admin/create-team", json={"team_id": "FULL-01"})
    await client.post("/join", json={"team_id": "FULL-01", "name": "Alice"})
    await client.post("/join", json={"team_id": "FULL-01", "name": "Bob"})
    res = await client.post("/join", json={"team_id": "FULL-01", "name": "Charlie"})
    assert res.status_code == 400
    assert "full" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_player_unique_session_tokens(client):
    await client.post("/admin/create-team", json={"team_id": "TOKEN-01"})
    r1 = await client.post("/join", json={"team_id": "TOKEN-01", "name": "Alice"})
    r2 = await client.post("/join", json={"team_id": "TOKEN-01", "name": "Bob"})
    assert r1.json()["session_token"] != r2.json()["session_token"]


@pytest.mark.asyncio
async def test_fetch_problem_detail(client):
    pids = list(get_all_problems().keys())
    res = await client.get(f"/problem/{pids[0]}")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == pids[0]
    assert "part_a_prompt" in data
    assert "part_b_prompt" in data
    assert "interface_stub" in data


@pytest.mark.asyncio
async def test_fetch_nonexistent_problem_rejected(client):
    res = await client.get("/problem/ZZZZ-DOES-NOT-EXIST")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_player_join_rejects_script_like_name(client):
    await client.post("/admin/create-team", json={"team_id": "SAFE-01"})
    res = await client.post("/join", json={"team_id": "SAFE-01", "name": "<script>alert(1)</script>"})
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_security_headers_present(client):
    res = await client.get("/health")
    assert res.status_code == 200
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-frame-options"] == "DENY"
    assert res.headers["referrer-policy"] == "no-referrer"
    assert res.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"
    assert res.headers["cache-control"] == "no-store"
