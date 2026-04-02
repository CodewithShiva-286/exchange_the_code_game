from typing import List, Optional
import re
from pydantic import BaseModel, Field, field_validator

SAFE_TEAM_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
SAFE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9 ._\-']+$")
SAFE_PROBLEM_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


# --- ADMIN ENDPOINTS ---

class TeamCreateRequest(BaseModel):
    team_id: str = Field(..., min_length=1, max_length=32, description="Unique alphanumeric team identifier")

    @field_validator("team_id")
    @classmethod
    def validate_team_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("team_id cannot be blank")
        if not SAFE_TEAM_ID_PATTERN.fullmatch(normalized):
            raise ValueError("team_id may only contain letters, numbers, underscores, and hyphens")
        return normalized


class TeamCreateResponse(BaseModel):
    status: str
    team_id: str


class ProblemAssignRequest(BaseModel):
    team_id: str = Field(..., min_length=1, max_length=32, description="Team ID to assign problems to")
    problem_ids: List[str] = Field(..., min_length=2, max_length=2, description="Exactly 2 problem IDs per team")

    @field_validator("team_id")
    @classmethod
    def validate_team_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("team_id cannot be blank")
        if not SAFE_TEAM_ID_PATTERN.fullmatch(normalized):
            raise ValueError("team_id may only contain letters, numbers, underscores, and hyphens")
        return normalized

    @field_validator("problem_ids")
    @classmethod
    def validate_problem_ids(cls, values: List[str]) -> List[str]:
        normalized_ids: List[str] = []
        for value in values:
            normalized = value.strip()
            if not normalized:
                raise ValueError("problem_ids cannot contain blank values")
            if not SAFE_PROBLEM_ID_PATTERN.fullmatch(normalized):
                raise ValueError("problem_ids may only contain letters, numbers, underscores, and hyphens")
            normalized_ids.append(normalized)
        return normalized_ids


class StandardResponse(BaseModel):
    status: str
    message: Optional[str] = None


# --- PLAYER ENDPOINTS ---

class JoinRequest(BaseModel):
    team_id: str = Field(..., min_length=1, max_length=32, description="Team ID to join")
    name: str = Field(..., min_length=1, max_length=40, description="Player alias/name")

    @field_validator("team_id")
    @classmethod
    def validate_team_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("team_id cannot be blank")
        if not SAFE_TEAM_ID_PATTERN.fullmatch(normalized):
            raise ValueError("team_id may only contain letters, numbers, underscores, and hyphens")
        return normalized

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name cannot be blank")
        if not SAFE_NAME_PATTERN.fullmatch(normalized):
            raise ValueError("name contains unsupported characters")
        return normalized


class JoinResponse(BaseModel):
    status: str
    session_token: str
    team_id: str
    player_id: int


class ProblemSummary(BaseModel):
    id: str
    title: str
    description: str


class ProblemDetail(ProblemSummary):
    part_a_prompt: str
    part_b_prompt: str
    interface_stub: str
    language: str


class TeamProblemsResponse(BaseModel):
    team_id: str
    problems: List[ProblemSummary]
