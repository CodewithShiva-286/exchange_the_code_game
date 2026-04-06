"""
websocket/events.py — v2 single source of truth for all WS event names + payload builders.

Changes from v1:
- REMOVED: SHOW_PROBLEMS, SELECTION_UPDATE (no selection system)
- REMOVED: CHOOSE_PROBLEM (client → server, no player choice)
- ADDED:   ASSIGNED (server → each player, their specific problem)
"""

# ─── Server → Client Events ───────────────────────────────────────────────────

ASSIGNED        = "ASSIGNED"         # Each player's deterministic problem assignment
PARTNER_JOINED  = "PARTNER_JOINED"   # Notifies first player when partner connects
CONNECTED       = "CONNECTED"        # Confirms WS connection to player
SESSION_RESTORE = "SESSION_RESTORE"  # Full state restore on reconnect
START_PART_A    = "START_PART_A"     # Admin triggers Part A (includes prompt + timer)
TIMER_TICK      = "TIMER_TICK"       # Keep client timers synced every 5s
LOCK_AND_SUBMIT = "LOCK_AND_SUBMIT"  # Part A timer expired; freeze editor
WAIT_FOR_SWAP   = "WAIT_FOR_SWAP"    # 10s buffer countdown after lock
START_PART_B    = "START_PART_B"     # Partner's Part A code + Part B prompt
END_GAME        = "END_GAME"         # Part B timer expired; freeze editor, execution starts
RUN_OUTPUT      = "RUN_OUTPUT"       # Result of a RUN (sample test cases) request
RESULT          = "RESULT"           # Final score + test case breakdown
ERROR           = "ERROR"            # Server error; includes code + retry flag
PONG            = "PONG"             # Heartbeat response

# ─── Client → Server Events ───────────────────────────────────────────────────

PING         = "PING"          # Heartbeat; server responds with PONG
DRAFT_SAVE   = "DRAFT_SAVE"    # Auto-save during coding (every 10s)
FINAL_SUBMIT = "FINAL_SUBMIT"  # Final code submission on lock
RUN_CODE     = "RUN_CODE"      # Run code against sample test cases

# ─── Admin Events ─────────────────────────────────────────────────────────────

ADMIN_CONNECTED     = "ADMIN_CONNECTED"
ADMIN_STATUS_UPDATE = "ADMIN_STATUS_UPDATE"
ADMIN_TEAM_UPDATE   = "ADMIN_TEAM_UPDATE"


# ─── Payload Builders ─────────────────────────────────────────────────────────

def build_event(event_type: str, data: dict = None) -> dict:
    """Standard envelope: { event: str, data: dict }"""
    return {"event": event_type, "data": data or {}}


def build_connected(player_id: int, team_id: str, player_name: str) -> dict:
    return build_event(CONNECTED, {
        "player_id": player_id,
        "team_id": team_id,
        "player_name": player_name,
    })


def build_partner_joined(partner_name: str) -> dict:
    return build_event(PARTNER_JOINED, {"partner_name": partner_name})


def build_assigned(player_slot: int, problem: dict, partner_title: str) -> dict:
    """
    Sent individually to each player when both WS-connect.
    `problem` contains: id, title, description, part_a_prompt, interface_stub, language
    `partner_title` is just the name of the partner's problem (context only).
    """
    return build_event(ASSIGNED, {
        "player_slot": player_slot,
        "assigned_problem": problem,
        "partner_problem_title": partner_title,
    })


def build_session_restore(phase: str, data: dict) -> dict:
    return build_event(SESSION_RESTORE, {"phase": phase, **data})


def build_error(code: str, message: str, retry: bool = False) -> dict:
    return build_event(ERROR, {"code": code, "message": message, "retry": retry})


def build_pong() -> dict:
    return build_event(PONG, {})


def build_admin_status(teams: list) -> dict:
    return build_event(ADMIN_STATUS_UPDATE, {"teams": teams})


def build_start_part_a(duration_seconds: int) -> dict:
    return build_event(START_PART_A, {"duration_seconds": duration_seconds})


def build_timer_tick(remaining_seconds: int, phase: str) -> dict:
    return build_event(TIMER_TICK, {"remaining_seconds": remaining_seconds, "phase": phase})


def build_lock_and_submit() -> dict:
    return build_event(LOCK_AND_SUBMIT, {})


def build_wait_for_swap(remaining_seconds: int) -> dict:
    return build_event(WAIT_FOR_SWAP, {"remaining_seconds": remaining_seconds})


def build_start_part_b(duration_seconds: int, partner_code: str, part_b_prompt: str, full_problem: dict) -> dict:
    return build_event(START_PART_B, {
        "duration_seconds": duration_seconds,
        "partner_code": partner_code,
        "part_b_prompt": part_b_prompt,
        "full_problem": full_problem
    })


def build_end_game() -> dict:
    return build_event(END_GAME, {})
