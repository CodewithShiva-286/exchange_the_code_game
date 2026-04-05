"""
models.py — v2 Pydantic request/response models

Changes from v1:
- REMOVED: ProblemAssignRequest (assign-problems endpoint gone)
- ADDED:   GroupCreateRequest, GroupAssignRequest
- UPDATED: JoinResponse now includes player_slot
- ADDED:   AssignedProblemDetail (what a player receives in ASSIGNED event)
"""

from pydantic import BaseModel, Field
from typing import List, Optional


# ── Admin Endpoints ───────────────────────────────────────────────────────────

class TeamCreateRequest(BaseModel):
    team_id: str = Field(..., min_length=1, description="Unique alphanumeric team identifier")

class TeamCreateResponse(BaseModel):
    status: str
    team_id: str

class GroupCreateRequest(BaseModel):
    group_id: str = Field(..., min_length=1, description="Unique group identifier (e.g. GROUP-A)")
    problem_ids: List[str] = Field(
        ...,
        min_length=2,
        max_length=2,
        description="Exactly 2 problem IDs: [position_1_problem, position_2_problem]"
    )

class GroupCreateResponse(BaseModel):
    status: str
    group_id: str

class GroupAssignRequest(BaseModel):
    team_id: str = Field(..., min_length=1, description="Team to assign the group to")
    group_id: str = Field(..., min_length=1, description="Group to assign")

class TeamReadyStatus(BaseModel):
    team_id: str
    connected_players: int
    ready: bool

class ReadyCheckResponse(BaseModel):
    teams: List[TeamReadyStatus]

class StandardResponse(BaseModel):
    status: str
    message: Optional[str] = None


# ── Player Endpoints ──────────────────────────────────────────────────────────

class JoinRequest(BaseModel):
    team_id: str = Field(..., min_length=1, description="Team ID to join")
    name: str = Field(..., min_length=1, description="Player alias/name")

class JoinResponse(BaseModel):
    status: str
    session_token: str
    team_id: str
    player_id: int
    player_slot: int  # 1 = first joiner, 2 = second joiner


# ── Problem Models ────────────────────────────────────────────────────────────

class ProblemSummary(BaseModel):
    id: str
    title: str
    description: str

class ProblemDetail(ProblemSummary):
    part_a_prompt: str
    part_b_prompt: str
    interface_stub: str
    language: str

class AssignedProblemDetail(BaseModel):
    """Sent to a player in the ASSIGNED WS event — their specific problem."""
    id: str
    title: str
    description: str
    part_a_prompt: str
    interface_stub: str
    language: str
    # Part B prompt intentionally omitted (revealed only at swap)


# ── Code Exchange Endpoints ───────────────────────────────────────────────────

class SubmitCodeRequest(BaseModel):
    team_id: str = Field(..., min_length=1, description="Team ID the player belongs to")
    player: str = Field(..., pattern="^[AB]$", description="Player identifier: 'A' or 'B'")
    problem_id: str = Field(..., min_length=1, description="Problem being solved")
    code: str = Field(..., description="Source code submitted by the player")

class SubmitCodeResponse(BaseModel):
    status: str
    message: str

class PartnerCodeResponse(BaseModel):
    status: str
    code: Optional[str] = None
    message: Optional[str] = None
