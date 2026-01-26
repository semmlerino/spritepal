"""
Comprehensive tests for Worker infrastructure.

Combines testing for BaseWorker lifecycle, error handling, and ManagedWorker
interactions.

Consolidated from:
- tests/unit/core/workers/test_base_worker.py
- tests/integration/test_worker_base.py
"""

from __future__ import annotations

import time
from unittest.mock import Mock

import pytest
from PySide6.QtCore import Signal
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from core.managers.base_manager import BaseManager
from core.workers.base import BaseWorker, ManagedWorker, handle_worker_errors
from ui.common import WorkerManager

# Shared markers
pytestmark = [
    pytest.mark.unit,
    pytest.mark.skip_thread_cleanup(reason="Worker tests create background worker threads"),
    pytest.mark.headless,
]


@pytest.fixture
def qtbot_app(qtbot):
    """Ensure QApplication exists for tests not using qtbot directly."""
    # qtbot fixture automatically handles QApplication creation
    return QApplication.instance()


class TestWorkerLifecycle:
    """Test worker lifecycle management (BaseWorker + WorkerManager)."""

    def test_worker_cleanup_pattern(self, qtbot_app):
        """Test proper worker cleanup pattern using WorkerManager"""

        class TestWorker(BaseWorker):
            progress = Signal(int)
            finished = Signal()

            @handle_worker_errors()
            def run(self):
                for i in range(50):
                    if self.is_cancelled:
                        break
                    self.progress.emit(i)
                    time.sleep(0.02)  # sleep-ok: thread interleaving
                self.finished.emit()

        worker = TestWorker()

        # Track cancellation
        cancel_called = False
        original_cancel = worker.cancel

        def track_cancel():
            nonlocal cancel_called
            cancel_called = True
            original_cancel()

        worker.cancel = track_cancel

        # Use WorkerManager for proper lifecycle
        worker.start()

        time.sleep(0.05)  # sleep-ok: thread interleaving
        WorkerManager.cleanup_worker(worker, timeout=1000)

        assert cancel_called
        assert worker.is_cancelled

    def test_worker_error_handling(self, qtbot_app):
        """Test worker error handling with decorator"""

        class ErrorWorker(BaseWorker):
            @handle_worker_errors()
            def run(self):
                raise ValueError("Test error")

        worker = ErrorWorker()
        errors = []
        worker.error.connect(lambda msg, exc: errors.append((msg, exc)))

        worker.start()
        worker.wait(1000)
        QApplication.processEvents()

        assert len(errors) == 1
        assert "Test error" in errors[0][0]
        assert isinstance(errors[0][1], ValueError)


class TestBaseWorkerFeatures:
    """Test BaseWorker specific features (Signals, Cancellation)."""

    def test_worker_initialization(self, qtbot):
        class TestWorker(BaseWorker):
            def run(self):
                pass

        worker = TestWorker()
        assert not worker.is_cancelled

    def test_worker_cancellation(self, qtbot):
        class TestWorker(BaseWorker):
            def run(self):
                self.check_cancellation()

        worker = TestWorker()
        worker.cancel()
        assert worker.is_cancelled

    def test_progress_emission(self, qtbot):
        class TestWorker(BaseWorker):
            def run(self):
                pass

        worker = TestWorker()
        progress_spy = QSignalSpy(worker.progress)

        # Normal
        worker.emit_progress(50, "Half done")
        assert progress_spy.at(0) == [50, "Half done"]

        # Clamping
        worker.emit_progress(-10, "Negative")
        assert progress_spy.at(1) == [0, "Negative"]
        worker.emit_progress(150, "Over 100")
        assert progress_spy.at(2) == [100, "Over 100"]

    def test_error_emission(self, qtbot):
        class TestWorker(BaseWorker):
            def run(self):
                pass

        worker = TestWorker()
        error_spy = QSignalSpy(worker.error)

        # String only
        worker.emit_error("Test error")
        assert error_spy.at(0)[0] == "Test error"

        # Exception
        exc = ValueError("Custom")
        worker.emit_error("Custom", exc)
        assert error_spy.at(1)[1] is exc

    def test_warning_emission(self, qtbot):
        class TestWorker(BaseWorker):
            def run(self):
                pass

        worker = TestWorker()
        warning_spy = QSignalSpy(worker.warning)

        worker.emit_warning("Test warning")
        assert warning_spy.at(0) == ["Test warning"]

    def test_wait_if_paused_with_cancellation(self, qtbot):
        class TestWorker(BaseWorker):
            def run(self):
                self.pause()
                self.wait_if_paused()

        worker = TestWorker()
        worker.pause()
        assert worker.is_paused

        worker.cancel()
        worker.wait_if_paused()  # Should return immediately
        # Pass if no hang


class TestManagedWorker:
    """Test ManagedWorker which wraps BaseManager operations."""

    def test_managed_worker_initialization(self, qtbot):
        class TestManagedWorker(ManagedWorker):
            def perform_operation(self):
                pass

        manager = Mock(spec=BaseManager)
        worker = TestManagedWorker(manager)
        assert worker.manager is manager

    def test_lifecycle_success(self, qtbot):
        """Test connect -> operate -> disconnect -> finish flow."""

        class TestManagedWorker(ManagedWorker):
            def __init__(self, mgr):
                super().__init__(mgr)
                self.connected = False
                self.disconnected = False

            def connect_manager_signals(self):
                self.connected = True

            def disconnect_manager_signals(self):
                self.disconnected = True

            def perform_operation(self):
                self.operation_finished.emit(True, "Done")

        manager = Mock(spec=BaseManager)
        worker = TestManagedWorker(manager)

        finished_spy = QSignalSpy(worker.operation_finished)
        worker.start()
        worker.wait(1000)
        QApplication.processEvents()

        assert worker.connected
        assert worker.disconnected
        assert finished_spy.at(0) == [True, "Done"]

    def test_lifecycle_error(self, qtbot):
        """Test error handling during operation."""

        class TestManagedWorker(ManagedWorker):
            def connect_manager_signals(self):
                pass

            def perform_operation(self):
                raise ValueError("Ops failed")

        manager = Mock(spec=BaseManager)
        worker = TestManagedWorker(manager)

        finished_spy = QSignalSpy(worker.operation_finished)
        error_spy = QSignalSpy(worker.error)

        worker.start()
        worker.wait(1000)
        QApplication.processEvents()

        assert "Ops failed" in error_spy.at(0)[0]
        assert finished_spy.at(0)[0] is False

    def test_cleanup_on_exception(self, qtbot):
        """Verify disconnect is called even if operation fails."""

        class TestManagedWorker(ManagedWorker):
            def __init__(self, mgr):
                super().__init__(mgr)
                self.cleanup_called = False

            def connect_manager_signals(self):
                pass

            def disconnect_manager_signals(self):
                self.cleanup_called = True

            def perform_operation(self):
                raise RuntimeError("Crash")

        manager = Mock(spec=BaseManager)
        worker = TestManagedWorker(manager)

        worker.start()
        worker.wait(1000)
        QApplication.processEvents()

        assert worker.cleanup_called
