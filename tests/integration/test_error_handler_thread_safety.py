"""
Test thread safety of ErrorHandler signal emissions.

Tests that ErrorHandler signals work correctly from multiple threads.
Qt signals are inherently thread-safe (queued connections across threads).
"""

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from PySide6.QtWidgets import QWidget

from tests.fixtures.timeouts import signal_timeout
from ui.common import ErrorHandler

# Serial execution required: Thread safety concerns
pytestmark = [pytest.mark.headless]


class TestErrorHandlerThreadSafety:
    """Test thread safety of ErrorHandler signal emissions."""

    def test_signal_emission_from_multiple_threads(self, qtbot):
        """Test that ErrorHandler signals can be emitted from multiple threads."""
        parent = QWidget()
        qtbot.addWidget(parent)

        handler = ErrorHandler(parent)
        handler.set_show_dialogs(False)

        # Track signal emissions
        received_errors = []
        handler.critical_error.connect(lambda title, msg: received_errors.append((title, msg)))

        errors = []

        def emit_error(thread_id: int):
            """Emit error from a thread."""
            try:
                handler.handle_critical_error(f"Thread {thread_id}", f"Message from thread {thread_id}")
                return True
            except Exception as e:
                errors.append(e)
                return False

        # Launch multiple threads
        num_emissions = 10
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(emit_error, i) for i in range(num_emissions)]
            [future.result() for future in as_completed(futures)]

        # Wait for all signals to be delivered using deterministic wait
        qtbot.waitUntil(
            lambda: len(received_errors) == num_emissions,
            timeout=signal_timeout(),
        )

        # Verify no errors occurred
        assert not errors, f"Errors in threads: {errors}"

        # Verify all signals were received
        assert len(received_errors) == num_emissions, f"Expected {num_emissions} errors, got {len(received_errors)}"
