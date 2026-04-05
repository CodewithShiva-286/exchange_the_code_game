"""
runner/sandbox.py — Chunk 5: Code safety scanning + execution isolation.

Provides:
1. Static code scanning for dangerous imports/patterns (blocklist-based).
2. Sandboxed subprocess execution in a temporary directory.
3. Automatic cleanup of temp files after every run.

DESIGN NOTES:
- This is a *lightweight* sandbox suitable for a LAN event, NOT a
  production-grade jail. True sandboxing (Docker/Firecracker) is Chunk 8 scope.
- The blocklist catches obvious cheating/damage attempts (os.system, subprocess,
  socket, file writes). A determined attacker could bypass keyword checks, but
  in a supervised LAN environment this provides sufficient protection.
- subprocess is run with a hard timeout; memory limits are OS-level (Windows
  doesn't easily support ulimit, but timeout catches runaway processes).
"""

import os
import re
import sys
import uuid
import shutil
import asyncio
import tempfile
import logging
import time
from typing import Optional

logger = logging.getLogger("runner.sandbox")

# ── Dangerous patterns (case-insensitive) ──────────────────────────────────────
# Each entry: (compiled_regex, human-readable description)
_PYTHON_BLOCKLIST: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bimport\s+os\b'), "import os"),
    (re.compile(r'\bfrom\s+os\b'), "from os"),
    (re.compile(r'\bimport\s+subprocess\b'), "import subprocess"),
    (re.compile(r'\bfrom\s+subprocess\b'), "from subprocess"),
    (re.compile(r'\bimport\s+shutil\b'), "import shutil"),
    (re.compile(r'\bfrom\s+shutil\b'), "from shutil"),
    (re.compile(r'\bimport\s+socket\b'), "import socket"),
    (re.compile(r'\bfrom\s+socket\b'), "from socket"),
    (re.compile(r'\bimport\s+sys\b'), "import sys"),
    (re.compile(r'\bfrom\s+sys\b'), "from sys"),
    (re.compile(r'\bimport\s+signal\b'), "import signal"),
    (re.compile(r'\bimport\s+ctypes\b'), "import ctypes"),
    (re.compile(r'\bimport\s+importlib\b'), "import importlib"),
    (re.compile(r'\b__import__\s*\('), "__import__()"),
    (re.compile(r'\bexec\s*\('), "exec()"),
    (re.compile(r'\beval\s*\('), "eval()"),
    (re.compile(r'\bcompile\s*\('), "compile()"),
    (re.compile(r'\bopen\s*\('), "open() — file access"),
    (re.compile(r'\bglobals\s*\('), "globals()"),
    (re.compile(r'\blocals\s*\('), "locals()"),
    (re.compile(r'\bgetattr\s*\('), "getattr()"),
    (re.compile(r'\bsetattr\s*\('), "setattr()"),
    (re.compile(r'\bdelattr\s*\('), "delattr()"),
]

_CPP_BLOCKLIST: list[tuple[re.Pattern, str]] = [
    (re.compile(r'#\s*include\s*<\s*fstream\s*>'), "<fstream> — file access"),
    (re.compile(r'#\s*include\s*<\s*cstdlib\s*>'), "<cstdlib> — system()"),
    (re.compile(r'\bsystem\s*\('), "system()"),
    (re.compile(r'\bpopen\s*\('), "popen()"),
    (re.compile(r'\bexecl?\s*\('), "exec()"),
    (re.compile(r'\bfork\s*\('), "fork()"),
    (re.compile(r'#\s*include\s*<\s*unistd\.h\s*>'), "<unistd.h>"),
    (re.compile(r'#\s*include\s*<\s*sys/'), "<sys/*> headers"),
    (re.compile(r'#\s*include\s*<\s*windows\.h\s*>'), "<windows.h>"),
    (re.compile(r'#\s*include\s*<\s*winsock'), "<winsock>"),
]


def scan_python_code(code: str) -> Optional[str]:
    """Returns a human-readable violation message, or None if clean."""
    for pattern, desc in _PYTHON_BLOCKLIST:
        if pattern.search(code):
            return f"Blocked: use of '{desc}' is not allowed"
    return None


def scan_cpp_code(code: str) -> Optional[str]:
    for pattern, desc in _CPP_BLOCKLIST:
        if pattern.search(code):
            return f"Blocked: use of '{desc}' is not allowed"
    return None


async def run_in_sandbox(
    cmd: list[str],
    *,
    stdin_data: str = "",
    timeout_seconds: float = 3.0,
    cwd: Optional[str] = None,
) -> tuple[str, str, int, float]:
    """
    Execute a command in a subprocess with strict timeout.

    Returns: (stdout, stderr, returncode, elapsed_seconds)
    """
    start = time.perf_counter()
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(input=stdin_data.encode("utf-8") if stdin_data else None),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            elapsed = time.perf_counter() - start
            return "", f"Execution timed out after {timeout_seconds}s", -1, elapsed

        elapsed = time.perf_counter() - start
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        return stdout, stderr, proc.returncode, elapsed

    except FileNotFoundError as e:
        elapsed = time.perf_counter() - start
        return "", f"Command not found: {e}", -1, elapsed
    except Exception as e:
        elapsed = time.perf_counter() - start
        return "", f"Sandbox error: {e}", -1, elapsed


def create_temp_dir() -> str:
    """Create a temporary directory for code execution, returns path."""
    return tempfile.mkdtemp(prefix="codeex_")


def cleanup_temp_dir(path: str):
    """Safely remove a temporary directory and all contents."""
    try:
        if os.path.exists(path):
            shutil.rmtree(path, ignore_errors=True)
    except Exception as e:
        logger.warning(f"Failed to cleanup temp dir {path}: {e}")
