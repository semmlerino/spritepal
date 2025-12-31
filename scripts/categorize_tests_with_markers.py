#!/usr/bin/env python3
from __future__ import annotations

"""
Comprehensive Test Categorization Script with pytest Markers

This script analyzes all test files and adds appropriate pytest markers based on content analysis.
It prevents segfaults by ensuring tests run only in appropriate environments.

Usage:
    python3 scripts/categorize_tests_with_markers.py [--dry-run] [--report-only]

Options:
    --dry-run     Show what changes would be made without applying them
    --report-only Generate categorization report only
"""

import argparse
import ast
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


class TestFileAnalyzer:
    """Analyzes test files to determine appropriate pytest markers."""

    def __init__(self):
        self.marker_patterns = {
            # GUI/Qt markers
            "gui": [
                "from PySide6",
                "from PyQt5",
                "from PyQt6",
                "QWidget",
                "QDialog",
                "QApplication",
                "QMainWindow",
                "qtbot",
                "QTest",
                "QSignalSpy",
                "QTimer",
                ".exec()",
                ".show()",
                ".hide()",
                "test.*gui",
                "test.*widget",
                "test.*dialog",
            ],
            "headless": ["mock", "Mock", "MagicMock", "patch", "headless", "no.*qt", "without.*display"],
            "unit": ["unittest", "test.*unit", "pure.*unit", "business.*logic", "core.*test"],
            "integration": [
                "integration",
                "test.*integration",
                "end.*to.*end",
                "workflow",
                "complete.*test",
                "comprehensive",
            ],
            "mock_only": [
                "@patch",
                "with patch",
                "MockFactory",
                "mock_factory",
                "MagicMock",
                "create_autospec",
                "spec_set",
            ],
            "requires_display": ["qtbot", "QApplication", "real.*qt", "actual.*widget", "gui.*test", "visual.*test"],
            "ci_safe": ["mock", "headless", "no.*display", "ci.*safe"],
            "slow": [
                "performance",
                "benchmark",
                "stress",
                "load.*test",
                "time.*sleep",
                "long.*running",
                "timeout.*[0-9]{4,}",
            ],
            "serial": [
                "singleton",
                "global.*state",
                "process.*pool",
                "shared.*resource",
                "database.*connection",
                "file.*lock",
                "threading.*lock",
            ],
            "qt_real": [
                "QWidget",
                "QDialog",
                "QMainWindow",
                "real.*qt",
                "actual.*widget",
                "qtbot",  # qtbot usually means real Qt
            ],
            "qt_mock": ["MockWidget", "MockDialog", "mock.*qt", "patch.*Qt", "fake.*widget"],
            "thread_safety": [
                "thread",
                "QThread",
                "threading",
                "concurrent",
                "multiprocessing",
                "asyncio",
                "race.*condition",
            ],
            "worker_threads": ["Worker", "QRunnable", "QThreadPool", "thread.*worker", "background.*task"],
            "signals_slots": ["signal", "slot", "emit", "connect", "disconnect", "QSignalSpy", "pyqtSignal", "Signal"],
            "rom_data": ["rom.*data", "ROM", ".sfc", ".smc", "test.*rom", "sprite.*data", "binary.*data"],
            "file_io": ["file.*io", "Path", "open.*file", "read.*file", "write.*file", "tmp_path", "tempfile"],
            "cache": ["cache", "Cache", "LRU", "memoize", "cached"],
            "memory": ["memory", "leak", "garbage.*collect", "reference.*count", "valgrind", "memory.*profile"],
            "dialog": ["Dialog", "dialog", "modal", "popup", "window"],
            "mock_dialogs": ["MockDialog", "mock.*dialog", "patch.*Dialog", "exec.*return.*value"],
            "stability": ["stability", "regression", "crash", "segfault", "critical.*fix", "phase.*fix"],
            "performance": ["performance", "benchmark", "timing", "speed", "optimization", "profiling"],
            "asyncio": ["async def", "await ", "asyncio", "aiofiles", "@pytest.mark.asyncio"],
        }

        # Markers that should be mutually exclusive
        self.exclusive_groups = [
            ["gui", "headless"],
            ["qt_real", "qt_mock"],
            ["unit", "integration"],
            ["mock_only", "qt_real"],
        ]

    def analyze_file(self, file_path: Path) -> dict[str, Any]:
        """Analyze a test file and return categorization info."""
        try:
            content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            return {"error": f"Could not read file: {file_path}"}

        analysis = {
            "file_path": file_path,
            "existing_markers": self._extract_existing_markers(content),
            "suggested_markers": set(),
            "confidence": {},
            "patterns_found": defaultdict(list),
            "imports": self._extract_imports(content),
            "has_qtbot": "qtbot" in content,
            "has_mock": any(pattern in content.lower() for pattern in ["mock", "patch"]),
            "has_qt_imports": any(qt in content for qt in ["PySide6", "PyQt5", "PyQt6"]),
            "is_integration": "integration" in str(file_path).lower(),
            "content_summary": self._get_content_summary(content),
        }

        # Analyze patterns and suggest markers
        for marker, patterns in self.marker_patterns.items():
            confidence = 0
            found_patterns = []

            for pattern in patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    confidence += 1
                    found_patterns.append(pattern)

            if confidence > 0:
                analysis["patterns_found"][marker] = found_patterns
                analysis["confidence"][marker] = confidence / len(patterns)

                # Add marker if confidence is high enough
                if self._should_add_marker(marker, confidence, len(patterns), analysis):
                    analysis["suggested_markers"].add(marker)

        # Apply intelligent marker logic
        analysis["suggested_markers"] = self._apply_intelligent_logic(analysis)

        return analysis

    def _extract_existing_markers(self, content: str) -> set[str]:
        """Extract existing pytest markers from file content."""
        markers = set()

        # Look for pytestmark declarations
        pytestmark_pattern = r"pytestmark\s*=\s*\[(.*?)\]"
        matches = re.findall(pytestmark_pattern, content, re.DOTALL)

        for match in matches:
            # Extract individual markers
            marker_patterns = re.findall(r"pytest\.mark\.(\w+)", match)
            markers.update(marker_patterns)

        # Look for individual @pytest.mark.* decorators
        individual_markers = re.findall(r"@pytest\.mark\.(\w+)", content)
        markers.update(individual_markers)

        return markers

    def _extract_imports(self, content: str) -> list[str]:
        """Extract import statements from file content."""
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return []

        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for name in node.names:
                    imports.append(name.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)

        return imports

    def _get_content_summary(self, content: str) -> dict[str, int]:
        """Get summary statistics about the file content."""
        return {
            "line_count": len(content.splitlines()),
            "test_function_count": len(re.findall(r"def test_\w+", content)),
            "class_count": len(re.findall(r"class Test\w+", content)),
            "mock_usage_count": len(re.findall(r"Mock|patch|MagicMock", content)),
            "qt_usage_count": len(re.findall(r"Q[A-Z]\w+", content)),
        }

    def _should_add_marker(self, marker: str, confidence: int, total_patterns: int, analysis: dict) -> bool:
        """Determine if a marker should be added based on confidence and context."""
        confidence_ratio = confidence / total_patterns

        # High confidence markers
        if confidence_ratio >= 0.3:
            return True

        # Special cases
        if marker == "gui" and analysis["has_qt_imports"]:
            return True

        if marker == "headless" and analysis["has_mock"] and not analysis["has_qt_imports"]:
            return True

        if marker == "integration" and analysis["is_integration"]:
            return True

        if marker == "serial" and confidence >= 2:  # Even low confidence is important for serial
            return True

        return False

    def _apply_intelligent_logic(self, analysis: dict) -> set[str]:
        """Apply intelligent logic to refine marker suggestions."""
        markers = analysis["suggested_markers"].copy()

        # Handle exclusive groups
        for group in self.exclusive_groups:
            group_markers = [m for m in markers if m in group]
            if len(group_markers) > 1:
                # Keep the one with highest confidence
                best_marker = max(group_markers, key=lambda m: analysis["confidence"].get(m, 0))
                for marker in group_markers:
                    if marker != best_marker:
                        markers.discard(marker)

        # Add implied markers
        if "gui" in markers:
            markers.add("requires_display")

        if analysis["has_mock"] and not analysis["has_qt_imports"]:
            markers.add("headless")
            markers.add("ci_safe")

        if "integration" in str(analysis["file_path"]).lower():
            markers.add("integration")

        if analysis["content_summary"]["line_count"] > 500:
            markers.add("slow")

        # Add default markers for safety
        if not any(env_marker in markers for env_marker in ["gui", "headless"]):
            if analysis["has_qt_imports"]:
                markers.add("gui")
            else:
                markers.add("headless")

        return markers


class TestCategorizer:
    """Main class for categorizing and updating test files."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.analyzer = TestFileAnalyzer()
        self.stats = defaultdict(int)
        self.categorization_report = defaultdict(list)

    def categorize_all_tests(self, test_dir: Path) -> dict[str, Any]:
        """Categorize all test files in the directory."""
        test_files = list(test_dir.rglob("test_*.py"))
        print(f"Found {len(test_files)} test files")

        results = []
        for test_file in test_files:
            print(f"Analyzing: {test_file.relative_to(test_dir)}")
            analysis = self.analyzer.analyze_file(test_file)
            results.append(analysis)

            # Update stats
            for marker in analysis.get("suggested_markers", set()):
                self.stats[f"suggested_{marker}"] += 1
                self.categorization_report[marker].append(test_file.relative_to(test_dir))

            for marker in analysis.get("existing_markers", set()):
                self.stats[f"existing_{marker}"] += 1

        return {
            "analyses": results,
            "stats": dict(self.stats),
            "categorization_report": dict(self.categorization_report),
        }

    def apply_markers(self, analysis: dict) -> bool:
        """Apply markers to a test file."""
        file_path = analysis["file_path"]
        existing_markers = analysis["existing_markers"]
        suggested_markers = analysis["suggested_markers"]

        # Skip if no new markers to add
        new_markers = suggested_markers - existing_markers
        if not new_markers:
            return False

        if self.dry_run:
            print(f"DRY RUN: Would add markers {new_markers} to {file_path.name}")
            return True

        try:
            content = file_path.read_text(encoding="utf-8")
            updated_content = self._add_markers_to_content(content, new_markers, existing_markers)
            file_path.write_text(updated_content, encoding="utf-8")
            print(f"Added markers {new_markers} to {file_path.name}")
            return True
        except Exception as e:
            print(f"Error updating {file_path}: {e}")
            return False

    def _add_markers_to_content(self, content: str, new_markers: set[str], existing_markers: set[str]) -> str:
        """Add new markers to file content."""
        lines = content.splitlines()

        # Find where to insert markers
        insert_line = self._find_marker_insertion_point(lines)

        # Create marker lines
        all_markers = existing_markers | new_markers
        if existing_markers:
            # Extend existing pytestmark
            marker_additions = [f"    pytest.mark.{marker}," for marker in sorted(new_markers)]
            # Find the existing pytestmark and extend it
            for i, line in enumerate(lines):
                if "pytestmark" in line and "[" in line:
                    # Find the closing bracket
                    bracket_line = i
                    while bracket_line < len(lines) and "]" not in lines[bracket_line]:
                        bracket_line += 1

                    # Insert new markers before the closing bracket
                    if bracket_line < len(lines):
                        lines[bracket_line:bracket_line] = marker_additions
                    break
        else:
            # Create new pytestmark
            marker_lines = ["", "pytestmark = ["]
            marker_lines.extend([f"    pytest.mark.{marker}," for marker in sorted(all_markers)])
            marker_lines.append("]")

            # Insert at appropriate location
            lines[insert_line:insert_line] = marker_lines

        return "\n".join(lines)

    def _find_marker_insertion_point(self, lines: list[str]) -> int:
        """Find the best place to insert pytest markers."""
        # Look for imports section end
        import_end = 0
        for i, line in enumerate(lines):
            if line.strip().startswith(("import ", "from ")) or line.strip() == "":
                import_end = i + 1
            elif line.strip() and not line.strip().startswith("#"):
                break

        return import_end

    def generate_report(self, results: dict) -> str:
        """Generate a comprehensive categorization report."""
        report = []
        report.append("# Test Categorization Report")
        report.append("=" * 50)
        report.append("")

        # Summary statistics
        report.append("## Summary Statistics")
        report.append(f"Total test files analyzed: {len(results['analyses'])}")
        report.append("")

        # Marker distribution
        report.append("## Marker Distribution")
        for marker, files in results["categorization_report"].items():
            report.append(f"- **{marker}**: {len(files)} files")
        report.append("")

        # Environment safety breakdown
        gui_tests = len(results["categorization_report"].get("gui", []))
        headless_tests = len(results["categorization_report"].get("headless", []))
        ci_safe_tests = len(results["categorization_report"].get("ci_safe", []))

        report.append("## Environment Safety Breakdown")
        report.append(f"- GUI tests (require display): {gui_tests}")
        report.append(f"- Headless tests (CI-safe): {headless_tests}")
        report.append(f"- Explicitly CI-safe: {ci_safe_tests}")
        report.append("")

        # Recommendations
        report.append("## CI/CD Recommendations")
        report.append("### For headless environments (CI):")
        report.append("```bash")
        report.append('pytest -m "headless or ci_safe or mock_only" --tb=line')
        report.append("```")
        report.append("")
        report.append("### For environments with display:")
        report.append("```bash")
        report.append('pytest -m "gui or headless" --tb=short')
        report.append("```")
        report.append("")
        report.append("### For parallel execution (safe tests only):")
        report.append("```bash")
        report.append('pytest -m "not serial" -n auto')
        report.append("```")
        report.append("")

        # Detailed file categorization
        report.append("## Detailed File Categorization")
        for marker, files in sorted(results["categorization_report"].items()):
            report.append(f"### {marker} ({len(files)} files)")
            for file_path in sorted(files):
                report.append(f"- {file_path}")
            report.append("")

        return "\n".join(report)


def main():
    parser = argparse.ArgumentParser(
        description="Categorize tests with pytest markers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--dry-run", action="store_true", help="Show changes without applying them")
    parser.add_argument("--report-only", action="store_true", help="Generate report only, no file modifications")
    parser.add_argument("--test-dir", type=Path, default=Path("tests"), help="Test directory to analyze")

    args = parser.parse_args()

    if not args.test_dir.exists():
        print(f"Test directory not found: {args.test_dir}")
        sys.exit(1)

    categorizer = TestCategorizer(dry_run=args.dry_run or args.report_only)

    print("Starting test categorization...")
    results = categorizer.categorize_all_tests(args.test_dir)

    # Generate and save report
    report = categorizer.generate_report(results)
    report_path = Path("test_categorization_report.md")
    report_path.write_text(report, encoding="utf-8")
    print(f"Report saved to: {report_path}")

    if not args.report_only:
        # Apply markers to files
        print("\nApplying markers...")
        updated_count = 0
        for analysis in results["analyses"]:
            if categorizer.apply_markers(analysis):
                updated_count += 1

        print(f"\nUpdated {updated_count} files with new markers")

    print(f"\nCategorization complete. Report available at: {report_path}")


if __name__ == "__main__":
    main()
