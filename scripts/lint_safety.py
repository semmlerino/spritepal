#!/usr/bin/env python3
"""
Safety lint script to detect dangerous threading patterns in the codebase.

This script checks for:
1. Dangerous QThread.terminate() calls in production code
2. Safe cancellation patterns in WorkerManager methods

Originally extracted from tests/integration/test_worker_manager.py as these
are static analysis checks better suited for CI linting than pytest.

Usage:
    uv run python scripts/lint_safety.py
"""

from __future__ import annotations

import inspect
import subprocess
import sys
from pathlib import Path


def check_no_terminate_calls() -> list[str]:
    """Check that no production code uses the dangerous QThread.terminate() method.

    Returns:
        List of problematic lines found, empty if none.
    """
    # Search for any terminate() calls in production code only
    # Exclude virtual environments, test files, and external dependencies
    result = subprocess.run(
        [
            "grep",
            "-r",
            r"\.terminate()",
            ".",
            "--include=*.py",
            "--exclude-dir=.venv",
            "--exclude-dir=venv",
            "--exclude-dir=__pycache__",
            "--exclude-dir=.git",
            "--exclude-dir=node_modules",
        ],
        check=False,
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True,
    )

    # Filter out test files, comments, and documentation
    lines = result.stdout.split("\n") if result.stdout else []
    problematic_lines = []

    for line in lines:
        if not line.strip():
            continue

        # Skip test files
        if "/test" in line or "test_" in line:
            continue

        # Skip this lint script itself
        if "lint_safety.py" in line:
            continue

        # Skip comment lines and documentation
        content = line.split(":", 1)[-1] if ":" in line else line
        content = content.strip()
        if content.startswith(("#", '"""', "'''")):
            continue

        # Skip lines that are clearly documentation/comments
        if "CRITICAL:" in content or "which can corrupt" in content or "Never uses" in content or "# " in content:
            continue

        # Skip external dependencies and virtual environments
        if "/.venv/" in line or "/venv/" in line or "/site-packages/" in line:
            continue

        # Skip hal_compression.py - it uses multiprocessing.Process.terminate()
        # which is safe and expected for process pool management
        if "hal_compression.py" in line:
            continue

        problematic_lines.append(line)

    return problematic_lines


def check_worker_manager_safe_patterns() -> list[str]:
    """Check WorkerManager follows safe cancellation patterns in code.

    Returns:
        List of issues found, empty if none.
    """
    from ui.common import WorkerManager

    issues = []

    # Get all methods from WorkerManager
    methods = inspect.getmembers(WorkerManager, predicate=inspect.ismethod)
    static_methods = inspect.getmembers(WorkerManager, predicate=inspect.isfunction)
    all_methods = methods + static_methods

    # Check each method for safe patterns
    for name, method in all_methods:
        if name.startswith("_"):
            continue  # Skip private methods

        try:
            source = inspect.getsource(method)
        except (OSError, TypeError):
            continue

        # Remove comments and docstrings to check only actual code
        source_lines = source.split("\n")
        code_lines = []
        in_docstring = False

        for line in source_lines:
            stripped = line.strip()

            # Skip docstring lines
            if '"""' in stripped or "'''" in stripped:
                in_docstring = not in_docstring
                continue
            if in_docstring:
                continue

            # Skip comment lines
            if stripped.startswith("#"):
                continue

            code_lines.append(line)

        actual_code = "\n".join(code_lines)

        # Verify no actual terminate() calls in code (only in comments/docs)
        if "terminate()" in actual_code:
            issues.append(f"Method {name} contains actual terminate() call in code")

        # Verify safe patterns are used in methods that should have them
        if "cleanup" in name.lower() or "cancel" in name.lower():
            # Either direct use of patterns OR delegation to cleanup_worker is valid
            has_safe_pattern = (
                "requestInterruption" in actual_code
                or "cancel()" in actual_code
                or "quit()" in actual_code
                or "cleanup_worker" in actual_code  # Delegates to safe cleanup method
            )
            if not has_safe_pattern:
                issues.append(f"Method {name} should use safe cancellation patterns")

    return issues


def main() -> int:
    """Run all safety lint checks.

    Returns:
        Exit code: 0 if all checks pass, 1 if any fail.
    """
    print("=== Safety Lint Checks ===\n")

    all_passed = True

    # Check 1: No terminate() calls
    print("Checking for dangerous terminate() calls...")
    terminate_issues = check_no_terminate_calls()
    if terminate_issues:
        all_passed = False
        print(f"  FAIL: Found {len(terminate_issues)} dangerous terminate() calls:")
        for line in terminate_issues:
            print(f"    {line}")
    else:
        print("  PASS: No dangerous terminate() calls found")

    print()

    # Check 2: WorkerManager safe patterns
    print("Checking WorkerManager safe patterns...")
    pattern_issues = check_worker_manager_safe_patterns()
    if pattern_issues:
        all_passed = False
        print(f"  FAIL: Found {len(pattern_issues)} pattern issues:")
        for issue in pattern_issues:
            print(f"    {issue}")
    else:
        print("  PASS: WorkerManager uses safe cancellation patterns")

    print()

    if all_passed:
        print("All safety lint checks passed.")
        return 0
    else:
        print("Some safety lint checks failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
