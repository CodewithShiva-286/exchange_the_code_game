"""
test_chunk5_strict.py — Strict Validation Suite for Chunk 5: Code Execution Engine

Tests:
1.  Python execution: valid code → SUCCESS
2.  Python runtime error: division by zero → RUNTIME_ERROR
3.  Python timeout: infinite loop → TIMEOUT
4.  Python blocked code: os.system → BLOCKED
5.  C++ missing compiler: → COMPILE_ERROR (graceful)
6.  Output normalization: trailing whitespace → PASS
7.  Multi-task queue: concurrent submissions don't crash
8.  Execution queue serialization: tasks processed in order
9.  Blocked patterns: eval, exec, subprocess → all caught
10. Final dedup: only executes once per team:problem
11. DB integrity: execution_results written correctly
12. Test case pass/fail accuracy
13. Temp file cleanup
14. stdin/stdout handling
"""

import pytest
import pytest_asyncio
import os
import asyncio
import aiosqlite

from backend.config import settings

settings.database_path = "test_exchange_chunk5.db"

from backend.runner.base_runner import RunResult, RunStatus
from backend.runner.python_runner import run_python
from backend.runner.cpp_runner import run_cpp
from backend.runner.sandbox import scan_python_code, scan_cpp_code
from backend.runner.execution_queue import (
    ExecutionTask, normalize_output,
    start_worker, stop_worker, submit_task, reset_final_tracker,
)


# ─── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session", autouse=True)
async def init_test_db():
    for suffix in ("", "-wal", "-shm"):
        path = settings.database_path + suffix
        if os.path.exists(path):
            try:
                os.remove(path)
            except:
                pass

    from backend.database import init_db
    from backend.problems.problem_loader import load_problems, seed_problems_to_db

    await init_db()
    load_problems()
    await seed_problems_to_db()
    yield
    for suffix in ("", "-wal", "-shm"):
        path = settings.database_path + suffix
        try:
            if os.path.exists(path):
                os.remove(path)
        except:
            pass


@pytest_asyncio.fixture
async def queue_worker():
    """Start/stop the execution queue worker for each test that needs it."""
    start_worker()
    yield
    stop_worker()


# ═══════════════════════════════════════════════════════════════════════════════
#  TEST 1: Python — Valid Execution
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_python_valid_execution():
    """Valid Python code should produce correct stdout and SUCCESS status."""
    code = 'print("hello world")'
    result = await run_python(code)

    assert result.status == RunStatus.SUCCESS, f"Expected SUCCESS, got {result.status}"
    assert result.stdout.strip() == "hello world"
    assert result.time_taken > 0


# ═══════════════════════════════════════════════════════════════════════════════
#  TEST 2: Python — Runtime Error
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_python_runtime_error():
    """Division by zero should return RUNTIME_ERROR with meaningful stderr."""
    code = "x = 1 / 0"
    result = await run_python(code)

    assert result.status == RunStatus.RUNTIME_ERROR
    assert "ZeroDivisionError" in result.stderr or "ZeroDivisionError" in result.error_message


# ═══════════════════════════════════════════════════════════════════════════════
#  TEST 3: Python — Timeout (Infinite Loop)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_python_timeout():
    """Infinite loop must be killed and return TIMEOUT status."""
    code = "while True: pass"
    result = await run_python(code, timeout=1.0)

    assert result.status == RunStatus.TIMEOUT
    assert result.time_taken >= 0.9  # Should take at least ~1 second


# ═══════════════════════════════════════════════════════════════════════════════
#  TEST 4: Python — Blocked Dangerous Code
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_python_blocked_os():
    """import os should be caught by the safety scanner and BLOCKED."""
    code = "import os\nos.system('echo pwned')"
    result = await run_python(code)

    assert result.status == RunStatus.BLOCKED
    assert "import os" in result.error_message


@pytest.mark.asyncio
async def test_python_blocked_subprocess():
    """import subprocess should be caught."""
    code = "import subprocess\nsubprocess.run(['ls'])"
    result = await run_python(code)

    assert result.status == RunStatus.BLOCKED
    assert "subprocess" in result.error_message


@pytest.mark.asyncio
async def test_python_blocked_eval():
    """eval() should be caught."""
    code = 'eval("1+1")'
    result = await run_python(code)

    assert result.status == RunStatus.BLOCKED
    assert "eval()" in result.error_message


@pytest.mark.asyncio
async def test_python_blocked_exec():
    """exec() should be caught."""
    code = 'exec("print(1)")'
    result = await run_python(code)

    assert result.status == RunStatus.BLOCKED
    assert "exec()" in result.error_message


@pytest.mark.asyncio
async def test_python_blocked_file_open():
    """open() for file access should be caught."""
    code = 'f = open("/etc/passwd", "r")\nprint(f.read())'
    result = await run_python(code)

    assert result.status == RunStatus.BLOCKED
    assert "open()" in result.error_message


# ═══════════════════════════════════════════════════════════════════════════════
#  TEST 5: Python — stdin/stdout with Input
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_python_stdin_handling():
    """Code that reads input and produces output should work correctly."""
    code = "n = int(input())\nprint(n * 2)"
    result = await run_python(code, stdin_data="21")

    assert result.status == RunStatus.SUCCESS
    assert result.stdout.strip() == "42"


# ═══════════════════════════════════════════════════════════════════════════════
#  TEST 6: C++ — g++ Detection Validation
# ═══════════════════════════════════════════════════════════════════════════════

def test_cpp_gpp_detection():
    """g++ must be a real executable, not a script file."""
    import shutil
    gpp = shutil.which("g++")
    assert gpp is not None, "g++ not found on PATH — C++ tests require MinGW"
    assert os.path.isfile(gpp), f"g++ path does not exist: {gpp}"
    assert gpp.lower().endswith(".exe"), f"g++ should be .exe on Windows, got: {gpp}"


# ═══════════════════════════════════════════════════════════════════════════════
#  TEST 7: C++ — Valid Compilation + Execution
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cpp_valid_execution():
    """Valid C++ code should compile and produce correct output."""
    code = """
#include <iostream>
int main() {
    std::cout << "hello cpp" << std::endl;
    return 0;
}
"""
    result = await run_cpp(code)

    assert result.status == RunStatus.SUCCESS, f"Expected SUCCESS, got {result.status}: {result.error_message}"
    assert result.stdout.strip() == "hello cpp"
    assert result.time_taken > 0


# ═══════════════════════════════════════════════════════════════════════════════
#  TEST 8: C++ — Compilation Error
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cpp_compile_error():
    """Invalid C++ code should return COMPILE_ERROR with compiler message."""
    code = """
#include <iostream>
int main() {
    this_function_does_not_exist();
    return 0;
}
"""
    result = await run_cpp(code)

    assert result.status == RunStatus.COMPILE_ERROR
    assert result.error_message  # Should contain compiler stderr
    assert "this_function_does_not_exist" in result.stderr or "error" in result.stderr.lower()


# ═══════════════════════════════════════════════════════════════════════════════
#  TEST 9: C++ — Runtime Error
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cpp_runtime_error():
    """C++ code that crashes at runtime should return RUNTIME_ERROR."""
    code = """
#include <iostream>
#include <stdexcept>
int main() {
    throw std::runtime_error("intentional crash");
    return 0;
}
"""
    result = await run_cpp(code)

    assert result.status == RunStatus.RUNTIME_ERROR


# ═══════════════════════════════════════════════════════════════════════════════
#  TEST 10: C++ — Timeout (Infinite Loop)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cpp_timeout():
    """Infinite loop in C++ must be killed and return TIMEOUT."""
    code = """
int main() {
    while(true) {}
    return 0;
}
"""
    result = await run_cpp(code, timeout=1.0)

    assert result.status == RunStatus.TIMEOUT
    assert result.time_taken >= 0.9


# ═══════════════════════════════════════════════════════════════════════════════
#  TEST 11: C++ — stdin/stdout
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cpp_stdin_handling():
    """C++ code reading from stdin should work correctly."""
    code = """
#include <iostream>
int main() {
    int n;
    std::cin >> n;
    std::cout << n * 3 << std::endl;
    return 0;
}
"""
    result = await run_cpp(code, stdin_data="7")

    assert result.status == RunStatus.SUCCESS
    assert result.stdout.strip() == "21"


# ═══════════════════════════════════════════════════════════════════════════════
#  TEST 12: C++ — Blocked Dangerous Code
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cpp_blocked_system():
    """system() call should be caught by scanner."""
    code = '#include <cstdlib>\nint main() { system("rm -rf /"); }'
    result = await run_cpp(code)

    assert result.status == RunStatus.BLOCKED
    assert "Blocked" in result.error_message


# ═══════════════════════════════════════════════════════════════════════════════
#  TEST 13: C++ — Temp File Cleanup
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cpp_temp_files_cleaned():
    """After C++ execution, no temp dirs should remain."""
    import tempfile
    import glob

    before = set(glob.glob(os.path.join(tempfile.gettempdir(), "codeex_*")))
    code = '#include <iostream>\nint main() { std::cout << "clean"; return 0; }'
    await run_cpp(code)
    after = set(glob.glob(os.path.join(tempfile.gettempdir(), "codeex_*")))

    leftover = after - before
    assert len(leftover) == 0, f"C++ temp dirs not cleaned up: {leftover}"


# ═══════════════════════════════════════════════════════════════════════════════
#  TEST 8: Output Normalization
# ═══════════════════════════════════════════════════════════════════════════════

def test_output_normalization():
    """Output comparison should ignore trailing whitespace and newlines."""
    assert normalize_output("hello  \n  world  \n\n") == "hello\n  world"
    assert normalize_output("42\n") == "42"
    assert normalize_output("  ") == ""

    # Same logical output with different formatting should match
    assert normalize_output("hello\nworld\n") == normalize_output("hello\nworld")


# ═══════════════════════════════════════════════════════════════════════════════
#  TEST 9: Scanner Completeness
# ═══════════════════════════════════════════════════════════════════════════════

def test_python_scanner_patterns():
    """All dangerous patterns should be detected."""
    dangerous = [
        "import os",
        "from os import path",
        "import subprocess",
        "from subprocess import run",
        "import socket",
        "import shutil",
        "import sys",
        "import signal",
        "import ctypes",
        "import importlib",
        "__import__('os')",
        "exec('print(1)')",
        "eval('1+1')",
        "compile('x', 'x', 'exec')",
        "open('file.txt')",
        "globals()",
        "locals()",
        "getattr(obj, 'x')",
        "setattr(obj, 'x', 1)",
        "delattr(obj, 'x')",
    ]
    for code in dangerous:
        result = scan_python_code(code)
        assert result is not None, f"Scanner missed: {code}"


def test_python_scanner_safe_code():
    """Normal Python code should NOT be flagged."""
    safe_codes = [
        "x = 1 + 2\nprint(x)",
        "def solve(n):\n    return n * 2",
        "for i in range(10):\n    print(i)",
        "my_list = [1, 2, 3]\nprint(sum(my_list))",
        "import math\nprint(math.sqrt(4))",
        "import json\nprint(json.dumps({'a': 1}))",
        "import collections\nfrom collections import defaultdict",
    ]
    for code in safe_codes:
        result = scan_python_code(code)
        assert result is None, f"False positive on safe code: {code} → {result}"


def test_cpp_scanner_patterns():
    """All dangerous C++ patterns should be detected."""
    dangerous = [
        '#include <fstream>',
        '#include <cstdlib>',
        'system("ls")',
        'popen("cmd", "r")',
        '#include <unistd.h>',
        '#include <sys/socket.h>',
        '#include <windows.h>',
    ]
    for code in dangerous:
        result = scan_cpp_code(code)
        assert result is not None, f"Scanner missed: {code}"


# ═══════════════════════════════════════════════════════════════════════════════
#  TEST 10: Queue — Multiple Tasks Don't Crash
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_queue_multiple_tasks(queue_worker):
    """Submit 5 tasks rapidly and verify all complete without crash."""
    tasks = []
    for i in range(5):
        task = ExecutionTask(
            task_type="run",
            team_id=f"Q-TEAM-{i}",
            player_id=i + 100,
            code=f'print({i})',
            language="python",
            test_cases=[{"id": 0, "input_data": "", "expected_output": str(i)}],
        )
        tasks.append(submit_task(task))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results):
        assert not isinstance(result, Exception), f"Task {i} raised: {result}"
        assert result.status == RunStatus.SUCCESS


# ═══════════════════════════════════════════════════════════════════════════════
#  TEST 11: Queue — Final Dedup (One per Team)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_final_dedup(queue_worker):
    """Final evaluation should only execute once per team:problem pair."""
    reset_final_tracker()

    task1 = ExecutionTask(
        task_type="final",
        team_id="DEDUP-T1",
        player_id=200,
        code='print("final")',
        language="python",
        test_cases=[{"id": 1, "input_data": "", "expected_output": "final"}],
        problem_id="p001",
    )

    # Submit first final — should execute
    result1 = await submit_task(task1)
    assert result1 is not None
    assert result1.status == RunStatus.SUCCESS

    # Submit duplicate — should be skipped
    task2 = ExecutionTask(
        task_type="final",
        team_id="DEDUP-T1",
        player_id=201,
        code='print("final again")',
        language="python",
        test_cases=[{"id": 1, "input_data": "", "expected_output": "final again"}],
        problem_id="p001",
    )
    result2 = await submit_task(task2)
    assert result2 is None  # Skipped due to dedup


# ═══════════════════════════════════════════════════════════════════════════════
#  TEST 12: DB Integrity — Final Results Stored
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_final_results_stored_in_db(queue_worker):
    """After a final execution, results should be persisted in execution_results."""
    reset_final_tracker()

    task = ExecutionTask(
        task_type="final",
        team_id="DB-T1",
        player_id=300,
        code='print("42")',
        language="python",
        test_cases=[{"id": 1, "input_data": "", "expected_output": "42"}],
        problem_id="p001",
    )
    result = await submit_task(task)
    assert result.status == RunStatus.SUCCESS

    # Check DB
    async with aiosqlite.connect(settings.database_path, timeout=15.0) as db:
        async with db.execute(
            "SELECT team_id, problem_id, status, score FROM execution_results WHERE team_id = ?",
            ("DB-T1",)
        ) as cursor:
            row = await cursor.fetchone()

    assert row is not None, "Execution result not found in DB"
    assert row[0] == "DB-T1"
    assert row[1] == "p001"
    assert row[2] == "success"
    assert row[3] == 100.0  # 1/1 test case passed


# ═══════════════════════════════════════════════════════════════════════════════
#  TEST 13: Test Case Comparison — Correct Pass/Fail
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_test_case_pass_fail(queue_worker):
    """Verify pass/fail is computed correctly against expected output."""
    reset_final_tracker()

    code = "n = int(input())\nprint(n * 2)"
    task = ExecutionTask(
        task_type="final",
        team_id="TC-T1",
        player_id=400,
        code=code,
        language="python",
        test_cases=[
            {"id": 1, "input_data": "5", "expected_output": "10"},
            {"id": 2, "input_data": "0", "expected_output": "0"},
            {"id": 3, "input_data": "3", "expected_output": "7"},  # Wrong expected — should FAIL
        ],
        problem_id="p002",
    )
    result = await submit_task(task)

    assert len(result.test_results) == 3
    assert result.test_results[0].passed is True   # 5*2=10 ✓
    assert result.test_results[1].passed is True   # 0*2=0  ✓
    assert result.test_results[2].passed is False   # 3*2=6≠7 ✗
    assert result.passed is False  # Not all passed


# ═══════════════════════════════════════════════════════════════════════════════
#  TEST 14: Temp File Cleanup
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_temp_files_cleaned():
    """After execution, no temp directories should remain."""
    import tempfile
    import glob

    before = set(glob.glob(os.path.join(tempfile.gettempdir(), "codeex_*")))
    await run_python('print("cleanup test")')
    after = set(glob.glob(os.path.join(tempfile.gettempdir(), "codeex_*")))

    # No new temp dirs should remain
    leftover = after - before
    assert len(leftover) == 0, f"Temp dirs not cleaned up: {leftover}"
