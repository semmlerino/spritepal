#!/usr/bin/env python3
from __future__ import annotations

"""
Audit script to find potential Qt boolean evaluation issues in the codebase.

This script looks for patterns where Qt objects might be used in boolean contexts,
which can cause bugs when the objects are empty but not None.
"""

import re
from collections import defaultdict
from pathlib import Path

# Qt object suffixes that might have boolean evaluation issues
QT_OBJECT_PATTERNS = [
    r"_widget\b",
    r"_layout\b",
    r"_tab_widget\b",
    r"_dialog\b",
    r"_button\b",
    r"_label\b",
    r"_spinbox\b",
    r"_combo\b",
    r"_list\b",
    r"_table\b",
    r"_tree\b",
    r"_view\b",
    r"_model\b",
    r"_action\b",
    r"_menu\b",
    r"_toolbar\b",
]

# Patterns to look for
PROBLEMATIC_PATTERNS = [
    # Direct boolean check: if self._widget:
    (r"if\s+(not\s+)?self\.([a-zA-Z_][a-zA-Z0-9_]*)\s*:", "direct_bool_check"),
    # Ternary operator: x if self._widget else y
    (r"[^:]\s+if\s+self\.([a-zA-Z_][a-zA-Z0-9_]*)\s+else\s+", "ternary_operator"),
    # Boolean operators: self._widget and x
    (r"self\.([a-zA-Z_][a-zA-Z0-9_]*)\s+(and|or)\s+", "bool_operator"),
    # While loops: while self._widget:
    (r"while\s+(not\s+)?self\.([a-zA-Z_][a-zA-Z0-9_]*)\s*:", "while_loop"),
]

# Patterns that are OK (to reduce false positives)
OK_PATTERNS = [
    r"is\s+not\s+None",
    r"is\s+None",
    r"==\s*None",
    r"!=\s*None",
    r"\(\s*\)",  # Method calls like widget()
    r"\.count\s*\(\s*\)",
    r"\.isVisible\s*\(\s*\)",
    r"\.isEnabled\s*\(\s*\)",
]


def is_qt_object(var_name: str) -> bool:
    """Check if a variable name looks like a Qt object."""
    return any(re.search(pattern, var_name) for pattern in QT_OBJECT_PATTERNS)


def is_ok_pattern(line: str, match_start: int) -> bool:
    """Check if the match is actually part of an OK pattern."""
    # Look at the context around the match
    context = line[max(0, match_start - 20) : min(len(line), match_start + 50)]

    return any(re.search(ok_pattern, context) for ok_pattern in OK_PATTERNS)


def audit_file(file_path: Path) -> list[tuple[int, str, str, str]]:
    """Audit a single Python file for Qt boolean evaluation issues."""
    issues = []

    try:
        with Path(file_path).open(encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return issues

    for line_num, line in enumerate(lines, 1):
        for pattern, issue_type in PROBLEMATIC_PATTERNS:
            matches = list(re.finditer(pattern, line))

            for match in matches:
                # Extract the variable name
                if issue_type in {"direct_bool_check", "while_loop"}:
                    var_name = match.group(2) if match.group(2) else match.group(1)
                else:
                    var_name = match.group(1)

                # Check if it looks like a Qt object
                if var_name and is_qt_object(var_name):
                    # Check if it's actually an OK pattern
                    if not is_ok_pattern(line, match.start()):
                        issues.append((line_num, var_name, issue_type, line.strip()))

    return issues


def audit_codebase(root_dir: Path) -> None:
    """Audit the entire codebase for Qt boolean evaluation issues."""
    print("=== Qt Boolean Evaluation Audit ===\n")

    all_issues = []
    file_count = 0

    # Walk through all Python files
    for py_file in root_dir.rglob("*.py"):
        # Skip test files and generated files
        if any(skip in str(py_file) for skip in ["__pycache__", ".pytest_cache", "venv/", ".git/"]):
            continue

        file_count += 1
        issues = audit_file(py_file)

        if issues:
            for line_num, var_name, issue_type, line_content in issues:
                all_issues.append(
                    {
                        "file": py_file.relative_to(root_dir),
                        "line": line_num,
                        "variable": var_name,
                        "type": issue_type,
                        "content": line_content,
                    }
                )

    print(f"Scanned {file_count} Python files\n")

    if all_issues:
        print(f"Found {len(all_issues)} potential Qt boolean evaluation issues:\n")

        # Group by file
        by_file = defaultdict(list)
        for issue in all_issues:
            by_file[issue["file"]].append(issue)

        # Sort files by number of issues
        sorted_files = sorted(by_file.items(), key=lambda x: len(x[1]), reverse=True)

        for file_path, file_issues in sorted_files:
            print(f"\n📄 {file_path} ({len(file_issues)} issues):")
            for issue in file_issues:
                print(f"  Line {issue['line']}: {issue['variable']} ({issue['type']})")
                print(f"    {issue['content']}")

        print("\n📊 Summary by issue type:")
        type_counts = defaultdict(int)
        for issue in all_issues:
            type_counts[issue["type"]] += 1

        for issue_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"  • {issue_type}: {count}")

        print("\n💡 Recommendation:")
        print("Replace these patterns with explicit 'is not None' checks:")
        print("  ❌ if self._widget:")
        print("  ✅ if self._widget is not None:")
    else:
        print("✅ No Qt boolean evaluation issues found!")

    print("\n📝 See docs/qt_boolean_evaluation_pitfall.md for more information")


if __name__ == "__main__":
    # Run audit from the spritepal directory
    root_dir = Path(__file__).parent.parent
    audit_codebase(root_dir)
