"""Tests for BaseWorker lifecycle and error handling.

Extracted from test_qt_threading_patterns.py to focus on application-specific
worker implementation testing rather than general Qt threading patterns.
"""

from __future__ import annotations

import time

import pytest
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QApplication

from core.workers.base import BaseWorker, handle_worker_errors
from ui.common import WorkerManager


class TestWorkerLifecycle:
    """Test worker lifecycle management"""

    @pytest.fixture
    def app(self):
        """Ensure QApplication exists"""
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield app

    def test_worker_cleanup_pattern(self, app):
        """Test proper worker cleanup pattern using WorkerManager"""

        class TestWorker(BaseWorker):
            progress = Signal(int)
            finished = Signal()

            @handle_worker_errors()  # Note: decorator factory needs parentheses
            def run(self):
                for i in range(50):  # Longer running to ensure still running when cleanup called
                    if self.is_cancelled:
                        break
                    self.progress.emit(i)
                    time.sleep(0.02)  # sleep-ok: thread interleaving
                self.finished.emit()

        # Create worker
        worker = TestWorker()

        # Track cancellation via the cancel method
        cancel_called = False
        original_cancel = worker.cancel

        def track_cancel():
            nonlocal cancel_called
            cancel_called = True
            original_cancel()

        worker.cancel = track_cancel

        # Use WorkerManager for proper lifecycle
        worker.start()

        # Wait a short bit then cleanup via WorkerManager (worker should still be running)
        time.sleep(0.05)  # sleep-ok: thread interleaving
        WorkerManager.cleanup_worker(worker, timeout=1000)

        # Verify cancel was called (WorkerManager calls cancel if available)
        assert cancel_called
        assert worker.is_cancelled

    def test_worker_error_handling(self, app):
        """Test worker error handling with decorator"""

        class ErrorWorker(BaseWorker):
            # BaseWorker already has 'error' signal, no need to redefine

            @handle_worker_errors()  # Note: decorator factory needs parentheses
            def run(self):
                # This will be caught by decorator
                raise ValueError("Test error")

        # Create worker
        worker = ErrorWorker()

        # Capture error using BaseWorker's error signal
        errors = []
        worker.error.connect(lambda msg, exc: errors.append((msg, exc)))

        # Run worker
        worker.start()
        worker.wait(1000)

        # Process queued signals from worker thread
        QApplication.processEvents()

        # Verify error was emitted
        assert len(errors) == 1
        assert "Test error" in errors[0][0]
        assert isinstance(errors[0][1], ValueError)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
