import pytest
import pytest_asyncio
import os
import logging
import sys
from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.config import settings
from backend.tests.test_chunk2 import _create_team_with_group

logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)

settings.database_path = "test_exchange_chunk4.db"

@pytest_asyncio.fixture(scope="session", autouse=True)
async def init_test_db():
    for suffix in ("", "-wal", "-shm"):
        path = settings.database_path + suffix
        if os.path.exists(path):
            try: 
                os.remove(path)
            except Exception: 
                pass

    from backend.database import init_db
    from backend.problems.problem_loader import load_problems, seed_problems_to_db

    await init_db()
    load_problems()
    await seed_problems_to_db()
    yield
    for suffix in ("", "-wal", "-shm"):
        path = settings.database_path + suffix
        try:
            if os.path.exists(path): os.remove(path)
        except: pass

@pytest_asyncio.fixture
async def http_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_full_game_loop_chunk4(http_client):
    # Alter durations to be very short to prevent hanging tests
    orig_a = settings.part_a_duration
    orig_b = settings.part_b_duration
    orig_buf = settings.buffer_duration
    settings.part_a_duration = 1
    settings.buffer_duration = 1
    settings.part_b_duration = 1

    try:
        team_id = "CHK4-01"
        group_id = "GRP-CHK4"
        p1, p2 = await _create_team_with_group(http_client, team_id, group_id)

        # Admin check - should be not ready
        res = await http_client.get("/admin/ready-check")
        assert res.status_code == 200
        team_status = next(t for t in res.json()["teams"] if t["team_id"] == team_id)
        assert team_status["ready"] is False

        with TestClient(app) as tc:
            with tc.websocket_connect(f"/ws/{team_id}/{p1['player_id']}?token={p1['session_token']}") as ws1, \
                 tc.websocket_connect(f"/ws/{team_id}/{p2['player_id']}?token={p2['session_token']}") as ws2:
                
                def wait_for_event(ws, event_name):
                    while True:
                        msg = ws.receive_json()
                        if msg["event"] == event_name:
                            return msg

                # Wait for ASSIGNED
                a1 = wait_for_event(ws1, "ASSIGNED")
                a2 = wait_for_event(ws2, "ASSIGNED")

                p1_prob_id = a1["data"]["assigned_problem"]["id"]

                # Admin triggers start
                res = tc.post("/admin/start")
                assert res.status_code == 200

                # ── 1. Part A ──
                ev1 = wait_for_event(ws1, "START_PART_A")
                wait_for_event(ws2, "START_PART_A")

                # Send a DRAFT_SAVE from Player 1
                draft_code = "def part_a_p1(): return True"
                ws1.send_json({
                    "event": "DRAFT_SAVE",
                    "data": {"problem_id": p1_prob_id, "code": draft_code}
                })

                # Expect LOCK_AND_SUBMIT 
                ev_lock = wait_for_event(ws1, "LOCK_AND_SUBMIT")
                wait_for_event(ws2, "LOCK_AND_SUBMIT")

                # ── 2. Buffer ──
                ev_wait = wait_for_event(ws1, "WAIT_FOR_SWAP")
                wait_for_event(ws2, "WAIT_FOR_SWAP")

                # ── 3. Part B (Swap) ──
                ev_b = wait_for_event(ws1, "START_PART_B")
                # ws1 (player_slot=1) gets partner's code (slot 2). Since p2 sent no draft, it's empty ""
                assert ev_b["data"]["partner_code"] == ""
                
                ev_b2 = wait_for_event(ws2, "START_PART_B")
                # ws2 (player_slot=2) gets p1's code. It must match the draft!
                assert ev_b2["data"]["partner_code"] == draft_code

                # ── 4. End Game ──
                ev_lock_b = wait_for_event(ws1, "LOCK_AND_SUBMIT")
                wait_for_event(ws2, "LOCK_AND_SUBMIT")

                ev_end = wait_for_event(ws1, "END_GAME")
                wait_for_event(ws2, "END_GAME")
                
                import asyncio
                await asyncio.sleep(0.5)

    finally:
        settings.part_a_duration = orig_a
        settings.part_b_duration = orig_b
        settings.buffer_duration = orig_buf
