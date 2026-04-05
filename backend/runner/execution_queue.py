"""
runner/execution_queue.py — Chunk 5: Async execution queue.

Prevents uncontrolled parallel execution by serializing tasks through
an asyncio.Queue processed by a background worker. The queue is bounded
to prevent memory blowup from rapid RUN button clicks.

Architecture:
- submit_task(): non-blocking, puts a task on the queue, returns a Future
- _worker(): background loop that pulls tasks and runs them one at a time
- start_worker() / stop_worker(): lifecycle management
"""

import asyncio
import json
import logging
import aiosqlite
from typing import Optional
from ..config import settings
from ..websocket.manager import manager
from ..websocket.events import build_event

from .base_runner import RunResult, RunStatus, TestCaseResult
from .python_runner import run_python
from .cpp_runner import run_cpp

logger = logging.getLogger("runner.queue")

# ── Output normalization ───────────────────────────────────────────────────────

def normalize_output(text: str) -> str:
    """Strip trailing whitespace per line & trailing newlines for comparison."""
    lines = text.strip().split("\n")
    return "\n".join(line.rstrip() for line in lines)


# ── Task types ─────────────────────────────────────────────────────────────────

class ExecutionTask:
    """A unit of work for the execution queue."""

    def __init__(
        self,
        task_type: str,         # "run" or "final"
        team_id: str,
        player_id: int,
        code: str,
        language: str,
        test_cases: list[dict],  # [{id, input_data, expected_output}]
        problem_id: str = "",
    ):
        self.task_type = task_type
        self.team_id = team_id
        self.player_id = player_id
        self.code = code
        self.language = language
        self.test_cases = test_cases
        self.problem_id = problem_id
        self.future: asyncio.Future | None = None


# ── Queue & Worker ─────────────────────────────────────────────────────────────

_queue: Optional[asyncio.Queue] = None
_worker_task: Optional[asyncio.Task] = None
# Track which teams already had final evaluation to prevent duplicates
_final_executed: set[str] = set()


async def _execute_code(code: str, language: str, stdin_data: str = "") -> RunResult:
    """Dispatch to the correct language runner."""
    if language == "python":
        return await run_python(code, stdin_data=stdin_data)
    elif language in ("cpp", "c++"):
        return await run_cpp(code, stdin_data=stdin_data)
    else:
        return RunResult(
            status=RunStatus.RUNTIME_ERROR,
            error_message=f"Unsupported language: {language}",
        )


async def _run_against_test_cases(
    code: str,
    language: str,
    test_cases: list[dict],
) -> RunResult:
    """
    Run code against each test case independently.
    Produces a RunResult with per-test-case breakdown.
    """
    all_results: list[TestCaseResult] = []
    total_time = 0.0
    all_passed = True

    for tc in test_cases:
        tc_id = tc.get("id", 0)
        input_data = tc.get("input_data", "")
        expected = tc.get("expected_output", "")

        result = await _execute_code(code, language, stdin_data=input_data)
        total_time += result.time_taken

        if result.status == RunStatus.SUCCESS:
            actual_norm = normalize_output(result.stdout)
            expected_norm = normalize_output(expected)
            passed = actual_norm == expected_norm
        elif result.status == RunStatus.BLOCKED:
            all_results.append(TestCaseResult(
                test_case_id=tc_id,
                input_data=input_data,
                expected_output=expected,
                actual_output="",
                passed=False,
                error=result.error_message,
                time_taken=result.time_taken,
            ))
            all_passed = False
            continue
        else:
            passed = False

        if not passed:
            all_passed = False

        all_results.append(TestCaseResult(
            test_case_id=tc_id,
            input_data=input_data,
            expected_output=expected,
            actual_output=result.stdout.rstrip(),
            passed=passed,
            error=result.error_message if not passed else None,
            time_taken=result.time_taken,
        ))

    # Determine overall status
    if all_results and all(r.passed for r in all_results):
        overall_status = RunStatus.SUCCESS
    elif any(r.error and "timed out" in (r.error or "") for r in all_results):
        overall_status = RunStatus.TIMEOUT
    elif any(r.error and "Blocked" in (r.error or "") for r in all_results):
        overall_status = RunStatus.BLOCKED
    else:
        overall_status = RunStatus.RUNTIME_ERROR

    return RunResult(
        status=overall_status,
        time_taken=total_time,
        passed=all_passed,
        test_results=all_results,
    )


async def _process_task(task: ExecutionTask):
    """Process a single execution task."""
    try:
        if task.task_type == "run":
            # RUN mode: quick feedback with sample test cases
            result = await _run_against_test_cases(
                task.code, task.language, task.test_cases
            )
            # Send RUN_OUTPUT to the specific player
            await manager.send_to_player(
                task.team_id,
                task.player_id,
                build_event("RUN_OUTPUT", result.to_dict()),
            )
            task.future.set_result(result)

        elif task.task_type == "final":
            # FINAL mode: run once per team, store result
            team_key = f"{task.team_id}:{task.problem_id}"
            if team_key in _final_executed:
                logger.warning(f"Final already executed for {team_key}, skipping")
                task.future.set_result(None)
                return

            _final_executed.add(team_key)

            result = await _run_against_test_cases(
                task.code, task.language, task.test_cases
            )

            # Compute score
            total = len(result.test_results)
            passed_count = sum(1 for r in result.test_results if r.passed)
            score = (passed_count / total * 100) if total > 0 else 0.0

            # Store in DB
            breakdown_json = json.dumps([
                {
                    "test_case_id": r.test_case_id,
                    "passed": r.passed,
                    "actual_output": r.actual_output,
                    "expected_output": r.expected_output,
                    "error": r.error,
                    "time_taken": round(r.time_taken, 4),
                }
                for r in result.test_results
            ])

            async with aiosqlite.connect(settings.database_path, timeout=15.0) as db:
                await db.execute(
                    """
                    INSERT INTO execution_results
                        (team_id, problem_id, status, score, test_case_breakdown, execution_time)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task.team_id,
                        task.problem_id,
                        result.status.value,
                        score,
                        breakdown_json,
                        round(result.time_taken, 4),
                    ),
                )
                await db.commit()

            # Broadcast RESULT to team
            await manager.broadcast_to_team(
                task.team_id,
                build_event("RESULT", {
                    "problem_id": task.problem_id,
                    "score": score,
                    "total_test_cases": total,
                    "passed_count": passed_count,
                    "status": result.status.value,
                    "execution_time": round(result.time_taken, 4),
                    "breakdown": json.loads(breakdown_json),
                }),
            )

            task.future.set_result(result)

    except Exception as e:
        logger.error(f"Queue task processing error: {e}")
        if not task.future.done():
            task.future.set_exception(e)


async def _worker():
    """Background worker that processes tasks sequentially."""
    logger.info("Execution queue worker started")
    while True:
        try:
            task: ExecutionTask = await _queue.get()
            await _process_task(task)
            _queue.task_done()
        except asyncio.CancelledError:
            logger.info("Execution queue worker shutting down")
            break
        except Exception as e:
            logger.error(f"Execution queue worker error: {e}")


def start_worker():
    """Start the background execution worker. Call at app startup."""
    global _queue, _worker_task
    _queue = asyncio.Queue(maxsize=100)
    _worker_task = asyncio.create_task(_worker())
    logger.info("Execution queue initialized")


def stop_worker():
    """Stop the worker. Call at app shutdown."""
    global _worker_task
    if _worker_task:
        _worker_task.cancel()
        _worker_task = None


async def submit_task(task: ExecutionTask) -> RunResult:
    """Submit a task to the execution queue. Returns the result via Future."""
    if _queue is None:
        raise RuntimeError("Execution queue not started. Call start_worker() first.")
    loop = asyncio.get_running_loop()
    task.future = loop.create_future()
    await _queue.put(task)
    return await task.future


def reset_final_tracker():
    """Reset the dedup tracker. Useful for testing or round resets."""
    _final_executed.clear()
