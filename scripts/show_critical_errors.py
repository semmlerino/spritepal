#!/usr/bin/env python3
from __future__ import annotations

"""
Quick script to show critical basedpyright errors.
Useful for focusing on the most important type issues.
"""

import re
import subprocess
from collections import defaultdict

# Define critical error types
CRITICAL_TYPES = [
    "reportGeneralTypeIssues",
    "reportMissingTypeArgument",
    "reportImportCycles",
    "reportArgumentType",
    "reportAssignmentType",
]


def main():
    print("🔍 Running basedpyright to find critical errors...\n")

    # Run basedpyright
    result = subprocess.run(["basedpyright", "."], check=False, capture_output=True, text=True)

    output = result.stdout + result.stderr

    # Parse errors
    error_pattern = r"([^:]+\.py):(\d+):(\d+) - error: (.+?)\s*\(([^)]+)\)"
    errors = defaultdict(list)
    total_errors = 0

    for line in output.split("\n"):
        match = re.match(error_pattern, line)
        if match:
            file_path, line_num, _col_num, message, error_type = match.groups()
            total_errors += 1

            if error_type in CRITICAL_TYPES:
                errors[error_type].append({"file": file_path, "line": int(line_num), "message": message})

    # Show results
    print(f"Total errors found: {total_errors}\n")

    if errors:
        print("🚨 CRITICAL ERRORS THAT NEED IMMEDIATE ATTENTION:\n")

        for error_type in CRITICAL_TYPES:
            if error_type in errors:
                print(f"\n🔴 {error_type} ({len(errors[error_type])} errors):")
                print("-" * 60)

                # Show first 5 of each type
                for error in errors[error_type][:5]:
                    print(f"{error['file']}:{error['line']}")
                    print(f"  {error['message']}\n")

                if len(errors[error_type]) > 5:
                    print(f"  ... and {len(errors[error_type]) - 5} more\n")
    else:
        print("✅ No critical errors found!")
        print("\nConsider running the full analysis with:")
        print("  python scripts/typecheck_analysis.py")


if __name__ == "__main__":
    main()
