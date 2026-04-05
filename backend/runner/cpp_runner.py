"""
runner/cpp_runner.py — Chunk 5: C++ code compilation + execution (hardened).

Writes code to temp file, compiles with g++, runs the resulting binary.
Includes defensive compiler detection and guaranteed cleanup.
"""

import os
import shutil
import logging
from .base_runner import RunResult, RunStatus
from .sandbox import (
    scan_cpp_code,
    run_in_sandbox,
    create_temp_dir,
    cleanup_temp_dir,
)

logger = logging.getLogger("runner.cpp")


def _find_gpp() -> str | None:
    """
    Locate g++ executable with defensive validation.
    
    Returns the absolute path to a valid g++ binary, or None if:
    - g++ is not on PATH
    - the resolved path is a script (.py, .bat, .sh) rather than a real executable
    - the resolved path doesn't actually exist
    """
    gpp = shutil.which("g++")
    if not gpp:
        return None

    # Normalize path for comparison
    gpp_lower = gpp.lower()

    # Reject if it resolved to a Python script or batch file (shadowing)
    bad_extensions = (".py", ".bat", ".sh", ".cmd", ".ps1")
    if any(gpp_lower.endswith(ext) for ext in bad_extensions):
        logger.warning(f"g++ resolved to a script file ({gpp}), rejecting as invalid")
        return None

    # On Windows, expect .exe; on Linux, no extension is fine
    if os.name == "nt" and not gpp_lower.endswith(".exe"):
        logger.warning(f"g++ resolved to non-.exe on Windows ({gpp}), rejecting")
        return None

    # Final check: file must actually exist on disk
    if not os.path.isfile(gpp):
        logger.warning(f"g++ path does not exist: {gpp}")
        return None

    return gpp


async def run_cpp(
    code: str,
    stdin_data: str = "",
    timeout: float = 5.0,
) -> RunResult:
    """
    Compile and execute C++ code in a sandboxed subprocess.

    Flow:
    1. Validate g++ availability (defensive checks).
    2. Scan for dangerous patterns (blocklist).
    3. Write code to temp file.
    4. Compile with g++ (10s timeout, stderr captured).
    5. Do NOT proceed if compilation fails.
    6. Execute binary with stdin (timeout enforced, process killed on timeout).
    7. Always cleanup temp directory (.cpp, .exe, everything).
    """
    # ── 0. Check compiler availability ─────────────────────────────────────
    gpp = _find_gpp()
    if not gpp:
        return RunResult(
            status=RunStatus.COMPILE_ERROR,
            error_message="C++ compiler not available. "
                          "g++ was not found or resolved to an invalid file. "
                          "Install MinGW or MSYS2 to enable C++ support.",
        )

    # ── 1. Safety scan ─────────────────────────────────────────────────────
    violation = scan_cpp_code(code)
    if violation:
        return RunResult(
            status=RunStatus.BLOCKED,
            error_message=violation,
        )

    # ── 2. Write to temp file ──────────────────────────────────────────────
    temp_dir = create_temp_dir()
    code_path = os.path.join(temp_dir, "solution.cpp")
    binary_name = "solution.exe" if os.name == "nt" else "solution"
    binary_path = os.path.join(temp_dir, binary_name)

    try:
        with open(code_path, "w", encoding="utf-8") as f:
            f.write(code)

        # ── 3. Compile ─────────────────────────────────────────────────────
        stdout, stderr, returncode, compile_time = await run_in_sandbox(
            [gpp, code_path, "-o", binary_path, "-std=c++17", "-O2"],
            timeout_seconds=10.0,
            cwd=temp_dir,
        )

        if returncode != 0:
            # Compilation failed — do NOT proceed to execution
            return RunResult(
                status=RunStatus.COMPILE_ERROR,
                stderr=stderr,
                time_taken=compile_time,
                error_message=stderr.strip() if stderr.strip() else "Compilation failed",
            )

        # Verify binary was actually created (defensive)
        if not os.path.isfile(binary_path):
            return RunResult(
                status=RunStatus.COMPILE_ERROR,
                time_taken=compile_time,
                error_message="Compilation reported success but no binary was produced.",
            )

        # ── 4. Execute binary ──────────────────────────────────────────────
        stdout, stderr, returncode, exec_time = await run_in_sandbox(
            [binary_path],
            stdin_data=stdin_data,
            timeout_seconds=timeout,
            cwd=temp_dir,
        )

        total_time = compile_time + exec_time

        if returncode == -1 and "timed out" in stderr:
            return RunResult(
                status=RunStatus.TIMEOUT,
                stderr=stderr,
                time_taken=total_time,
                error_message=f"Execution timed out after {timeout}s",
            )

        if returncode != 0:
            return RunResult(
                status=RunStatus.RUNTIME_ERROR,
                stdout=stdout,
                stderr=stderr,
                time_taken=total_time,
                error_message=stderr.strip() if stderr.strip() else "Runtime error",
            )

        return RunResult(
            status=RunStatus.SUCCESS,
            stdout=stdout,
            stderr=stderr,
            time_taken=total_time,
        )

    except Exception as e:
        logger.error(f"C++ runner error: {e}")
        return RunResult(
            status=RunStatus.RUNTIME_ERROR,
            error_message=str(e),
        )
    finally:
        # Guaranteed cleanup — .cpp, .exe, everything
        cleanup_temp_dir(temp_dir)
