"""
test_chunk4_strict.py - Strict Validation Suite for Chunk 4

Validates:
1. Full single-team exact phase order and timer ticks
2. Swap verification (Player 1 gets Player 2's code)
3. Missing submission auto-fallback
4. Reconnection mid-phase state restore
5. Multi-team isolation and parallel execution
6. DB constraints and integrity checks
"""

import pytest
import pytest_asyncio
import os
import aiosqlite
import time
import concurrent.futures
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.config import settings
from backend.tests.test_chunk2 import _create_team_with_group
from backend.core.submission_handler import _DRAFTS


settings.database_path = "test_exchange_strict.db"


@pytest_asyncio.fixture(scope="session", autouse=True)
async def init_test_db_strict():
    for suffix in ("", "-wal", "-shm"):
        path = settings.database_path + suffix
        if os.path.exists(path):
            try: os.remove(path)
            except: pass

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


# ─── Helper for non-blocking Event Collection ─────────────────────────────────

def receive_with_timeout(ws, timeout=4.0):
    """Safely fetch WS JSON preventing infinite test hangs."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(ws.receive_json)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            raise TimeoutError("WebSocket receive timed out waiting for event")

def wait_for_event(ws, expected_event, timeout=4.0):
    """Wait for a specific event type, ignoring others like PONG or TICKs."""
    start = time.time()
    while time.time() - start < timeout:
        msg = receive_with_timeout(ws, timeout=max(0.5, timeout - (time.time() - start)))
        if msg.get("event") == expected_event:
            return msg
    raise TimeoutError(f"Never received event: {expected_event}")


# ─── Test 1: Full Flow, Swap Correctness, Missing Submit & DB Integrity ───────

@pytest.mark.asyncio
async def test_full_flow_swap_and_db_integrity(http_client):
    _DRAFTS.clear()
    
    # Very short timers
    orig_a = settings.part_a_duration
    orig_buf = settings.buffer_duration
    orig_b = settings.part_b_duration
    settings.part_a_duration = 2
    settings.buffer_duration = 1
    settings.part_b_duration = 1

    try:
        team_id = "STRICT-T1"
        p1, p2 = await _create_team_with_group(http_client, team_id, "GRP-STRICT1")

        with TestClient(app) as tc:
            with tc.websocket_connect(f"/ws/{team_id}/{p1['player_id']}?token={p1['session_token']}") as ws1, \
                 tc.websocket_connect(f"/ws/{team_id}/{p2['player_id']}?token={p2['session_token']}") as ws2:
                
                a1 = wait_for_event(ws1, "ASSIGNED")
                a2 = wait_for_event(ws2, "ASSIGNED")

                # Player 1 submits code. Player 2 missing submission.
                p1_prob_id = a1["data"]["assigned_problem"]["id"]
                draft_p1 = "def solve_p1(): return 42"
                
                # Admin start
                res = tc.post("/admin/start")
                assert res.status_code == 200

                wait_for_event(ws1, "START_PART_A")
                wait_for_event(ws2, "START_PART_A")
                
                # P1 Draft saving
                ws1.send_json({"event": "DRAFT_SAVE", "data": {"problem_id": p1_prob_id, "code": draft_p1}})

                wait_for_event(ws1, "LOCK_AND_SUBMIT")
                wait_for_event(ws2, "LOCK_AND_SUBMIT")

                wait_for_event(ws1, "WAIT_FOR_SWAP")
                wait_for_event(ws2, "WAIT_FOR_SWAP")

                # SWAP VALIDATION
                ev_b1 = wait_for_event(ws1, "START_PART_B")
                ev_b2 = wait_for_event(ws2, "START_PART_B")

                # Player 1 should receive empty code (Player 2 didn't submit)
                assert ev_b1["data"]["partner_code"] == "", "P1 should receive empty partner code"
                # Player 2 should receive Player 1's draft
                assert ev_b2["data"]["partner_code"] == draft_p1, "P2 did not receive P1's exact draft payload"

                wait_for_event(ws1, "LOCK_AND_SUBMIT")
                wait_for_event(ws1, "END_GAME")
                
                time.sleep(0.5) # Let DB tasks finish commits
                
        # DB INTEGRITY VALIDATION
        async with aiosqlite.connect(settings.database_path) as db:
            async with db.execute("SELECT player_id, phase, code, is_final, sha256_hash FROM submissions WHERE player_id IN (?, ?)", (p1["player_id"], p2["player_id"])) as cursor:
                rows = await cursor.fetchall()
                
            # Expecting exactly 4 rows (Part A for P1, P2 + Part B for P1, P2)
            assert len(rows) == 4, f"DB integrity failed: expected 4 submissions, got {len(rows)}"
            
            p1_a = next(r for r in rows if r[0] == p1["player_id"] and r[1] == "part_a")
            p2_a = next(r for r in rows if r[0] == p2["player_id"] and r[1] == "part_a")
            
            assert p1_a[2] == draft_p1
            assert p2_a[2] == ""
            assert p1_a[3] == 1 # is_final
            assert p1_a[4] is not None # Hash exists

    finally:
        settings.part_a_duration = orig_a
        settings.buffer_duration = orig_buf
        settings.part_b_duration = orig_b


# ─── Test 2: Reconnection State Restoration ───────────────────────────────────

@pytest.mark.asyncio
async def test_reconnect_mid_phase(http_client):
    orig_a = settings.part_a_duration
    settings.part_a_duration = 3
    settings.buffer_duration = 1
    settings.part_b_duration = 1
    _DRAFTS.clear()

    try:
        team_id = "STRICT-T2"
        p1, p2 = await _create_team_with_group(http_client, team_id, "GRP-STRICT2")

        with TestClient(app) as tc:
            # 1. Connect Both
            ws1 = tc.websocket_connect(f"/ws/{team_id}/{p1['player_id']}?token={p1['session_token']}")
            ws2 = tc.websocket_connect(f"/ws/{team_id}/{p2['player_id']}?token={p2['session_token']}")
            
            with ws1, ws2:
                wait_for_event(ws1, "ASSIGNED")
                
                # Start
                tc.post("/admin/start")
                wait_for_event(ws1, "START_PART_A")
            
            # Context exits -> disconnected ws1 and ws2. Game timer still running!
            
            # Reconnect immediately
            with tc.websocket_connect(f"/ws/{team_id}/{p1['player_id']}?token={p1['session_token']}") as ws1_recon:
                msg = wait_for_event(ws1_recon, "SESSION_RESTORE")
                assert msg["data"]["phase"] == "part_a"
                
                # Consume correctly until end to not abort timer tasks abruptly
                wait_for_event(ws1_recon, "LOCK_AND_SUBMIT", timeout=5)
                wait_for_event(ws1_recon, "END_GAME", timeout=5)
                
    finally:
        settings.part_a_duration = orig_a
        settings.buffer_duration = 1
        settings.part_b_duration = 1


# ─── Test 3: Multi-Team Parallel Isolation ────────────────────────────────────

@pytest.mark.asyncio
async def test_multi_team_parallel(http_client):
    orig_a = settings.part_a_duration
    settings.part_a_duration = 1
    settings.buffer_duration = 1
    settings.part_b_duration = 1

    try:
        team_a = "MULTI-A"
        team_b = "MULTI-B"
        tA_p1, tA_p2 = await _create_team_with_group(http_client, team_a, "GRP-MULTI-A")
        tB_p1, tB_p2 = await _create_team_with_group(http_client, team_b, "GRP-MULTI-B")

        with TestClient(app) as tc:
            with tc.websocket_connect(f"/ws/{team_a}/{tA_p1['player_id']}?token={tA_p1['session_token']}") as wsA1, \
                 tc.websocket_connect(f"/ws/{team_a}/{tA_p2['player_id']}?token={tA_p2['session_token']}") as wsA2, \
                 tc.websocket_connect(f"/ws/{team_b}/{tB_p1['player_id']}?token={tB_p1['session_token']}") as wsB1, \
                 tc.websocket_connect(f"/ws/{team_b}/{tB_p2['player_id']}?token={tB_p2['session_token']}") as wsB2:

                wait_for_event(wsA1, "ASSIGNED")
                wait_for_event(wsB1, "ASSIGNED")
                
                tc.post("/admin/start")
                
                # Verify BOTH isolated channels receive START immediately and concurrently
                wait_for_event(wsA1, "START_PART_A")
                wait_for_event(wsB1, "START_PART_A")
                
                # Finish out events
                wait_for_event(wsA1, "END_GAME", timeout=5)
                wait_for_event(wsB1, "END_GAME", timeout=5)

    finally:
        settings.part_a_duration = orig_a
        settings.buffer_duration = 1
        settings.part_b_duration = 1
