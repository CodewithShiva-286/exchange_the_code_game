# Exchange The Code — System Document v2

> **Version:** 2.0 — Group-Based Deterministic Assignment  
> **Replaces:** v1 (Selection-Based Model)  
> **Status:** Authoritative — all future chunks must use this as the single source of truth.

---

## 1. System Overview

**Exchange the Code** is a real-time, relay-style competitive coding platform for offline college techfests. Runs entirely on a LAN — no internet required.

### Core Mechanic
- Player in slot 1 writes Part A of Problem at group position 1
- Player in slot 2 writes Part A of Problem at group position 2
- After timer lock: code is swapped
- Assignment is **deterministic** — driven by join order (player_slot), not player choice

### Roles
- **Admin** — Creates teams, assigns problem groups, starts the round, monitors all teams live
- **Player** — Joins a team, gets auto-assigned a problem based on slot, codes, swaps, submits

---

## 2. Game Flow

```
JOIN → WAIT_FOR_PARTNER → ASSIGNED → ADMIN_START
     → PART_A → LOCK → WAIT_BUFFER → SWAP → PART_B → EXECUTE → RESULTS
```

> **KEY CHANGE from v1:** Phase 2 (Selection) is completely removed.
> Problems are assigned deterministically when players join. No choice, no conflict, no selection UI.

---

### Phase 0 — Setup (Admin only)
- Admin creates teams; assigns a **group** (NOT individual problems) to each team
- A group contains exactly 2 problems at fixed positions (position 1 and position 2)
- Team IDs distributed to players

### Phase 1 — Join
- Player enters name + Team ID → `POST /join`
- Server atomically assigns `player_slot` (1 = first joiner, 2 = second joiner)
- Server returns: session token + player_id + assigned slot
- Player opens WS at `/ws/{team_id}/{player_id}`

### Phase 2 — Assignment (replaces Selection entirely)
- When BOTH players WS-connected, server sends `ASSIGNED` to EACH player individually
- `ASSIGNED` payload: their assigned problem (full detail) + partner's problem title only
- No player choice. No conflict possible. Team immediately moves to `ready`.

### Phases 3–9 — Coding, Lock, Swap, Execution, Results
*(Unchanged from v1 except swap logic — see Section 6)*

---

## 3. Database Schema (v2)

### NEW: `groups` table
```sql
CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### NEW: `group_problems` table
```sql
CREATE TABLE IF NOT EXISTS group_problems (
    group_id TEXT NOT NULL,
    problem_id TEXT NOT NULL,
    position INTEGER NOT NULL CHECK (position IN (1, 2)),
    FOREIGN KEY (group_id) REFERENCES groups (group_id) ON DELETE CASCADE,
    FOREIGN KEY (problem_id) REFERENCES problems (id) ON DELETE CASCADE,
    UNIQUE(group_id, position),        -- max 2 per group, positions unique
    UNIQUE(group_id, problem_id)       -- no duplicate problems in one group
);
```

### UPDATED: `teams` table
```sql
CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id TEXT UNIQUE NOT NULL,
    group_id TEXT,                     -- replaces team_problems junction
    status TEXT DEFAULT 'waiting',
    current_phase TEXT DEFAULT 'waiting',
    FOREIGN KEY (group_id) REFERENCES groups (group_id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### UPDATED: `players` table
```sql
CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id TEXT NOT NULL,
    name TEXT NOT NULL,
    session_token TEXT UNIQUE NOT NULL,
    player_slot INTEGER CHECK (player_slot IN (1, 2)),   -- NEW: join order slot
    connection_status TEXT DEFAULT 'offline',
    -- REMOVED: chosen_problem_id
    -- REMOVED: selection_locked_at
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (team_id) REFERENCES teams (team_id) ON DELETE CASCADE
);
```

### UPDATED: `submissions` table (stricter constraint)
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
    FOREIGN KEY (player_id) REFERENCES players (id) ON DELETE CASCADE,
    FOREIGN KEY (problem_id) REFERENCES problems (id) ON DELETE CASCADE,
    UNIQUE(player_id, problem_id, phase)   -- prevents duplicate final submissions
);
```

### REMOVED tables
- `team_problems` — replaced by `groups` + `group_problems`
- `selection_log` — no selection system exists

### Unchanged tables
- `problems`, `test_cases`, `execution_results`

---

## 4. Assignment Logic

### Slot Assignment at `POST /join` (atomic)
```
First player to join team  → player_slot = 1
Second player to join team → player_slot = 2
3rd attempt                → 400 Team Full
```

Race condition fix — runs inside a DB transaction:
```sql
BEGIN TRANSACTION;
SELECT COUNT(*) FROM players WHERE team_id = ?;
-- 0 → slot=1 | 1 → slot=2 | 2 → reject
INSERT INTO players (..., player_slot) VALUES (..., ?);
COMMIT;
```

### Problem Resolution (from slot)
```
player_slot 1 → group_problems WHERE group_id = team.group_id AND position = 1
player_slot 2 → group_problems WHERE group_id = team.group_id AND position = 2
```

### Swap Mapping (Phase 6)
```
Slot 1 writes problem at position 1 (Part A)
Slot 2 writes problem at position 2 (Part A)

After swap:
  Slot 1 → gets slot 2's Part A code + problem position 2's Part B prompt
  Slot 2 → gets slot 1's Part A code + problem position 1's Part B prompt
```

---

## 5. WebSocket Events (v2)

### Server → Client

| Event | Trigger | Notes |
|-------|---------|-------|
| `CONNECTED` | WS connect accepted | Player info |
| `PARTNER_JOINED` | 2nd player connects | Notify 1st player |
| `ASSIGNED` | Both players WS-connected | Each gets their problem (replaces SHOW_PROBLEMS) |
| `START_PART_A` | Admin start | Problem prompt + timer |
| `TIMER_TICK` | Every 5s | Sync client timers |
| `LOCK_AND_SUBMIT` | Timer expires | Freeze editor |
| `WAIT_FOR_SWAP` | After lock, 10s countdown | Buffer ticks |
| `START_PART_B` | After buffer | Partner code + Part B prompt |
| `RESULT` | After execution | Score + breakdown |
| `SESSION_RESTORE` | Reconnect | Full state |
| `ERROR` | Any failure | Code + retry flag |
| `PONG` | Response to PING | Heartbeat |

**REMOVED from v1:** `SHOW_PROBLEMS`, `SELECTION_UPDATE`

### Client → Server

| Event | Purpose |
|-------|---------|
| `DRAFT_SAVE` | Persist editor content |
| `FINAL_SUBMIT` | Final code submission |
| `PING` | Heartbeat |

**REMOVED from v1:** `CHOOSE_PROBLEM`

---

## 6. Error Handling (v2)

| Scenario | Handling |
|----------|---------|
| Simultaneous joins (race condition) | Atomic DB transaction — one gets slot 1, other slot 2, guaranteed |
| 3rd player join attempt | 400 Team Full from REST layer |
| Duplicate WS (same player, two tabs) | Old WS closed (4010) before new accepted |
| Invalid session token | WS accept → close(4001) immediately |
| Disconnect during coding | SESSION_RESTORE: code + timer + phase + assignment |
| Timer fires with no submission | Server uses last DRAFT_SAVE; else submits empty stub |
| Swap fails (missing Part A) | ERROR with SWAP_FAILED sent to admin |
| Part A hash mismatch | integrity_error result; score = 0 |

---

## 7. Chunk Breakdown (v2)

| Chunk | Name | Status | Notes |
|-------|------|--------|-------|
| 1 | Backend Foundation | ✅ Done → needs DB update | Add groups/group_problems; update players |
| 2 | WebSocket System | ✅ Done → needs event update | ASSIGNED replaces SHOW_PROBLEMS |
| 3 | Assignment System | 🔄 New (replaces Chunk 3 Selection) | Slot-based assignment logic |
| 4 | Timer + Swap Engine | ⏳ Not started | Swap uses player_slot, not chosen_problem_id |
| 5 | Code Execution | ⏳ Not started | Unchanged |
| 6 | Player Console UI | ⏳ Not started | No selection screen; add assignment/waiting screen |
| 7 | Admin Dashboard | ⏳ Not started | Admin assigns groups, not individual problems |
| 8 | Integration + Deploy | ⏳ Not started | Full E2E test with new model |
