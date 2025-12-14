#!/usr/bin/env python3
from __future__ import annotations

"""
Test Infrastructure Cleanup Script

This script modernizes the SpritePal test infrastructure by:
1. Identifying tests with excessive mocking patterns
2. Providing migration recommendations
3. Validating test references and imports
4. Generating cleanup reports
"""

import ast
import sys
from collections import defaultdict
from pathlib import Path

import pytest

# NOTE: pythonpath configured in pyproject.toml - no sys.path manipulation needed

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.dialog,
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.mock_dialogs,
    pytest.mark.mock_only,
    pytest.mark.parallel_safe,
    pytest.mark.qt_mock,
    pytest.mark.rom_data,
    pytest.mark.ci_safe,
    pytest.mark.integration,
]

class InfrastructureAnalyzer:
    """Analyzes and reports on test infrastructure issues."""

    def __init__(self, test_dir: Path):
        self.test_dir = test_dir
        self.issues = defaultdict(list)
        self.mock_patterns = defaultdict(int)
        self.outdated_imports = []

    def analyze_all_tests(self) -> dict[str, any]:
        """Analyze all test files and generate comprehensive report."""
        test_files = list(self.test_dir.glob("**/*.py"))

        results = {
            "total_files": len(test_files),
            "excessive_mocking": [],
            "outdated_imports": [],
            "conftest_issues": [],
            "recommendations": [],
        }

        for test_file in test_files:
            if test_file.name.startswith("test_"):
                self._analyze_test_file(test_file, results)

        self._analyze_conftest_files(results)
        self._generate_recommendations(results)

        return results

    def _analyze_test_file(self, test_file: Path, results: dict):
        """Analyze a single test file for issues."""
        try:
            with open(test_file, encoding="utf-8") as f:
                content = f.read()

            # Parse AST
            tree = ast.parse(content)

            # Count mock usage
            mock_count = self._count_mock_usage(tree, content)
            if mock_count > 5:  # Threshold for excessive mocking
                results["excessive_mocking"].append({
                    "file": str(test_file.relative_to(self.test_dir)),
                    "mock_count": mock_count,
                    "patterns": self._identify_mock_patterns(content)
                })

            # Check for outdated imports
            outdated = self._check_outdated_imports(tree, content, test_file)
            if outdated:
                results["outdated_imports"].extend(outdated)

        except (SyntaxError, UnicodeDecodeError) as e:
            results["outdated_imports"].append({
                "file": str(test_file.relative_to(self.test_dir)),
                "error": f"Parse error: {e}"
            })

    def _count_mock_usage(self, tree: ast.AST, content: str) -> int:
        """Count the number of mock-related patterns in the file."""
        mock_count = 0

        # Count @patch decorators
        mock_count += content.count("@patch")

        # Count Mock() instantiations
        mock_count += content.count("Mock(")

        # Count create_mock_ function calls
        mock_count += content.count("create_mock_")

        return mock_count

    def _identify_mock_patterns(self, content: str) -> list[str]:
        """Identify specific mock patterns used in the file."""
        patterns = []

        if "@patch" in content:
            patterns.append("decorator_patching")
        if "create_mock_main_window" in content:
            patterns.append("main_window_mocking")
        if "create_mock_extraction_worker" in content:
            patterns.append("worker_mocking")
        if "MockSignal" in content:
            patterns.append("signal_mocking")
        if content.count("Mock(") > 3:
            patterns.append("heavy_mocking")

        return patterns

    def _check_outdated_imports(self, tree: ast.AST, content: str, test_file: Path) -> list[dict]:
        """Check for outdated import references."""
        outdated = []

        # Check for manual_offset_dialog imports (should be UnifiedManualOffsetDialog)
        if "manual_offset_dialog_simplified" in content and "UnifiedManualOffsetDialog" not in content:
            outdated.append({
                "file": str(test_file.relative_to(self.test_dir)),
                "issue": "outdated_manual_offset_dialog_import",
                "line": self._find_import_line(content, "manual_offset_dialog")
            })

        # Check for direct Qt imports in test files (should use conftest fixtures)
        qt_imports = ["from PySide6", "import PySide6"]
        for qt_import in qt_imports:
            if qt_import in content:
                outdated.append({
                    "file": str(test_file.relative_to(self.test_dir)),
                    "issue": "direct_qt_import",
                    "line": self._find_import_line(content, qt_import)
                })

        return outdated

    def _find_import_line(self, content: str, import_text: str) -> int:
        """Find the line number of an import statement."""
        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            if import_text in line:
                return i
        return 0

    def _analyze_conftest_files(self, results: dict):
        """Analyze conftest file configuration."""
        conftest_files = list(self.test_dir.glob("conftest*.py"))

        if len(conftest_files) > 1:
            results["conftest_issues"].append({
                "issue": "multiple_conftest_files",
                "files": [str(f.relative_to(self.test_dir)) for f in conftest_files],
                "recommendation": "Consolidate into single conftest.py"
            })

        # Check if conftest files have overlapping fixtures
        if len(conftest_files) > 1:
            fixtures = self._extract_fixtures_from_conftest_files(conftest_files)
            overlapping = self._find_overlapping_fixtures(fixtures)
            if overlapping:
                results["conftest_issues"].append({
                    "issue": "overlapping_fixtures",
                    "fixtures": overlapping
                })

    def _extract_fixtures_from_conftest_files(self, conftest_files: list[Path]) -> dict[str, list[str]]:
        """Extract fixture names from conftest files."""
        fixtures = {}

        for conftest_file in conftest_files:
            try:
                with open(conftest_file, encoding="utf-8") as f:
                    content = f.read()

                tree = ast.parse(content)
                file_fixtures = []

                for node in ast.walk(tree):
                    if (isinstance(node, ast.FunctionDef) and
                        any((isinstance(decorator, ast.Name) and decorator.id == "fixture") or
                            (isinstance(decorator, ast.Attribute) and decorator.attr == "fixture")
                            for decorator in node.decorator_list)):
                        file_fixtures.append(node.name)

                fixtures[str(conftest_file.relative_to(self.test_dir))] = file_fixtures

            except (SyntaxError, UnicodeDecodeError):
                fixtures[str(conftest_file.relative_to(self.test_dir))] = ["<parse_error>"]

        return fixtures

    def _find_overlapping_fixtures(self, fixtures: dict[str, list[str]]) -> list[str]:
        """Find fixtures that are defined in multiple conftest files."""
        all_fixtures = []
        for file_fixtures in fixtures.values():
            all_fixtures.extend(file_fixtures)

        seen = set()
        overlapping = set()

        for fixture in all_fixtures:
            if fixture in seen:
                overlapping.add(fixture)
            seen.add(fixture)

        return list(overlapping)

    def _generate_recommendations(self, results: dict):
        """Generate recommendations based on analysis."""
        recommendations = []

        if results["excessive_mocking"]:
            recommendations.append({
                "category": "mocking",
                "title": "Reduce Excessive Mocking",
                "description": "Consider using integration tests instead of heavy mocking",
                "affected_files": len(results["excessive_mocking"]),
                "action": "Replace with MockFactory or integration tests"
            })

        if results["outdated_imports"]:
            recommendations.append({
                "category": "imports",
                "title": "Update Outdated Imports",
                "description": "Fix references to old dialog names and direct Qt imports",
                "affected_files": len({item["file"] for item in results["outdated_imports"]}),
                "action": "Update import statements and use conftest fixtures"
            })

        if results["conftest_issues"]:
            recommendations.append({
                "category": "configuration",
                "title": "Consolidate Test Configuration",
                "description": "Merge multiple conftest files and eliminate duplicate fixtures",
                "affected_files": len(results["conftest_issues"]),
                "action": "Use unified conftest.py with modern fixtures"
            })

        results["recommendations"] = recommendations

def generate_cleanup_report(test_dir: Path) -> str:
    """Generate a comprehensive cleanup report."""
    analyzer = InfrastructureAnalyzer(test_dir)
    results = analyzer.analyze_all_tests()

    report = []
    report.append("# SpritePal Test Infrastructure Cleanup Report")
    report.append("=" * 50)
    report.append("")

    # Summary
    report.append("## Summary")
    report.append(f"- Total test files analyzed: {results['total_files']}")
    report.append(f"- Files with excessive mocking: {len(results['excessive_mocking'])}")
    report.append(f"- Files with outdated imports: {len(results['outdated_imports'])}")
    report.append(f"- Conftest configuration issues: {len(results['conftest_issues'])}")
    report.append("")

    # Excessive Mocking
    if results["excessive_mocking"]:
        report.append("## Files with Excessive Mocking (>5 mock patterns)")
        for item in results["excessive_mocking"]:
            report.append(f"- {item['file']}: {item['mock_count']} mock patterns")
            report.append(f"  Patterns: {', '.join(item['patterns'])}")
        report.append("")

    # Outdated Imports
    if results["outdated_imports"]:
        report.append("## Outdated Import References")
        for item in results["outdated_imports"]:
            report.append(f"- {item['file']}:{item.get('line', '?')}: {item['issue']}")
        report.append("")

    # Conftest Issues
    if results["conftest_issues"]:
        report.append("## Conftest Configuration Issues")
        for item in results["conftest_issues"]:
            report.append(f"- {item['issue']}: {item.get('recommendation', 'See details')}")
        report.append("")

    # Recommendations
    if results["recommendations"]:
        report.append("## Recommended Actions")
        for i, rec in enumerate(results["recommendations"], 1):
            report.append(f"{i}. **{rec['title']}** ({rec['category']})")
            report.append(f"   - {rec['description']}")
            report.append(f"   - Affected: {rec['affected_files']} files")
            report.append(f"   - Action: {rec['action']}")
            report.append("")

    return "\n".join(report)

if __name__ == "__main__":
    test_dir = Path(__file__).parent
    report = generate_cleanup_report(test_dir)
    print(report)

    # Save report to file
    report_file = test_dir / "infrastructure_cleanup_report.txt"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\nReport saved to: {report_file}")
