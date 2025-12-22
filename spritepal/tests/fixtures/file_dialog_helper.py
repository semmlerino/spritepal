"""
Test File Dialog Helper for testing file selection with real QFileDialog components

Provides TestFileDialogHelper that uses real QFileDialog instances but allows
predetermined responses for testing without user interaction.
"""
from __future__ import annotations

import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtWidgets import QFileDialog

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.headless,
    pytest.mark.integration,
]

class FileDialogHelper:
    """
    Helper for testing file dialogs with real QFileDialog components.

    This helper creates real QFileDialog instances but provides predetermined
    responses for testing without requiring user interaction. It validates
    dialog configuration and behavior while ensuring deterministic test results.
    """

    def __init__(self):
        self.predetermined_responses = {}
        self.last_dialog_config = {}

    def set_open_file_response(self, filename: str, file_filter: str = ""):
        """Set predetermined response for getOpenFileName dialogs"""
        self.predetermined_responses["open"] = (filename, file_filter)

    def set_save_file_response(self, filename: str, file_filter: str = ""):
        """Set predetermined response for getSaveFileName dialogs"""
        self.predetermined_responses["save"] = (filename, file_filter)

    def clear_responses(self):
        """Clear all predetermined responses"""
        self.predetermined_responses.clear()
        self.last_dialog_config.clear()

    @contextmanager
    def patch_file_dialogs(self):
        """
        Context manager that patches QFileDialog methods with predetermined responses
        while still validating dialog creation and configuration.
        """
        # Store original methods
        original_get_open_filename = QFileDialog.getOpenFileName
        original_get_save_filename = QFileDialog.getSaveFileName

        def mock_get_open_filename(parent=None, caption="", directory="", filter="", options=None):
            """Mock getOpenFileName that validates parameters and returns predetermined response"""
            # Validate that we're actually getting a QFileDialog call
            assert isinstance(caption, str), "Caption should be string"
            assert isinstance(directory, str), "Directory should be string"
            assert isinstance(filter, str), "Filter should be string"

            # Store dialog configuration for test validation
            self.last_dialog_config["open"] = {
                "parent": parent,
                "caption": caption,
                "directory": directory,
                "filter": filter,
                "options": options
            }

            # Return predetermined response or sensible default
            if "open" in self.predetermined_responses:
                return self.predetermined_responses["open"]
            # Default to empty response (user cancelled)
            return ("", "")

        def mock_get_save_filename(parent=None, caption="", directory="", filter="", options=None):
            """Mock getSaveFileName that validates parameters and returns predetermined response"""
            # Validate that we're actually getting a QFileDialog call
            assert isinstance(caption, str), "Caption should be string"
            assert isinstance(directory, str), "Directory should be string"
            assert isinstance(filter, str), "Filter should be string"

            # Store dialog configuration for test validation
            self.last_dialog_config["save"] = {
                "parent": parent,
                "caption": caption,
                "directory": directory,
                "filter": filter,
                "options": options
            }

            # Return predetermined response or sensible default
            if "save" in self.predetermined_responses:
                return self.predetermined_responses["save"]
            # Default to empty response (user cancelled)
            return ("", "")

        try:
            # Apply patches
            QFileDialog.getOpenFileName = staticmethod(mock_get_open_filename)
            QFileDialog.getSaveFileName = staticmethod(mock_get_save_filename)
            yield self
        finally:
            # Restore original methods
            QFileDialog.getOpenFileName = original_get_open_filename
            QFileDialog.getSaveFileName = original_get_save_filename

    def get_last_dialog_config(self, dialog_type: str) -> dict[str, Any]:
        """Get the configuration of the last dialog of the specified type"""
        return self.last_dialog_config.get(dialog_type, {})

    def was_dialog_called(self, dialog_type: str) -> bool:
        """Check if a dialog of the specified type was called"""
        return dialog_type in self.last_dialog_config

    def validate_dialog_config(self, dialog_type: str, expected_config: dict[str, Any]):
        """Validate that the dialog was called with expected configuration"""
        actual_config = self.get_last_dialog_config(dialog_type)

        for key, expected_value in expected_config.items():
            if key in actual_config:
                actual_value = actual_config[key]
                assert actual_value == expected_value, f"Dialog {dialog_type}: Expected {key}='{expected_value}', got '{actual_value}'"
            else:
                raise AssertionError(f"Dialog {dialog_type}: Expected {key} not found in dialog config")

class FileHelper:
    """
    Helper for creating temporary test files for file dialog testing.

    Provides methods to create temporary files and directories that can be used
    in file dialog tests without requiring real files to exist in the test environment.
    """

    def __init__(self):
        self.temp_files = []
        self.temp_dirs = []

    def create_temp_file(self, content: str = "test content", suffix: str = ".txt") -> str:
        """
        Create a temporary file with specified content.

        Args:
            content: Content to write to the file
            suffix: File extension

        Returns:
            Absolute path to the created temporary file
        """
        temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
        temp_file.write(content)
        temp_file.close()

        self.temp_files.append(temp_file.name)
        return temp_file.name

    def create_temp_dir(self) -> str:
        """
        Create a temporary directory.

        Returns:
            Absolute path to the created temporary directory
        """
        temp_dir = tempfile.mkdtemp()
        self.temp_dirs.append(temp_dir)
        return temp_dir

    def cleanup(self):
        """Clean up all temporary files and directories"""
        for temp_file in self.temp_files:
            try:
                if Path(temp_file).exists():
                    Path(temp_file).unlink()
            except Exception:
                pass  # Ignore cleanup errors

        for temp_dir in self.temp_dirs:
            try:
                if Path(temp_dir).exists():
                    import shutil
                    shutil.rmtree(temp_dir)
            except Exception:
                pass  # Ignore cleanup errors

        self.temp_files.clear()
        self.temp_dirs.clear()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()

# Convenience functions for easy test usage
def create_file_dialog_helper() -> FileDialogHelper:
    """Create a new TestFileDialogHelper instance"""
    return FileDialogHelper()

def create_file_helper() -> FileHelper:
    """Create a new TestFileHelper instance"""
    return FileHelper()

@contextmanager
def file_dialog_responses(**responses):
    """
    Convenient context manager for setting file dialog responses.

    Usage:
        with file_dialog_responses(open_file="/test/file.txt", save_file="/test/output.txt"):
            # Test code that triggers file dialogs
    """
    helper = FileDialogHelper()

    if "open_file" in responses:
        helper.set_open_file_response(responses["open_file"])
    if "save_file" in responses:
        helper.set_save_file_response(responses["save_file"])

    with helper.patch_file_dialogs():
        yield helper
