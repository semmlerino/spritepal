"""
Test suite for real-world Qt threading patterns used in SpritePal.

This suite documents and validates SpritePal-specific threading patterns:
1. Safe GUI updates from worker threads
2. Concurrent operations with proper synchronization
"""

from __future__ import annotations

import time

import pytest
from PySide6.QtCore import QMutex, QMutexLocker, QObject, QThread, Signal
from PySide6.QtWidgets import QApplication

pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("session_app_context"),
    pytest.mark.shared_state_safe,
    pytest.mark.skip_thread_cleanup(reason="Thread tests may intentionally leave threads running"),
    pytest.mark.headless,
    pytest.mark.slow,
]


class TestRealWorldScenarios:
    """Test real-world threading scenarios"""

    @pytest.fixture
    def app(self):
        """Ensure QApplication exists"""
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield app

    def test_gui_update_from_worker(self, app):
        """Test safe GUI updates from worker thread"""

        class GUIUpdater(QObject):
            update_gui = Signal(str)

            def __init__(self):
                super().__init__()
                self.gui_updates = []
                self.update_threads = []

                # Connect signal to slot
                self.update_gui.connect(self._on_update_gui)

            def _on_update_gui(self, text):
                # This should always run in main thread
                self.gui_updates.append(text)
                self.update_threads.append(QThread.currentThread())

        class Worker(QThread):
            def __init__(self, updater):
                super().__init__()
                self.updater = updater

            def run(self):
                # Emit updates from worker thread
                for i in range(3):
                    self.updater.update_gui.emit(f"Update {i}")
                    time.sleep(0.01)  # sleep-ok: thread interleaving

        # Create updater and worker
        updater = GUIUpdater()
        worker = Worker(updater)

        # Get main thread reference
        main_thread = QThread.currentThread()

        # Run worker
        worker.start()
        worker.wait(1000)

        # Process events
        app.processEvents()

        # Verify all updates received in main thread
        assert len(updater.gui_updates) == 3
        for thread in updater.update_threads:
            assert thread == main_thread

    def test_concurrent_operations(self, app):
        """Test concurrent operations with proper synchronization"""

        class DataProcessor(QObject):
            processing_done = Signal(int, list)

            def __init__(self):
                super().__init__()
                self.mutex = QMutex()
                self.processed_data = {}

            def process_chunk(self, chunk_id, data):
                # Simulate processing
                result = [x * 2 for x in data]
                time.sleep(0.01)  # sleep-ok: thread interleaving

                # Store result thread-safely
                with QMutexLocker(self.mutex):
                    self.processed_data[chunk_id] = result

                # Emit completion
                self.processing_done.emit(chunk_id, result)

        # Create processor
        processor = DataProcessor()

        class ChunkWorker(QThread):
            def __init__(self, chunk_id: int, data: list[int]):
                super().__init__()
                self.chunk_id = chunk_id
                self.data = data

            def run(self):
                processor.process_chunk(self.chunk_id, self.data)

        # Create multiple worker threads
        threads = []
        chunks = {0: [1, 2, 3], 1: [4, 5, 6], 2: [7, 8, 9]}

        for chunk_id, data in chunks.items():
            # Process chunk when thread starts
            worker = ChunkWorker(chunk_id, data)
            threads.append(worker)
            worker.start()

        # Wait for all threads
        for thread in threads:
            assert thread.wait(1000)

        # Process queued signals from worker threads
        QApplication.processEvents()

        # Verify all chunks processed correctly
        assert len(processor.processed_data) == 3
        assert processor.processed_data[0] == [2, 4, 6]
        assert processor.processed_data[1] == [8, 10, 12]
        assert processor.processed_data[2] == [14, 16, 18]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
