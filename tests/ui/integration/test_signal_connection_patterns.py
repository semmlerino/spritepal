"""
Qt Signal Connection Pattern Tests.

Tests for Qt signal connection patterns and best practices used throughout the codebase.
These tests use mock workers to verify PATTERNS (not production classes) including:
- _signals_connected flag synchronization (prevents duplicate connections)
- blockSignals() usage during cleanup
- QueuedConnection for cross-thread signals
- disconnect-before-reconnect patterns

NOTE: This file tests signal connection PATTERNS, not production BatchThumbnailWorker
or PreviewWorkerPool classes directly. For production class testing, see:
- tests/integration/test_batch_thumbnail_worker_integration.py
- tests/ui/integration/test_preview_worker_pool.py (if it exists)

The patterns tested here mirror those in:
- preview_worker_pool.py:447-450, 532-535 - _signals_connected flag management
- batch_thumbnail_worker.py:817-819 - signal connection lifecycle

Async Safety Notes
------------------
These tests involve real threaded workers and MUST use qtbot.waitSignal():

    with qtbot.waitSignal(worker.preview_ready, timeout=worker_timeout()):
        pool.submit_request(...)

Without the context manager, signals may emit before the wait starts (race condition).

Key Patterns:
1. Connect spies BEFORE starting async operations
2. Use MultiSignalRecorder for multi-signal tracking
3. Use timeouts from tests/fixtures/timeouts.py
4. Clean up workers in fixture teardown to prevent thread leaks
"""

from __future__ import annotations

import queue
import time
import weakref
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, Mock, patch

import pytest
from PySide6.QtCore import QCoreApplication, QMutex, QMutexLocker, QObject, Qt, QThread, Signal
from PySide6.QtTest import QSignalSpy

from tests.fixtures.timeouts import signal_timeout, worker_timeout
from tests.ui.integration.helpers.signal_spy_utils import MultiSignalRecorder

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


# =============================================================================
# Mock Worker for Testing Pool Behavior
# =============================================================================


class MockPooledWorker(QObject):
    """Mock worker that mimics PooledPreviewWorker signal behavior."""

    preview_ready = Signal(
        int, bytes, int, int, str, int, int, int, bool, bytes
    )  # request_id, tile_data, width, height, name, compressed_size, slack_size, actual_offset, hal_succeeded, header_bytes

    preview_error = Signal(int, str)  # request_id, error_msg

    def __init__(self, pool_ref: weakref.ref[object] | None = None) -> None:
        super().__init__()
        self._signals_connected = False
        self._current_request_id = 0
        self._pool_ref = pool_ref
        self._being_destroyed = False

    def setup_request(self, request: object, extractor: object) -> None:
        """Setup for a request."""
        if hasattr(request, "request_id"):
            self._current_request_id = request.request_id

    def start(self) -> None:
        """Simulate starting work."""
        # Emit success after short delay (simulates async work)
        self.preview_ready.emit(
            self._current_request_id,
            b"\x00" * 32,  # tile_data
            8,  # width
            8,  # height
            "TestSprite",  # name
            32,  # compressed_size
            0,  # slack_size
            0x1000,  # actual_offset
            True,  # hal_succeeded
            b"",  # header_bytes
        )

    def cancel_current_request(self) -> None:
        """Cancel current request."""
        pass

    def blockSignals(self, block: bool) -> bool:  # noqa: N802 - Qt naming
        """Block/unblock signals."""
        return super().blockSignals(block)


class MockPreviewRequest:
    """Mock preview request."""

    _next_id = 0

    def __init__(self, offset: int = 0x1000) -> None:
        MockPreviewRequest._next_id += 1
        self.request_id = MockPreviewRequest._next_id
        self.offset = offset
        self.preview_ready_callback = None
        self.preview_error_callback = None


# =============================================================================
# PreviewWorkerPool Signal Connection Flag Tests
# =============================================================================


class TestPreviewWorkerPoolSignalFlags:
    """Test _signals_connected flag behavior in PreviewWorkerPool-like scenarios.

    These tests verify the pattern used in preview_worker_pool.py:447-450 and 532-535.
    """

    def test_signals_connected_flag_set_on_first_connection(self, qtbot: QtBot) -> None:
        """_signals_connected flag must be True after first connection."""
        worker = MockPooledWorker()
        received_count = 0

        def handler(*args: object) -> None:
            nonlocal received_count
            received_count += 1

        # Simulate pool connection logic (from preview_worker_pool.py:447-450)
        if not worker._signals_connected:
            worker.preview_ready.connect(handler, Qt.ConnectionType.QueuedConnection)
            worker._signals_connected = True

        assert worker._signals_connected is True

        # Emit signal
        worker.start()
        QCoreApplication.processEvents()

        assert received_count == 1, "Signal should be delivered once"

    def test_duplicate_connection_prevented_by_flag(self, qtbot: QtBot) -> None:
        """Flag should prevent duplicate signal connections on worker reuse."""
        worker = MockPooledWorker()
        received_count = 0

        def handler(*args: object) -> None:
            nonlocal received_count
            received_count += 1

        # First connection
        if not worker._signals_connected:
            worker.preview_ready.connect(handler, Qt.ConnectionType.QueuedConnection)
            worker._signals_connected = True

        # Simulate worker reuse - flag prevents second connection
        if not worker._signals_connected:
            worker.preview_ready.connect(handler, Qt.ConnectionType.QueuedConnection)
            worker._signals_connected = True

        # Emit signal
        worker.start()
        QCoreApplication.processEvents()

        # Should only receive once (not twice)
        assert received_count == 1, f"Expected 1 emission, got {received_count} (duplicate connection bug)"

    def test_flag_desync_causes_missed_signals(self, qtbot: QtBot) -> None:
        """Demonstrate bug: if flag is True but no connection, signals are missed."""
        worker = MockPooledWorker()
        received_count = 0

        def handler(*args: object) -> None:
            nonlocal received_count
            received_count += 1

        # BUG SCENARIO: Flag set but never actually connected
        worker._signals_connected = True  # Incorrectly set

        # Reuse check - flag says connected, so skip connection
        if not worker._signals_connected:
            worker.preview_ready.connect(handler, Qt.ConnectionType.QueuedConnection)
            worker._signals_connected = True

        # Emit signal
        worker.start()
        QCoreApplication.processEvents()

        # BUG: Signal missed because never actually connected
        assert received_count == 0, "This test demonstrates the desync bug - signals missed when flag is wrong"

    def test_flag_must_be_reset_on_cleanup(self, qtbot: QtBot) -> None:
        """_signals_connected flag must be reset when worker is cleaned up."""
        worker = MockPooledWorker()
        received_values: list[int] = []

        def handler(request_id: int, *args: object) -> None:
            received_values.append(request_id)

        # Connect and set flag
        worker.preview_ready.connect(handler, Qt.ConnectionType.QueuedConnection)
        worker._signals_connected = True

        # Simulate cleanup (from preview_worker_pool.py:644)
        worker.blockSignals(True)
        try:
            worker.preview_ready.disconnect(handler)
        except (TypeError, RuntimeError):
            pass
        worker._signals_connected = False  # Must reset flag

        assert worker._signals_connected is False, "Flag should be reset after cleanup"

        # After cleanup, reconnection should work
        worker.blockSignals(False)
        worker.preview_ready.connect(handler, Qt.ConnectionType.QueuedConnection)
        worker._signals_connected = True

        worker.start()
        QCoreApplication.processEvents()

        assert len(received_values) == 1, "Reconnection after cleanup should work"


class TestPreviewWorkerPoolReuse:
    """Test worker reuse patterns from preview_worker_pool.py."""

    def test_worker_return_to_pool_signals_remain_connected(self, qtbot: QtBot) -> None:
        """Workers returned to pool should keep signals connected (critical fix)."""
        # This tests the behavior documented at preview_worker_pool.py:488-491
        worker = MockPooledWorker()
        emission_count = 0

        def handler(*args: object) -> None:
            nonlocal emission_count
            emission_count += 1

        # Initial connection
        worker.preview_ready.connect(handler, Qt.ConnectionType.QueuedConnection)
        worker._signals_connected = True

        # First use
        worker.start()
        QCoreApplication.processEvents()
        assert emission_count == 1

        # "Return to pool" - signals remain connected
        # (We don't disconnect here - that's the fix)

        # Second use (worker reused from pool)
        worker.start()
        QCoreApplication.processEvents()

        assert emission_count == 2, "Reused worker should still emit signals"

    def test_pool_connection_idempotent_across_requests(self, qtbot: QtBot) -> None:
        """Multiple submit_request calls should not create duplicate connections."""
        worker = MockPooledWorker()
        emissions: list[int] = []

        def handler(request_id: int, *args: object) -> None:
            emissions.append(request_id)

        # Simulate multiple requests going through the pool connection logic
        for i in range(3):
            request = MockPreviewRequest(offset=0x1000 + i * 0x100)
            worker.setup_request(request, None)

            # Pool connection logic (from preview_worker_pool.py:447-450)
            if not worker._signals_connected:
                worker.preview_ready.connect(handler, Qt.ConnectionType.QueuedConnection)
                worker._signals_connected = True

            worker.start()
            QCoreApplication.processEvents()

        # Should have exactly 3 emissions (one per request), not 6 (if duplicated)
        assert len(emissions) == 3, f"Expected 3 emissions, got {len(emissions)}"


# =============================================================================
# BatchThumbnailWorker Signal Connection Tests
# =============================================================================


class MockBatchThumbnailWorker(QObject):
    """Mock worker that mimics BatchThumbnailWorker signal behavior."""

    thumbnail_ready = Signal(int, object)  # offset, QImage
    progress = Signal(int, int)  # completed, total
    error = Signal(str)
    started = Signal()
    finished = Signal()

    def __init__(self, rom_path: str = "", rom_extractor: object = None) -> None:
        super().__init__()
        self._rom_path = rom_path
        self._stopped = False

    def run(self) -> None:
        """Simulate worker run."""
        self.started.emit()
        self.progress.emit(1, 1)
        self.finished.emit()

    def stop(self) -> None:
        """Stop the worker."""
        self._stopped = True

    def queue_thumbnail(self, offset: int, size: int = 384, priority: int = 0) -> None:
        """Queue a thumbnail."""
        pass

    def cleanup(self) -> None:
        """Clean up resources."""
        pass


class TestBatchThumbnailWorkerSignals:
    """Test signal connection patterns in batch_thumbnail_worker.py.

    Tests the pattern at batch_thumbnail_worker.py:817-819.
    """

    def test_start_worker_connects_signals(self, qtbot: QtBot) -> None:
        """start_worker must connect all required signals."""
        # Create controller-like object
        controller_emissions: dict[str, int] = {
            "thumbnail_ready": 0,
            "progress": 0,
            "error": 0,
        }

        class MockController(QObject):
            thumbnail_ready = Signal(int, object)
            progress = Signal(int, int)
            error = Signal(str)

            def __init__(self) -> None:
                super().__init__()
                self.worker: MockBatchThumbnailWorker | None = None
                self._thread: QThread | None = None

            def _on_thumbnail_ready(self, offset: int, qimage: object) -> None:
                controller_emissions["thumbnail_ready"] += 1
                self.thumbnail_ready.emit(offset, qimage)

            def start_worker(self, rom_path: str) -> None:
                self.worker = MockBatchThumbnailWorker(rom_path)

                # Simulate signal connections (from batch_thumbnail_worker.py:817-819)
                self.worker.thumbnail_ready.connect(self._on_thumbnail_ready)
                self.worker.progress.connect(self.progress.emit)
                self.worker.error.connect(self.error.emit)

        controller = MockController()
        controller.start_worker("test.sfc")

        # Manually emit from worker to test connections
        controller.worker.thumbnail_ready.emit(0x1000, None)
        controller.worker.progress.emit(1, 10)
        controller.worker.error.emit("test error")
        QCoreApplication.processEvents()

        assert controller_emissions["thumbnail_ready"] == 1
        # Progress and error go directly to controller signals

    def test_restart_worker_creates_fresh_connections(self, qtbot: QtBot) -> None:
        """Restarting worker should create new worker with new connections."""
        emissions: list[str] = []

        class MockWorkerController(QObject):
            def __init__(self) -> None:
                super().__init__()
                self.worker: MockBatchThumbnailWorker | None = None

            def _on_progress(self, completed: int, total: int) -> None:
                emissions.append(f"progress_{completed}")

            def start_worker(self, rom_path: str) -> None:
                # Clean up old worker if exists
                if self.worker:
                    self.worker.stop()
                    # Note: In real code, thread quit is called, worker deleted

                # Create new worker (simulates batch_thumbnail_worker.py:803-804)
                self.worker = MockBatchThumbnailWorker(rom_path)
                self.worker.progress.connect(self._on_progress)

            def stop_worker(self) -> None:
                if self.worker:
                    self.worker.stop()
                    self.worker = None

        controller = MockWorkerController()

        # First start
        controller.start_worker("test.sfc")
        controller.worker.progress.emit(1, 5)  # type: ignore[union-attr]
        QCoreApplication.processEvents()

        # Restart (creates new worker)
        controller.start_worker("test.sfc")
        controller.worker.progress.emit(2, 5)  # type: ignore[union-attr]
        QCoreApplication.processEvents()

        # Should have 2 emissions (one from each worker instance)
        assert emissions == ["progress_1", "progress_2"], f"Got: {emissions}"

    def test_worker_controller_lifecycle_signals(self, qtbot: QtBot) -> None:
        """Test proper signal lifecycle: started -> progress -> finished."""
        from PySide6.QtCore import QThread

        worker = MockBatchThumbnailWorker()
        thread = QThread()
        worker.moveToThread(thread)

        recorder = MultiSignalRecorder()
        recorder.connect_signal(worker.started, "started")
        recorder.connect_signal(worker.progress, "progress")
        recorder.connect_signal(worker.finished, "finished")

        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)

        with qtbot.waitSignal(worker.finished, timeout=worker_timeout()):
            thread.start()

        thread.wait()

        # Verify lifecycle order
        order = recorder.emission_order()
        assert order[0] == "started", f"First signal should be 'started', got: {order}"
        assert order[-1] == "finished", f"Last signal should be 'finished', got: {order}"
        recorder.assert_contains_sequence(["started", "progress", "finished"])


# =============================================================================
# Signal Connection Pattern Best Practices Tests
# =============================================================================


class TestSignalConnectionPatterns:
    """Test and document correct signal connection patterns."""

    def test_connection_with_type_prevents_race(self, qtbot: QtBot) -> None:
        """Using QueuedConnection type is safer for cross-thread signals."""
        worker = MockPooledWorker()
        emissions: list[int] = []

        def handler(request_id: int, *args: object) -> None:
            emissions.append(request_id)

        # Correct pattern: use QueuedConnection for worker signals
        worker.preview_ready.connect(handler, Qt.ConnectionType.QueuedConnection)

        worker._current_request_id = 42
        worker.start()
        QCoreApplication.processEvents()

        assert 42 in emissions

    def test_disconnect_before_reconnect_pattern(self, qtbot: QtBot) -> None:
        """Proper pattern: always disconnect before reconnecting."""

        class SignalHolder(QObject):
            test_signal = Signal(int)

        holder = SignalHolder()
        emissions: list[int] = []

        def handler(value: int) -> None:
            emissions.append(value)

        # First connection
        holder.test_signal.connect(handler)

        # Emit
        holder.test_signal.emit(1)
        QCoreApplication.processEvents()
        assert emissions == [1]

        # CORRECT PATTERN: Disconnect first, then reconnect
        try:
            holder.test_signal.disconnect(handler)
        except (TypeError, RuntimeError):
            pass  # Already disconnected

        holder.test_signal.connect(handler)

        # Emit again
        holder.test_signal.emit(2)
        QCoreApplication.processEvents()

        # Should have [1, 2], not [1, 2, 2]
        assert emissions == [1, 2], f"Expected [1, 2], got {emissions}"

    def test_blockSignals_during_cleanup(self, qtbot: QtBot) -> None:
        """blockSignals(True) during cleanup prevents unexpected emissions."""
        worker = MockPooledWorker()
        emissions: list[int] = []

        def handler(request_id: int, *args: object) -> None:
            emissions.append(request_id)

        worker.preview_ready.connect(handler, Qt.ConnectionType.QueuedConnection)

        # Simulate cleanup
        worker.blockSignals(True)

        # This emission should be blocked
        worker._current_request_id = 99
        worker.start()
        QCoreApplication.processEvents()

        assert 99 not in emissions, "Emissions should be blocked during cleanup"

        # Unblock and verify signals work again
        worker.blockSignals(False)
        worker._current_request_id = 100
        worker.start()
        QCoreApplication.processEvents()

        assert 100 in emissions, "Signals should work after unblocking"
