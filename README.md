# Exchange the Code - Platform Backend

A real-time, zero-trust competitive coding platform built specifically for LAN-based Techfests. It leverages a robust **FastAPI** backend with **async SQLite (aiosqlite)**, utilizing WAL mode for extreme concurrency and zero locks during problem dispatching and atomic team swapping.

---

## 🏗️ Architecture & Progress

The platform development is split into 8 precise "chunks". Currently, **Chunks 1 and 2 are 100% complete and fully tested**.

### ✅ Chunk 1: Backend Foundation
- Fully normalized relational database schema via raw `aiosqlite` SQL using WAL mode.
- Complete strict Pydantic model configurations.
- REST endpoints for **admin** team creation and exact 2-problem assignments.
- REST endpoints for **players** to join a team, limited precisely to 2 players per team.
- Built-in static problem JSON loader with local in-memory dict caching and auto-seeding to the DB.
- Comprehensive `pytest` coverage enforcing validation errors and database constraints (14/14 tests passing).

### ✅ Chunk 2: WebSocket Infrastructure
- High-performance, Team-based `ConnectionManager`.
- Validation of session tokens directly from the DB on every single WebSocket request (rejects immediately with 4001 if invalid).
- Anti-ghosting algorithm: safely forces old connections to close when a duplicate player joins.
- Auto-triggers (`SHOW_PROBLEMS` only firing once per team) when both players successfully establish a connection.
- Strict grouping of WebSockets avoiding `rooms`, explicitly using `team_id`.
- Robust reconnect tolerance returning `SESSION_RESTORE`. Safe disconnect cleanup protecting fresh references.
- Dedicated `ws/admin` dashboard connection.
- Verified without affecting any Chunk 1 progress (9/9 tests passing).

---

## 🛠️ Project Structure

```
.
├── backend/
│   ├── .env                    # Configuration (host, port, admin keys, timer defaults)
│   ├── main.py                 # FastAPI application and lifespan definitions
│   ├── config.py               # Pydantic Settings implementation
│   ├── database.py             # SQLite WAL initialization and db dependencies
│   ├── models.py               # Request/Response data shapes validation
│   ├── problems/
│   │   ├── data/               # Raw JSON files describing code problems
│   │   └── problem_loader.py   # Code loading, memory caching, and DB seeding
│   ├── routers/
│   │   ├── admin.py            # REST endpoints: Team configurations and assignments
│   │   └── player.py           # REST endpoints: Joining and querying problems
│   ├── websocket/
│   │   ├── admin_ws.py         # WS endpoint: Admin Dashboard control
│   │   ├── player_ws.py        # WS endpoint: Player interactions and gameplay
│   │   ├── events.py           # Central source-of-truth for WebSocket payload formats
│   │   └── manager.py          # Central WS routing, broadcasting, and session logic
│   └── tests/
│       ├── test_chunk1.py      # Regression tests for foundational REST schemas
│       └── test_chunk2.py      # WS lifecycle tests, token validations, reconnect checks
└── docs/                       # Design guides, game flow outlines, and task tracking
```

---

## 🚀 Quick Setup & Local Development

### Prerequisites
- Python 3.9+
- Basic knowledge of REST + WebSockets

### 1. Installation & Core Dependencies
Clone the repository and install the Python dependencies into a virtual environment. The platform relies on the following core technologies listed in `backend/requirements.txt`:
- **fastapi & uvicorn**: Web framework and async ASGI server.
- **aiosqlite**: Asynchronous SQLite driver for non-blocking WAL database interactions.
- **pydantic & pydantic-settings**: Strict data validation and `.env` parsing.
- **pytest, pytest-asyncio & httpx**: The testing suite for synchronous/asynchronous behavioral validation.

```sh
# Create a virtual environment
python -m venv .venv

# Activate it
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install all required packages
pip install -r backend/requirements.txt
```

### 2. Configuration
The application relies on `backend/.env` for secrets and timers. Ensure your `.env` contains:
```env
# Networking
LAN_HOST=0.0.0.0
LAN_PORT=8000

# Security (Passed via Admin requests)
ADMIN_KEY="techfest-admin-secret-2026"

# Timers (In seconds)
PART_A_DURATION=900
PART_B_DURATION=900
BUFFER_DURATION=10

# DB
DATABASE_PATH=exchange.db
```

### 3. Run the Application
Launch the server. It will automatically load the JSON problems directly into the database and memory.
```sh
# Add the project directory to PYTHONPATH to resolve standard imports
export PYTHONPATH=$(pwd) # (or $env:PYTHONPATH="..." on Windows)

python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```
You can now access the interactive API docs at: `http://localhost:8000/docs`.

### 4. Running the Tests
Strict testing is in place for chunk development stability. Run the pytest suite without cache to avoid Windows lock issues.
```sh
python -m pytest backend/tests/ -v
```
