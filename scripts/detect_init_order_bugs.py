#!/usr/bin/env python3
from __future__ import annotations

"""
Detect potential initialization order bugs in the codebase.

This script searches for patterns where instance variables might be
assigned None after setup methods are called, potentially overwriting
already-created widgets or objects.
"""

import ast
import json
import sys
from pathlib import Path
from typing import Any


class InitOrderDetector(ast.NodeVisitor):
    """AST visitor to detect initialization order issues."""

    def __init__(self, filename: str):
        self.filename = filename
        self.issues: list[dict[str, Any]] = []
        self.current_class: str | None = None
        self.in_init: bool = False
        self.setup_methods_called: list[tuple[str, int]] = []
        self.attribute_assignments: list[tuple[str, int, Any]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit class definition."""
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit function definition."""
        if node.name == "__init__" and self.current_class:
            self.in_init = True
            self.setup_methods_called = []
            self.attribute_assignments = []

            # Visit the function body
            for stmt in node.body:
                self.visit(stmt)

            # Check for potential issues
            self._check_init_order_issues()

            self.in_init = False
        else:
            self.generic_visit(node)

    def visit_Expr(self, node: ast.Expr) -> None:
        """Visit expression statement."""
        if self.in_init and isinstance(node.value, ast.Call):
            # Check if it's a method call like self._setup_ui()
            if (
                isinstance(node.value.func, ast.Attribute)
                and isinstance(node.value.func.value, ast.Name)
                and node.value.func.value.id == "self"
                and node.value.func.attr.startswith("_setup")
            ):
                self.setup_methods_called.append((node.value.func.attr, node.lineno))
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Visit annotated assignment (e.g., self.foo: Type = value)."""
        if self.in_init and isinstance(node.target, ast.Attribute):
            if isinstance(node.target.value, ast.Name) and node.target.value.id == "self":
                value = None
                if node.value:
                    if isinstance(node.value, ast.Constant) and node.value.value is None:
                        value = "None"
                    else:
                        value = ast.unparse(node.value) if hasattr(ast, "unparse") else str(node.value)
                self.attribute_assignments.append((node.target.attr, node.lineno, value))
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        """Visit regular assignment."""
        if self.in_init:
            for target in node.targets:
                if isinstance(target, ast.Attribute):
                    if isinstance(target.value, ast.Name) and target.value.id == "self":
                        value = None
                        if isinstance(node.value, ast.Constant) and node.value.value is None:
                            value = "None"
                        else:
                            value = ast.unparse(node.value) if hasattr(ast, "unparse") else str(node.value)
                        self.attribute_assignments.append((target.attr, node.lineno, value))
        self.generic_visit(node)

    def _check_init_order_issues(self) -> None:
        """Check for initialization order issues."""
        if not self.setup_methods_called:
            return

        # Find the last setup method call
        last_setup_line = max(line for _, line in self.setup_methods_called)

        # Check for None assignments after setup methods
        for attr, line, value in self.attribute_assignments:
            if line > last_setup_line and value == "None":
                self.issues.append(
                    {
                        "file": self.filename,
                        "class": self.current_class,
                        "line": line,
                        "attribute": attr,
                        "issue": f"Instance variable 'self.{attr}' assigned None after setup methods called",
                        "setup_methods": [m for m, _ in self.setup_methods_called],
                    }
                )

        # Also check for any attribute assignments after setup that might overwrite
        suspicious_attrs = []
        for attr, line, value in self.attribute_assignments:
            if line > last_setup_line and not attr.startswith("_"):
                suspicious_attrs.append((attr, line, value))

        if suspicious_attrs:
            for attr, line, value in suspicious_attrs:
                self.issues.append(
                    {
                        "file": self.filename,
                        "class": self.current_class,
                        "line": line,
                        "attribute": attr,
                        "issue": f"Instance variable 'self.{attr}' assigned after setup methods (value: {value})",
                        "severity": "warning",
                    }
                )


def analyze_file(filepath: Path) -> list[dict[str, Any]]:
    """Analyze a single Python file for initialization order issues."""
    try:
        with Path(filepath).open(encoding="utf-8") as f:
            content = f.read()

        tree = ast.parse(content, filename=str(filepath))
        detector = InitOrderDetector(str(filepath))
        detector.visit(tree)
        return detector.issues
    except Exception as e:
        print(f"Error analyzing {filepath}: {e}")
        return []


def main():
    """Main function to scan the project."""
    # Get the project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    # Directories to scan
    directories = ["ui", "core", "utils"]

    all_issues = []
    files_scanned = 0

    print("Scanning for initialization order bugs...\n")

    for directory in directories:
        dir_path = project_root / directory
        if not dir_path.exists():
            continue

        for py_file in dir_path.rglob("*.py"):
            # Skip test files and __pycache__
            if "test" in py_file.name or "__pycache__" in str(py_file):
                continue

            files_scanned += 1
            issues = analyze_file(py_file)
            all_issues.extend(issues)

    # Report findings
    print(f"Scanned {files_scanned} files\n")

    if not all_issues:
        print("✅ No initialization order issues found!")
    else:
        # Group by severity
        errors = [i for i in all_issues if i.get("severity") != "warning"]
        warnings = [i for i in all_issues if i.get("severity") == "warning"]

        if errors:
            print(f"❌ Found {len(errors)} potential bugs:\n")
            for issue in errors:
                print(f"  {issue['file']}:{issue['line']}")
                print(f"    Class: {issue['class']}")
                print(f"    Issue: {issue['issue']}")
                print(f"    Setup methods: {', '.join(issue['setup_methods'])}")
                print()

        if warnings:
            print(f"⚠️  Found {len(warnings)} warnings:\n")
            for issue in warnings[:5]:  # Show first 5 warnings
                print(f"  {issue['file']}:{issue['line']}")
                print(f"    {issue['issue']}")
            if len(warnings) > 5:
                print(f"\n  ... and {len(warnings) - 5} more warnings")

    # Save detailed report
    if all_issues:
        report_path = project_root / "init_order_issues.json"
        with Path(report_path).open("w") as f:
            json.dump(all_issues, f, indent=2)
        print(f"\nDetailed report saved to: {report_path}")

    return len(errors) if all_issues else 0


if __name__ == "__main__":
    sys.exit(main())
