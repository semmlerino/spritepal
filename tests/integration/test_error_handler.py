"""
Test error handler functionality
"""

from __future__ import annotations

import pytest
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QWidget

from ui.common import ErrorHandler

# Test characteristics: Real GUI components requiring display
pytestmark = [
    pytest.mark.gui,
    pytest.mark.slow,
    pytest.mark.allows_registry_state(reason="Pure error handling tests, no managers"),
]


class TestErrorHandler:
    """Test error handler signal-based approach"""

    def test_error_handler_emits_signals(self, qtbot):
        """Test that error handler emits signals instead of showing dialogs"""
        # Create a parent widget
        parent = QWidget()
        qtbot.addWidget(parent)

        # Create error handler
        handler = ErrorHandler(parent)
        handler.set_show_dialogs(False)  # Disable dialogs for testing

        # Create signal spies
        critical_spy = QSignalSpy(handler.critical_error)
        warning_spy = QSignalSpy(handler.warning_error)
        info_spy = QSignalSpy(handler.info_message)

        # Test critical error
        handler.handle_critical_error("Test Error", "This is a test error")
        assert critical_spy.count() == 1
        assert critical_spy.at(0) == ["Test Error", "This is a test error"]

        # Test warning
        handler.handle_warning("Test Warning", "This is a test warning")
        assert warning_spy.count() == 1
        assert warning_spy.at(0) == ["Test Warning", "This is a test warning"]

        # Test info
        handler.handle_info("Test Info", "This is test info")
        assert info_spy.count() == 1
        assert info_spy.at(0) == ["Test Info", "This is test info"]

    def test_error_handler_handles_exceptions(self, qtbot):
        """Test that error handler can handle exceptions"""
        parent = QWidget()
        qtbot.addWidget(parent)

        handler = ErrorHandler(parent)
        handler.set_show_dialogs(False)

        critical_spy = QSignalSpy(handler.critical_error)

        # Test exception handling
        test_exception = ValueError("Test exception")
        handler.handle_exception(test_exception, "Test context")

        assert critical_spy.count() == 1
        assert critical_spy.at(0)[0] == "Error"
        assert "Test context: Test exception" in critical_spy.at(0)[1]

    def test_custom_signal_handlers(self, qtbot):
        """Test that custom handlers can be connected to error signals"""
        parent = QWidget()
        qtbot.addWidget(parent)

        handler = ErrorHandler(parent)
        handler.set_show_dialogs(False)

        # Track custom handler calls
        custom_calls = []

        def custom_critical_handler(title: str, message: str):
            custom_calls.append(("critical", title, message))

        def custom_warning_handler(title: str, message: str):
            custom_calls.append(("warning", title, message))

        # Connect custom handlers
        handler.critical_error.connect(custom_critical_handler)
        handler.warning_error.connect(custom_warning_handler)

        # Trigger errors
        handler.handle_critical_error("Critical", "Critical message")
        handler.handle_warning("Warning", "Warning message")

        # Verify custom handlers were called
        assert len(custom_calls) == 2
        assert custom_calls[0] == ("critical", "Critical", "Critical message")
        assert custom_calls[1] == ("warning", "Warning", "Warning message")
