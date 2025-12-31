#!/usr/bin/env python3
from __future__ import annotations

"""
Migration helper script for updating Qt tests to use proper qtbot fixtures.

This script analyzes test files and helps migrate them from unsafe Qt patterns
to proper qtbot usage, preventing QApplication conflicts and resource leaks.

Usage:
    python scripts/migrate_qt_tests.py --analyze    # Analyze current state
    python scripts/migrate_qt_tests.py --fix        # Apply migrations
    python scripts/migrate_qt_tests.py --verify     # Verify migrations
"""

import argparse
import ast
import re
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class QtTestAnalyzer(ast.NodeVisitor):
    """AST visitor to analyze Qt usage patterns in test files."""

    def __init__(self):
        self.has_qt_imports = False
        self.has_qtbot_param = False
        self.has_qapp_creation = False
        self.test_methods = []
        self.qt_widgets_created = []
        self.parent_widget_usage = []
        self.qapp_instance_calls = []

    def visit_ImportFrom(self, node):
        """Track Qt imports."""
        if node.module and ("PySide6" in node.module or "PySide6" in node.module):
            self.has_qt_imports = True
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        """Analyze test method signatures and Qt usage."""
        if node.name.startswith("test_"):
            # Check for qtbot parameter
            qtbot_in_args = any(arg.arg == "qtbot" for arg in node.args.args)
            parent_widget_in_args = any(arg.arg == "parent_widget" for arg in node.args.args)

            self.test_methods.append(
                {
                    "name": node.name,
                    "line": node.lineno,
                    "has_qtbot": qtbot_in_args,
                    "has_parent_widget": parent_widget_in_args,
                    "needs_migration": parent_widget_in_args and not qtbot_in_args,
                }
            )

            if qtbot_in_args:
                self.has_qtbot_param = True

        self.generic_visit(node)

    def visit_Call(self, node):
        """Track QApplication and QWidget creation calls."""
        if isinstance(node.func, ast.Name):
            if node.func.id in ["QApplication", "QWidget", "QDialog", "QMainWindow"]:
                self.qt_widgets_created.append({"type": node.func.id, "line": getattr(node, "lineno", 0)})
                if node.func.id == "QApplication":
                    self.has_qapp_creation = True

        elif isinstance(node.func, ast.Attribute):
            if node.func.attr == "instance" and isinstance(node.func.value, ast.Name):
                if node.func.value.id == "QApplication":
                    self.qapp_instance_calls.append(getattr(node, "lineno", 0))

        self.generic_visit(node)


class QtTestMigrator:
    """Handles migration of Qt tests to proper qtbot usage."""

    def __init__(self, tests_dir: Path):
        self.tests_dir = tests_dir
        self.analysis_results = {}

    def analyze_test_file(self, file_path: Path) -> dict:
        """Analyze a single test file for Qt usage patterns."""
        try:
            with Path(file_path).open(encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content)
            analyzer = QtTestAnalyzer()
            analyzer.visit(tree)

            return {
                "file_path": file_path,
                "has_qt_imports": analyzer.has_qt_imports,
                "has_qtbot_param": analyzer.has_qtbot_param,
                "has_qapp_creation": analyzer.has_qapp_creation,
                "test_methods": analyzer.test_methods,
                "qt_widgets_created": analyzer.qt_widgets_created,
                "qapp_instance_calls": analyzer.qapp_instance_calls,
                "needs_migration": analyzer.has_qt_imports and not analyzer.has_qtbot_param,
                "migration_complexity": self._assess_migration_complexity(analyzer),
            }

        except Exception as e:
            return {"file_path": file_path, "error": str(e), "needs_migration": False, "migration_complexity": "error"}

    def _assess_migration_complexity(self, analyzer: QtTestAnalyzer) -> str:
        """Assess how complex the migration will be."""
        if not analyzer.has_qt_imports:
            return "none"

        complexity_score = 0

        # Basic Qt usage
        if analyzer.qt_widgets_created:
            complexity_score += 1

        # QApplication management
        if analyzer.has_qapp_creation or analyzer.qapp_instance_calls:
            complexity_score += 2

        # Multiple test methods needing migration
        methods_needing_migration = sum(1 for m in analyzer.test_methods if m["needs_migration"])
        complexity_score += min(methods_needing_migration, 3)

        if complexity_score == 0:
            return "none"
        if complexity_score <= 2:
            return "simple"
        if complexity_score <= 5:
            return "moderate"
        return "complex"

    def analyze_all_tests(self) -> dict[str, dict]:
        """Analyze all test files in the tests directory."""
        test_files = list(self.tests_dir.glob("test_*.py"))

        for test_file in test_files:
            self.analysis_results[str(test_file)] = self.analyze_test_file(test_file)

        return self.analysis_results

    def generate_migration_report(self) -> str:
        """Generate a detailed migration report."""
        if not self.analysis_results:
            self.analyze_all_tests()

        total_files = len(self.analysis_results)
        files_with_qt = sum(1 for r in self.analysis_results.values() if r.get("has_qt_imports", False))
        files_with_qtbot = sum(1 for r in self.analysis_results.values() if r.get("has_qtbot_param", False))
        files_needing_migration = sum(1 for r in self.analysis_results.values() if r.get("needs_migration", False))

        complexity_counts = {}
        for result in self.analysis_results.values():
            complexity = result.get("migration_complexity", "none")
            complexity_counts[complexity] = complexity_counts.get(complexity, 0) + 1

        report = f"""
# Qt Test Migration Analysis Report

## Summary
- Total test files: {total_files}
- Files with Qt imports: {files_with_qt}
- Files already using qtbot: {files_with_qtbot}
- Files needing migration: {files_needing_migration}

## Migration Complexity
- Simple: {complexity_counts.get("simple", 0)} files
- Moderate: {complexity_counts.get("moderate", 0)} files
- Complex: {complexity_counts.get("complex", 0)} files
- None needed: {complexity_counts.get("none", 0)} files
- Errors: {complexity_counts.get("error", 0)} files

## Files Requiring Migration
"""

        for file_path, result in self.analysis_results.items():
            if result.get("needs_migration", False):
                complexity = result.get("migration_complexity", "unknown")
                methods_count = len([m for m in result.get("test_methods", []) if m.get("needs_migration", False)])
                report += f"- {Path(file_path).name} ({complexity}, {methods_count} methods)\n"

        report += "\n## Recommended Migration Order\n"

        # Sort by complexity for recommended migration order
        files_by_complexity = {"simple": [], "moderate": [], "complex": []}

        for file_path, result in self.analysis_results.items():
            if result.get("needs_migration", False):
                complexity = result.get("migration_complexity", "moderate")
                if complexity in files_by_complexity:
                    files_by_complexity[complexity].append(Path(file_path).name)

        for complexity in ["simple", "moderate", "complex"]:
            if files_by_complexity[complexity]:
                report += f"\n### {complexity.title()} Migration ({len(files_by_complexity[complexity])} files)\n"
                for file_name in sorted(files_by_complexity[complexity]):
                    report += f"- {file_name}\n"

        return report

    def migrate_test_file(self, file_path: Path, dry_run: bool = True) -> tuple[bool, str]:
        """Migrate a single test file to use proper qtbot fixtures."""
        try:
            with Path(file_path).open(encoding="utf-8") as f:
                content = f.read()

            original_content = content

            # Apply migration patterns
            content = self._apply_migration_patterns(content, file_path)

            if content == original_content:
                return True, "No changes needed"

            if not dry_run:
                # Create backup
                backup_path = file_path.with_suffix(file_path.suffix + ".bak")
                with Path(backup_path).open("w", encoding="utf-8") as f:
                    f.write(original_content)

                # Write migrated content
                with Path(file_path).open("w", encoding="utf-8") as f:
                    f.write(content)

                return True, f"Migrated successfully (backup: {backup_path.name})"
            return True, "Would migrate (dry run)"

        except Exception as e:
            return False, f"Migration failed: {e}"

    def _apply_migration_patterns(self, content: str, file_path: Path) -> str:
        """Apply common migration patterns to test content."""
        lines = content.split("\n")
        modified_lines = []

        for i, line in enumerate(lines):
            modified_line = line

            # Pattern 1: Replace parent_widget parameter with qtbot
            if "def test_" in line and "parent_widget" in line and "qtbot" not in line:
                modified_line = re.sub(r"def (test_\w+)\(self, parent_widget\):", r"def \1(self, qtbot):", line)

            # Pattern 2: Add qtbot.addWidget calls after widget creation
            if modified_line != line or (
                "parent_widget" in line and any(widget in line for widget in ["QWidget()", "QDialog(", "QMainWindow("])
            ):
                # Look for widget creation patterns and add qtbot registration
                if "parent_widget = QWidget()" in modified_line:
                    modified_line = modified_line.replace(
                        "parent_widget = QWidget()", "parent_widget = QWidget()\n        qtbot.addWidget(parent_widget)"
                    )

                # Add import if needed
                widget_created = re.search(r"(\w+) = \w+Widget\(parent_widget\)", line)
                if widget_created and i < len(lines) - 1:
                    widget_var = widget_created.group(1)
                    # Add qtbot.addWidget call after widget creation
                    if not any(f"qtbot.addWidget({widget_var})" in future_line for future_line in lines[i + 1 : i + 5]):
                        modified_line += f"\n        qtbot.addWidget({widget_var})"

            # Pattern 3: Add PySide6.QtWidgets import if creating widgets inline
            if (
                i < 10
                and "from PySide6.QtWidgets import QWidget" not in content
                and "QWidget()" in modified_line
                and "import" not in modified_line
            ):
                # Add import before widget creation
                if "from PySide6.QtWidgets import" not in "\n".join(lines[: i + 5]):
                    modified_line = "        from PySide6.QtWidgets import QWidget\n        \n" + modified_line

            modified_lines.append(modified_line)

        return "\n".join(modified_lines)


def main():
    parser = argparse.ArgumentParser(description="Migrate Qt tests to use proper qtbot fixtures")
    parser.add_argument("--analyze", action="store_true", help="Analyze current test state")
    parser.add_argument("--fix", action="store_true", help="Apply migrations")
    parser.add_argument("--verify", action="store_true", help="Verify migrations")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without applying")
    parser.add_argument("--file", type=str, help="Process specific file only")

    args = parser.parse_args()

    tests_dir = project_root / "tests"
    migrator = QtTestMigrator(tests_dir)

    if args.analyze or (not args.fix and not args.verify):
        print("Analyzing Qt test files...")
        report = migrator.generate_migration_report()
        print(report)

        # Save report to file
        report_file = project_root / "QT_MIGRATION_REPORT.md"
        with Path(report_file).open("w") as f:
            f.write(report)
        print(f"\nDetailed report saved to: {report_file}")

    if args.fix:
        files_to_process = []

        if args.file:
            file_path = tests_dir / args.file
            if file_path.exists():
                files_to_process = [file_path]
            else:
                print(f"Error: File {file_path} not found")
                return
        else:
            # Process all files that need migration
            migrator.analyze_all_tests()
            files_to_process = [
                Path(file_path)
                for file_path, result in migrator.analysis_results.items()
                if result.get("needs_migration", False)
            ]

        print(f"Migrating {len(files_to_process)} test files...")

        for file_path in files_to_process:
            success, message = migrator.migrate_test_file(file_path, dry_run=args.dry_run)
            status = "✓" if success else "✗"
            print(f"{status} {file_path.name}: {message}")

    if args.verify:
        print("Verifying migrations...")
        migrator.analyze_all_tests()

        still_need_migration = sum(1 for r in migrator.analysis_results.values() if r.get("needs_migration", False))

        if still_need_migration == 0:
            print("✓ All Qt tests are properly using qtbot fixtures!")
        else:
            print(f"⚠ {still_need_migration} files still need migration")
            print("Run with --analyze to see details")


if __name__ == "__main__":
    main()
