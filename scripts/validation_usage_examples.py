"""
Usage examples for the code validation system.

This module demonstrates how code-generating agents can integrate
the validation system into their workflow.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add the parent directory to sys.path to import validation modules
sys.path.insert(0, str(Path(__file__).parent))

from code_validation import (
    validate_file,
    validate_generated_code,
    validate_qt_code,
    validate_test_code,
)


def example_basic_validation():
    """Example of basic code validation."""
    print("=== Basic Code Validation Example ===")

    code = '''
from typing import Any

def process_data(items: list[Any]) -> dict[str, Any]:
    """Process a list of items."""
    result = {}
    for item in items:
        if isinstance(item, str):
            result[item] = len(item)
    return result
'''

    is_valid, formatted_code, issues = validate_generated_code(code)

    print(f"Valid: {is_valid}")
    print(f"Issues found: {len(issues)}")
    for issue in issues:
        print(f"  - {issue}")

    if is_valid:
        print("Formatted code:")
        print(formatted_code[:200] + "..." if len(formatted_code) > 200 else formatted_code)


def example_test_validation():
    """Example of test code validation."""
    print("\n=== Test Code Validation Example ===")

    test_code = '''
import pytest
from unittest.mock import Mock

def test_user_registration():
    """Test user registration functionality."""
    mock_db = Mock()
    mock_db.save.return_value = True

    user_service = UserService(mock_db)
    result = user_service.register("john@example.com", "password123")

    assert result is True
    mock_db.save.assert_called_once()

def helper_function():  # This should trigger warning
    return "helper"
'''

    is_valid, _formatted_code, issues = validate_test_code(test_code)

    print(f"Valid: {is_valid}")
    print(f"Issues found: {len(issues)}")
    for issue in issues:
        print(f"  - {issue}")


def example_qt_validation():
    """Example of Qt code validation."""
    print("\n=== Qt Code Validation Example ===")

    qt_code = '''
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton
from PySide6.QtCore import Signal

class MyWidget(QWidget):
    """Example Qt widget."""

    data_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout()  # This should trigger warning
        self.button = QPushButton("Click me")

        # This should trigger warning about GUI in lambda
        self.button.clicked.connect(lambda: QMessageBox.information(self, "Title", "Message"))

        if self.layout:  # This should trigger Qt boolean warning
            self.layout.addWidget(self.button)
'''

    is_valid, _formatted_code, issues = validate_qt_code(qt_code)

    print(f"Valid: {is_valid}")
    print(f"Issues found: {len(issues)}")
    for issue in issues:
        print(f"  - {issue}")


def example_agent_workflow():
    """Example of how an agent would use validation in its workflow."""
    print("\n=== Agent Workflow Example ===")

    def generate_code_with_validation(requirements: str) -> str:
        """
        Simulate an agent generating code with validation.

        Args:
            requirements: What the code should do

        Returns:
            Validated and formatted code
        """
        # Step 1: Generate initial code (simulated)
        generated_code = f'''
def process_requirement():
    """Generated function for: {requirements}"""
    # TODO: Implement {requirements}
    pass

# Some other code here
import os  # This import should be at top
'''

        print("Generated initial code...")

        # Step 2: Validate the generated code
        is_valid, formatted_code, issues = validate_generated_code(generated_code, format_code=True, sort_imports=True)

        print(f"Validation result: {'✓' if is_valid else '✗'}")

        if issues:
            print("Issues found:")
            for issue in issues:
                print(f"  - {issue}")

        # Step 3: Return validated code or raise error
        if not is_valid:
            raise ValueError("Generated code failed validation")

        return formatted_code

    try:
        validated_code = generate_code_with_validation("data processing functionality")
        print("Final validated code:")
        print(validated_code[:300] + "..." if len(validated_code) > 300 else validated_code)
    except ValueError as e:
        print(f"Agent workflow failed: {e}")


def example_file_validation():
    """Example of validating existing files."""
    print("\n=== File Validation Example ===")

    # Create a temporary file with issues
    temp_file = Path("/tmp/example_file.py")
    temp_file.write_text('''
def bad_function()  # Syntax error - missing colon
    return "error"

def good_function(param: str) -> str:
    """A good function."""
    return f"Hello {param}"
''')

    # Validate the file
    is_valid, issues = validate_file(temp_file)

    print(f"File '{temp_file.name}' validation: {'✓' if is_valid else '✗'}")
    print(f"Issues found: {len(issues)}")
    for issue in issues:
        print(f"  - {issue}")

    # Clean up
    temp_file.unlink()


def example_strict_mode():
    """Example of validation in strict mode."""
    print("\n=== Strict Mode Example ===")

    code_with_warnings = '''
def function_without_return_type(param):  # Missing type hints
    """Function with type hint warnings."""
    return str(param)

# This will generate warnings about missing type hints
'''

    print("Normal mode:")
    is_valid, _, issues = validate_generated_code(code_with_warnings, strict_mode=False)
    print(f"Valid: {is_valid}, Issues: {len(issues)}")

    print("\nStrict mode:")
    is_valid, _, issues = validate_generated_code(code_with_warnings, strict_mode=True)
    print(f"Valid: {is_valid}, Issues: {len(issues)}")


if __name__ == "__main__":
    """Run all validation examples."""
    example_basic_validation()
    example_test_validation()
    example_qt_validation()
    example_agent_workflow()
    example_file_validation()
    example_strict_mode()

    print("\n=== All Examples Completed ===")
    print("\nKey takeaways for code-generating agents:")
    print("1. Always validate generated code before writing files")
    print("2. Use appropriate validator (test, Qt, or general)")
    print("3. Handle validation errors gracefully")
    print("4. Consider strict mode for critical code")
    print("5. Format and sort imports automatically")
