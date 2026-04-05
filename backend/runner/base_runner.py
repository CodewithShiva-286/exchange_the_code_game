"""
runner/base_runner.py — Chunk 5: Data models for code execution results.

Provides the RunResult dataclass used by all language runners and the
execution queue. Every execution (RUN or FINAL) produces a RunResult.
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class RunStatus(str, Enum):
    SUCCESS = "success"
    COMPILE_ERROR = "compile_error"
    RUNTIME_ERROR = "runtime_error"
    TIMEOUT = "timeout"
    BLOCKED = "blocked"          # Dangerous code detected


@dataclass
class TestCaseResult:
    """Result for a single test case execution."""
    test_case_id: int
    input_data: str
    expected_output: str
    actual_output: str
    passed: bool
    error: Optional[str] = None
    time_taken: float = 0.0


@dataclass
class RunResult:
    """Aggregate result for a single code execution attempt."""
    status: RunStatus
    stdout: str = ""
    stderr: str = ""
    time_taken: float = 0.0
    passed: Optional[bool] = None
    error_message: str = ""
    test_results: list[TestCaseResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "time_taken": round(self.time_taken, 4),
            "passed": self.passed,
            "error_message": self.error_message,
            "test_results": [
                {
                    "test_case_id": tr.test_case_id,
                    "input_data": tr.input_data,
                    "expected_output": tr.expected_output,
                    "actual_output": tr.actual_output,
                    "passed": tr.passed,
                    "error": tr.error,
                    "time_taken": round(tr.time_taken, 4),
                }
                for tr in self.test_results
            ],
        }
