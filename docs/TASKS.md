# Exchange The Code: Implementation Checklist (v2)

> Updated for Group-Based Deterministic Assignment model.
> All selection-related items removed. New slot-based assignment added as Chunk 3.

---

## ✅ Chunk 1: Backend Foundation (REST + DB)
- [x] Initialize project structure and `requirements.txt`
- [x] Create `.env` and `config.py`
- [x] Create `database.py` with WAL mode
- [x] Create `models.py` with Pydantic models
- [x] Create `problem_loader.py` + problem JSON files
- [x] `POST /join` — creates player record, returns session token
- [x] `GET /team/{team_id}/problems`, `GET /problem/{problem_id}`
- [x] `POST /admin/create-team`, `POST /admin/assign-problems`
- [x] 14/14 tests passing ✅
- [ ] **[UPDATE NEEDED]** Migrate DB schema:
  - [x] Add `groups` table
  - [x] Add `group_problems` table (position 1 or 2, unique constraints)
  - [x] Add `player_slot` column to `players` (1 or 2)
  - [x] Remove `chosen_problem_id`, `selection_locked_at` from `players`
  - [x] Remove `team_problems` junction table
  - [x] Remove `selection_log` table
  - [x] Add `UNIQUE(player_id, problem_id, phase)` to `submissions`
  - [x] Add `group_id`, `status`, `current_phase` columns to `teams`
- [x] New admin endpoint: `POST /admin/create-group`
- [x] New admin endpoint: `POST /admin/assign-group` (assigns group to team)
- [x] `POST /join` — atomically assigns player_slot (transaction-safe)
- [x] Update all REST tests for new schema

---

## ✅ Chunk 2: WebSocket System (needs update)
- [x] `ConnectionManager` with session validation, broadcast, send-to-player
- [x] Duplicate connection protection (old WS closed before new accepted)
- [x] `SHOW_PROBLEMS` fires once per team (now being replaced)
- [x] `SESSION_RESTORE` on reconnect
- [x] Admin WS with key validation
- [x] PING/PONG heartbeat
- [x] Stale disconnect protection
- [x] 9/9 tests passing ✅
- [x] Replace `SHOW_PROBLEMS` event with `ASSIGNED`
  - [x] `ASSIGNED` sends each player their specific assigned problem (not both problems to both)
  - [x] Uses player_slot → group_problem position mapping
- [x] Remove all `CHOOSE_PROBLEM` / `SELECTION_UPDATE` references from `events.py`
- [x] Update `SESSION_RESTORE` to include assignment (not selection state)
- [x] Update `_problems_shown` tracking → rename to `_assigned_sent` 
- [x] Update WS tests to verify `ASSIGNED` event shape and content

---

## 🔄 Chunk 3: Assignment System (replaces Selection System)

> **FULLY REPLACED.** Old Chunk 3 (Selection Manager with atomic conflict prevention) is removed.
> New Chunk 3 implements deterministic slot-based assignment — no conflicts possible.

- [x] Implement slot assignment in `POST /join` using atomic DB transaction
  - [x] Read player count for team inside transaction
  - [x] Assign slot 1 or slot 2 based on count
  - [x] Reject if count = 2 (team full)
- [x] Implement `core/team_manager.py` (and refactor helper functions to it):
  - [x] `get_assigned_problem(team_id, player_slot)` — queries group_problems by slot→position
  - [x] `get_team_group(team_id)` — returns group_id for a team
  - [x] `get_team_status(team_id)` — returns current status + phase
  - [x] `all_teams_ready()` / `get_all_teams()` — used by admin to gate the Start button
- [x] On both players WS-connected: server sends `ASSIGNED` event to each player
  - [x] Player's assigned problem: full Part A prompt + interface stub
  - [x] Partner's problem: title only (for context)
- [x] Include assignment in `SESSION_RESTORE` payload
- [x] `GET /admin/ready-check` — returns teams not yet in `ready` status
- [x] Write tests (mostly covered in Chunk 1 and 2 tests now):
  - [x] Slot 1 assigned correctly to first joiner
  - [x] Slot 2 assigned correctly to second joiner
  - [x] Simultaneous joins resolve to distinct slots (no duplicates)
  - [x] Team full error on 3rd join
  - [x] `ASSIGNED` WS event received with correct problem

---

## ✅ Chunk 4: Timer Engine and Swap System

- [x] `core/timer_engine.py`:
  - `run_part_a_phase(team_id)` — async countdown, broadcasts `TIMER_TICK` every 5s
  - `run_wait_buffer(team_id)` — 10s countdown, `WAIT_FOR_SWAP` every 1s
  - `run_part_b_phase(team_id)` — async countdown
  - `LOCK_AND_SUBMIT` broadcast on timer expiry
- [x] `core/submission_handler.py`:
  - `receive_draft(player_id, problem_id, code)` — stores draft submission
  - `receive_final(player_id, problem_id, code)` — SHA-256 hash, `is_final=True`
  - `auto_submit_draft(player_id, problem_id)` — fallback on lock
  - `compute_hash(code)` → SHA-256
- [x] `core/swap_engine.py` — **uses player_slot, NOT chosen_problem_id**
  - Query slot 1 and slot 2 players for the team
  - Get their Part A final submissions
  - Verify SHA-256 hashes
  - Build per-player payload: slot 1 gets position 2 Part B prompt + slot 2's code
  - Build per-player payload: slot 2 gets position 1 Part B prompt + slot 1's code
  - Send `START_PART_B` individually
- [x] `core/validation_engine.py`: (Basic pre-swap validation implemented directly in swap engine / timer flow logic)
  - `verify_part_a_hash(player_id, problem_id)` — check stored hash
  - `verify_interface_stub(code, stub)` — check function signature present
- [x] `POST /admin/start` — validates all teams ready, triggers timers for all teams
- [x] Write tests:
  - Correct player gets correct Part B prompt after swap
  - Buffer countdown fires correct number of ticks

---

## ✅ Chunk 5: Code Execution Engine

- [x] `runner/base_runner.py` — `RunResult`, `TestCaseResult`, `RunStatus` dataclass/enum
- [x] `runner/sandbox.py` — blocklist scanning (Python + C++), subprocess isolation with timeout, temp dir management
- [x] `runner/python_runner.py` — write to temp, execute via subprocess, capture stdout/stderr, safety scan
- [x] `runner/cpp_runner.py` — compile with g++, execute binary, graceful missing-compiler handling
- [x] `runner/execution_queue.py` — async queue with background worker, output normalization, per-test-case execution
- [x] `RUN_CODE` WS event — player hits "Run", sample test cases only, `RUN_OUTPUT` sent back
- [x] `FINAL` execution mode — triggered once per team:problem, stores result in `execution_results` DB table
- [x] Final dedup — prevents duplicate execution per team:problem pair
- [x] Populate `execution_results` table with score, breakdown JSON, execution time
- [x] Broadcast `RESULT` to team via WS after final evaluation
- [x] Scoring: `(passed_count / total * 100)`
- [x] Dangerous code blocking: os, subprocess, eval, exec, open, socket, ctypes, etc.
- [x] Strict test suite: 19 passed, 1 skipped (no g++), covering all edge cases

---

## ⏳ Chunk 6: Player Console UI

- [ ] `frontend/player/index.html` — single-page container
- [ ] `screens/join.js` — name + Team ID form → `POST /join` → open WS
- [ ] `screens/waiting.js` — waiting for partner / waiting for admin start / swap buffer
- [ ] `screens/editor.js` — Monaco; Part A prompt; Part B read-only partner code panel
- [ ] `screens/result.js` — score + per-test-case breakdown
- [ ] ~~`screens/selection.js`~~ — **REMOVED** (no selection system)
- [ ] `websocket.js` — WS connect, reconnect with backoff, all event routing
- [ ] `timer.js` — client countdown, syncs to `TIMER_TICK`
- [ ] `storage.js` — IndexedDB draft save/load/clear; `DRAFT_SAVE` event

---

## ⏳ Chunk 7: Admin Dashboard UI

- [ ] `frontend/admin/index.html`
- [ ] `setup.js` — create teams; create groups; assign groups to teams
- [ ] `monitor.js` — live team grid: connection + assignment + submission status
- [ ] `controls.js` — Start All (gated on ready-check); Reset Round; Force Lock
- [ ] `leaderboard.js` — ranked table; updates on `RESULT` events
- [ ] `websocket.js` — admin WS with key auth

---

## ⏳ Chunk 8: Integration and Deployment

- [ ] `scripts/setup_lan.sh` — static IP, DNSMasq, firewall
- [ ] `scripts/deploy.sh` — uvicorn production start
- [ ] `scripts/backup.sh` — DB snapshot every 60s
- [ ] `scripts/watchdog.py` — auto-restart on crash
- [ ] Full E2E test checklist:
  1. Two teams, four players, complete full round
  2. Disconnect mid-Part A → reconnect → state restored
  3. Slot assignment verified under simultaneous joins
  4. Compilation error → readable error to client
  5. Infinite loop → timeout kill
  6. Admin reset → all state clears
  7. Second round after reset
