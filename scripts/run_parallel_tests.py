#!/usr/bin/env python3
from __future__ import annotations

"""
Parallel test runner for SpritePal test suite.

SpritePal uses PARALLEL-BY-DEFAULT test execution:
- All tests run in parallel by default (no marker needed)
- Tests using `session_managers` are auto-serialized
- Tests marked @pytest.mark.parallel_unsafe are forced to serial

Note: The @pytest.mark.parallel_safe marker is deprecated and ignored.

Usage:
    # Run all tests with parallel execution (default via pyproject.toml)
    uv run pytest

    # This script provides additional control options:
    QT_QPA_PLATFORM=offscreen python scripts/run_parallel_tests.py

    # Run only parallel tests
    QT_QPA_PLATFORM=offscreen python scripts/run_parallel_tests.py --parallel-only

    # Run only serial tests (session_managers, parallel_unsafe)
    QT_QPA_PLATFORM=offscreen python scripts/run_parallel_tests.py --serial-only
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path


def run_command(cmd: list[str], description: str, timeout: int = 300) -> tuple[bool, str]:
    """Run a command and return success status and output."""
    print(f"\n{'=' * 60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'=' * 60}")

    start_time = time.time()

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=Path.cwd())

        duration = time.time() - start_time
        success = result.returncode == 0

        print(f"\n{description} {'PASSED' if success else 'FAILED'} in {duration:.1f}s")

        if result.stdout:
            print("\nSTDOUT:")
            print(result.stdout)

        if result.stderr:
            print("\nSTDERR:")
            print(result.stderr)

        return success, result.stdout + result.stderr

    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        print(f"\n{description} TIMEOUT after {duration:.1f}s")
        return False, f"Command timed out after {timeout}s"
    except Exception as e:
        duration = time.time() - start_time
        print(f"\n{description} ERROR after {duration:.1f}s: {e}")
        return False, str(e)


def get_test_counts() -> tuple[int | str, int | str]:
    """Get counts of parallel_safe vs other tests."""
    try:
        # Count all tests
        result = subprocess.run(
            ["pytest", "--collect-only", "-q", "tests/"], capture_output=True, text=True, timeout=60
        )

        total_tests: int | str = "unknown"
        if result.returncode == 0:
            lines = result.stdout.split("\n")
            for line in lines:
                if "tests collected" in line or "test collected" in line:
                    total_tests = int(line.split()[0])
                    break

        # Count parallel_safe tests (these will run in parallel)
        result = subprocess.run(
            ["pytest", "--collect-only", "-q", "-m", "parallel_safe", "tests/"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        parallel_tests: int | str = 0
        if result.returncode == 0:
            lines = result.stdout.split("\n")
            for line in lines:
                if "tests collected" in line or "test collected" in line:
                    parallel_tests = int(line.split()[0])
                    break

        # Serial tests = all tests minus parallel_safe tests
        if isinstance(total_tests, int) and isinstance(parallel_tests, int):
            serial_tests = total_tests - parallel_tests
        else:
            serial_tests = "unknown"

        return parallel_tests, serial_tests

    except Exception as e:
        print(f"Warning: Error counting tests: {e}")
        return "unknown", "unknown"


def main():
    parser = argparse.ArgumentParser(
        description="Run SpritePal tests with conservative parallel execution",
        epilog="Uses opt-in approach: only @pytest.mark.parallel_safe tests run in parallel.",
    )
    parser.add_argument("--parallel-only", action="store_true", help="Run only parallel-safe tests (with xdist)")
    parser.add_argument("--serial-only", action="store_true", help="Run only serial tests (not parallel_safe)")
    parser.add_argument("--workers", "-n", type=str, default="auto", help="Number of parallel workers (default: auto)")
    parser.add_argument("--timeout", type=int, default=600, help="Timeout per test phase in seconds (default: 600)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--maxfail", type=int, default=5, help="Stop after N failures (default: 5)")
    parser.add_argument("tests", nargs="*", help="Specific test files to run")

    args = parser.parse_args()

    # Get test counts
    parallel_count, serial_count = get_test_counts()

    print("SpritePal Conservative Parallel Test Runner")
    print("-" * 50)
    print(f"Parallel-safe tests: {parallel_count} (will run with xdist)")
    print(f"Serial tests: {serial_count} (will run sequentially)")
    print(f"Workers: {args.workers}")
    print(f"Timeout: {args.timeout}s per phase")
    print("-" * 50)

    # Base command components
    base_pytest = ["pytest"]
    if args.verbose:
        base_pytest.append("-v")
    else:
        base_pytest.append("-q")

    base_pytest.extend(
        [
            "--tb=short",
            f"--maxfail={args.maxfail}",
        ]
    )

    # Determine test paths
    test_paths = args.tests if args.tests else ["tests/"]

    results = []

    # CONSERVATIVE APPROACH: Run serial tests first (all non-parallel_safe tests)
    if not args.parallel_only:
        serial_cmd = [*base_pytest, "-m", "not parallel_safe", *test_paths]

        serial_success, serial_output = run_command(
            serial_cmd, f"Serial tests ({serial_count} tests, not parallel_safe)", args.timeout
        )
        results.append(("Serial", serial_success, serial_output))

        if not serial_success and not args.serial_only:
            print("\n⚠️  Serial tests failed, but continuing with parallel tests...")

    # Then run parallel_safe tests with xdist
    if not args.serial_only:
        parallel_cmd = [*base_pytest, f"-n{args.workers}", "--dist=worksteal", "-m", "parallel_safe", *test_paths]

        parallel_success, parallel_output = run_command(
            parallel_cmd, f"Parallel tests ({parallel_count} tests, {args.workers} workers)", args.timeout
        )
        results.append(("Parallel", parallel_success, parallel_output))

    # Summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")

    all_passed = True
    for phase, success, output in results:
        status = "PASSED" if success else "FAILED"
        print(f"{phase:12} {status}")
        if not success:
            all_passed = False

    if all_passed:
        print("\n✅ All test phases passed!")
        return 0
    else:
        print("\n❌ Some test phases failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
