"""
Mock Window Infrastructure for Testing

This module provides mock implementations of MainWindow and other windows
to prevent heavy component creation during tests.

Following Qt Testing Best Practices:
- Pattern 1: Real components with mocked dependencies
- Lightweight mocks with real Qt signals
- No heavy initialization or resource loading
"""
from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any
from unittest.mock import Mock

from .mock_dialogs_base import CallbackSignal


class MockMainWindowImpl:
    """
    Pure Python test MainWindow that provides callback-based signals without Qt dependencies.

    Avoids QMainWindow inheritance to prevent metaclass conflicts and crashes.
    For integration tests that require real Qt, use RealMainWindow instead.
    """

    def __init__(self, parent: Any | None = None):
        self.parent_widget = parent

        # Callback-based signals
        self.extraction_started_callbacks: list[Callable[[], None]] = []
        self.extraction_completed_callbacks: list[Callable[[], None]] = []
        self.extraction_error_callbacks: list[Callable[[str], None]] = []
        self.injection_started_callbacks: list[Callable[[], None]] = []
        self.injection_completed_callbacks: list[Callable[[], None]] = []
        self.file_opened_callbacks: list[Callable[[str], None]] = []
        self.window_closing_callbacks: list[Callable[[], None]] = []

        # Remove super().__init__(parent) call

        # Lazy controller initialization (not created until accessed)
        self._controller = None

        # Mock UI components
        self.extraction_panel = Mock()
        self.extraction_panel.get_extraction_params.return_value = {
            'vram_path': '/test/vram.dmp',
            'cgram_path': '/test/cgram.dmp',
            'oam_path': '/test/oam.dmp'
        }

        self.injection_panel = Mock()
        self.status_bar = Mock()
        self.menu_bar = Mock()

        # Mock managers
        self.extraction_manager = Mock()
        self.injection_manager = Mock()
        self.session_manager = Mock()

        # Mock state
        self.current_file = None
        self.is_modified = False

        # Set window properties
        self.setWindowTitle("MockMainWindow")

    @property
    def controller(self):
        """Lazy controller access - creates controller on first access."""
        if self._controller is None:
            self._controller = Mock()
            self._controller.extract_sprites = Mock()
            self._controller.inject_sprites = Mock()
        return self._controller

    def get_extraction_params(self):
        """Get extraction parameters from UI."""
        return self.extraction_panel.get_extraction_params()

    def show_error(self, message: str):
        """Show error message."""
        for callback in self.extraction_error_callbacks:
            with contextlib.suppress(Exception):
                callback(message)

    def update_status(self, message: str):
        """Update status bar."""
        self.status_bar.showMessage(message)

    def extraction_complete(self, extracted_files):
        """Handle extraction completion."""
        for callback in self.extraction_completed_callbacks:
            with contextlib.suppress(Exception):
                callback()

    def injection_complete(self, success: bool):
        """Handle injection completion."""
        for callback in self.injection_completed_callbacks:
            with contextlib.suppress(Exception):
                callback()

    def closeEvent(self, event):
        """Handle close event."""
        for callback in self.window_closing_callbacks:
            with contextlib.suppress(Exception):
                callback()
        # No super().closeEvent(event) since we don't inherit from QWidget

    # Signal-like properties for compatibility
    @property
    def extraction_started(self):
        """Extraction started signal interface."""
        return CallbackSignal(self.extraction_started_callbacks)

    @property
    def extraction_completed(self):
        """Extraction completed signal interface."""
        return CallbackSignal(self.extraction_completed_callbacks)

    @property
    def extraction_error(self):
        """Extraction error signal interface."""
        return CallbackSignal(self.extraction_error_callbacks)

    @property
    def injection_started(self):
        """Injection started signal interface."""
        return CallbackSignal(self.injection_started_callbacks)

    @property
    def injection_completed(self):
        """Injection completed signal interface."""
        return CallbackSignal(self.injection_completed_callbacks)

    @property
    def file_opened(self):
        """File opened signal interface."""
        return CallbackSignal(self.file_opened_callbacks)

    @property
    def window_closing(self):
        """Window closing signal interface."""
        return CallbackSignal(self.window_closing_callbacks)

class MockWorkerBase:
    """
    Pure Python test worker that provides callback-based signals without Qt dependencies.

    This avoids QThread inheritance to prevent metaclass conflicts and thread cleanup issues.
    """

    def __init__(self, parent: Any | None = None):
        self.parent_widget = parent

        # Callback-based signals
        self.started_callbacks: list[Callable[[], None]] = []
        self.finished_callbacks: list[Callable[[], None]] = []
        self.progress_callbacks: list[Callable[[int, str], None]] = []
        self.error_callbacks: list[Callable[[str, object], None]] = []
        self.warning_callbacks: list[Callable[[str], None]] = []
        self.is_cancelled = False
        self.is_paused = False
        self._is_running = False

    def start(self):
        """Mock start that doesn't actually create a thread."""
        self._is_running = True
        # Emit started signal
        for callback in self.started_callbacks:
            with contextlib.suppress(Exception):
                callback()
        # Simulate immediate completion for tests
        self.run()
        self._is_running = False
        # Emit finished signal
        for callback in self.finished_callbacks:
            with contextlib.suppress(Exception):
                callback()

    def run(self):
        """Mock run method - override in subclasses."""
        pass

    def quit(self):
        """Mock quit method."""
        self._is_running = False

    def wait(self, msecs: int = -1) -> bool:
        """Mock wait method."""
        return True

    def isRunning(self) -> bool:
        """Check if worker is running."""
        return self._is_running

    def cancel(self):
        """Cancel the worker."""
        self.is_cancelled = True
        self.quit()

    def pause(self):
        """Pause the worker."""
        self.is_paused = True

    def resume(self):
        """Resume the worker."""
        self.is_paused = False

    # Signal-like properties for compatibility
    @property
    def started(self):
        """Started signal interface."""
        return CallbackSignal(self.started_callbacks)

    @property
    def finished(self):
        """Finished signal interface."""
        return CallbackSignal(self.finished_callbacks)

    @property
    def progress(self):
        """Progress signal interface."""
        return CallbackSignal(self.progress_callbacks)

    @property
    def error(self):
        """Error signal interface."""
        return CallbackSignal(self.error_callbacks)

    @property
    def warning(self):
        """Warning signal interface."""
        return CallbackSignal(self.warning_callbacks)

class MockExtractionWorkerImpl(MockWorkerBase):
    """Test extraction worker for testing."""

    def __init__(self, params: dict, parent: Any | None = None):
        super().__init__(parent)
        self.extraction_completed_callbacks: list[Callable[[dict], None]] = []
        self.params = params
        self.result = {'sprites': [], 'metadata': {}}

    def run(self):
        """Mock extraction operation."""
        # Emit progress
        for callback in self.progress_callbacks:
            with contextlib.suppress(Exception):
                callback(50, "Extracting sprites...")
        # Emit completion with mock result
        for callback in self.extraction_completed_callbacks:
            with contextlib.suppress(Exception):
                callback(self.result)

    @property
    def extraction_completed(self):
        """Extraction completed signal interface."""
        return CallbackSignal(self.extraction_completed_callbacks)

class MockInjectionWorkerImpl(MockWorkerBase):
    """Test injection worker for testing."""

    def __init__(self, params: dict, parent: Any | None = None):
        super().__init__(parent)
        self.injection_completed_callbacks: list[Callable[[bool], None]] = []
        self.params = params

    def run(self):
        """Mock injection operation."""
        # Emit progress
        for callback in self.progress_callbacks:
            with contextlib.suppress(Exception):
                callback(50, "Injecting sprites...")
        # Emit completion
        for callback in self.injection_completed_callbacks:
            with contextlib.suppress(Exception):
                callback(True)

    @property
    def injection_completed(self):
        """Injection completed signal interface."""
        return CallbackSignal(self.injection_completed_callbacks)

class MockWorkerManager:
    """
    Mock WorkerManager that tracks workers without actual thread management.

    This prevents thread cleanup issues during tests.
    """

    def __init__(self):
        self.workers = []
        self.active_workers = []

    def add_worker(self, worker):
        """Add a worker to track."""
        self.workers.append(worker)
        if hasattr(worker, '_is_running') and worker._is_running:
            self.active_workers.append(worker)

    def remove_worker(self, worker):
        """Remove a worker from tracking."""
        if worker in self.workers:
            self.workers.remove(worker)
        if worker in self.active_workers:
            self.active_workers.remove(worker)

    def cleanup_all(self):
        """Clean up all workers."""
        for worker in self.workers[:]:
            if hasattr(worker, 'cancel'):
                worker.cancel()
            if hasattr(worker, 'wait'):
                worker.wait(100)
        self.workers.clear()
        self.active_workers.clear()

    @classmethod
    def cleanup_all_workers(cls):
        """Class method for global cleanup."""
        pass  # Mock implementation

def create_test_main_window() -> MockMainWindowImpl:
    """
    Factory function to create a properly configured TestMainWindow.

    Returns:
        TestMainWindow instance ready for testing
    """
    window = MockMainWindowImpl()

    # Set up any additional mocking needed
    window.extraction_manager = Mock()
    window.extraction_manager.extract_sprites = Mock(return_value={'sprites': []})

    window.injection_manager = Mock()
    window.injection_manager.inject_sprites = Mock(return_value=True)

    return window

def patch_main_window_creation(monkeypatch):
    """
    Patch MainWindow creation to use TestMainWindow.

    Args:
        monkeypatch: pytest monkeypatch fixture
    """
    monkeypatch.setattr('ui.main_window.MainWindow', MockMainWindowImpl)

    # Also patch any direct imports
    import sys
    if 'ui.main_window' in sys.modules:
        sys.modules['ui.main_window'].MainWindow = MockMainWindowImpl

# Backward compatibility aliases
MockMainWindow = MockMainWindowImpl
MockExtractionWorker = MockExtractionWorkerImpl
MockInjectionWorker = MockInjectionWorkerImpl
create_mock_main_window = create_test_main_window
