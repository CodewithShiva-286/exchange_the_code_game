import contextlib
import subprocess
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

class CodeRequest(BaseModel):
    code: str
    language: str
from .database import init_db
from .problems.problem_loader import load_problems, seed_problems_to_db
from .routers import admin, player
from .websocket import player_ws, admin_ws
from .runner.execution_queue import start_worker, stop_worker

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    load_problems()
    await init_db()
    await seed_problems_to_db()
    start_worker()
    yield
    stop_worker()

app = FastAPI(title="Exchange The Code", lifespan=lifespan)

# Enable CORS so the file:// frontend can fetch the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# REST routers
app.include_router(player.router)
app.include_router(admin.router)

# WebSocket routers
app.include_router(player_ws.router)
app.include_router(admin_ws.router)

@app.get("/health")
async def health_check():
    return {"status": "ok"}

import tempfile
import os

@app.post("/run-code")
async def run_code(req: CodeRequest):
    if req.language == "python":
        try:
            result = subprocess.run(
                ["python", "-c", req.code],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                return {"error": result.stderr}
            return {"output": result.stdout}
        except subprocess.TimeoutExpired:
            return {"error": "Execution timed out (5 seconds limit)."}
        except Exception as e:
            return {"error": str(e)}
            
    elif req.language == "c++":
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                cpp_file = os.path.join(temp_dir, "temp.cpp")
                exe_file = os.path.join(temp_dir, "temp.exe")
                
                with open(cpp_file, "w") as f:
                    f.write(req.code)
                    
                # Compile C++
                compile_result = subprocess.run(
                    ["g++", cpp_file, "-o", exe_file],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if compile_result.returncode != 0:
                    return {"error": f"Compilation Error:\n{compile_result.stderr}"}
                
                # Execute C++ Program
                exec_result = subprocess.run(
                    [exe_file],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if exec_result.returncode != 0:
                    return {"error": f"Runtime Error:\n{exec_result.stderr}"}
                
                return {"output": exec_result.stdout}
                
        except subprocess.TimeoutExpired:
            return {"error": "Execution timed out (5 seconds limit)."}
        except Exception as e:
            return {"error": f"System Error: {str(e)}"}
            
    else:
        return {"error": f"Language '{req.language}' is not supported yet."}
