#!/usr/bin/env python3
"""Check for common test anti-patterns in Python test files.

This script can be used as a pre-commit hook or standalone linter to detect
problematic patterns in test code that are known to cause flaky tests,
crashes, or maintenance issues.

Usage:
    # Check specific files
    python check_test_patterns.py tests/test_foo.py tests/test_bar.py

    # Use with pre-commit (in .pre-commit-config.yaml):
    - repo: local
      hooks:
        - id: check-test-patterns
          name: Check test anti-patterns
          entry: python tests/infrastructure/check_test_patterns.py
          language: python
          types: [python]
          files: "^tests/.*\\\\.py$"
"""
from __future__ import annotations

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
        r'time\.sleep\(\d+\)',
        'Use qtbot.wait() or qtbot.waitSignal() instead of time.sleep() in Qt tests',
        'warning'
    ),
    AntiPattern(
        r'QThread\.sleep\(',
        'Use QThread.currentThread().msleep() instead of QThread.sleep()',
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
        r'QPixmap\s*\(',
        'QPixmap in worker threads causes crashes. Use ThreadSafeTestImage or QImage instead.',
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

            issues.append((
                line_num,
                anti_pattern.severity,
                matched_text,
                anti_pattern.message
            ))

    return issues


def main() -> int:
    """Main entry point.

    Returns:
        Exit code: 0 if no errors, 1 if errors found
    """
    if len(sys.argv) < 2:
        print("Usage: check_test_patterns.py <file1.py> [file2.py ...]", file=sys.stderr)
        return 1

    files = [Path(f) for f in sys.argv[1:]]
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
        return 1 if has_errors else 0

    return 0


if __name__ == '__main__':
    sys.exit(main())
