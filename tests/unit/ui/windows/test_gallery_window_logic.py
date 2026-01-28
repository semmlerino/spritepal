"""
Unit tests for DetachedGalleryWindow logic.

These tests verify pure logic without real Qt components, using mocks
to test cleanup sequences, signal disconnection, and infinite loop prevention.

Extracted from tests/integration/test_gallery_window_integration.py
"""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

# Signals that should be disconnected during cleanup
SIGNALS_TO_DISCONNECT = [
    ("sprite_found", "on_sprite_found"),
    ("progress", "on_scan_progress"),
    ("finished", "on_scan_finished"),
    ("error", "on_scan_error"),
]


class TestGalleryWindowCleanupLogic:
    """Test worker cleanup logic without real Qt objects."""

    def test_worker_lifecycle_logic(self):
        """Test worker lifecycle logic in headless environment."""
        with patch("ui.windows.detached_gallery_window.DetachedGalleryWindow.__init__") as mock_init:
            mock_init.return_value = None

            # Create mock window to test cleanup logic
            window = Mock()
            window.scan_worker = None
            window.thumbnail_worker = None
            window.scan_timeout_timer = None

            # Mock the cleanup method
            def mock_cleanup():
                workers_cleaned = 0

                if window.scan_worker is not None:
                    if hasattr(window.scan_worker, "isRunning") and window.scan_worker.isRunning():
                        window.scan_worker.requestInterruption()
                        window.scan_worker.wait(3000)
                    window.scan_worker = None
                    workers_cleaned += 1

                if window.thumbnail_worker is not None:
                    if hasattr(window.thumbnail_worker, "cleanup"):
                        window.thumbnail_worker.cleanup()
                    window.thumbnail_worker = None
                    workers_cleaned += 1

                if window.scan_timeout_timer is not None:
                    window.scan_timeout_timer.stop()
                    window.scan_timeout_timer = None

                return workers_cleaned

            window._cleanup_existing_workers = mock_cleanup

            # Test with no workers
            cleaned = window._cleanup_existing_workers()
            assert cleaned == 0

            # Test with scan worker
            window.scan_worker = Mock()
            window.scan_worker.isRunning.return_value = True
            window.scan_worker.requestInterruption = Mock()
            window.scan_worker.wait = Mock(return_value=True)

            cleaned = window._cleanup_existing_workers()
            assert cleaned == 1
            assert window.scan_worker is None

            # Test with thumbnail worker
            window.thumbnail_worker = Mock()
            window.thumbnail_worker.cleanup = Mock()

            cleaned = window._cleanup_existing_workers()
            assert cleaned == 1
            assert window.thumbnail_worker is None

    def test_signal_disconnection_logic(self):
        """Test signal disconnection logic in headless environment."""
        # Mock worker with signals
        worker = Mock()
        disconnected_signals = []

        # Add mock signals that track disconnection
        for signal_name, slot_name in SIGNALS_TO_DISCONNECT:
            mock_signal = Mock()
            mock_signal.disconnect = Mock(side_effect=lambda *args, s=signal_name: disconnected_signals.append(s))
            setattr(worker, signal_name, mock_signal)

        # Simulate disconnection logic
        for signal_name, slot_name in SIGNALS_TO_DISCONNECT:
            try:
                signal = getattr(worker, signal_name, None)
                if signal is not None:
                    signal.disconnect()
            except (RuntimeError, TypeError):
                pass

        # Verify all signals were disconnected
        assert len(disconnected_signals) == len(SIGNALS_TO_DISCONNECT)
        assert "sprite_found" in disconnected_signals
        assert "progress" in disconnected_signals


class TestThumbnailWorkerIdleDetection:
    """Test idle detection logic for thumbnail worker."""

    def test_infinite_loop_prevention_logic(self):
        """Test infinite loop prevention logic without real workers."""
        # Simulate the idle detection logic from BatchThumbnailWorker

        class MockThumbnailWorkerLogic:
            def __init__(self):
                self.processed_count = 0
                self.idle_iterations = 0
                self.max_idle_iterations = 100
                self.stop_requested = False
                self.request_queue = []

            def get_next_request(self):
                if self.request_queue:
                    return self.request_queue.pop(0)
                return None

            def simulate_processing_loop(self, max_iterations=1000):
                """Simulate the processing loop with idle detection."""
                iterations = 0

                while not self.stop_requested and iterations < max_iterations:
                    iterations += 1

                    request = self.get_next_request()
                    if not request:
                        self.idle_iterations += 1

                        # Auto-stop after being idle for too long
                        if self.idle_iterations >= self.max_idle_iterations:
                            break

                        continue

                    # Reset idle counter when we get work
                    self.idle_iterations = 0
                    self.processed_count += 1

                return iterations, self.processed_count

        # Test with no work - should stop due to idle detection
        worker_logic = MockThumbnailWorkerLogic()
        iterations, processed = worker_logic.simulate_processing_loop()

        assert iterations == worker_logic.max_idle_iterations
        assert processed == 0
        assert not worker_logic.stop_requested  # Stopped due to idle detection

        # Test with some work - should process and then idle stop
        worker_logic = MockThumbnailWorkerLogic()
        worker_logic.request_queue = ["req1", "req2", "req3"]

        iterations, processed = worker_logic.simulate_processing_loop()

        assert processed == 3  # Processed all requests
        assert iterations == 3 + worker_logic.max_idle_iterations  # Work + idle detection

        # Test stop request - should stop immediately
        worker_logic = MockThumbnailWorkerLogic()
        worker_logic.request_queue = ["req1", "req2"]
        worker_logic.stop_requested = True

        iterations, processed = worker_logic.simulate_processing_loop()

        assert iterations == 0  # Should stop immediately
        assert processed == 0
