"""
database.py — v2 schema (group-based deterministic assignment)

Changes from v1:
- REMOVED: team_problems table, selection_log table
- REMOVED: chosen_problem_id, selection_locked_at columns from players
- ADDED:   groups table, group_problems table (position 1|2)
- ADDED:   player_slot column in players (1 or 2, set at join time)
- ADDED:   group_id, status, current_phase columns in teams
- UPDATED: submissions → UNIQUE(player_id, problem_id, phase) constraint
"""

import aiosqlite
from .config import settings


async def get_db():
    db = await aiosqlite.connect(settings.database_path, timeout=15.0)
    await db.execute("PRAGMA journal_mode=WAL;")
    await db.execute("PRAGMA foreign_keys=ON;")
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()


async def init_db():
    async with aiosqlite.connect(settings.database_path, timeout=15.0) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA foreign_keys=ON;")

        # ── Problems table (unchanged) ────────────────────────────────────
        await db.execute("""
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
        """)

        # ── Groups table (NEW) ────────────────────────────────────────────
        # A group is a named pair of problems at fixed positions.
        # Reusable: same group can be assigned to multiple teams.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ── Group Problems table (NEW) ────────────────────────────────────
        # Exactly 2 problems per group, at positions 1 and 2.
        # position 1 → assigned to player_slot 1
        # position 2 → assigned to player_slot 2
        await db.execute("""
            CREATE TABLE IF NOT EXISTS group_problems (
                group_id TEXT NOT NULL,
                problem_id TEXT NOT NULL,
                position INTEGER NOT NULL CHECK (position IN (1, 2)),
                FOREIGN KEY (group_id) REFERENCES groups (group_id) ON DELETE CASCADE,
                FOREIGN KEY (problem_id) REFERENCES problems (id) ON DELETE CASCADE,
                UNIQUE(group_id, position),
                UNIQUE(group_id, problem_id)
            )
        """)

        # ── Teams table (UPDATED) ─────────────────────────────────────────
        # Added: group_id FK, status, current_phase
        await db.execute("""
            CREATE TABLE IF NOT EXISTS teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id TEXT UNIQUE NOT NULL,
                group_id TEXT,
                status TEXT DEFAULT 'waiting',
                current_phase TEXT DEFAULT 'waiting',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (group_id) REFERENCES groups (group_id)
            )
        """)

        # ── Players table (UPDATED) ───────────────────────────────────────
        # Added:   player_slot (1 or 2, assigned atomically at join)
        # Removed: chosen_problem_id, selection_locked_at
        await db.execute("""
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id TEXT NOT NULL,
                name TEXT NOT NULL,
                session_token TEXT UNIQUE NOT NULL,
                player_slot INTEGER CHECK (player_slot IN (1, 2)),
                connection_status TEXT DEFAULT 'offline',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (team_id) REFERENCES teams (team_id) ON DELETE CASCADE
            )
        """)

        # ── Submissions table (UPDATED) ───────────────────────────────────
        # Added: UNIQUE(player_id, problem_id, phase) to prevent duplicate finals
        await db.execute("""
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
                UNIQUE(player_id, problem_id, phase)
            )
        """)

        # ── Execution Results table (unchanged) ───────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS execution_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id TEXT NOT NULL,
                problem_id TEXT NOT NULL,
                status TEXT NOT NULL,
                score FLOAT NOT NULL,
                test_case_breakdown TEXT NOT NULL,
                execution_time FLOAT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (team_id) REFERENCES teams (team_id) ON DELETE CASCADE,
                FOREIGN KEY (problem_id) REFERENCES problems (id) ON DELETE CASCADE
            )
        """)

        # ── Test Cases table (unchanged) ──────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS test_cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                problem_id TEXT NOT NULL,
                input_data TEXT NOT NULL,
                expected_output TEXT NOT NULL,
                is_visible BOOLEAN DEFAULT 0,
                FOREIGN KEY (problem_id) REFERENCES problems (id) ON DELETE CASCADE
            )
        """)

        # ── Team Scores table (NEW) ───────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS team_scores (
                team_id TEXT,
                round INTEGER,
                score INTEGER,
                total_score INTEGER,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (team_id) REFERENCES teams (team_id) ON DELETE CASCADE
            )
        """)

        await db.commit()
