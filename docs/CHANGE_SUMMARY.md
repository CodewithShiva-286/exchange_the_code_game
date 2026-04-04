# Exchange The Code: v1 → v2 Change Summary

> This document records every deliberate change made when switching from the
> selection-based model (v1) to the group-based deterministic assignment model (v2).

---

## Change Summary Table

| Area | Old (v1) | New (v2) | Reason |
|------|----------|----------|--------|
| **Core game model** | Players select from 2 problems (choice-based) | System assigns problems automatically by join order (`player_slot`) | Eliminates conflicts, race conditions, and complexity |
| **Problem grouping** | `team_problems` junction table (team_id → problem_id list) | `groups` + `group_problems` tables; each group has exactly 2 problems at positions 1 and 2 | Explicit, queryable structure; enforces exactly-2 constraint at DB level |
| **Admin setup** | Create team → `POST /admin/assign-problems` with list of 2 problem IDs | Create group (2 problems) → Create team → `POST /admin/assign-group` | Decouples group definition from team; groups reusable |
| **Player join** | `POST /join` inserts player; no slot | `POST /join` uses `BEGIN IMMEDIATE` transaction; assigns `player_slot` 1 or 2 based on join order | Prevents race condition; slot is immutable and deterministic |
| **players table** | Has `chosen_problem_id`, `selection_locked_at`; no `player_slot` | Has `player_slot`; no `chosen_problem_id`, no `selection_locked_at` | Slot replaces chosen_problem_id as the assignment mechanism |
| **teams table** | No `group_id` column | Has `group_id FK → groups.id` | Team now linked to a group, not loose problems |
| **groups table** | Does not exist | `groups (id, name, created_at)` | New concept: named collection of exactly 2 problems |
| **group_problems table** | Does not exist | `group_problems (group_id, problem_id, position)` with `UNIQUE(group_id, position)` | Enforces 2 problems per group; makes position queryable |
| **team_problems table** | Used to link problems to teams | Removed entirely | Replaced by groups system; was flat, had no ordering/position |
| **selection_log table** | Append-only audit trail of all selection attempts | Removed entirely | No selection phase → no audit needed |
| **submissions table** | No UNIQUE constraint across (player_id, problem_id, phase) | `UNIQUE(player_id, problem_id, phase)` added | Prevents duplicate final submissions from race conditions |
| **Phase 2 (after join)** | `SHOW_PROBLEMS` → player sees 2 cards → clicks to claim → `CHOOSE_PROBLEM` → `SELECTION_UPDATE` | `PROBLEM_ASSIGNED` sent individually to each player with their specific problem — no interaction required | Removes 3-step interaction; fully automatic |
| **WS event: SHOW_PROBLEMS** | Sent to both players in room; both see 2 problems to choose from | Removed | Replaced by PROBLEM_ASSIGNED |
| **WS event: PROBLEM_ASSIGNED** | Did not exist | Sent individually to each player; includes only their assigned problem and its position | Clean, direct, no ambiguity |
| **WS event: SELECTION_UPDATE** | Broadcast after every selection attempt; showed both players' choices | Removed entirely | No selection → no update needed |
| **WS event: CHOOSE_PROBLEM** | Client → Server; player claims a problem | Removed entirely | No player choice in v2 |
| **WS event: SESSION_RESTORE** | Included current selection state and `chosen_problem_id` | Includes `player_slot` and `assigned_problem`; no selection state | Simpler restore; slot is permanent, problem is deterministic |
| **WS event: CONNECTED** | Included player_id, team_id, name | Also includes `player_slot` | Client needs slot to know which problem it will receive |
| **Swap logic** | Based on `chosen_problem_id` — queried from players table | Based on `player_slot` and `group_problems.position` — formula: `swap_target_position = (3 - player_slot)` | Slot-based swap is deterministic; no dependency on mutable selection state |
| **selection_manager.py** | `core/selection_manager.py` — atomic selection, conflict prevention, audit log | Removed entirely — file does not exist in v2 | No selection system → no selection manager |
| **screens/selection.js** | Frontend screen: 2 problem cards, claim button, conflict error display | Removed — file does not exist in v2 | No selection screen needed |
| **Admin ready-check** | Teams were "ready" when both players had selected problems | Teams are "ready" when both players have joined (slots assigned) | Selection not required; assignment is automatic |
| **Chunk 3 (v1: Selection)** | Dedicated chunk for atomic selection, conflict prevention, CHOOSE_PROBLEM routing | Removed from chunk plan | Entire phase eliminated |
| **Chunk 3 (v2: Timer+Swap)** | Was Chunk 4 in v1 | Promoted to Chunk 3 — runs immediately after WS system | No selection chunk between WS and Timer now |
| **Total chunks** | 8 chunks | 7 chunks | Selection chunk removed; others renumbered |
| **Join race condition** | Two simultaneous joins could produce no slot conflict (no slots existed) | Handled by `BEGIN IMMEDIATE` transaction; exactly one gets slot 1, one gets slot 2 | New risk introduced by slot system; mitigated at DB level |
| **Duplicate PROBLEM_ASSIGNED** | `SHOW_PROBLEMS` could fire multiple times on reconnect without guard | `_problems_shown` set in ConnectionManager guards against repeat — already implemented | Existing guard repurposed for new event name |
| **Stale WS connections** | Stale disconnects could remove active connection from registry | `disconnect_player()` checks WS reference before removing — already implemented | Existing fix maintained |
| **Duplicate WS connections** | Same player in multiple tabs caused ghost connections | Old WS closed with code 4010 before new one registered — already implemented | Existing fix maintained |
| **Invalid token on WS** | Could cause state changes before rejection | Accept then immediately close with code 4001 before any state change — already implemented | Existing fix maintained |

---

## What Was Already Correctly Implemented (Kept Unchanged)

These mechanisms were built correctly in v1 and carry forward without modification:

| Mechanism | Location | Status |
|-----------|----------|--------|
| Duplicate connection handling (old WS → code 4010) | `websocket/manager.py:connect_player()` | ✅ Kept |
| Stale disconnect guard (WS reference check) | `websocket/manager.py:disconnect_player()` | ✅ Kept |
| `_problems_shown` guard (fires once per team) | `websocket/manager.py` | ✅ Kept, repurposed for PROBLEM_ASSIGNED |
| Invalid token rejection (code 4001) | `websocket/player_ws.py` | ✅ Kept |
| Admin WS key validation | `websocket/admin_ws.py` | ✅ Kept, unchanged |
| SHA-256 submission hashing | `core/submission_handler.py` (planned) | ✅ Design unchanged |
| Part A hash verification before execution | `core/validation_engine.py` (planned) | ✅ Design unchanged |
| SQLite WAL mode + foreign key enforcement | `database.py` | ✅ Kept |
| Max 2 players per team validation at REST level | `routers/player.py` | ✅ Kept, now also enforced in transaction |
| Session token UUID generation at join | `routers/player.py` | ✅ Kept |

---

## Migration Impact on Existing Code

| File | Action Required | Priority |
|------|----------------|----------|
| `backend/database.py` | Rewrite schema: new tables, removed tables, updated columns | **HIGH — blocks everything** |
| `backend/models.py` | Add group models; update JoinResponse; remove selection models | **HIGH — blocks router tests** |
| `backend/routers/admin.py` | Replace `assign-problems` with `create-group` + `assign-group` | **HIGH** |
| `backend/routers/player.py` | Rewrite `POST /join` with transaction + slot logic | **HIGH** |
| `backend/websocket/events.py` | Remove CHOOSE_PROBLEM, SELECTION_UPDATE; add PROBLEM_ASSIGNED | **HIGH** |
| `backend/websocket/player_ws.py` | Remove chosen_problem_id refs; slot-based PROBLEM_ASSIGNED send | **HIGH** |
| `backend/websocket/manager.py` | No logic changes; verify existing guards work correctly | LOW |
| `backend/websocket/admin_ws.py` | No changes required | NONE |
| `backend/tests/test_chunk1.py` | Update tests for new schema, new endpoints, slot assignment | **HIGH** |
| `backend/tests/test_chunk2.py` | Update tests for PROBLEM_ASSIGNED, SESSION_RESTORE with slot | **HIGH** |

---

## Entities That Must Never Appear in v2

If any of the following appear in any new code, file, or comment — it is a v1 regression:

- `chosen_problem_id`
- `selection_locked_at`
- `CHOOSE_PROBLEM`
- `SELECTION_UPDATE`
- `SHOW_PROBLEMS` (as a selection prompt showing multiple problems)
- `selection_manager`
- `selection_log`
- `team_problems`
- `attempt_selection()`
- `all_teams_ready()` based on selection state
- `screens/selection.js`
- "ALREADY_CLAIMED" error code
- Any logic that allows a player to choose their problem

---

*Change summary for v1 → v2 redesign. Compiled from full codebase analysis.*
