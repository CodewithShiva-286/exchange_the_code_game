# Exchange The Code — Change Summary (v1 → v2)

> This document records every architectural change made when migrating from the
> selection-based v1 model to the group-based deterministic v2 model.

---

## Change Summary Table

| Area | v1 (Old) | v2 (New) | Reason |
|------|----------|----------|--------|
| **Assignment Model** | Player chooses a problem (CHOOSE_PROBLEM) | Player is auto-assigned by join order (player_slot) | Eliminates conflict, race conditions, and selection complexity |
| **Database: teams** | No group_id, no status/phase columns | Added group_id FK, status, current_phase | Teams need to track their assigned group and current game phase |
| **Database: team_problems** | Junction table linking team ↔ 2 problems | **REMOVED** | Replaced by groups + group_problems which are reusable across teams |
| **Database: players** | chosen_problem_id, selection_locked_at columns | **REMOVED** both; added player_slot (1 or 2) | Slot is deterministic; no need to store a choice |
| **Database: groups** | Did not exist | **NEW TABLE** — group_id, created_at | Represents a named pair of problems that can be assigned to multiple teams |
| **Database: group_problems** | Did not exist | **NEW TABLE** — group_id, problem_id, position (1 or 2) | Defines which problems are in a group and at which position |
| **Database: submissions** | No uniqueness constraint on (player, problem, phase) | UNIQUE(player_id, problem_id, phase) added | Prevents duplicate final submissions corrupting results |
| **Database: selection_log** | Append-only audit log for all selection attempts | **REMOVED** | No selection system; no conflicts to audit |
| **WS Event: SHOW_PROBLEMS** | Broadcast both problems to both players | **REMOVED** | Replaced by ASSIGNED — each player gets only their own problem |
| **WS Event: ASSIGNED** | Did not exist | **NEW** — sent individually to each player with their assigned problem | Deterministic; no shared problem list needed |
| **WS Event: SELECTION_UPDATE** | Broadcast after every selection attempt | **REMOVED** | No selection system |
| **WS Event: CHOOSE_PROBLEM** | Client → Server event to claim a problem | **REMOVED** | No player choice |
| **Swap Logic** | Driven by chosen_problem_id stored in players table | Driven by player_slot ↔ group_problem.position mapping | Slot is guaranteed unique and conflict-free; chosen_problem_id is removed |
| **Chunk 3** | Selection System — atomic transaction conflict prevention, ALREADY_CLAIMED errors | **REPLACED** — Assignment System: slot assignment at join, ASSIGNED WS event | Entire concept replaced; selection manager file removed |
| **core/selection_manager.py** | Core file for atomic selection conflict handling | **DELETED/REMOVED** | No selection system |
| **POST /join response** | Returns session_token + player_id | Returns session_token + player_id + player_slot | Slot needed by client to understand assignment context |
| **POST /admin/assign-problems** | Assigns 2 individual problem IDs to a team | **REPLACED** by POST /admin/assign-group | Admin assigns a group (which contains exactly 2 problems at fixed positions) |
| **POST /admin/create-group** | Did not exist | **NEW** — creates a reusable problem group | Groups are created once and can be assigned to any team |
| **Session Restore** | Includes selection state (chosen_problem_id, selection phase) | Includes assignment (player_slot, assigned problem) | State to restore is now slot + problem, not a choice |
| **Race Condition at join** | No explicit handling needed (selection handled separately) | Atomic DB transaction at join enforces unique slot assignment | Must guarantee slot 1 ≠ slot 2 even under simultaneous joins |
| **Player console UI** | Join → Selection → Waiting → Editor → Result | Join → Waiting (for partner) → Assignment display → Editor → Result | Selection screen removed entirely |
| **Admin UI** | Assign individual problems to teams | Assign groups to teams | Simpler admin flow; group is the unit of assignment |

---

## Files Affected

### Modified
- `backend/database.py` — schema migration
- `backend/models.py` — new request/response models for groups
- `backend/routers/admin.py` — new group endpoints, remove assign-problems
- `backend/routers/player.py` — atomic slot assignment in POST /join
- `backend/websocket/events.py` — remove SHOW_PROBLEMS/SELECTION_UPDATE/CHOOSE_PROBLEM; add ASSIGNED
- `backend/websocket/player_ws.py` — ASSIGNED trigger replaces SHOW_PROBLEMS broadcast
- `backend/websocket/manager.py` — rename _problems_shown to _assigned_sent

### New Files
- `backend/core/team_manager.py` — get_assigned_problem, get_team_status, all_teams_ready
- `docs/PRD_v2.md` — authoritative new system document

### Removed/Disabled (do not build)
- `backend/core/selection_manager.py` — DO NOT CREATE
- `selection_log` DB table — DO NOT CREATE
- `team_problems` DB table — DO NOT CREATE (replaced by group_problems)

---

## Invariants That Must Hold in v2

1. `player_slot` is always 1 or 2 — never NULL for a player who has joined
2. A team has exactly 0 or 1 `group_id` assigned
3. A group has exactly 2 entries in `group_problems` (position 1 and position 2)
4. `ASSIGNED` is sent exactly once per team — only when BOTH players are WS-connected
5. Slot 1 always maps to problem at position 1; Slot 2 always maps to position 2
6. After swap: Slot 1 receives position 2 content; Slot 2 receives position 1 content
7. `UNIQUE(player_id, problem_id, phase)` is enforced at DB level in submissions
8. 3rd join attempt always returns 400 — enforced at both API and DB level
