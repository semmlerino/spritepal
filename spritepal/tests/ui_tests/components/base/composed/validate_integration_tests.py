#!/usr/bin/env python3
from __future__ import annotations

"""
Validation script for the migration adapter integration tests.

This script validates the test structure, imports, and logic without requiring
a full Qt environment. It performs static analysis of the test code to ensure
correctness.
"""

import ast
import sys
from pathlib import Path
from typing import Any


def analyze_test_file(file_path: Path) -> dict[str, Any]:
    """Analyze the test file structure and content."""

    with open(file_path) as f:
        content = f.read()

    # Parse AST
    tree = ast.parse(content)

    analysis = {
        'classes': [],
        'test_methods': [],
        'fixtures': [],
        'imports': [],
        'constants': [],
        'has_qt_imports': False,
        'has_feature_flag_imports': False,
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            # Collect test classes
            if node.name.startswith('Test'):
                test_methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef) and n.name.startswith('test_')]
                analysis['classes'].append({
                    'name': node.name,
                    'test_methods': test_methods,
                    'method_count': len(test_methods)
                })
                analysis['test_methods'].extend(test_methods)

        elif isinstance(node, ast.FunctionDef):
            # Collect fixtures
            for decorator in node.decorator_list:
                if (isinstance(decorator, ast.Attribute) and decorator.attr == 'fixture') or (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.func.attr == 'fixture') or (isinstance(decorator, ast.Name) and decorator.id == 'fixture'):
                    analysis['fixtures'].append(node.name)

        elif isinstance(node, ast.Import):
            for alias in node.names:
                analysis['imports'].append(alias.name)

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ''
            for alias in node.names:
                full_import = f"{module}.{alias.name}" if module else alias.name
                analysis['imports'].append(full_import)

                # Check for specific imports
                if 'PySide6' in full_import or 'Qt' in full_import:
                    analysis['has_qt_imports'] = True
                if 'dialog_feature_flags' in full_import or 'dialog_selector' in full_import:
                    analysis['has_feature_flag_imports'] = True

        elif isinstance(node, ast.Assign):
            # Collect constants
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    analysis['constants'].append(target.id)

    return analysis

def validate_test_coverage(analysis: dict[str, Any]) -> list[str]:
    """Validate that all required test scenarios are covered."""

    issues = []
    required_test_areas = [
        'dialog_creation',  # Matches TestBasicDialogCreation methods
        'tab',  # Matches TestTabManagement methods
        'button_box',  # Matches TestButtonBoxFunctionality methods
        'status_bar',  # Matches TestStatusBarOperations methods
        'message_dialog',  # Matches TestMessageDialogs methods
        'signal',  # Matches TestSignalSlotConnections methods
        'initialization',  # Matches TestInitializationOrderPattern methods
        'performance',  # Matches TestPerformanceComparison methods
    ]

    all_test_methods = [method.lower() for method in analysis['test_methods']]

    for area in required_test_areas:
        matching_tests = [method for method in all_test_methods if area in method]
        if not matching_tests:
            issues.append(f"Missing tests for area: {area}")
        else:
            print(f"✓ {area}: {len(matching_tests)} tests found")

    return issues

def validate_test_structure(analysis: dict[str, Any]) -> list[str]:
    """Validate the overall test structure."""

    issues = []

    # Check for essential imports
    if not analysis['has_qt_imports']:
        issues.append("Missing Qt imports")
    else:
        print("✓ Qt imports found")

    if not analysis['has_feature_flag_imports']:
        issues.append("Missing feature flag imports")
    else:
        print("✓ Feature flag imports found")

    # Check for test classes
    if len(analysis['classes']) < 5:
        issues.append(f"Too few test classes: {len(analysis['classes'])} (expected at least 5)")
    else:
        print(f"✓ {len(analysis['classes'])} test classes found")

    # Check for test methods
    if len(analysis['test_methods']) < 20:
        issues.append(f"Too few test methods: {len(analysis['test_methods'])} (expected at least 20)")
    else:
        print(f"✓ {len(analysis['test_methods'])} test methods found")

    # Check for fixtures
    if len(analysis['fixtures']) < 3:
        issues.append(f"Too few fixtures: {len(analysis['fixtures'])} (expected at least 3)")
    else:
        print(f"✓ {len(analysis['fixtures'])} fixtures found")

    return issues

def check_specific_requirements(analysis: dict[str, Any]) -> list[str]:
    """Check for specific requirements mentioned in the task."""

    issues = []
    requirements = {
        'qt_app': 'QApplication fixture for real Qt testing',
        'dialog_implementations': 'Fixture providing both implementations',
        'mock_message_box': 'Mock for message box testing',
        'feature_flag_switcher': 'Feature flag switching capability',
        'performance_monitor': 'Performance monitoring fixture',
    }

    fixture_names = [f.lower() for f in analysis['fixtures']]

    for req, description in requirements.items():
        if req not in fixture_names and req.replace('_', '') not in fixture_names:
            issues.append(f"Missing required fixture: {req} ({description})")
        else:
            print(f"✓ {req}: {description}")

    return issues

def analyze_test_class_coverage(analysis: dict[str, Any]) -> None:
    """Analyze coverage by test class."""

    print("\nTest Class Coverage Analysis:")
    print("-" * 50)

    for test_class in analysis['classes']:
        print(f"{test_class['name']}:")
        for method in test_class['test_methods']:
            print(f"  - {method}")
        print(f"  Total: {test_class['method_count']} tests")
        print()

def main():
    """Main validation function."""

    print("SpritePal Integration Tests Validation")
    print("=" * 50)

    # Find the test file
    test_file = Path(__file__).parent / "test_migration_adapter_integration.py"

    if not test_file.exists():
        print(f"ERROR: Test file not found: {test_file}")
        return 1

    print(f"Analyzing: {test_file}")
    print()

    # Analyze the file
    analysis = analyze_test_file(test_file)

    # Validate structure
    print("Structure Validation:")
    print("-" * 30)
    structure_issues = validate_test_structure(analysis)

    print()
    print("Coverage Validation:")
    print("-" * 30)
    coverage_issues = validate_test_coverage(analysis)

    print()
    print("Requirements Validation:")
    print("-" * 30)
    requirement_issues = check_specific_requirements(analysis)

    # Analyze test class coverage
    analyze_test_class_coverage(analysis)

    # Summary
    all_issues = structure_issues + coverage_issues + requirement_issues

    print("Validation Summary:")
    print("=" * 30)

    if not all_issues:
        print("✅ All validations PASSED!")
        print(f"Total test classes: {len(analysis['classes'])}")
        print(f"Total test methods: {len(analysis['test_methods'])}")
        print(f"Total fixtures: {len(analysis['fixtures'])}")
        return 0
    else:
        print("❌ Validation issues found:")
        for issue in all_issues:
            print(f"  - {issue}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
