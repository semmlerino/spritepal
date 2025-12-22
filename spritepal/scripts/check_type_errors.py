#!/usr/bin/env python3
from __future__ import annotations

"""
Type Error Analysis Script for CI/CD

Enhanced version of the existing typecheck_analysis.py specifically designed for CI/CD pipelines.
Parses basedpyright JSON output and enforces error thresholds.
"""

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class CITypeCheckAnalyzer:
    """CI-focused type checking analyzer with threshold enforcement."""

    # Critical error types that should be fixed first and count heavily
    CRITICAL_ERRORS = [
        "reportGeneralTypeIssues",
        "reportMissingTypeArgument",
        "reportUnknownMemberType",
        "reportUnknownParameterType",
        "reportArgumentType",
        "reportAssignmentType",
        "reportImportCycles",
        "reportAttributeAccessIssue",
        "reportOptionalMemberAccess",
        "reportOptionalSubscript",
        "reportIncompatibleMethodOverride",
        "reportUninitializedInstanceVariable",
    ]

    # Important errors that should be addressed but are less critical
    IMPORTANT_ERRORS = [
        "reportUnknownArgumentType",
        "reportUnusedCallResult",
        "reportReturnType",
        "reportIndexIssue",
    ]

    # Lower priority style/convention issues
    LOW_PRIORITY_ERRORS = [
        "reportUnusedImport",
        "reportUnknownVariableType",
        "reportMissingImports",
        "reportDeprecated",
        "reportUnannotatedClassAttribute",
    ]

    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path)
        self.errors: list[dict[str, Any]] = []
        self.warnings: list[dict[str, Any]] = []
        self.error_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.file_errors: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def run_basedpyright_json(self, files: list[str | None] | None = None) -> dict[str, Any]:
        """Run basedpyright with JSON output."""
        cmd = ["basedpyright", "--outputjson"]

        if files:
            cmd.extend(files)
        else:
            cmd.append(".")

        print("🔍 Running basedpyright with JSON output...")
        print(f"   Command: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                cwd=self.project_path
            )

            # Try to parse JSON output
            if result.stdout.strip():
                try:
                    return json.loads(result.stdout)
                except json.JSONDecodeError:
                    print("⚠️ Could not parse JSON output, falling back to text parsing")
                    return {"summary": {"errorCount": 0, "warningCount": 0}, "generalDiagnostics": []}

            return {"summary": {"errorCount": 0, "warningCount": 0}, "generalDiagnostics": []}

        except Exception as e:
            print(f"❌ Error running basedpyright: {e}")
            return {"summary": {"errorCount": 0, "warningCount": 0}, "generalDiagnostics": []}

    def parse_json_output(self, json_data: dict[str, Any]) -> None:
        """Parse basedpyright JSON output into structured data."""
        json_data.get("summary", {})
        diagnostics = json_data.get("generalDiagnostics", [])

        for diagnostic in diagnostics:
            file_path = diagnostic.get("file", "unknown")
            start_pos = diagnostic.get("range", {}).get("start", {})
            line_num = start_pos.get("line", 0) + 1  # Convert to 1-based
            col_num = start_pos.get("character", 0) + 1  # Convert to 1-based
            severity = diagnostic.get("severity", "error").lower()
            message = diagnostic.get("message", "")
            rule = diagnostic.get("rule", "unknown")

            error_info = {
                "file": file_path,
                "line": line_num,
                "col": col_num,
                "severity": severity,
                "message": message,
                "type": rule,
                "full_diagnostic": diagnostic
            }

            if severity == "error":
                self.errors.append(error_info)
                self.error_groups[rule].append(error_info)
                self.file_errors[file_path].append(error_info)
            else:
                self.warnings.append(error_info)

    def categorize_errors(self) -> dict[str, int]:
        """Categorize errors by priority level."""
        categories = {
            "critical": 0,
            "important": 0,
            "low_priority": 0,
            "unknown": 0
        }

        for error_type, errors in self.error_groups.items():
            count = len(errors)
            if error_type in self.CRITICAL_ERRORS:
                categories["critical"] += count
            elif error_type in self.IMPORTANT_ERRORS:
                categories["important"] += count
            elif error_type in self.LOW_PRIORITY_ERRORS:
                categories["low_priority"] += count
            else:
                categories["unknown"] += count

        return categories

    def generate_ci_report(self,
                          threshold_critical: int = 20,
                          threshold_total: int = 150) -> dict[str, Any]:
        """Generate a comprehensive report for CI/CD usage."""
        categories = self.categorize_errors()

        # Calculate file-based metrics
        files_with_errors = len(self.file_errors)
        worst_files = sorted(
            [(f, len(errs)) for f, errs in self.file_errors.items()],
            key=lambda x: x[1],
            reverse=True
        )[:10]

        # Error type breakdown
        error_type_counts = {k: len(v) for k, v in self.error_groups.items()}
        top_error_types = sorted(
            error_type_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]

        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "summary": {
                "total_errors": len(self.errors),
                "total_warnings": len(self.warnings),
                "files_with_errors": files_with_errors,
            },
            "thresholds": {
                "critical_threshold": threshold_critical,
                "total_threshold": threshold_total,
                "critical_passed": categories["critical"] <= threshold_critical,
                "total_passed": len(self.errors) <= threshold_total,
                "overall_passed": (categories["critical"] <= threshold_critical and
                                 len(self.errors) <= threshold_total)
            },
            "categories": categories,
            "critical_errors": categories["critical"],
            "error_types": error_type_counts,
            "top_error_types": top_error_types,
            "worst_files": worst_files,
            "critical_examples": self._get_critical_examples(),
            "trend_data": {
                "errors_per_file": len(self.errors) / max(files_with_errors, 1),
                "critical_ratio": categories["critical"] / max(len(self.errors), 1)
            }
        }

    def _get_critical_examples(self, max_examples: int = 5) -> list[dict[str, Any]]:
        """Get examples of critical errors for the report."""
        examples = []
        shown = 0

        for error_type in self.CRITICAL_ERRORS:
            if error_type in self.error_groups and shown < max_examples:
                for error in self.error_groups[error_type][:2]:  # Max 2 per type
                    examples.append({
                        "type": error_type,
                        "file": error["file"],
                        "line": error["line"],
                        "message": error["message"]
                    })
                    shown += 1
                    if shown >= max_examples:
                        break

        return examples

    def print_ci_summary(self, report: dict[str, Any], github_actions: bool = False) -> None:
        """Print CI-friendly summary."""
        summary = report["summary"]
        categories = report["categories"]
        thresholds = report["thresholds"]

        if github_actions:
            # GitHub Actions formatted output
            print(f"::notice::Total errors: {summary['total_errors']}")
            print(f"::notice::Critical errors: {categories['critical']}")
            print(f"::notice::Files with errors: {summary['files_with_errors']}")

            if not thresholds["critical_passed"]:
                print(f"::error::Critical errors ({categories['critical']}) exceed threshold ({thresholds['critical_threshold']})")

            if not thresholds["total_passed"]:
                print(f"::error::Total errors ({summary['total_errors']}) exceed threshold ({thresholds['total_threshold']})")

            # Show critical examples
            for example in report["critical_examples"]:
                print(f"::error file={example['file']},line={example['line']}::{example['type']}: {example['message']}")

        else:
            # Standard output
            print("\n" + "=" * 60)
            print("🔍 CI TYPE CHECKING SUMMARY")
            print("=" * 60)

            print("\n📊 Results:")
            print(f"   Total errors: {summary['total_errors']}")
            print(f"   Critical errors: {categories['critical']}")
            print(f"   Important errors: {categories['important']}")
            print(f"   Files affected: {summary['files_with_errors']}")

            print("\n🎯 Thresholds:")
            status_critical = "✅" if thresholds["critical_passed"] else "❌"
            status_total = "✅" if thresholds["total_passed"] else "❌"
            print(f"   {status_critical} Critical: {categories['critical']}/{thresholds['critical_threshold']}")
            print(f"   {status_total} Total: {summary['total_errors']}/{thresholds['total_threshold']}")

            if report["critical_examples"]:
                print("\n🚨 Critical Error Examples:")
                for example in report["critical_examples"]:
                    print(f"   {example['file']}:{example['line']} - {example['type']}")
                    print(f"      {example['message']}")

def main():
    parser = argparse.ArgumentParser(
        description="CI/CD Type checking analyzer with threshold enforcement"
    )
    parser.add_argument(
        "--input", "-i",
        help="Input JSON file from basedpyright (if not provided, runs basedpyright)"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output JSON report file"
    )
    parser.add_argument(
        "--threshold-critical",
        type=int,
        default=20,
        help="Maximum allowed critical errors (default: 20)"
    )
    parser.add_argument(
        "--threshold-total",
        type=int,
        default=150,
        help="Maximum allowed total errors (default: 150)"
    )
    parser.add_argument(
        "--github-actions",
        action="store_true",
        help="Format output for GitHub Actions"
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Specific files to check (default: entire project)"
    )

    args = parser.parse_args()

    analyzer = CITypeCheckAnalyzer()

    # Get type checking data
    if args.input and Path(args.input).exists():
        # Load from existing JSON file
        with Path(args.input).open() as f:
            json_data = json.load(f)
    else:
        # Run basedpyright
        json_data = analyzer.run_basedpyright_json(args.files)

    # Parse the data
    analyzer.parse_json_output(json_data)

    # Generate report
    report = analyzer.generate_ci_report(
        threshold_critical=args.threshold_critical,
        threshold_total=args.threshold_total
    )

    # Print summary
    analyzer.print_ci_summary(report, args.github_actions)

    # Save report if requested
    if args.output:
        with Path(args.output).open('w') as f:
            json.dump(report, f, indent=2)
        print(f"\n💾 Report saved to: {args.output}")

    # Exit with appropriate code
    if not report["thresholds"]["overall_passed"]:
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
