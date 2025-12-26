"""
Code validation module for syntax and formatting validation.

This module provides comprehensive validation for generated code to prevent
syntax errors and ensure consistent formatting before code is written to files.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

# Optional dependencies - gracefully handle missing packages
try:
    import black

    HAS_BLACK = True
except ImportError:
    HAS_BLACK = False

try:
    import isort

    HAS_ISORT = True
except ImportError:
    HAS_ISORT = False


class ValidationError(Exception):
    """Raised when code validation fails."""

    pass


class CodeValidator:
    """Validates Python code for syntax and formatting issues."""

    def __init__(self):
        """Initialize the code validator."""
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def reset(self) -> None:
        """Reset error and warning lists."""
        self.errors.clear()
        self.warnings.clear()

    def validate_syntax(self, code: str) -> bool:
        """
        Validate Python syntax using AST parsing.

        Args:
            code: Python code to validate

        Returns:
            True if syntax is valid, False otherwise
        """
        try:
            ast.parse(code)
            return True
        except SyntaxError as e:
            error_msg = f"Syntax error at line {e.lineno}: {e.msg}"
            if e.text:
                error_msg += f"\n  {e.text.strip()}"
                if e.offset:
                    error_msg += f"\n  {' ' * (e.offset - 1)}^"
            self.errors.append(error_msg)
            return False
        except Exception as e:
            self.errors.append(f"Unexpected parsing error: {e}")
            return False

    def format_with_black(self, code: str, line_length: int = 88) -> tuple[bool, str]:
        """
        Format code with Black formatter.

        Args:
            code: Python code to format
            line_length: Maximum line length for Black

        Returns:
            (success, formatted_code)
        """
        if not HAS_BLACK:
            self.warnings.append("Black not available - skipping formatting")
            return True, code

        try:
            import black  # Re-import for type checker

            mode = black.FileMode(line_length=line_length)
            formatted = black.format_str(code, mode=mode)
            return True, formatted
        except black.InvalidInput as e:
            self.errors.append(f"Black formatting error: {e}")
            return False, code
        except Exception as e:
            self.errors.append(f"Unexpected Black error: {e}")
            return False, code

    def sort_imports(self, code: str) -> tuple[bool, str]:
        """
        Sort imports using isort.

        Args:
            code: Python code with imports to sort

        Returns:
            (success, code_with_sorted_imports)
        """
        if not HAS_ISORT:
            self.warnings.append("isort not available - skipping import sorting")
            return True, code

        try:
            import isort  # Re-import for type checker

            # Configure isort to match Black compatibility
            sorted_code = isort.code(
                code,
                profile="black",
                line_length=88,
                multi_line_output=3,
                include_trailing_comma=True,
                force_grid_wrap=0,
                use_parentheses=True,
                ensure_newline_before_comments=True,
            )
            return True, sorted_code
        except Exception as e:
            self.warnings.append(f"Import sorting failed: {e}")
            return True, code  # Non-fatal, return original code

    def normalize_line_endings(self, code: str) -> str:
        """
        Normalize line endings to LF (Unix style).

        Args:
            code: Code with potentially mixed line endings

        Returns:
            Code with normalized LF line endings
        """
        # Replace CRLF and CR with LF
        normalized = code.replace("\r\n", "\n").replace("\r", "\n")
        return normalized

    def validate_imports(self, code: str) -> bool:
        """
        Validate import statements for common issues.

        Args:
            code: Python code to check

        Returns:
            True if imports are valid
        """
        valid = True
        lines = code.split("\n")

        # Check for common import issues
        for i, line in enumerate(lines, 1):
            line = line.strip()

            # Check for star imports (except in __init__.py)
            if re.match(r"from .+ import \*", line):
                self.warnings.append(f"Line {i}: Star import found - consider explicit imports")

            # Check for relative imports without proper package structure
            if line.startswith("from .") and not self._is_package_context():
                self.warnings.append(f"Line {i}: Relative import may fail outside package")

            # Check for imports after code (should be at top)
            if line.startswith(("import ", "from ")) and i > 1:
                # Look for non-import, non-comment, non-docstring code before this
                for prev_line in lines[: i - 1]:
                    prev_clean = prev_line.strip()
                    if (
                        prev_clean
                        and not prev_clean.startswith("#")
                        and not prev_clean.startswith('"""')
                        and not prev_clean.startswith("'''")
                        and not prev_clean.startswith("from __future__")
                        and not prev_clean.startswith('"""')
                        and not prev_clean.startswith("'''")
                        and prev_clean not in {'"""', "'''"}
                    ):
                        # Check if it's not a docstring
                        if not (prev_clean.startswith('"""') or prev_clean.startswith("'''")):
                            self.warnings.append(f"Line {i}: Import after code - move to top")
                            break

        return valid

    def _is_package_context(self) -> bool:
        """Check if we're in a package context (has __init__.py nearby)."""
        # This is a simplified check - in practice, you might want more sophisticated logic
        return True  # Assume package context for now

    def validate_type_annotations(self, code: str) -> bool:
        """
        Validate type annotations for common issues.

        Args:
            code: Python code to check

        Returns:
            True if type annotations are valid
        """
        valid = True

        try:
            tree = ast.parse(code)

            # Check for missing return type annotations on functions
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if node.returns is None and node.name != "__init__":
                        self.warnings.append(f"Function '{node.name}' missing return type annotation")

                # Check for missing type annotations on function parameters
                if isinstance(node, ast.FunctionDef):
                    for arg in node.args.args:
                        if arg.annotation is None and arg.arg not in ("self", "cls"):
                            self.warnings.append(
                                f"Parameter '{arg.arg}' in function '{node.name}' missing type annotation"
                            )

        except Exception as e:
            self.warnings.append(f"Type annotation check failed: {e}")

        return valid


def validate_generated_code(
    code: str, language: str = "python", format_code: bool = True, sort_imports: bool = True, strict_mode: bool = False
) -> tuple[bool, str, list[str]]:
    """
    Validate generated code for syntax and formatting.

    Args:
        code: Code to validate
        language: Programming language (currently only 'python' supported)
        format_code: Whether to format code with Black
        sort_imports: Whether to sort imports with isort
        strict_mode: If True, warnings are treated as errors

    Returns:
        (is_valid, formatted_code, errors_and_warnings)
    """
    if language != "python":
        return False, code, [f"Unsupported language: {language}"]

    validator = CodeValidator()
    validator.reset()

    # Step 1: Normalize line endings
    normalized_code = validator.normalize_line_endings(code)

    # Step 2: Validate syntax
    if not validator.validate_syntax(normalized_code):
        return False, code, validator.errors + validator.warnings

    # Step 3: Sort imports if requested
    current_code = normalized_code
    if sort_imports:
        success, current_code = validator.sort_imports(current_code)
        if not success:
            return False, code, validator.errors + validator.warnings

    # Step 4: Format with Black if requested
    if format_code:
        success, current_code = validator.format_with_black(current_code)
        if not success:
            return False, code, validator.errors + validator.warnings

    # Step 5: Additional validations
    validator.validate_imports(current_code)
    validator.validate_type_annotations(current_code)

    # Determine if valid based on strict mode
    all_issues = validator.errors + validator.warnings
    is_valid = len(validator.errors) == 0

    if strict_mode and validator.warnings:
        is_valid = False

    return is_valid, current_code, all_issues


def validate_test_code(code: str, **kwargs) -> tuple[bool, str, list[str]]:
    """
    Validate test code with additional test-specific checks.

    Args:
        code: Test code to validate
        **kwargs: Additional arguments for validate_generated_code

    Returns:
        (is_valid, formatted_code, errors_and_warnings)
    """
    is_valid, formatted_code, issues = validate_generated_code(code, **kwargs)

    # Additional test-specific validations
    extra_issues = []

    # Check for proper test function naming
    lines = code.split("\n")
    for i, log_line in enumerate(lines, 1):
        log_line = log_line.strip()
        if log_line.startswith("def ") and not log_line.startswith("def test_") and not log_line.startswith("def _"):
            # Check if it's actually a test function (not a helper)
            if "assert" in log_line or any("assert" in line for line in lines[i : i + 10]):
                extra_issues.append(f"Line {i}: Test function should start with 'test_'")

    # Check for missing docstrings in test functions
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                if not ast.get_docstring(node):
                    extra_issues.append(f"Test function '{node.name}' missing docstring")
    except Exception:
        pass  # Ignore AST parsing errors - already caught in main validation

    # Check for proper fixture usage
    if "@pytest.fixture" in code and "import pytest" not in code:
        extra_issues.append("Using pytest fixtures but missing 'import pytest'")

    all_issues = issues + extra_issues
    return is_valid and len(extra_issues) == 0, formatted_code, all_issues


def validate_qt_code(code: str, **kwargs) -> tuple[bool, str, list[str]]:
    """
    Validate Qt code with Qt-specific pattern checks.

    Args:
        code: Qt code to validate
        **kwargs: Additional arguments for validate_generated_code

    Returns:
        (is_valid, formatted_code, errors_and_warnings)
    """
    is_valid, formatted_code, issues = validate_generated_code(code, **kwargs)

    # Additional Qt-specific validations
    extra_issues = []

    # Check for proper Qt imports
    if "PySide6" in code or "PySide6" in code:
        # Check for common Qt patterns
        lines = code.split("\n")

        # Check for proper signal connection
        for i, line in enumerate(lines, 1):
            if ".connect(" in line:
                # Ensure signal is properly connected
                if "lambda" in line and "QMessageBox" in line:
                    extra_issues.append(f"Line {i}: Avoid creating GUI objects in lambda connected to signals")

        # Check for Qt boolean evaluation issues
        for i, line in enumerate(lines, 1):
            # Look for if statements with Qt objects
            if line.strip().startswith("if ") and any(
                qt_class in line for qt_class in ["QLayout", "QWidget", "QTabWidget", "QListWidget"]
            ):
                if " is not None" not in line and " is None" not in line:
                    extra_issues.append(f"Line {i}: Use 'is not None' instead of truthiness for Qt objects")

        # Check for proper super() calls in Qt classes
        if "class " in code and ("QWidget" in code or "QDialog" in code):
            if "super().__init__()" not in code:
                extra_issues.append("Qt widget class missing super().__init__() call")

    all_issues = issues + extra_issues
    return is_valid and len(extra_issues) == 0, formatted_code, all_issues


# Integration helpers
def create_pre_commit_hook() -> str:
    """
    Generate pre-commit hook configuration for code validation.

    Returns:
        YAML configuration for .pre-commit-hooks.yaml
    """
    return """repos:
  - repo: local
    hooks:
      - id: validate-generated-code
        name: Validate Generated Code
        entry: python scripts/code_validation.py
        language: system
        types: [python]
        stages: [commit]
"""


def get_ci_integration_script() -> str:
    """
    Generate CI/CD integration script.

    Returns:
        Shell script for CI validation
    """
    return """#!/bin/bash
# CI/CD Code Validation Script

set -e

echo "Running code validation..."

# Find all Python files
find . -name "*.py" -not -path "./venv/*" -not -path "./.venv/*" | while read -r file; do
    echo "Validating: $file"
    python scripts/code_validation.py "$file" --strict
done

echo "Code validation completed successfully!"
"""


def validate_file(filepath: str | Path, **kwargs) -> tuple[bool, list[str]]:
    """
    Validate a Python file.

    Args:
        filepath: Path to Python file
        **kwargs: Arguments for validation function

    Returns:
        (is_valid, issues)
    """
    filepath = Path(filepath)

    if not filepath.exists():
        return False, [f"File not found: {filepath}"]

    try:
        code = filepath.read_text(encoding="utf-8")
    except Exception as e:
        return False, [f"Failed to read file: {e}"]

    # Choose appropriate validator based on file type
    if "test_" in filepath.name or filepath.parent.name == "tests":
        is_valid, _, issues = validate_test_code(code, **kwargs)
    elif any(qt_import in code for qt_import in ["PyQt", "PySide"]):
        is_valid, _, issues = validate_qt_code(code, **kwargs)
    else:
        is_valid, _, issues = validate_generated_code(code, **kwargs)

    return is_valid, issues


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Validate Python code")
    parser.add_argument("files", nargs="*", help="Python files to validate")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    parser.add_argument("--no-format", action="store_true", help="Skip code formatting")
    parser.add_argument("--no-sort-imports", action="store_true", help="Skip import sorting")

    args = parser.parse_args()

    if not args.files:
        print("No files specified")
        sys.exit(1)

    all_valid = True

    for filepath in args.files:
        print(f"\nValidating: {filepath}")

        is_valid, issues = validate_file(
            filepath, strict_mode=args.strict, format_code=not args.no_format, sort_imports=not args.no_sort_imports
        )

        if issues:
            print("Issues found:")
            for issue in issues:
                print(f"  - {issue}")
        else:
            print("✓ No issues found")

        if not is_valid:
            all_valid = False

    if not all_valid:
        print("\n❌ Validation failed")
        sys.exit(1)
    else:
        print("\n✅ All files validated successfully")
