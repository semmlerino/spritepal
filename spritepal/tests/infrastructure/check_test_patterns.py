#!/usr/bin/env python3
"""Check for common test anti-patterns in Python test files.

This script can be used as a pre-commit hook or standalone linter to detect
problematic patterns in test code that are known to cause flaky tests,
crashes, or maintenance issues.

Usage:
    # Check all test files (default when paths omitted)
    python -m tests.infrastructure.check_test_patterns

    # Check specific directories or files
    python -m tests.infrastructure.check_test_patterns --paths tests/integration tests/fixtures/qt_fixtures.py

    # Use with pre-commit (in .pre-commit-config.yaml):
    - repo: local
      hooks:
        - id: check-test-patterns
          name: Check test anti-patterns
          entry: python -m tests.infrastructure.check_test_patterns --paths tests
          language: python
          types: [python]
          files: "^tests/.*\\\\.py$"
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import NamedTuple


class AntiPattern(NamedTuple):
    """Represents a test anti-pattern to detect."""
    pattern: str
    message: str
    severity: str  # 'error' or 'warning'


# Anti-patterns that indicate problematic test code
ANTI_PATTERNS: list[AntiPattern] = [
    AntiPattern(
        r'time\.sleep\([^)]+\)',
        'Prefer qtbot.waitUntil/waitSignal in Qt tests; allowlist with "# sleep-ok: reason" if intentional',
        'warning'
    ),
    AntiPattern(
        r'qtbot\.wait\s*\(',
        'This wait pattern can segfault in offscreen mode. Use waitUntil(), '  # wait-ok: msg
        'waitSignal(), or wait_for_condition(). Allowlist with "# wait-ok: reason"',
        'warning'
    ),
    AntiPattern(
        r'QTest\.qWait\s*\(',
        'This wait pattern can segfault in offscreen mode. Use waitUntil(), '  # wait-ok: msg
        'waitSignal(), or wait_for_condition(). Allowlist with "# wait-ok: reason"',
        'warning'
    ),
    AntiPattern(
        r'from time import sleep',  # sleep-ok: pattern definition
        'Import time module instead; bare sleep is harder to grep for',
        'warning'
    ),
    AntiPattern(
        r'QThread\.sleep\(',
        'Use currentThread().msleep() instead of this sleep pattern',  # wait-ok: msg
        'warning'
    ),
    AntiPattern(
        r'class\s+Mock\w*\s*\(\s*QDialog\s*\)',
        'Never inherit from QDialog in mocks - causes metaclass crashes. Use QObject instead.',
        'error'
    ),
    AntiPattern(
        r'threading\.active_count\(\)\s*<=\s*\d+(?!\s*\+)',
        'Use baseline thread count instead of hardcoded value (capture at fixture start)',
        'warning'
    ),
    AntiPattern(
        r'cast\s*\(\s*\w+Manager\s*,',
        'Use RealComponentFactory instead of cast() for manager types',
        'warning'
    ),
    AntiPattern(
        r'(?<![a-zA-Z])QPixmap\s*\(',
        'QPixmap constructor in worker threads causes crashes. Use ThreadSafeTestImage or QImage instead.',
        'warning'
    ),
    AntiPattern(
        r'def\s+setup_singleton_cleanup\s*\(',
        'Use the centralized cleanup_singleton fixture from conftest.py instead',
        'warning'
    ),
    AntiPattern(
        r'if\s+self\.layout\s*:',
        'Qt containers can be falsy when empty. Use "if self.layout is not None:" instead',
        'warning'
    ),
]


def _iter_python_files(paths: list[Path]) -> list[Path]:
    """Expand files/directories into unique Python file paths."""
    seen: set[Path] = set()
    expanded: list[Path] = []

    for path in paths:
        if not path.exists():
            print(f"File not found: {path}", file=sys.stderr)
            continue

        if path.is_dir():
            for py_file in path.rglob("*.py"):
                if py_file not in seen:
                    seen.add(py_file)
                    expanded.append(py_file)
        elif path.suffix == ".py":
            if path not in seen:
                seen.add(path)
                expanded.append(path)

    return expanded


def check_file(file_path: Path) -> list[tuple[int, str, str, str]]:
    """Check a file for anti-patterns.

    Args:
        file_path: Path to the Python file to check

    Returns:
        List of tuples: (line_number, severity, pattern, message)
    """
    issues: list[tuple[int, str, str, str]] = []

    try:
        content = file_path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError) as e:
        print(f"Error reading {file_path}: {e}", file=sys.stderr)
        return issues

    lines = content.split('\n')

    for anti_pattern in ANTI_PATTERNS:
        for match in re.finditer(anti_pattern.pattern, content):
            # Find line number
            line_num = content[:match.start()].count('\n') + 1
            matched_text = match.group(0)

            # Skip if in a comment
            line = lines[line_num - 1] if line_num <= len(lines) else ''
            stripped = line.lstrip()
            if stripped.startswith('#'):
                continue

            # Skip if explicitly allowlisted
            if any(marker in line for marker in ['# sleep-ok', '# wait-ok', '# pixmap-ok', '# cast-ok']):
                continue

            issues.append((
                line_num,
                anti_pattern.severity,
                matched_text,
                anti_pattern.message
            ))

    return issues


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments for the checker."""
    parser = argparse.ArgumentParser(
        description="Check test files for common anti-patterns.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Files or directories to scan (defaults to tests/ when omitted).",
    )
    parser.add_argument(
        "--paths",
        dest="paths_flag",
        nargs="+",
        help="Files or directories to scan (explicit flag form).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if any issues found (warnings or errors). Default: only errors fail.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Main entry point.

    Returns:
        Exit code: 0 if no errors, 1 if errors found
    """
    args = _parse_args(argv or sys.argv[1:])
    raw_paths = args.paths_flag or args.paths or ["tests"]
    files = _iter_python_files([Path(p) for p in raw_paths])

    if not files:
        print("No Python files found to scan.", file=sys.stderr)
        return 0

    all_issues: list[tuple[Path, int, str, str, str]] = []
    has_errors = False

    for file_path in files:
        if not file_path.exists():
            print(f"File not found: {file_path}", file=sys.stderr)
            continue

        if file_path.suffix != '.py':
            continue

        issues = check_file(file_path)
        for line_num, severity, pattern, message in issues:
            all_issues.append((file_path, line_num, severity, pattern, message))
            if severity == 'error':
                has_errors = True

    if all_issues:
        print("Test anti-patterns detected:")
        print("-" * 60)
        for file_path, line_num, severity, pattern, message in all_issues:
            severity_marker = "[ERROR]" if severity == 'error' else "[WARN]"
            print(f"{severity_marker} {file_path}:{line_num}")
            print(f"  Pattern: {pattern}")
            print(f"  {message}")
            print()

        print(f"Total: {len(all_issues)} issue(s) found")
        if has_errors:
            return 1
        if args.strict:
            return 1
        return 0

    return 0


if __name__ == '__main__':
    sys.exit(main())
