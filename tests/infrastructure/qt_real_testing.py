"""
Real Qt Testing Framework - Base Patterns

This module provides base patterns for testing with real Qt components,
eliminating the need for excessive mocking and reducing memory overhead.

Key Features:
- Real QApplication management for tests
- Offscreen platform configuration for headless testing
- Widget factory methods for common components
- Automatic cleanup and resource management
- Thread safety helpers for concurrent testing
- Event loop management for async operations
"""

from __future__ import annotations

import gc
import os
import sys
import weakref
from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import Any, TypeVar, cast

from PySide6.QtCore import (
    QCoreApplication,
    QEventLoop,
    QObject,
    QThread,
    QTimer,
    Signal,
)
from PySide6.QtWidgets import QApplication, QWidget

# Re-export MemoryHelper from memory_helpers for backwards compatibility
from tests.fixtures.memory_helpers import MemoryHelper

__all__ = ["MemoryHelper", "QtTestCase", "EventLoopHelper", "ThreadSafetyHelper"]

# Type variable for generic widget types
W = TypeVar("W", bound=QWidget)


class QtTestCase:
    """
    Base class for Qt tests with real components.

    Provides QApplication management, widget lifecycle, and cleanup.
    """

    @classmethod
    def setup_class(cls):
        """Setup QApplication for test class."""
        cls.app = cls._ensure_qapplication()

    @classmethod
    def teardown_class(cls):
        """Cleanup QApplication after test class."""
        # Process remaining events
        if cls.app:
            cls.app.processEvents()
            # Don't quit the app as it might be shared

    @staticmethod
    def _ensure_qapplication() -> QApplication:
        """
        Ensure QApplication exists for testing.

        Returns:
            QApplication instance (existing or newly created)
        """
        app = QApplication.instance()
        if app is None:
            # Set offscreen platform for headless testing
            if not os.environ.get("DISPLAY") or os.environ.get("CI"):
                os.environ["QT_QPA_PLATFORM"] = "offscreen"
            app = QApplication(sys.argv)
        return cast(QApplication, app)

    def setup_method(self):
        """Setup before each test method."""
        self.widgets: list[weakref.ref[QWidget]] = []
        self.timers: list[QTimer] = []
        self.threads: list[QThread] = []

    def teardown_method(self):
        """Cleanup after each test method."""
        # Stop all timers
        for timer in self.timers:
            if timer and timer.isActive():
                timer.stop()

        # Stop all threads
        for thread in self.threads:
            if thread and thread.isRunning():
                thread.quit()
                if not thread.wait(1000):  # Wait max 1 second
                    thread.terminate()
                    thread.wait()

        # Close and delete widgets
        for widget_ref in self.widgets:
            widget = widget_ref()
            if widget:
                try:
                    widget.close()
                    widget.deleteLater()
                except RuntimeError:
                    # Widget already deleted
                    pass

        # Process events to ensure deleteLater takes effect
        QApplication.processEvents()

        # Skip explicit gc.collect() during cleanup
        # Reason: gc.collect() can trigger finalization of PySide6/Qt objects
        # while background threads are still running, which causes segfaults.
        # Qt object cleanup is handled via deleteLater() and processEvents() above.

        # Clear references
        self.widgets.clear()
        self.timers.clear()
        self.threads.clear()

    def create_widget(self, widget_class: type[W], *args, **kwargs) -> W:
        """
        Create a widget and track it for cleanup.

        Args:
            widget_class: Widget class to instantiate
            *args: Positional arguments for widget constructor
            **kwargs: Keyword arguments for widget constructor

        Returns:
            Created widget instance
        """
        widget = widget_class(*args, **kwargs)
        self.widgets.append(weakref.ref(widget))
        return widget

    def create_timer(self, interval: int = 0, single_shot: bool = False) -> QTimer:
        """
        Create a timer and track it for cleanup.

        Args:
            interval: Timer interval in milliseconds
            single_shot: Whether timer fires only once

        Returns:
            Created timer instance
        """
        timer = QTimer()
        timer.setInterval(interval)
        timer.setSingleShot(single_shot)
        self.timers.append(timer)
        return timer

    def create_thread(self) -> QThread:
        """
        Create a thread and track it for cleanup.

        Returns:
            Created thread instance
        """
        thread = QThread()
        self.threads.append(thread)
        return thread


class EventLoopHelper:
    """Helper class for managing Qt event loops in tests."""

    @staticmethod
    def process_events(duration_ms: int = 0, max_iterations: int = 100) -> None:
        """
        Process Qt events for a specified duration.

        Args:
            duration_ms: Duration in milliseconds (0 = process pending only)
            max_iterations: Maximum iterations to prevent infinite loops
        """
        app = QApplication.instance()
        if not app:
            return

        if duration_ms == 0:
            # Process all pending events
            for _ in range(max_iterations):
                if not app.hasPendingEvents():
                    break
                app.processEvents()
        else:
            # Process events for specified duration using Qt-safe waiting
            # Uses processEvents with WaitForMoreEvents to wait for events without
            # time.sleep(), which violates Qt threading rules per CLAUDE.md
            from PySide6.QtCore import QElapsedTimer, QEventLoop

            timer = QElapsedTimer()
            timer.start()
            while timer.elapsed() < duration_ms:
                remaining = duration_ms - timer.elapsed()
                if remaining <= 0:
                    break
                # Process events, waiting up to 10ms for new ones if none pending
                wait_time = min(10, int(remaining))
                app.processEvents(QEventLoop.AllEvents | QEventLoop.WaitForMoreEvents, wait_time)


class ThreadSafetyHelper:
    """Helper class for thread-safe Qt testing."""

    @staticmethod
    def assert_main_thread():
        """Assert that code is running in the main thread."""
        current_thread = QThread.currentThread()
        main_thread = QCoreApplication.instance().thread() if QCoreApplication.instance() else None
        assert current_thread == main_thread, "Code must run in main thread"

    @staticmethod
    def assert_worker_thread():
        """Assert that code is running in a worker thread."""
        current_thread = QThread.currentThread()
        main_thread = QCoreApplication.instance().thread() if QCoreApplication.instance() else None
        assert current_thread != main_thread, "Code must run in worker thread"

    @staticmethod
    @contextmanager
    def run_in_thread(func: Callable, *args, **kwargs) -> Generator[QThread, None, None]:
        """
        Run a function in a separate thread.

        Args:
            func: Function to run in thread
            *args: Positional arguments for function
            **kwargs: Keyword arguments for function

        Yields:
            Thread instance
        """

        class Worker(QObject):
            finished = Signal()
            error = Signal(Exception)
            result = Signal(object)

            def __init__(self, func, args, kwargs):
                super().__init__()
                self.func = func
                self.args = args
                self.kwargs = kwargs
                self._result = None
                self._error = None

            def run(self):
                try:
                    self._result = self.func(*self.args, **self.kwargs)
                    self.result.emit(self._result)
                except Exception as e:
                    self._error = e
                    self.error.emit(e)
                finally:
                    self.finished.emit()

        thread = QThread()
        worker = Worker(func, args, kwargs)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        thread.start()

        try:
            yield thread
        finally:
            if thread.isRunning():
                thread.quit()
                thread.wait(1000)
                if thread.isRunning():
                    thread.terminate()
                    thread.wait()
