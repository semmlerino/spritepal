"""
Comprehensive ErrorHandler tests: signal emission, exception handling, and thread safety.

Consolidated from:
- test_error_handler.py
- test_error_handler_thread_safety.py
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QWidget

from tests.fixtures.timeouts import signal_timeout
from ui.common import ErrorHandler

pytestmark = [
    pytest.mark.integration,
    pytest.mark.headless,
]


class TestErrorHandlerSignals:
    """Test error handler signal-based approach."""

    @pytest.mark.gui
    def test_error_handler_emits_signals(self, qtbot):
        """Test that error handler emits signals instead of showing dialogs."""
        parent = QWidget()
        qtbot.addWidget(parent)

        handler = ErrorHandler(parent)
        handler.set_show_dialogs(False)

        critical_spy = QSignalSpy(handler.critical_error)
        warning_spy = QSignalSpy(handler.warning_error)
        info_spy = QSignalSpy(handler.info_message)

        handler.handle_critical_error("Test Error", "This is a test error")
        assert critical_spy.count() == 1
        assert critical_spy.at(0) == ["Test Error", "This is a test error"]

        handler.handle_warning("Test Warning", "This is a test warning")
        assert warning_spy.count() == 1
        assert warning_spy.at(0) == ["Test Warning", "This is a test warning"]

        handler.handle_info("Test Info", "This is test info")
        assert info_spy.count() == 1
        assert info_spy.at(0) == ["Test Info", "This is test info"]

    @pytest.mark.gui
    def test_error_handler_handles_exceptions(self, qtbot):
        """Test that error handler can handle exceptions."""
        parent = QWidget()
        qtbot.addWidget(parent)

        handler = ErrorHandler(parent)
        handler.set_show_dialogs(False)

        critical_spy = QSignalSpy(handler.critical_error)

        test_exception = ValueError("Test exception")
        handler.handle_exception(test_exception, "Test context")

        assert critical_spy.count() == 1
        assert critical_spy.at(0)[0] == "Error"
        assert "Test context: Test exception" in critical_spy.at(0)[1]

    @pytest.mark.gui
    def test_custom_signal_handlers(self, qtbot):
        """Test that custom handlers can be connected to error signals."""
        parent = QWidget()
        qtbot.addWidget(parent)

        handler = ErrorHandler(parent)
        handler.set_show_dialogs(False)

        custom_calls = []

        def custom_critical_handler(title: str, message: str):
            custom_calls.append(("critical", title, message))

        def custom_warning_handler(title: str, message: str):
            custom_calls.append(("warning", title, message))

        handler.critical_error.connect(custom_critical_handler)
        handler.warning_error.connect(custom_warning_handler)

        handler.handle_critical_error("Critical", "Critical message")
        handler.handle_warning("Warning", "Warning message")

        assert len(custom_calls) == 2
        assert custom_calls[0] == ("critical", "Critical", "Critical message")
        assert custom_calls[1] == ("warning", "Warning", "Warning message")


class TestErrorHandlerThreadSafety:
    """Test thread safety of ErrorHandler signal emissions.

    Qt signals are inherently thread-safe (queued connections across threads).
    """

    def test_signal_emission_from_multiple_threads(self, qtbot):
        """Test that ErrorHandler signals can be emitted from multiple threads."""
        parent = QWidget()
        qtbot.addWidget(parent)

        handler = ErrorHandler(parent)
        handler.set_show_dialogs(False)

        received_errors: list[tuple[str, str]] = []
        handler.critical_error.connect(lambda title, msg: received_errors.append((title, msg)))

        errors: list[Exception] = []

        def emit_error(thread_id: int):
            """Emit error from a thread."""
            try:
                handler.handle_critical_error(f"Thread {thread_id}", f"Message from thread {thread_id}")
                return True
            except Exception as e:
                errors.append(e)
                return False

        num_emissions = 10
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(emit_error, i) for i in range(num_emissions)]
            [future.result() for future in as_completed(futures)]

        qtbot.waitUntil(
            lambda: len(received_errors) == num_emissions,
            timeout=signal_timeout(),
        )

        assert not errors, f"Errors in threads: {errors}"
        assert len(received_errors) == num_emissions


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
