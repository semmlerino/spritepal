"""
Dialog mocking fixtures for SpritePal tests.

Consolidates 30+ scattered QMessageBox patches into a single, reusable fixture.
This reduces test boilerplate and ensures consistent dialog handling.

Usage:
    def test_something(mock_dialogs):
        mock_dialogs.set_response("warning", QMessageBox.StandardButton.No)
        mock_dialogs.set_response("question", QMessageBox.StandardButton.Yes)

        # ... trigger code that shows dialogs ...

        assert mock_dialogs.get_call_count("warning") == 1
        assert mock_dialogs.was_called("question")

Note: The fixture automatically patches all QMessageBox static methods at
the PySide6.QtWidgets level, so it works for all imports.
"""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QMessageBox


@dataclass
class MockDialogs:
    """
    Centralized mock for QMessageBox dialog methods.

    Provides a type-safe interface for:
    - Setting return values for dialog methods
    - Tracking call counts and arguments
    - Asserting dialog behavior in tests
    """

    # Default responses for each dialog type
    _responses: dict[str, QMessageBox.StandardButton] = field(default_factory=dict)

    # Underlying mock objects for each dialog type
    _mocks: dict[str, MagicMock] = field(default_factory=dict)

    # Context manager for cleanup
    _exit_stack: ExitStack = field(default_factory=ExitStack)

    def __post_init__(self) -> None:
        """Initialize default responses."""
        # Default responses that allow tests to proceed without dialogs blocking
        self._responses = {
            "warning": QMessageBox.StandardButton.Yes,
            "information": QMessageBox.StandardButton.Ok,
            "critical": QMessageBox.StandardButton.Ok,
            "question": QMessageBox.StandardButton.Yes,
        }

    def _start_patches(self) -> None:
        """Start all QMessageBox patches."""
        dialog_methods = ["warning", "information", "critical", "question"]

        for method_name in dialog_methods:
            # Create mock that returns the configured response
            mock = MagicMock()
            mock.return_value = self._responses.get(method_name, QMessageBox.StandardButton.Ok)

            # Patch at PySide6 level to catch all imports
            p = patch.object(QMessageBox, method_name, mock)
            self._exit_stack.enter_context(p)
            self._mocks[method_name] = mock

    def _stop_patches(self) -> None:
        """Stop all patches and clean up."""
        self._exit_stack.close()
        self._mocks.clear()

    def set_response(self, method: str, response: QMessageBox.StandardButton) -> MockDialogs:
        """
        Set the return value for a dialog method.

        Args:
            method: Dialog method name ("warning", "information", "critical", "question")
            response: The StandardButton to return when this dialog is shown

        Returns:
            self for method chaining

        Example:
            mock_dialogs.set_response("warning", QMessageBox.StandardButton.No)
        """
        self._responses[method] = response
        if method in self._mocks:
            self._mocks[method].return_value = response
        return self

    def get_call_count(self, method: str) -> int:
        """
        Get the number of times a dialog method was called.

        Args:
            method: Dialog method name

        Returns:
            Number of times the method was called
        """
        if method in self._mocks:
            return self._mocks[method].call_count
        return 0

    def was_called(self, method: str) -> bool:
        """
        Check if a dialog method was called at least once.

        Args:
            method: Dialog method name

        Returns:
            True if method was called at least once
        """
        return self.get_call_count(method) > 0

    def get_calls(self, method: str) -> list[tuple[tuple[Any, ...], dict[str, Any]]]:
        """
        Get all call arguments for a dialog method.

        Args:
            method: Dialog method name

        Returns:
            List of (args, kwargs) tuples for each call
        """
        if method in self._mocks:
            return [(call.args, call.kwargs) for call in self._mocks[method].call_args_list]
        return []

    def get_last_message(self, method: str) -> str | None:
        """
        Get the message text from the last call to a dialog method.

        Args:
            method: Dialog method name

        Returns:
            The message text argument, or None if not called
        """
        calls = self.get_calls(method)
        if not calls:
            return None
        # QMessageBox.warning(parent, title, text, ...) - text is 3rd positional arg
        args, kwargs = calls[-1]
        if len(args) >= 3:
            return str(args[2])
        if "text" in kwargs:
            return str(kwargs["text"])
        return None

    def reset(self) -> None:
        """Reset all call counts and history (but keep responses)."""
        for mock in self._mocks.values():
            mock.reset_mock()

    def assert_not_called(self, method: str) -> None:
        """
        Assert that a dialog method was never called.

        Args:
            method: Dialog method name

        Raises:
            AssertionError: If the method was called
        """
        if method in self._mocks:
            self._mocks[method].assert_not_called()

    def assert_called_once(self, method: str) -> None:
        """
        Assert that a dialog method was called exactly once.

        Args:
            method: Dialog method name

        Raises:
            AssertionError: If the method was not called exactly once
        """
        if method in self._mocks:
            self._mocks[method].assert_called_once()
        else:
            raise AssertionError(f"Unknown dialog method: {method}")


@pytest.fixture
def mock_dialogs() -> MockDialogs:
    """
    Fixture that provides a MockDialogs instance with all QMessageBox methods patched.

    The fixture:
    - Patches warning, information, critical, and question methods
    - Provides sensible defaults (Yes for warning/question, Ok for info/critical)
    - Allows setting custom responses
    - Tracks all calls for assertions

    Usage:
        def test_something(mock_dialogs):
            # Override default if needed
            mock_dialogs.set_response("warning", QMessageBox.StandardButton.No)

            # ... trigger code that shows dialogs ...

            # Verify dialogs were shown
            assert mock_dialogs.was_called("warning")
            assert mock_dialogs.get_call_count("warning") == 1
    """
    dialogs = MockDialogs()
    dialogs._start_patches()
    yield dialogs
    dialogs._stop_patches()


@pytest.fixture
def mock_dialogs_deny() -> MockDialogs:
    """
    Fixture variant that defaults to rejecting/canceling all dialogs.

    Useful for testing cancel/abort paths.

    Usage:
        def test_user_cancels(mock_dialogs_deny):
            # All dialogs will return No/Cancel by default
            # ... trigger code that shows dialogs ...
            # Verify cancellation was handled correctly
    """
    dialogs = MockDialogs()
    dialogs._responses = {
        "warning": QMessageBox.StandardButton.No,
        "information": QMessageBox.StandardButton.Ok,  # Info only has Ok
        "critical": QMessageBox.StandardButton.Ok,  # Critical only has Ok
        "question": QMessageBox.StandardButton.No,
    }
    dialogs._start_patches()
    yield dialogs
    dialogs._stop_patches()
