import json
import os
import aiosqlite
from typing import Dict
from ..models import ProblemDetail
from ..config import settings

_PROBLEM_CACHE: Dict[str, ProblemDetail] = {}

def load_problems():
    """Load all JSON problems from the data directory into memory."""
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    if not os.path.exists(data_dir):
        return
    for filename in os.listdir(data_dir):
        if filename.endswith(".json"):
            filepath = os.path.join(data_dir, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                problem = ProblemDetail(**data)
                _PROBLEM_CACHE[problem.id] = problem

async def seed_problems_to_db():
    """Insert loaded problems into the DB so foreign keys on team_problems work."""
    async with aiosqlite.connect(settings.database_path, timeout=15.0) as db:
        for p in _PROBLEM_CACHE.values():
            await db.execute(
                """INSERT OR IGNORE INTO problems
                   (id, title, description, part_a_prompt, part_b_prompt, interface_stub, language)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (p.id, p.title, p.description, p.part_a_prompt, p.part_b_prompt, p.interface_stub, p.language)
            )
        await db.commit()

def get_problem(problem_id: str) -> ProblemDetail:
    """Retrieve problem details by ID."""
    return _PROBLEM_CACHE.get(problem_id)

def get_all_problems() -> Dict[str, ProblemDetail]:
    """Retrieve all loaded problems."""
    return _PROBLEM_CACHE
