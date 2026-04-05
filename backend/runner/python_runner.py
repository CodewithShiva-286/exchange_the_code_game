"""
runner/python_runner.py — Chunk 5: Python code execution.

Writes code to a temp file, runs it via subprocess with stdin/stdout capture,
and applies code safety scanning before execution.
"""

import os
import sys
import logging
from .base_runner import RunResult, RunStatus
from .sandbox import (
    scan_python_code,
    run_in_sandbox,
    create_temp_dir,
    cleanup_temp_dir,
)

logger = logging.getLogger("runner.python")

# Use the same Python executable that's running the server
_PYTHON_EXE = sys.executable


async def run_python(
    code: str,
    stdin_data: str = "",
    timeout: float = 3.0,
) -> RunResult:
    """
    Execute Python code in a sandboxed subprocess.

    1. Scan for dangerous patterns.
    2. Write to temp file.
    3. Execute with subprocess (timeout enforced).
    4. Capture output and cleanup.
    """
    # ── 1. Safety scan ─────────────────────────────────────────────────────
    violation = scan_python_code(code)
    if violation:
        return RunResult(
            status=RunStatus.BLOCKED,
            error_message=violation,
        )

    # ── 2. Write to temp file ──────────────────────────────────────────────
    temp_dir = create_temp_dir()
    code_path = os.path.join(temp_dir, "solution.py")

    try:
        with open(code_path, "w", encoding="utf-8") as f:
            f.write(code)

        # ── 3. Execute ─────────────────────────────────────────────────────
        stdout, stderr, returncode, elapsed = await run_in_sandbox(
            [_PYTHON_EXE, "-u", code_path],
            stdin_data=stdin_data,
            timeout_seconds=timeout,
            cwd=temp_dir,
        )

        # ── 4. Interpret result ────────────────────────────────────────────
        if returncode == -1 and "timed out" in stderr:
            return RunResult(
                status=RunStatus.TIMEOUT,
                stderr=stderr,
                time_taken=elapsed,
                error_message=f"Code execution timed out after {timeout}s",
            )

        if returncode != 0:
            return RunResult(
                status=RunStatus.RUNTIME_ERROR,
                stdout=stdout,
                stderr=stderr,
                time_taken=elapsed,
                error_message=stderr.strip().split("\n")[-1] if stderr.strip() else "Runtime error",
            )

        return RunResult(
            status=RunStatus.SUCCESS,
            stdout=stdout,
            stderr=stderr,
            time_taken=elapsed,
        )

    except Exception as e:
        logger.error(f"Python runner error: {e}")
        return RunResult(
            status=RunStatus.RUNTIME_ERROR,
            error_message=str(e),
        )
    finally:
        cleanup_temp_dir(temp_dir)
