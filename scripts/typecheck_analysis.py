#!/usr/bin/env python3
from __future__ import annotations

"""
BasedPyright Type Checking Analysis Tool

A development utility for running basedpyright and analyzing type errors.
Helps prioritize and fix the most critical type checking issues.
"""

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path


class TypeCheckAnalyzer:
    """Analyzes basedpyright output to help prioritize fixes."""

    # Critical error types that should be fixed first
    CRITICAL_ERRORS = [
        "reportGeneralTypeIssues",
        "reportMissingTypeArgument",
        "reportUnknownMemberType",
        "reportUnknownParameterType",
        "reportArgumentType",
        "reportAssignmentType",
        "reportImportCycles",
    ]

    # Common error types that are lower priority
    COMMON_ERRORS = [
        "reportOptionalMemberAccess",
        "reportOptionalSubscript",
        "reportUninitializedInstanceVariable",
        "reportUnusedCallResult",
        "reportUnknownArgumentType",
    ]

    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path)
        self.errors = []
        self.warnings = []
        self.error_groups = defaultdict(list)
        self.file_errors = defaultdict(list)

    def run_basedpyright(self, files: list[str] | None = None) -> str:
        """Run basedpyright and capture output."""
        cmd = ["basedpyright"]

        if files:
            cmd.extend(files)
        else:
            cmd.append(".")

        print("🔍 Running basedpyright...")
        print(f"   Command: {' '.join(cmd)}")
        print()

        try:
            result = subprocess.run(cmd, check=False, capture_output=True, text=True, cwd=self.project_path)
            return result.stdout + result.stderr
        except Exception as e:
            print(f"❌ Error running basedpyright: {e}")
            return ""

    def parse_output(self, output: str):
        """Parse basedpyright output into structured data."""

        # Pattern for error/warning lines
        pattern = r"([^:]+\.py):(\d+):(\d+) - (error|warning): (.+?)\s*\(([^)]+)\)"

        for line in output.split("\n"):
            match = re.match(pattern, line)
            if match:
                file_path, line_num, col_num, severity, message, error_type = match.groups()

                error_info = {
                    "file": file_path,
                    "line": int(line_num),
                    "col": int(col_num),
                    "severity": severity,
                    "message": message,
                    "type": error_type,
                    "full_line": line,
                }

                if severity == "error":
                    self.errors.append(error_info)
                    self.error_groups[error_type].append(error_info)
                    self.file_errors[file_path].append(error_info)
                else:
                    self.warnings.append(error_info)

    def print_summary(self):
        """Print a summary of findings."""
        print("\n" + "=" * 60)
        print("📊 TYPE CHECKING SUMMARY")
        print("=" * 60)
        print(f"\n🔴 Errors: {len(self.errors)}")
        print(f"⚠️  Warnings: {len(self.warnings)}")
        print(f"📁 Files with errors: {len(self.file_errors)}")

    def print_critical_errors(self, max_show: int = 10):
        """Print the most critical errors."""
        print("\n" + "=" * 60)
        print("🚨 CRITICAL ERRORS (Fix These First)")
        print("=" * 60)

        shown = 0
        for error_type in self.CRITICAL_ERRORS:
            if error_type in self.error_groups and shown < max_show:
                errors = self.error_groups[error_type]
                print(f"\n🔴 {error_type} ({len(errors)} errors):")
                print("-" * 40)

                for error in errors[:3]:  # Show up to 3 examples
                    print(f"{error['file']}:{error['line']}:{error['col']}")
                    print(f"  {error['message']}\n")
                    shown += 1
                    if shown >= max_show:
                        break

    def print_error_by_type(self):
        """Print errors grouped by type."""
        print("\n" + "=" * 60)
        print("📈 ERRORS BY TYPE")
        print("=" * 60)

        # Sort by count
        sorted_errors = sorted(self.error_groups.items(), key=lambda x: len(x[1]), reverse=True)

        for error_type, errors in sorted_errors:
            severity = "🔴" if error_type in self.CRITICAL_ERRORS else "🟡"
            print(f"{severity} {error_type}: {len(errors)} errors")

    def print_files_with_most_errors(self, limit: int = 10):
        """Print files with the most errors."""
        print("\n" + "=" * 60)
        print("📄 FILES WITH MOST ERRORS")
        print("=" * 60)

        sorted_files = sorted(self.file_errors.items(), key=lambda x: len(x[1]), reverse=True)

        for file_path, errors in sorted_files[:limit]:
            print(f"\n{file_path}: {len(errors)} errors")
            # Show error type breakdown
            type_counts = defaultdict(int)
            for error in errors:
                type_counts[error["type"]] += 1
            for error_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
                print(f"  - {error_type}: {count}")

    def save_report(self, filename: str | None = None):
        """Save analysis report to file."""
        if not filename:
            timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            filename = f"typecheck_report_{timestamp}.json"

        report = {
            "timestamp": datetime.now(UTC).isoformat(),
            "summary": {
                "total_errors": len(self.errors),
                "total_warnings": len(self.warnings),
                "files_with_errors": len(self.file_errors),
            },
            "error_groups": {k: len(v) for k, v in self.error_groups.items()},
            "file_errors": {k: len(v) for k, v in self.file_errors.items()},
            "critical_errors": [],
        }

        # Add some critical error examples
        for error_type in self.CRITICAL_ERRORS:
            if error_type in self.error_groups:
                report["critical_errors"].extend(self.error_groups[error_type][:3])

        filename_path = Path(filename)
        with filename_path.open("w") as f:
            json.dump(report, f, indent=2)

        print(f"\n💾 Report saved to: {filename}")


def main():
    parser = argparse.ArgumentParser(description="Analyze basedpyright type checking results")
    parser.add_argument("files", nargs="*", help="Specific files to check (default: entire project)")
    parser.add_argument("--save", "-s", help="Save report to file", action="store_true")
    parser.add_argument("--critical", "-c", help="Show only critical errors", action="store_true")
    parser.add_argument("--limit", "-l", type=int, default=20, help="Maximum number of errors to show (default: 20)")

    args = parser.parse_args()

    analyzer = TypeCheckAnalyzer()

    # Run basedpyright
    output = analyzer.run_basedpyright(args.files)
    if not output:
        print("❌ Failed to run basedpyright")
        return 1

    # Parse output
    analyzer.parse_output(output)

    # Show results
    analyzer.print_summary()

    if args.critical:
        analyzer.print_critical_errors(args.limit)
    else:
        analyzer.print_critical_errors(10)
        analyzer.print_error_by_type()
        analyzer.print_files_with_most_errors()

    # Save report if requested
    if args.save:
        analyzer.save_report()

    # Return exit code based on errors
    return 0 if len(analyzer.errors) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
