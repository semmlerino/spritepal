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
from PySide6.QtWidgets import QApplication, QDialog, QWidget

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

        # Force garbage collection
        gc.collect()

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

class WidgetFactory:
    """Factory for creating common Qt widgets with standard configurations."""

    @staticmethod
    def create_dialog(
        title: str = "Test Dialog",
        modal: bool = True,
        size: tuple[int, int] = (400, 300),
        parent: QWidget | None = None
    ) -> QDialog:
        """
        Create a dialog with standard configuration.

        Args:
            title: Dialog window title
            modal: Whether dialog is modal
            size: Dialog size (width, height)
            parent: Parent widget

        Returns:
            Configured dialog instance
        """
        dialog = QDialog(parent)
        dialog.setWindowTitle(title)
        dialog.setModal(modal)
        dialog.resize(*size)
        return dialog

    @staticmethod
    def create_widget_with_layout(
        widget_class: type[W],
        layout_class: type,
        parent: QWidget | None = None
    ) -> tuple[W, Any]:
        """
        Create a widget with a layout.

        Args:
            widget_class: Widget class to create
            layout_class: Layout class to apply
            parent: Parent widget

        Returns:
            Tuple of (widget, layout)
        """
        widget = widget_class(parent)
        layout = layout_class(widget)
        widget.setLayout(layout)
        return widget, layout

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

    @staticmethod
    @contextmanager
    def wait_for_signal(
        signal: Signal,
        timeout_ms: int = 1000
    ) -> Generator[list[Any], None, None]:
        """
        Context manager to wait for a signal to be emitted.

        Handles fast signals that emit before the event loop starts by tracking
        whether the signal was already received during the context body.

        Args:
            signal: Signal to wait for
            timeout_ms: Maximum wait time in milliseconds

        Yields:
            List to collect signal arguments

        Example:
            with EventLoopHelper.wait_for_signal(widget.clicked, 1000) as args:
                widget.click()
            assert len(args) > 0
        """
        loop = QEventLoop()
        args: list[Any] = []
        received = [False]  # List for closure mutation

        def on_signal(*signal_args: Any) -> None:
            args.extend(signal_args)
            received[0] = True
            if loop.isRunning():
                loop.quit()

        signal.connect(on_signal)

        # Setup timeout
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(timeout_ms)

        try:
            yield args
            # Only enter event loop if signal wasn't already received
            if not received[0]:
                loop.exec()
        finally:
            signal.disconnect(on_signal)
            timer.stop()

    @staticmethod
    def wait_until(
        condition: Callable[[], bool],
        timeout_ms: int = 1000,
        interval_ms: int = 10
    ) -> bool:
        """
        Wait until a condition becomes true.

        Args:
            condition: Callable that returns True when condition is met
            timeout_ms: Maximum wait time in milliseconds
            interval_ms: Check interval in milliseconds

        Returns:
            True if condition was met, False if timeout
        """
        from PySide6.QtTest import QTest

        elapsed = 0
        while elapsed < timeout_ms:
            if condition():
                return True
            QTest.qWait(interval_ms)
            elapsed += interval_ms
        return False

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
    def run_in_thread(
        func: Callable,
        *args,
        **kwargs
    ) -> Generator[QThread, None, None]:
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

class MemoryHelper:
    """Helper class for memory management in Qt tests."""

    @staticmethod
    def get_widget_count() -> int:
        """Get count of all QWidget instances."""
        return len([
            obj for obj in gc.get_objects()
            if isinstance(obj, QWidget)
        ])

    @staticmethod
    def get_object_count(obj_type: type) -> int:
        """Get count of objects of specific type."""
        return len([
            obj for obj in gc.get_objects()
            if isinstance(obj, obj_type)
        ])

    @staticmethod
    @contextmanager
    def assert_no_leak(
        obj_type: type,
        max_increase: int = 0
    ) -> Generator[None, None, None]:
        """
        Context manager to assert no memory leak of specific object type.

        Args:
            obj_type: Object type to monitor
            max_increase: Maximum allowed increase in object count

        Example:
            with MemoryHelper.assert_no_leak(QWidget):
                widget = QWidget()
                widget.deleteLater()
        """
        gc.collect()
        initial_count = MemoryHelper.get_object_count(obj_type)

        try:
            yield
        finally:
            # Process events to allow deleteLater to take effect
            QApplication.processEvents()
            gc.collect()

            final_count = MemoryHelper.get_object_count(obj_type)
            increase = final_count - initial_count

            assert increase <= max_increase, (
                f"Memory leak detected: {increase} {obj_type.__name__} "
                f"objects leaked (max allowed: {max_increase})"
            )

# Widget pool for performance optimization
class WidgetPool:
    """Pool of reusable widgets for test performance optimization."""

    def __init__(self, widget_class: type[W], pool_size: int = 5):
        """
        Initialize widget pool.

        Args:
            widget_class: Class of widgets to pool
            pool_size: Maximum pool size
        """
        self.widget_class = widget_class
        self.pool_size = pool_size
        self._available: list[W] = []
        self._in_use: set[W] = set()

    def acquire(self, *args, **kwargs) -> W:
        """
        Acquire a widget from the pool.

        Args:
            *args: Arguments for widget creation if pool is empty
            **kwargs: Keyword arguments for widget creation

        Returns:
            Widget instance
        """
        if self._available:
            widget = self._available.pop()
        else:
            widget = self.widget_class(*args, **kwargs)

        self._in_use.add(widget)
        return widget

    def release(self, widget: W):
        """
        Release a widget back to the pool.

        Args:
            widget: Widget to release
        """
        if widget not in self._in_use:
            return

        self._in_use.remove(widget)

        # Reset widget state
        widget.hide()
        widget.setParent(None)

        # Add back to pool if not at capacity
        if len(self._available) < self.pool_size:
            self._available.append(widget)
        else:
            widget.deleteLater()

    def clear(self):
        """Clear the pool and delete all widgets."""
        for widget in self._available:
            widget.deleteLater()
        for widget in self._in_use:
            widget.deleteLater()
        self._available.clear()
        self._in_use.clear()
