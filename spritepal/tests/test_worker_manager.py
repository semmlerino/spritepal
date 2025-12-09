"""
Test the WorkerManager utility class.

NOTE: Cleanup-related tests have been removed due to Qt threading segfault issues.
Only basic worker start functionality is tested here.
"""

import pytest
from PySide6.QtCore import QThread, Signal

from ui.common import WorkerManager
from ui.common.timing_constants import (
    SLEEP_MEDIUM,
    TEST_TIMEOUT_MEDIUM,
)

# Test characteristics: Real GUI components requiring display, Thread safety concerns
pytestmark = [
    pytest.mark.gui,
    pytest.mark.qt_app,
    pytest.mark.qt_real,
    pytest.mark.rom_data,
    pytest.mark.serial,
    pytest.mark.slow,
    pytest.mark.worker_threads,
    pytest.mark.requires_display,
    pytest.mark.signals_slots,
]

class DummyWorker(QThread):
    """Simple test worker that can be controlled"""

    finished_work = Signal()

    def __init__(self):
        super().__init__()
        self.should_run = True
        self.work_done = False

    def run(self):
        """Simple work simulation"""
        # Simulate some work
        self.msleep(int(SLEEP_MEDIUM * 1000))  # Sleep for 50ms
        if self.should_run:
            self.work_done = True
            self.finished_work.emit()

    def stop(self):
        """Stop the worker"""
        self.should_run = False
        self.quit()

class TestWorkerManager:
    """Test WorkerManager functionality - basic start tests only"""

    def test_start_worker(self, qtbot):
        """Test starting a worker"""
        worker = DummyWorker()

        # Start worker
        WorkerManager.start_worker(worker)

        # Worker should be running
        qtbot.waitUntil(worker.isRunning, timeout=TEST_TIMEOUT_MEDIUM)
        assert worker.isRunning()

        # Cleanup
        worker.stop()
        qtbot.waitUntil(lambda: not worker.isRunning(), timeout=TEST_TIMEOUT_MEDIUM)

    def test_create_and_start(self, qtbot):
        """Test create_and_start helper"""
        # Create and start in one call
        worker = WorkerManager.create_and_start(DummyWorker)

        # Worker should be running
        qtbot.waitUntil(worker.isRunning, timeout=TEST_TIMEOUT_MEDIUM)
        assert worker.isRunning()
        assert isinstance(worker, DummyWorker)

        # Cleanup
        worker.stop()
        qtbot.waitUntil(lambda: not worker.isRunning(), timeout=TEST_TIMEOUT_MEDIUM)
