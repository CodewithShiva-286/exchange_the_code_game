import os
import tempfile

import aiosqlite
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient

from backend.config import settings

settings.database_path = os.path.join(
    tempfile.gettempdir(),
    "test_exchange_leaderboard.db",
)

from backend.database import init_db  # noqa: E402
from backend.main import app  # noqa: E402
from backend.problems.problem_loader import load_problems, seed_problems_to_db  # noqa: E402
from backend.runner.execution_queue import ExecutionTask, reset_final_tracker, submit_task  # noqa: E402
from backend.websocket.manager import manager  # noqa: E402


@pytest_asyncio.fixture(scope="session", autouse=True)
async def init_test_db():
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
    async with aiosqlite.connect(settings.database_path, timeout=15.0) as db:
        await db.execute("DELETE FROM team_scores")
        await db.execute("DELETE FROM execution_results")
        await db.execute("DELETE FROM submissions")
        await db.execute("DELETE FROM players")
        await db.execute("DELETE FROM group_problems")
        await db.execute("DELETE FROM groups")
        await db.execute("DELETE FROM teams")
        await db.commit()

    await seed_problems_to_db()
    reset_final_tracker()

    manager._teams.clear()
    manager._admin_ws = None
    manager._assigned_sent.clear()

    yield


@pytest_asyncio.fixture
async def http_client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_admin_leaderboard_returns_current_cumulative_totals(http_client):
    async with aiosqlite.connect(settings.database_path, timeout=15.0) as db:
        await db.execute("INSERT INTO teams (team_id) VALUES ('TEAM-1')")
        await db.execute("INSERT INTO teams (team_id) VALUES ('TEAM-2')")
        await db.execute(
            "INSERT INTO team_scores (team_id, round, score, total_score) VALUES (?, ?, ?, ?)",
            ("TEAM-1", 1, 20, 20),
        )
        await db.execute(
            "INSERT INTO team_scores (team_id, round, score, total_score) VALUES (?, ?, ?, ?)",
            ("TEAM-1", 2, 30, 50),
        )
        await db.execute(
            "INSERT INTO team_scores (team_id, round, score, total_score) VALUES (?, ?, ?, ?)",
            ("TEAM-2", 1, 40, 40),
        )
        await db.commit()

    response = await http_client.get("/admin/leaderboard")
    assert response.status_code == 200
    assert response.json() == [
        {"team_id": "TEAM-1", "total_score": 50},
        {"team_id": "TEAM-2", "total_score": 40},
    ]


@pytest.mark.asyncio
async def test_final_score_broadcasts_leaderboard_update_to_admin():
    async with aiosqlite.connect(settings.database_path, timeout=15.0) as db:
        await db.execute("INSERT INTO teams (team_id) VALUES ('LIVE-TEAM-1')")
        await db.commit()

    task = ExecutionTask(
        task_type="final",
        team_id="LIVE-TEAM-1",
        player_id=101,
        code='print("42")',
        language="python",
        test_cases=[{"id": 1, "input_data": "", "expected_output": "42"}],
        problem_id="p001",
    )

    with TestClient(app) as test_client:
        with test_client.websocket_connect(f"/ws/admin?key={settings.admin_key}") as ws:
            connected = ws.receive_json()
            assert connected["event"] == "ADMIN_CONNECTED"

            result = await submit_task(task)
            assert result is not None

            update = ws.receive_json()
            assert update["event"] == "LEADERBOARD_UPDATE"
            assert update["data"]["leaderboard"] == [
                {"team_id": "LIVE-TEAM-1", "total_score": 10}
            ]
