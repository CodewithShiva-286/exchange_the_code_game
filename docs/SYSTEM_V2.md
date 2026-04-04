# Exchange The Code — System Design Document v2

> **Version:** 2.0 — Group-Based Deterministic Assignment Model
> **Supersedes:** `PREPARATION_EXCHANGE_THE_CODE (1).md` (v1, selection-based)
> **Status:** Authoritative reference for all chunks from here forward.

---

## 1. System Understanding

**Exchange the Code** is a real-time, relay-style competitive coding platform for offline college techfests. It runs entirely on a **Local Area Network (LAN)** — no internet dependency.

**The core mechanic** is forced context switching:
- Player A (slot 1) writes the foundation of Problem 1 in Part A
- Player B (slot 2) writes the foundation of Problem 2 in Part A
- After a timed lock, code is swapped deterministically:
  - Player A (slot 1) completes Problem 2's Part B using Player B's foundation
  - Player B (slot 2) completes Problem 1's Part B using Player A's foundation
- Neither player can modify the other's Part A

**Key change from v1:** Problem assignment is now **automatic and deterministic** based on join order (`player_slot`). There is no selection phase, no conflict, no `CHOOSE_PROBLEM` event.

**Two roles exist:**
- **Admin** — Creates groups (with exactly 2 problems), creates teams, assigns groups to teams, triggers the round, monitors all rooms live, views the leaderboard
- **Player** — Joins a team, receives their automatically assigned problem, codes Part A, receives partner's code, codes Part B, receives final score

**Infrastructure:**
- Backend: FastAPI (Python) + aiosqlite (SQLite with WAL mode)
- Frontend: Vanilla JS + Monaco Editor (browser-based)
- Transport: WebSockets for real-time events + REST for join/setup
- Network: LAN star topology, accessible at `techfest.local:8000` via DNSMasq
- Execution: Sandboxed subprocesses with resource limits (Python + C++)

---

## 2. Game Flow (Clean Step-by-Step)

```
JOIN → WAIT_FOR_PARTNER → PROBLEM_ASSIGNED → ADMIN_START
     → PART_A → LOCK → WAIT_BUFFER → SWAP → PART_B → EXECUTE → RESULTS
```

> **Removed from v1:** `SHOW_PROBLEMS → SELECT → WAIT_FOR_BOTH` phases are entirely gone.

### Phase 0 — Setup (Admin only, before players join)

1. Admin creates a **group** with exactly 2 problems (e.g., `p001` at position 1, `p002` at position 2).
2. Admin creates a **team** and assigns the group to it.
3. Team ID is distributed to players verbally or on paper.

### Phase 1 — Join

1. Each player opens the player console, enters name + Team ID.
2. Client calls `POST /join` — server runs a `BEGIN IMMEDIATE` transaction:
   - Counts existing players on the team
   - If 0 players: assigns `player_slot = 1`
   - If 1 player: assigns `player_slot = 2`
   - If 2 players: rejects with HTTP 400 (team full)
3. Server creates player record with `player_slot`, returns `session_token`, `player_id`, `player_slot`.
4. Player opens WebSocket connection to `/ws/{team_id}/{player_id}?token={session_token}`.
5. Server waits until **both** players in the team are connected before proceeding.

### Phase 2 — Problem Assignment (Automatic)

- When the **second** player connects and `is_team_full()` becomes true:
  - Server sends `PROBLEM_ASSIGNED` individually to each player:
    - Player slot 1 gets Problem at group position 1
    - Player slot 2 gets Problem at group position 2
  - This event fires **exactly once** per team (tracked by `_problems_shown` set in `ConnectionManager`).
  - No user interaction. No selection. No conflict.
- First connected player sees a "waiting for partner" screen.
- On reconnect: `SESSION_RESTORE` includes the player's assigned problem.

### Phase 3 — Part A Coding

- Admin sees all rooms as "ready" on dashboard (both players assigned problems).
- Admin clicks **Start All** → server broadcasts `START_PART_A` to all rooms.
- Each player receives their assigned problem's Part A prompt + non-editable function stub.
- Monaco editor is active; countdown timer runs.
- Auto-save: IndexedDB every 10s + `DRAFT_SAVE` WS event to server.
- Server sends `TIMER_TICK` every 5s.

### Phase 4 — Lock and Submit

- Part A timer expires → server broadcasts `LOCK_AND_SUBMIT`.
- Monaco editor set to `readOnly = true` on client.
- Client sends `FINAL_SUBMIT` WS event with current code.
- Server stores code + SHA-256 hash, sets `is_final = true`.
- Fallback: last `DRAFT_SAVE` if no `FINAL_SUBMIT`; empty stub if no draft.

### Phase 5 — Wait Buffer

- Server broadcasts `WAIT_FOR_SWAP` with 10-second countdown.
- Ticks every 1 second. Swap executes at 0.

### Phase 6 — Code Exchange (Swap)

Swap is driven entirely by `player_slot` and `group_problems.position`:

```
player_slot 1 → worked on position 1 (Problem P1) in Part A
player_slot 2 → worked on position 2 (Problem P2) in Part A

After swap:
  player_slot 1 receives: player_slot 2's Part A code + Problem P2's Part B prompt
  player_slot 2 receives: player_slot 1's Part A code + Problem P1's Part B prompt

Formula: swap_target_position = (3 - player_slot)
  slot 1 → does Part B of position 2
  slot 2 → does Part B of position 1
```

Server sends `START_PART_B` individually to each player with partner's code + Part B prompt.

### Phase 7 — Part B Coding

- Each player sees partner's Part A code in a **permanently read-only** panel.
- Player writes Part B in Monaco editor (active).
- Second countdown timer runs; `TIMER_TICK` keeps sync.
- Auto-save continues.

### Phase 8 — Final Execution

- Part B timer expires → LOCK flow (same as Phase 4).
- Server combines Part A (original author, hash-verified) + Part B (current player).
- Validation: hash integrity + function interface stub present.
- Code runner executes combined code in sandboxed subprocess against all test cases.
- Scoring: `(passed_tests / total_tests) * 100 + time_bonus`
- Results stored in `execution_results`.

### Phase 9 — Results

- Server broadcasts `RESULT` to room and admin.
- Player console shows: score, per-test-case breakdown, team rank.
- Admin leaderboard shows all teams ranked by total score.

---

## 3. Architecture Summary

### Client Layer (Browsers)
- **Player Console** x2 per team — Monaco editor, timer, WebSocket client, IndexedDB storage
- **Admin Dashboard** x1 — Monitor grid, control bar, leaderboard, admin WebSocket

### Backend Layer (FastAPI on LAN server)
- **REST Routers** — Handle join (slot assignment), group management, admin setup, admin start
- **WebSocket Endpoints** — Player WS at `/ws/{team_id}/{player_id}`, Admin WS at `/ws/admin`
- **Core Services:**
  - `room_manager.py` — Room lifecycle state machine
  - `timer_engine.py` — Async per-room timers; phase transitions
  - `swap_engine.py` — Slot-based swap logic
  - `submission_handler.py` — SHA-256, is_final flag
  - `validation_engine.py` — Hash + interface verification
- **REMOVED from v1:** `selection_manager.py` — does not exist in this system

### Storage Layer
- SQLite (WAL mode) — All persistent state: groups, group_problems, teams, players (with player_slot), problems, submissions, results

### Infrastructure Layer
- LAN — DNSMasq, static IP, `techfest.local`, port 8000
- Backup — DB snapshots every 60s via rsync to standby
- Ops — Watchdog auto-restart, deploy script

---

## 4. Data Flow Summary

### Group Creation Flow
```
Admin creates group (2 problems)
  → POST /admin/create-group { group_id, problem_ids: [p1, p2] }
  → Server validates: exactly 2 unique problem IDs, both exist
  → INSERT INTO groups
  → INSERT INTO group_problems: (group_id, p1, position=1), (group_id, p2, position=2)
```

### Team Creation + Group Assignment Flow
```
Admin creates team and assigns group
  → POST /admin/create-team { team_id }
  → POST /admin/assign-group { team_id, group_id }
  → Server validates: team exists, group exists
  → UPDATE teams SET group_id = group_id WHERE team_id = team_id
```

### Join Flow (With Race Condition Fix)
```
Player types name + Team ID
  → POST /join { team_id, name }
  → BEGIN IMMEDIATE transaction
    → Validate team exists, has a group assigned
    → SELECT COUNT(*) FROM players WHERE team_id = ? (must be < 2)
    → player_slot = count + 1
    → INSERT player with player_slot
  → COMMIT
  → Returns: session_token, player_id, player_slot, team_id
  → Player opens WS connection
```

### Problem Assignment Flow (Replaces Selection Flow)
```
Both players connected to WS
  → ConnectionManager.is_team_full() == True
  → should_show_problems() == True (fires only once per team)
  → Query group_problems for team's group: position 1 → ProblemA, position 2 → ProblemB
  → Send PROBLEM_ASSIGNED to player_slot 1: { problem: ProblemA, position: 1 }
  → Send PROBLEM_ASSIGNED to player_slot 2: { problem: ProblemB, position: 2 }
  → mark_problems_shown(team_id)
```

### Swap Flow (New — Slot-Based)
```
Swap engine:
  → Fetch both players for team (slot 1 and slot 2)
  → Fetch group_problems for team's group (position 1 and position 2)
  → Fetch final Part A submissions for each player
  → Validate SHA-256 hashes
  → Build per-player START_PART_B payload:
      player_slot 1: partner_code = slot2's Part A, prompt = position 2's part_b_prompt
      player_slot 2: partner_code = slot1's Part A, prompt = position 1's part_b_prompt
  → Send START_PART_B individually to each player
```

### Reconnect Flow
```
Player reconnects (within 30s window)
  → WS connection re-established
  → Server queries DB: player_slot, assigned problem (via group), current phase, code, timer
  → Sends SESSION_RESTORE with full state
  → Client restores exactly where player was
```

---

## 5. Module Breakdown

### 5.1 Player Console (Frontend)

| File | Responsibility |
|------|----------------|
| `index.html` | Single-page container; hosts all screens |
| `screens/join.js` | Name + Team ID form; calls POST /join; opens WS |
| `screens/waiting.js` | Generic waiting: partner join / admin start / swap buffer countdown |
| `screens/editor.js` | Monaco init; Part A prompt panel; Part B partner-code read-only panel; lock/unlock |
| `screens/result.js` | Score display; per-test-case breakdown table |
| `websocket.js` | WS connection; exponential backoff reconnect; all incoming event routing |
| `timer.js` | Client-side countdown; syncs with TIMER_TICK from server |
| `storage.js` | IndexedDB draft: saveDraft(), loadDraft(), clearDraft(); sends DRAFT_SAVE WS event |

> **REMOVED from v1:** `screens/selection.js` — does not exist in this system

### 5.2 Admin Dashboard (Frontend)

| File | Responsibility |
|------|----------------|
| `index.html` | Single-page admin dashboard |
| `setup.js` | Group creation (2 problems); team creation; group assignment; Team ID display with copy |
| `monitor.js` | Live room grid: connection/slot assignment/submission status per player |
| `controls.js` | Start All (ready-check gate); Reset Round; Force Lock |
| `leaderboard.js` | Sorted results table; updates on RESULT events |
| `websocket.js` | Admin WS with key auth; routes status updates to monitor and leaderboard |

### 5.3 Backend Services

| Module | File | Key Functions |
|--------|------|---------------|
| Room Manager | `core/room_manager.py` | `create_team()`, `assign_group_to_team()`, `get_team_group()`, `get_room_players()`, `update_room_status()` |
| Timer Engine | `core/timer_engine.py` | `run_part_a_phase()`, `run_wait_buffer()`, `run_part_b_phase()` — TIMER_TICK every 5s |
| Swap Engine | `core/swap_engine.py` | `swap_code(team_id)` — slot+position based; validates hashes; builds per-player payload |
| Submission Handler | `core/submission_handler.py` | `receive_submission()`, `auto_submit_draft()`, `compute_hash()` |
| Validation Engine | `core/validation_engine.py` | `verify_part_a_hash()`, `verify_interface_stub()` |
| WS Manager | `websocket/manager.py` | Connection registry; connect/disconnect/broadcast; session validation; `_problems_shown` guard |
| WS Events | `websocket/events.py` | All event constants + payload builders |
| Player WS | `websocket/player_ws.py` | Endpoint `/ws/{team_id}/{player_id}`; incoming event routing |
| Admin WS | `websocket/admin_ws.py` | Endpoint `/ws/admin`; admin key validation |

> **REMOVED from v1:** `core/selection_manager.py` — does not exist in this system

### 5.4 Code Execution Engine

| Module | File | Responsibility |
|--------|------|----------------|
| Base Runner | `runner/base_runner.py` | `RunResult` dataclass; common interface |
| Sandbox | `runner/sandbox.py` | Subprocess environment; CPU time + memory limits; temp file cleanup |
| Python Runner | `runner/python_runner.py` | Run Python code against test cases; captures stdout/stderr; handles timeout |
| C++ Runner | `runner/cpp_runner.py` | Compile with g++; execute binary; per-test-case results |

---

## 6. Database Schema (8 Tables)

> **Changes from v1:**
> - ADDED: `groups` table
> - ADDED: `group_problems` table (with position 1 or 2)
> - ADDED: `player_slot` column in `players`
> - ADDED: `UNIQUE(player_id, problem_id, phase)` in `submissions`
> - REMOVED: `chosen_problem_id` from `players`
> - REMOVED: `selection_locked_at` from `players`
> - REMOVED: `team_problems` table entirely
> - REMOVED: `selection_log` table entirely
> - UPDATED: `teams` now has `group_id` FK

### Table: `groups`
```sql
CREATE TABLE IF NOT EXISTS groups (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

### Table: `group_problems`
```sql
CREATE TABLE IF NOT EXISTS group_problems (
    group_id TEXT NOT NULL,
    problem_id TEXT NOT NULL,
    position INTEGER NOT NULL CHECK (position IN (1, 2)),
    FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
    FOREIGN KEY (problem_id) REFERENCES problems(id) ON DELETE CASCADE,
    UNIQUE(group_id, position),      -- exactly one problem per position
    UNIQUE(group_id, problem_id)    -- same problem cannot fill both positions
)
```

### Table: `teams`
```sql
CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id TEXT UNIQUE NOT NULL,
    group_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (group_id) REFERENCES groups(id)
)
```

### Table: `players`
```sql
CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id TEXT NOT NULL,
    name TEXT NOT NULL,
    session_token TEXT UNIQUE NOT NULL,
    player_slot INTEGER NOT NULL CHECK (player_slot IN (1, 2)),
    connection_status TEXT DEFAULT 'offline',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (team_id) REFERENCES teams(team_id) ON DELETE CASCADE
)
```
> REMOVED: `chosen_problem_id`, `selection_locked_at`

### Table: `problems`
```sql
CREATE TABLE IF NOT EXISTS problems (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    part_a_prompt TEXT NOT NULL,
    part_b_prompt TEXT NOT NULL,
    interface_stub TEXT NOT NULL,
    language TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

### Table: `test_cases`
```sql
CREATE TABLE IF NOT EXISTS test_cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_id TEXT NOT NULL,
    input_data TEXT NOT NULL,
    expected_output TEXT NOT NULL,
    is_visible BOOLEAN DEFAULT 0,
    FOREIGN KEY (problem_id) REFERENCES problems(id) ON DELETE CASCADE
)
```

### Table: `submissions`
```sql
CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    problem_id TEXT NOT NULL,
    code TEXT NOT NULL,
    sha256_hash TEXT NOT NULL,
    phase TEXT NOT NULL CHECK (phase IN ('part_a', 'part_b')),
    is_final BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
    FOREIGN KEY (problem_id) REFERENCES problems(id) ON DELETE CASCADE,
    UNIQUE(player_id, problem_id, phase)  -- prevents duplicate submissions
)
```

### Table: `execution_results`
```sql
CREATE TABLE IF NOT EXISTS execution_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id TEXT NOT NULL,
    problem_id TEXT NOT NULL,
    status TEXT NOT NULL,
    score FLOAT NOT NULL,
    test_case_breakdown TEXT NOT NULL,
    execution_time FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (team_id) REFERENCES teams(team_id) ON DELETE CASCADE,
    FOREIGN KEY (problem_id) REFERENCES problems(id) ON DELETE CASCADE
)
```

> **REMOVED from v1:** `selection_log` table
> **REMOVED from v1:** `team_problems` table

---

## 7. WebSocket Event Reference

### Server → Client Events

| Event | Trigger | Purpose |
|-------|---------|---------|
| `CONNECTED` | Player WS accepted | Confirm connection; send player_id, name, player_slot |
| `PARTNER_JOINED` | Second player connects | Notify first player that partner is now connected |
| `PROBLEM_ASSIGNED` | Both players connected (once per team) | Send each player THEIR specific assigned problem only |
| `START_PART_A` | Admin triggers start | Begin Part A; includes Part A prompt + timer duration |
| `TIMER_TICK` | Every 5s during active phase | Keep client timers synced with server |
| `LOCK_AND_SUBMIT` | Part A timer expires | Freeze editor; trigger auto-submit |
| `WAIT_FOR_SWAP` | After lock; every 1s for 10s | Show swap countdown |
| `START_PART_B` | After buffer completes | Deliver partner's code + Part B prompt (individual per player) |
| `RESULT` | After execution completes | Deliver score + per-test-case results |
| `SESSION_RESTORE` | Player reconnects | Restore full state: phase, player_slot, assigned problem, code, timer |
| `ERROR` | Any server-side failure | Error code + retry flag |
| `PONG` | Response to PING | Heartbeat reply |

> **REMOVED from v1:** `SHOW_PROBLEMS` (showed both problems for selection)
> **REMOVED from v1:** `SELECTION_UPDATE` — does not exist in this system

### Client → Server Events

| Event | When Sent | Purpose |
|-------|-----------|---------|
| `DRAFT_SAVE` | Every 10 seconds | Persist current editor content server-side |
| `FINAL_SUBMIT` | On lock or manual submit | Send final code for hash + storage |
| `PING` | Every 15 seconds | Keep-alive heartbeat |

> **REMOVED from v1:** `CHOOSE_PROBLEM` — does not exist in this system

### Admin Events (Server → Admin)

| Event | Trigger | Purpose |
|-------|---------|---------|
| `ADMIN_CONNECTED` | Admin WS accepted | Confirm admin connection |
| `ADMIN_STATUS_UPDATE` | Any room state change | Live update of all team statuses |
| `PONG` | Response to PING | Heartbeat reply |

---

## 8. Error Handling and Edge Cases

| Scenario | Handling |
|----------|---------|
| **Join race condition** (simultaneous) | `BEGIN IMMEDIATE` transaction; exactly one gets slot 1, other gets slot 2; serialized by SQLite |
| **Team full at join** | `POST /join` returns HTTP 400 — validated inside transaction before INSERT |
| **No group assigned to team** | `POST /join` returns HTTP 400: "Team has no group assigned" |
| **Duplicate WS connection** | `connect_player()` closes old WS with code 4010 before accepting new one |
| **PROBLEM_ASSIGNED fires twice** | `_problems_shown` set in ConnectionManager; `should_show_problems()` guards against repeat |
| **Partner never joins** | First player stays on waiting screen; admin can force-start (team treated as unsubmitted) |
| **Disconnect during Part A** | `SESSION_RESTORE` includes current code + time remaining + assigned problem |
| **Timer fires with no submission** | Server uses last `DRAFT_SAVE`; if none, submits empty stub with function signature |
| **Swap fails (missing Part A)** | `ERROR` broadcast with `SWAP_FAILED` to admin; admin can manual-override |
| **Part A hash mismatch** | Execution rejected; result = `integrity_error`; team scores zero for that problem |
| **Invalid session token on WS** | Accept then immediately close with code 4001 before any state change |
| **Stale connection disconnect** | `disconnect_player()` checks WS reference match — stale disconnects are silently ignored |
| **Compilation error** | Runner captures stderr; returned to client as readable error |
| **Infinite loop** | Subprocess timeout (5s) kills process; result = `timeout` |
| **Server crash mid-round** | Hot standby takes over; SQLite WAL ensures consistency; states restored from DB on restart |

---

## 9. Security and Integrity Mechanisms

| Mechanism | Implementation |
|-----------|----------------|
| Session tokens | UUID per player at `/join`; validated on every WS connect; invalid = closed code 4001 |
| player_slot immutability | Assigned once in a transaction at join time; never updated after |
| Part A lock (frontend) | Monaco `readOnly = true` on `LOCK_AND_SUBMIT`; Part A panel in Part B is non-editable |
| Part A lock (backend) | SHA-256 stored at lock; recomputed before execution; mismatch = zero score |
| Sandboxed execution | Subprocess with OS-level limits; no network/filesystem access outside temp dir |
| Admin authentication | Admin key required on both WS connect and REST endpoints |
| DB constraints | `UNIQUE(group_id, position)` prevents corrupt group; `UNIQUE(player_id, problem_id, phase)` prevents double-submit |
| Transaction locking | `BEGIN IMMEDIATE` on join prevents slot assignment race conditions |

---

## 10. Chunk Breakdown (7 Chunks)

> **Removed from v1:** Chunk 3 (Problem Selection System) — does not exist in v2.

```
Chunk 1 (Revise) → Chunk 2 (Revise) → Chunk 3
                                           ↓
                         ┌─────────────────┼─────────────────┐
                         ↓                 ↓                 ↓
                      Chunk 4           Chunk 5           Chunk 6
                   (Execution)        (Player UI)        (Admin UI)
                         └─────────────────┼─────────────────┘
                                           ↓
                                       Chunk 7
                                (Integration + Deploy)
```

Chunks 1–3 are strictly sequential. Chunks 4, 5, 6 can be built in parallel after Chunk 3. Chunk 7 requires all prior chunks.

---

### Chunk 1 — Backend Foundation (REVISION REQUIRED)

**Goal:** Running FastAPI server with revised DB schema, slot-based player join, group management API.

**State:** Originally complete (14/14 tests). **Requires revision to match v2 model.**

**Files to revise:**
- `database.py` — Drop: `chosen_problem_id`, `selection_locked_at`, `selection_log`, `team_problems`. Add: `groups`, `group_problems`, `player_slot` in players, `UNIQUE(player_id, problem_id, phase)` in submissions, `group_id` FK in teams
- `routers/player.py` — Update `POST /join`: use `BEGIN IMMEDIATE` transaction, assign `player_slot` based on count, validate group is assigned. Remove `GET /team/{team_id}/problems` (replaced by assignment system)
- `routers/admin.py` — Replace `POST /admin/assign-problems` with `POST /admin/create-group` and `POST /admin/assign-group`
- `models.py` — Add `GroupCreateRequest`, `GroupCreateResponse`, `GroupAssignRequest`. Update `JoinResponse` to include `player_slot`. Remove selection-related models

**Expected outcome:** Two players can `POST /join` the same team — first gets slot 1, second gets slot 2. Concurrent joins give distinct slots. Third join returns 400. Admin can create a group with 2 problems and assign it to a team.

---

### Chunk 2 — WebSocket System (REVISION REQUIRED)

**Goal:** Clean WS system with no selection logic. `PROBLEM_ASSIGNED` replaces `SHOW_PROBLEMS`.

**State:** Originally complete (9/9 tests). **Requires revision to remove all selection references.**

**Files to revise:**
- `websocket/events.py` — Remove: `SELECTION_UPDATE`, `CHOOSE_PROBLEM`. Add: `PROBLEM_ASSIGNED` constant + payload builder. Update `build_session_restore()` to include `player_slot` and `assigned_problem`
- `websocket/player_ws.py` — Remove: `chosen_problem_id` from all DB queries. Update: `_get_player_info()` to return `player_slot`. Update: `_get_partner_info()` to return `player_slot`. Replace: `SHOW_PROBLEMS` broadcast with individual `PROBLEM_ASSIGNED` sends (each player gets only their own problem). Update: `_build_restore_data()` uses slot-based logic. Remove: `CHOOSE_PROBLEM` stub handler
- `websocket/manager.py` — No structural changes needed; `_problems_shown` guard already correct

**Expected outcome:** Second player connects → each player receives `PROBLEM_ASSIGNED` with their specific problem only. Reconnect triggers `SESSION_RESTORE` with `player_slot` + assigned problem. No `CHOOSE_PROBLEM` handling. No `SELECTION_UPDATE` emitted. Re-run WS tests, all should pass.

---

### Chunk 3 — Timer Engine and Swap System (NEW)

**Goal:** Complete backend game flow from admin START through SWAP to Part B, fully automated. Swap is slot-based.

**Dependencies:** Revised Chunks 1 + 2

**Files built:**
- `core/timer_engine.py` — `run_part_a_phase()`, `run_wait_buffer()`, `run_part_b_phase()` — async per-room; `TIMER_TICK` every 5s; `LOCK_AND_SUBMIT` trigger; marks room locked; stores drafts as final if no explicit submit
- `core/submission_handler.py` — `receive_submission()`, `auto_submit_draft()`, `compute_hash()` — uses `INSERT OR REPLACE` respecting `UNIQUE(player_id, problem_id, phase)`
- `core/swap_engine.py` — Reads `player_slot` for both players; looks up `group_problems` by `team.group_id`; uses `swap_target_position = (3 - player_slot)` formula; 10s buffer with per-second `WAIT_FOR_SWAP` ticks; sends `START_PART_B` individually
- `core/validation_engine.py` — `verify_part_a_hash()`, `verify_interface_stub()`
- `POST /admin/start` — validates all teams have 2 players with slots, then triggers timers for all rooms

**Swap engine logic (explicit):**
```
1. Query both players (slot 1, slot 2) for team
2. Fetch team.group_id → query group_problems for position 1 and position 2
3. Fetch final Part A submission for slot 1 (their problem = position 1)
4. Fetch final Part A submission for slot 2 (their problem = position 2)
5. Validate hashes for both
6. Send START_PART_B to slot 1:
     { partner_code: slot2's code, prompt: position2.part_b_prompt, problem_id: position2.problem_id }
7. Send START_PART_B to slot 2:
     { partner_code: slot1's code, prompt: position1.part_b_prompt, problem_id: position1.problem_id }
```

**Expected outcome:** Admin hits start → all rooms get `START_PART_A` → timer ticks → `LOCK` fires → 10s buffer ticks → swap executes → each player receives correct partner code in `START_PART_B`. No randomness. No selection dependency whatsoever.

---

### Chunk 4 — Code Execution Engine

**Goal:** Sandboxed code execution for Python and C++ with test case validation and scoring.

**Dependencies:** Revised Chunk 1 + Chunk 3

**Files built:**
- `runner/base_runner.py` — `RunResult` dataclass; common interface
- `runner/sandbox.py` — Subprocess environment; CPU time + memory limits; temp file cleanup
- `runner/python_runner.py` — Execute Python code against test cases; captures stdout/stderr; handles timeout
- `runner/cpp_runner.py` — Compile with g++; execute binary; per-test-case results
- After Part B final submit: validate hash → run combined code → score
- `execution_results` table populated
- `RESULT` event broadcast to room and admin
- Scoring: `(passed_tests / total_tests) * 100 + time_bonus`

**Expected outcome:** Valid code → correct score. Wrong code → test failures. Infinite loop → killed at 5s, result = timeout. Syntax error → readable compile error to client.

---

### Chunk 5 — Player Console UI

**Goal:** Complete, fully functional player-facing interface. No selection screen.

**Dependencies:** Revised Chunks 1–3

**Files built:**
- `frontend/player/index.html`
- `screens/join.js` — form, `POST /join`, open WS, displays assigned slot
- `screens/waiting.js` — partner waiting / admin waiting / swap buffer countdown
- `screens/editor.js` — Monaco editor; Part A prompt; Part B partner-code read-only panel; lock behaviour
- `screens/result.js` — score + test case breakdown table
- `websocket.js` — WS connect, reconnect with backoff, all event routing including `PROBLEM_ASSIGNED`
- `timer.js` — client countdown, syncs to server `TIMER_TICK`
- `storage.js` — IndexedDB draft save/load/clear, `DRAFT_SAVE` event

> **NOT built:** `screens/selection.js` — does not exist in this system

**Expected outcome:** Player joins → waits for partner → both receive `PROBLEM_ASSIGNED` → wait for admin start → code Part A → lock + buffer → receive partner code in Part B → submit → see score. No selection step anywhere. Reconnect at each phase works correctly.

---

### Chunk 6 — Admin Dashboard UI

**Goal:** Fully functional admin control panel with group/team setup, live monitoring, leaderboard.

**Dependencies:** Revised Chunks 1–3 for backend; Chunk 5 for design reference

**Files built:**
- `frontend/admin/index.html`
- `setup.js` — Create group (2 problems); create team; assign group to team; display Team IDs with copy
- `monitor.js` — Live room grid: connection status, slot assignment status, submission status per player
- `controls.js` — Start All (ready-check gate); Reset Round; Force Lock
- `leaderboard.js` — Ranked table; updates on `RESULT` events
- `websocket.js` — Admin WS with key auth; routes status updates

**Expected outcome:** Admin creates groups, creates teams, assigns groups, distributes Team IDs, monitors all teams live, starts round, watches progress, views final leaderboard — without touching terminal.

---

### Chunk 7 — Integration, Backup, and Deployment

**Goal:** System runs reliably on LAN, survives failures, passes full end-to-end test.

**Dependencies:** All prior chunks (1–6) complete

**Files built:**
- `scripts/setup_lan.sh` — static IP, DNSMasq config, firewall rules
- `scripts/deploy.sh` — uvicorn production start, backup cron
- `scripts/backup.sh` — DB snapshot every 60s, rsync to standby
- `scripts/watchdog.py` — monitor and auto-restart main server
- SQLite WAL mode verified in production

**End-to-end checklist (7 items):**
1. Two teams, four players, complete a full round on separate machines
2. Disconnect one player mid-Part A; verify reconnect restores state and assigned problem
3. Two players join same team simultaneously; verify exactly one gets slot 1, other gets slot 2
4. Submit code with compilation error; verify error message reaches client
5. Submit infinitely looping code; verify timeout kills it
6. Admin resets round; verify all state clears correctly
7. Run a second round immediately after reset

> **Removed from v1 checklist item 3:** "Both players attempt same problem simultaneously" — cannot occur in v2

**Expected outcome:** System runs for a full simulated event session with no manual server intervention.

---

## 11. File Structure Reference

```
exchange-the-code/
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── database.py              -- REVISED: groups, group_problems, player_slot
│   ├── models.py                -- REVISED: GroupCreateRequest, GroupAssignRequest; no selection models
│   ├── routers/
│   │   ├── player.py            -- REVISED: slot-based join with BEGIN IMMEDIATE
│   │   ├── submit.py            -- REST fallback submit
│   │   └── admin.py             -- REVISED: create-group, assign-group; NO assign-problems
│   ├── websocket/
│   │   ├── manager.py           -- MINOR REVISION: per-player PROBLEM_ASSIGNED send helper
│   │   ├── events.py            -- REVISED: PROBLEM_ASSIGNED added; CHOOSE_PROBLEM, SELECTION_UPDATE removed
│   │   ├── player_ws.py         -- REVISED: no chosen_problem_id; slot-based PROBLEM_ASSIGNED
│   │   └── admin_ws.py          -- UNCHANGED
│   ├── core/
│   │   ├── room_manager.py      -- REVISED: assign_group_to_team; no assign_problems_to_team
│   │   ├── timer_engine.py      -- NEW (Chunk 3)
│   │   ├── swap_engine.py       -- NEW (Chunk 3) -- slot-based
│   │   ├── submission_handler.py -- NEW (Chunk 3)
│   │   └── validation_engine.py  -- NEW (Chunk 3)
│   │   [NO selection_manager.py]
│   ├── runner/
│   │   ├── base_runner.py
│   │   ├── python_runner.py
│   │   ├── cpp_runner.py
│   │   └── sandbox.py
│   └── problems/
│       ├── problem_loader.py
│       └── data/
│           ├── p001.json
│           └── p002.json
├── frontend/
│   ├── player/
│   │   ├── index.html
│   │   ├── screens/
│   │   │   ├── join.js
│   │   │   ├── waiting.js        [NO selection.js]
│   │   │   ├── editor.js
│   │   │   └── result.js
│   │   ├── websocket.js
│   │   ├── timer.js
│   │   └── storage.js
│   └── admin/
│       ├── index.html
│       ├── setup.js              -- Group + team creation
│       ├── monitor.js
│       ├── controls.js
│       ├── leaderboard.js
│       └── websocket.js
├── scripts/
│   ├── setup_lan.sh
│   ├── deploy.sh
│   ├── backup.sh
│   └── watchdog.py
├── docs/
│   ├── SYSTEM_V2.md              -- This document (authoritative)
│   ├── TASKS.md                  -- Updated task checklist
│   └── CHANGE_SUMMARY.md        -- v1→v2 change log
├── .env
├── requirements.txt
└── README.md
```

---

## 12. Cross-Verification (v2)

- **Game flow ↔ DB:** `player_slot` is the single source of truth for assignment. Written once at join (in a transaction). Read by swap engine and WS. No ambiguity.
- **Swap logic ↔ DB:** `swap_target_position = (3 - player_slot)` is explicit, reversible, deterministic. Swap engine reads `group_problems.position` — no random element.
- **WS events ↔ DB:** `PROBLEM_ASSIGNED` built from `group_problems WHERE position = player.player_slot`. `SESSION_RESTORE` rebuilds same. Consistent.
- **No selection orphans:** `CHOOSE_PROBLEM`, `SELECTION_UPDATE`, `selection_log`, `team_problems`, `chosen_problem_id`, `selection_locked_at`, `selection_manager.py`, `screens/selection.js` — none exist anywhere in v2.
- **Race condition handled:** `BEGIN IMMEDIATE` is the only mechanism writing `player_slot`. SQLite serializes these writes. Concurrent joins cannot produce duplicate slots.
- **PROBLEM_ASSIGNED guard:** `_problems_shown` set in `ConnectionManager` prevents duplicate sends on reconnect.
- **DB integrity:** `UNIQUE(group_id, position)` enforces exactly 2 problems per group. `UNIQUE(player_id, problem_id, phase)` prevents duplicate final submissions.
- **0 contradictions found.**

---
*Document v2.0 — Supersedes v1 in all respects. Selection system is fully removed.*
*Single source of truth for all chunk-by-chunk development from here forward.*
