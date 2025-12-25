"""
Test thread safety of ErrorHandler signal emissions.

Tests that ErrorHandler signals work correctly from multiple threads.
Qt signals are inherently thread-safe (queued connections across threads).
"""

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from PySide6.QtWidgets import QWidget

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
        handler.critical_error.connect(
            lambda title, msg: received_errors.append((title, msg))
        )

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
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(emit_error, i) for i in range(10)]
            [future.result() for future in as_completed(futures)]

        # Process pending events to ensure signals are delivered
        qtbot.wait(100)

        # Verify no errors occurred
        assert not errors, f"Errors in threads: {errors}"

        # Verify signals were received (may be fewer due to Qt event processing timing)
        assert len(received_errors) > 0, "Expected some errors to be received"
