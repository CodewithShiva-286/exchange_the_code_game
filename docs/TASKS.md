# Exchange The Code: Implementation Checklist

## Chunk 1: Backend Foundation (REST + DB)
- [x] Initialize project directory (`backend`) and install dependencies (`requirements.txt`).
- [x] Create `.env` and `config.py` for settings.
- [x] Create `database.py` with SQLite WAL mode and strictly team-based table schemas (`players`, `teams`, `team_problems`, `submissions`, etc.).
- [x] Create Pydantic `models.py`.
- [x] Create core problem JSONs (`p001.json`, `p002.json`) and `problem_loader.py`.
- [x] Create player router (`POST /join`, `GET /team/{team_id}/problems`, `GET /problem/{problem_id}`).
- [x] Create admin router (`POST /admin/create-team`, `POST /admin/assign-problems` - exactly 2 problems per team).
- [x] Create `main.py` to start the FastAPI server.
- [x] Validate Chunk 1 via test cases (DB integrity, edge cases, invalid inputs). ✅ 14/14 passed

## Chunk 2: WebSocket System
- [x] Implement `websocket/manager.py` with session validation and team-based broadcasting.
- [x] Define baseline WS events in `events.py` (connection, disconnection, state sync wrappers).
- [x] Implement `player_ws.py` endpoint `/ws/{team_id}/{player_id}` and `admin_ws.py`.
- [x] Validate reconnects, token failures, duplicate connection closures, and core WS transport flow (no game logic). ✅ 9/9 passed

## Chunk 3: Problem Selection System
- [ ] Implement atomic selection logic in `selection_manager.py`.
- [ ] Route WS events for problem choice (`CHOOSE_PROBLEM`).
- [ ] Broadcast `SELECTION_UPDATE` to the team.
- [ ] Validate conflict handling (simultaneous selections, duplicate attempts).

## Chunk 4: Timer Engine and Swap System
- [ ] Implement `timer_engine.py` (phase transitions, ticks per team).
- [ ] Implement `submission_handler.py`.
- [ ] Implement `swap_engine.py` logic (swap strictly based on `chosen_problem_id`, not player slot).
- [ ] Implement `validation_engine.py` (pre-execution hash checks).
- [ ] Verify full backend automated game loop from admin start to Part B.

## Chunk 5: Code Execution Engine
- [ ] Create `base_runner.py` and `sandbox.py` (subprocess limits).
- [ ] Create language runners (`python_runner.py`, `cpp_runner.py`).
- [ ] Validate scoring and per-test-case results.

## Chunk 6: Player Console UI
- [ ] Create `index.html` and UI base for players.
- [ ] Implement screens (join, selection, waiting, editor, results).
- [ ] Bind UX events to server via WebSocket and sync timers using team-based logic.
- [ ] Ensure Part A codebase displays as strictly read-only during Part B.

## Chunk 7: Admin Dashboard UI
- [ ] Create admin `index.html`.
- [ ] Implement setup (team creation and assigned problems), monitor, controls, and leaderboard screens.
- [ ] Test live synchronization with team states across the LAN.

## Chunk 8: Integration & Deployment
- [ ] Create `deploy.sh`, `backup.sh`, `setup_lan.sh`, `watchdog.py`.
- [ ] Run full end-to-end multi-player test load.
