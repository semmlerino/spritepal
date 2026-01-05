"""
Mock density monitoring script.

This script monitors mock usage density in test files to ensure tests remain
focused and maintainable. High mock density can indicate over-mocking or
poorly structured tests.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any


class MockDensityAnalyzer:
    """Analyzes mock usage density in test files."""

    # Keywords that indicate mock usage
    MOCK_KEYWORDS = {
        "mock",
        "Mock",
        "MagicMock",
        "patch",
        "mock_open",
        "create_autospec",
        "spec_set",
        "side_effect",
        "return_value",
        "call_count",
        "called",
        "assert_called",
        "assert_called_with",
        "assert_called_once",
        "assert_called_once_with",
        "assert_has_calls",
        "assert_any_call",
        "assert_not_called",
        "reset_mock",
        "configure_mock",
        "attach_mock",
        "MockFactory",
        "mock_manager",
        "mock_dialog",
        "mock_widget",
        "mock_extraction_manager",
    }

    # Mock-related imports
    MOCK_IMPORTS = {
        "unittest.mock",
        "mock",
        "pytest_mock",
        "unittest.mock.Mock",
        "unittest.mock.MagicMock",
        "unittest.mock.patch",
    }

    def __init__(self, max_density: float = 0.02):
        """
        Initialize the mock density analyzer.

        Args:
            max_density: Maximum allowed mock density (mocks per line of code)
        """
        self.max_density = max_density
        self.results: list[dict[str, Any]] = []

    def analyze_file(self, filepath: Path) -> dict[str, Any]:
        """
        Analyze mock density in a single file.

        Args:
            filepath: Path to the test file to analyze

        Returns:
            Dictionary containing analysis results
        """
        try:
            code = filepath.read_text(encoding="utf-8")
            lines = code.split("\n")
            total_lines = len([line for line in lines if line.strip()])  # Non-empty lines

            if total_lines == 0:
                return {
                    "file": str(filepath),
                    "total_lines": 0,
                    "mock_usage_count": 0,
                    "mock_density": 0.0,
                    "exceeds_limit": False,
                    "mock_details": [],
                    "error": None,
                }

            # Count mock usage
            mock_usage_count, mock_details = self._count_mock_usage(code, lines)

            # Calculate density
            mock_density = mock_usage_count / total_lines if total_lines > 0 else 0.0
            exceeds_limit = mock_density > self.max_density

            return {
                "file": str(filepath),
                "total_lines": total_lines,
                "mock_usage_count": mock_usage_count,
                "mock_density": round(mock_density, 4),
                "exceeds_limit": exceeds_limit,
                "mock_details": mock_details,
                "error": None,
            }

        except Exception as e:
            return {
                "file": str(filepath),
                "total_lines": 0,
                "mock_usage_count": 0,
                "mock_density": 0.0,
                "exceeds_limit": False,
                "mock_details": [],
                "error": str(e),
            }

    def _count_mock_usage(self, code: str, lines: list[str]) -> tuple[int, list[dict[str, Any]]]:
        """
        Count mock usage in code.

        Args:
            code: Full code content
            lines: List of code lines

        Returns:
            (mock_count, list_of_mock_details)
        """
        mock_count = 0
        mock_details = []

        # Count keyword occurrences in lines
        for line_num, line in enumerate(lines, 1):
            line_mocks = []

            for keyword in self.MOCK_KEYWORDS:
                # Count occurrences of each keyword in the line
                occurrences = line.count(keyword)
                if occurrences > 0:
                    mock_count += occurrences
                    line_mocks.append(
                        {
                            "keyword": keyword,
                            "count": occurrences,
                            "context": line.strip()[:100],  # First 100 chars for context
                        }
                    )

            if line_mocks:
                mock_details.append({"line": line_num, "mocks": line_mocks})

        # Also analyze AST for more sophisticated detection
        try:
            tree = ast.parse(code)
            ast_mocks = self._analyze_ast_for_mocks(tree)
            mock_details.extend(ast_mocks)
        except SyntaxError:
            # If AST parsing fails, continue with line-based analysis
            pass

        return mock_count, mock_details

    def _analyze_ast_for_mocks(self, tree: ast.AST) -> list[dict[str, Any]]:
        """
        Analyze AST for mock patterns.

        Args:
            tree: AST tree to analyze

        Returns:
            List of mock details found via AST analysis
        """
        mock_details = []

        for node in ast.walk(tree):
            # Look for decorator patterns
            if isinstance(node, ast.FunctionDef):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Name) and "mock" in decorator.id.lower():
                        mock_details.append(
                            {
                                "type": "decorator",
                                "line": decorator.lineno,
                                "function": node.name,
                                "decorator": decorator.id,
                            }
                        )
                    elif isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                        if "mock" in str(decorator.func.attr).lower():
                            mock_details.append(
                                {
                                    "type": "decorator_call",
                                    "line": decorator.lineno,
                                    "function": node.name,
                                    "decorator": str(decorator.func.attr),
                                }
                            )

            # Look for mock imports
            if isinstance(node, ast.Import | ast.ImportFrom):
                for alias in node.names:
                    if any(mock_import in (alias.name or "") for mock_import in self.MOCK_IMPORTS):
                        mock_details.append(
                            {"type": "import", "line": node.lineno, "module": alias.name, "alias": alias.asname}
                        )

        return mock_details

    def analyze_directory(self, directory: Path, pattern: str = "test_*.py") -> list[dict[str, Any]]:
        """
        Analyze all test files in a directory.

        Args:
            directory: Directory containing test files
            pattern: Glob pattern for test files

        Returns:
            List of analysis results for each file
        """
        self.results = []

        test_files = list(directory.glob(pattern))
        if not test_files:
            test_files = list(directory.rglob(pattern))  # Recursive search

        for test_file in test_files:
            result = self.analyze_file(test_file)
            self.results.append(result)

        return self.results

    def generate_report(self, output_file: Path | None = None) -> str:
        """
        Generate a mock density report.

        Args:
            output_file: Optional file to save report to

        Returns:
            Report as string
        """
        if not self.results:
            return "No analysis results available"

        # Sort by density (highest first)
        sorted_results = sorted(self.results, key=lambda x: x["mock_density"], reverse=True)

        report_lines = [
            "Mock Density Analysis Report",
            "=" * 40,
            f"Maximum allowed density: {self.max_density}",
            f"Total files analyzed: {len(self.results)}",
            "",
        ]

        # Summary statistics
        total_violations = sum(1 for r in self.results if r["exceeds_limit"])
        avg_density = sum(r["mock_density"] for r in self.results) / len(self.results)
        max_density = max(r["mock_density"] for r in self.results)

        report_lines.extend(
            [
                "Summary:",
                f"  Files exceeding limit: {total_violations}",
                f"  Average density: {avg_density:.4f}",
                f"  Maximum density: {max_density:.4f}",
                "",
            ]
        )

        # Files exceeding limit
        violations = [r for r in sorted_results if r["exceeds_limit"]]
        if violations:
            report_lines.extend(["Files Exceeding Density Limit:", "-" * 35])

            for result in violations:
                report_lines.extend(
                    [
                        f"❌ {result['file']}",
                        f"   Density: {result['mock_density']} ({result['mock_usage_count']} mocks / {result['total_lines']} lines)",
                        "",
                    ]
                )

        # All files summary
        report_lines.extend(["All Files:", "-" * 15])

        for result in sorted_results:
            status = "❌" if result["exceeds_limit"] else "✅"
            error_info = f" (ERROR: {result['error']})" if result["error"] else ""

            report_lines.append(f"{status} {Path(result['file']).name}: {result['mock_density']:.4f}{error_info}")

        report = "\n".join(report_lines)

        # Save to file if requested
        if output_file:
            output_file.write_text(report, encoding="utf-8")

        return report

    def save_detailed_json(self, output_file: Path) -> None:
        """
        Save detailed analysis results to JSON.

        Args:
            output_file: Path to save JSON results
        """
        output_file.write_text(json.dumps(self.results, indent=2, default=str), encoding="utf-8")

    def check_compliance(self) -> bool:
        """
        Check if all files comply with density limits.

        Returns:
            True if all files are compliant
        """
        return all(not result["exceeds_limit"] for result in self.results)


def main():
    """Main entry point for the script."""
    import argparse

    parser = argparse.ArgumentParser(description="Monitor mock density in test files")
    parser.add_argument(
        "directory", nargs="?", default="tests", help="Directory containing test files (default: tests)"
    )
    parser.add_argument("--max-density", type=float, default=0.02, help="Maximum allowed mock density (default: 0.02)")
    parser.add_argument("--pattern", default="test_*.py", help="Glob pattern for test files (default: test_*.py)")
    parser.add_argument("--output", type=Path, help="Save report to file")
    parser.add_argument("--json-output", type=Path, help="Save detailed JSON results to file")
    parser.add_argument("--fail-on-violation", action="store_true", help="Exit with non-zero code if violations found")
    parser.add_argument("--quiet", action="store_true", help="Only show violations, not full report")

    args = parser.parse_args()

    # Initialize analyzer
    analyzer = MockDensityAnalyzer(max_density=args.max_density)

    # Find directory
    directory = Path(args.directory)
    if not directory.exists():
        print(f"Error: Directory '{directory}' not found")
        sys.exit(1)

    # Analyze files
    print(f"Analyzing test files in {directory} with pattern '{args.pattern}'...")
    results = analyzer.analyze_directory(directory, args.pattern)

    if not results:
        print("No test files found")
        sys.exit(0)

    # Generate report
    report = analyzer.generate_report(args.output)

    # Save detailed JSON if requested
    if args.json_output:
        analyzer.save_detailed_json(args.json_output)
        print(f"Detailed results saved to: {args.json_output}")

    # Display results
    if not args.quiet:
        print("\n" + report)
    else:
        # Only show violations in quiet mode
        violations = [r for r in results if r["exceeds_limit"]]
        if violations:
            print(f"Found {len(violations)} violations:")
            for result in violations:
                print(f"  {result['file']}: {result['mock_density']:.4f}")
        else:
            print("No violations found")

    # Check compliance
    is_compliant = analyzer.check_compliance()

    if args.fail_on_violation and not is_compliant:
        print("\n❌ Mock density violations found!")
        sys.exit(1)
    elif is_compliant:
        print("\n✅ All files comply with mock density limits")

    return 0 if is_compliant else 1


if __name__ == "__main__":
    sys.exit(main())
