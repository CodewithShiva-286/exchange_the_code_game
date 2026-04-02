import pytest
import pytest_asyncio
import os
from httpx import AsyncClient, ASGITransport
from backend.database import settings, init_db
from backend.problems.problem_loader import load_problems, seed_problems_to_db, get_all_problems

# Override DB path for tests — must happen before app import
settings.database_path = "test_exchange.db"

from backend.main import app  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Fresh DB + problem cache for every test."""
    for suffix in ("", "-wal", "-shm"):
        path = settings.database_path + suffix
        if os.path.exists(path):
            os.remove(path)

    await init_db()
    load_problems()
    await seed_problems_to_db()

    yield

    for suffix in ("", "-wal", "-shm"):
        path = settings.database_path + suffix
        if os.path.exists(path):
            os.remove(path)


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver"
    ) as c:
        yield c

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

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
async def test_assign_exactly_two_problems(client):
    await client.post("/admin/create-team", json={"team_id": "ASSIGN-01"})
    pids = list(get_all_problems().keys())
    assert len(pids) >= 2, "Need at least 2 loaded problems"

    res = await client.post(
        "/admin/assign-problems",
        json={"team_id": "ASSIGN-01", "problem_ids": [pids[0], pids[1]]}
    )
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_assign_problems_rejects_single(client):
    """Pydantic min_length=2 should reject a list of 1."""
    await client.post("/admin/create-team", json={"team_id": "SINGLE-01"})
    pids = list(get_all_problems().keys())
    res = await client.post(
        "/admin/assign-problems",
        json={"team_id": "SINGLE-01", "problem_ids": [pids[0]]}
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_assign_problems_rejects_duplicates(client):
    await client.post("/admin/create-team", json={"team_id": "DUPPROB-01"})
    pids = list(get_all_problems().keys())
    res = await client.post(
        "/admin/assign-problems",
        json={"team_id": "DUPPROB-01", "problem_ids": [pids[0], pids[0]]}
    )
    assert res.status_code == 400
    assert "unique" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_assign_problems_rejects_reassignment(client):
    """Once problems are assigned to a team, assigning again should fail."""
    await client.post("/admin/create-team", json={"team_id": "REASSIGN-01"})
    pids = list(get_all_problems().keys())
    await client.post(
        "/admin/assign-problems",
        json={"team_id": "REASSIGN-01", "problem_ids": [pids[0], pids[1]]}
    )
    res = await client.post(
        "/admin/assign-problems",
        json={"team_id": "REASSIGN-01", "problem_ids": [pids[0], pids[1]]}
    )
    assert res.status_code == 400
    assert "already assigned" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_player_join_success(client):
    await client.post("/admin/create-team", json={"team_id": "JOIN-01"})
    res = await client.post("/join", json={"team_id": "JOIN-01", "name": "Alice"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "session_token" in data
    assert data["team_id"] == "JOIN-01"
    assert isinstance(data["player_id"], int)


@pytest.mark.asyncio
async def test_player_join_invalid_team_rejected(client):
    res = await client.post("/join", json={"team_id": "DOES-NOT-EXIST", "name": "Ghost"})
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_player_join_max_two_per_team(client):
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
async def test_fetch_team_problems(client):
    await client.post("/admin/create-team", json={"team_id": "FETCH-01"})
    pids = list(get_all_problems().keys())
    await client.post(
        "/admin/assign-problems",
        json={"team_id": "FETCH-01", "problem_ids": [pids[0], pids[1]]}
    )
    res = await client.get("/team/FETCH-01/problems")
    assert res.status_code == 200
    data = res.json()
    assert data["team_id"] == "FETCH-01"
    assert len(data["problems"]) == 2
    returned_ids = {p["id"] for p in data["problems"]}
    assert returned_ids == set(pids[:2])


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
