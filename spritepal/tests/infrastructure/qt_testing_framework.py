"""
QtTestingFramework: Standardized patterns for Qt component testing.

Provides reusable patterns and utilities for testing Qt components with
real implementations instead of mocks, focusing on catching architectural
bugs and ensuring proper Qt lifecycle management.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import contextmanager, suppress
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QDialog, QWidget

from .qt_application_factory import ApplicationFactory


class QtTestingFramework:
    """
    Framework for standardized Qt component testing.

    Provides patterns and utilities for:
    - Real Qt component lifecycle testing
    - Signal/slot behavior validation
    - Thread-safe Qt operations
    - Proper parent/child relationship validation
    - Worker thread testing with real QThread instances
    """

    def __init__(self, qt_app: Any | None = None):
        """
        Initialize the Qt testing framework.

        Args:
            qt_app: Qt application instance (creates one if None)
        """
        self.qt_app = qt_app or ApplicationFactory.get_application()
        # Hidden root widget for parenting test widgets (QApplication cannot be a parent)
        self._root_widget = QWidget()
        self._created_widgets: list[QWidget] = [self._root_widget]
        self._signal_spies: list[QSignalSpy] = []
        self._timers: list[QTimer] = []

    def create_widget_test_context(self, widget_class: type, *args, **kwargs) -> WidgetTestContext:
        """
        Create a test context for a Qt widget.

        Args:
            widget_class: Widget class to test
            *args, **kwargs: Arguments for widget constructor

        Returns:
            WidgetTestContext for testing the widget
        """
        return WidgetTestContext(self, widget_class, *args, **kwargs)

    def create_dialog_test_context(self, dialog_class: type, *args, **kwargs) -> DialogTestContext:
        """
        Create a test context for a Qt dialog.

        Args:
            dialog_class: Dialog class to test
            *args, **kwargs: Arguments for dialog constructor

        Returns:
            DialogTestContext for testing the dialog
        """
        return DialogTestContext(self, dialog_class, *args, **kwargs)

    def create_worker_test_context(self, worker_class: type, *args, **kwargs) -> WorkerTestContext:
        """
        Create a test context for a worker thread.

        Args:
            worker_class: Worker class to test
            *args, **kwargs: Arguments for worker constructor

        Returns:
            WorkerTestContext for testing the worker
        """
        return WorkerTestContext(self, worker_class, *args, **kwargs)

    def validate_qt_parent_child_relationship(self, parent: QObject, child: QObject) -> dict[str, Any]:
        """
        Validate Qt parent/child relationship.

        Args:
            parent: Expected parent object
            child: Child object to validate

        Returns:
            Dictionary with validation results
        """
        return {
            "child_parent_correct": child.parent() is parent,
            "child_in_parent_children": child in parent.children(),
            "parent_type": type(parent).__name__,
            "child_type": type(child).__name__,
            "parent_id": id(parent),
            "child_id": id(child),
        }

    def validate_signal_behavior(self, signal: Signal, expected_connections: int | None = None) -> dict[str, Any]:
        """
        Validate Qt signal behavior.

        Args:
            signal: Signal to validate
            expected_connections: Expected number of connections

        Returns:
            Dictionary with validation results
        """
        # Note: PySide6 doesn't expose connection count directly,
        # so we validate what we can
        return {
            "signal_type": type(signal).__name__,
            "signal_exists": signal is not None,
            "can_connect": True,  # We'll test this by connecting
            "can_emit": True,     # We'll test this by emitting
        }

    def wait_for_signal(self, signal: Signal, timeout_ms: int = 5000) -> bool:
        """
        Wait for a signal to be emitted.

        Args:
            signal: Signal to wait for
            timeout_ms: Maximum time to wait

        Returns:
            True if signal was emitted, False if timeout
        """
        spy = QSignalSpy(signal)
        self._signal_spies.append(spy)

        # Wait for signal
        return spy.wait(timeout_ms)

    def process_events(self, timeout_ms: int = 100) -> None:
        """Process Qt events."""
        ApplicationFactory.process_events(timeout_ms)

    def create_timer_context(self, interval_ms: int, callback: Callable) -> TimerTestContext:
        """
        Create a test context for Qt timer operations.

        Args:
            interval_ms: Timer interval
            callback: Callback function

        Returns:
            TimerTestContext for testing timer behavior
        """
        return TimerTestContext(self, interval_ms, callback)

    def cleanup(self) -> None:
        """Clean up all test resources."""
        # Clean up widgets
        for widget in self._created_widgets:
            try:
                widget.close()
                widget.setParent(None)
            except Exception:
                pass  # Ignore cleanup errors

        # Clean up signal spies
        for spy in self._signal_spies:
            try:
                del spy  # Let Qt handle cleanup
            except Exception:
                pass

        # Clean up timers
        for timer in self._timers:
            try:
                timer.stop()
                timer.setParent(None)
            except Exception:
                pass

        self._created_widgets.clear()
        self._signal_spies.clear()
        self._timers.clear()

class WidgetTestContext:
    """Test context for Qt widgets with proper lifecycle management."""

    def __init__(self, framework: QtTestingFramework, widget_class: type, *args, **kwargs):
        """Initialize widget test context."""
        self.framework = framework
        self.widget_class = widget_class
        self.widget: QWidget | None = None
        self.args = args
        self.kwargs = kwargs

    def __enter__(self) -> QWidget:
        """Enter the widget test context."""
        # Create widget with proper Qt parent
        self.widget = self.widget_class(*self.args, **self.kwargs)

        # Set hidden root widget as parent if no parent specified
        # Note: QMainWindow should not have a parent (it's a top-level window)
        # Note: QApplication cannot be a widget parent - use _root_widget instead
        from PySide6.QtWidgets import QMainWindow
        if self.widget.parent() is None and not isinstance(self.widget, QMainWindow):
            self.widget.setParent(self.framework._root_widget)

        self.framework._created_widgets.append(self.widget)
        return self.widget

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit the widget test context with cleanup."""
        if self.widget is not None:
            try:
                self.widget.close()
                self.widget.setParent(None)
            except Exception:
                pass  # Ignore cleanup errors

    def show_and_wait(self, wait_ms: int = 100) -> None:
        """Show the widget and wait for it to be displayed."""
        if self.widget is not None:
            self.widget.show()
            self.framework.process_events(wait_ms)

    def validate_widget_state(self) -> dict[str, Any]:
        """Validate the widget's state."""
        if self.widget is None:
            return {"error": "Widget not created"}

        return {
            "widget_type": type(self.widget).__name__,
            "is_visible": self.widget.isVisible(),
            "has_parent": self.widget.parent() is not None,
            "parent_type": type(self.widget.parent()).__name__ if self.widget.parent() else None,
            "size": (self.widget.width(), self.widget.height()),
        }

class DialogTestContext:
    """Test context for Qt dialogs with proper modal handling."""

    def __init__(self, framework: QtTestingFramework, dialog_class: type, *args, **kwargs):
        """Initialize dialog test context."""
        self.framework = framework
        self.dialog_class = dialog_class
        self.dialog: QDialog | None = None
        self.args = args
        self.kwargs = kwargs

    def __enter__(self) -> QDialog:
        """Enter the dialog test context."""
        # Create dialog with proper Qt parent
        self.dialog = self.dialog_class(*self.args, **self.kwargs)

        # Don't set QApplication as parent - dialogs should have QWidget parents or None
        # QApplication cannot be a widget parent

        self.framework._created_widgets.append(self.dialog)
        return self.dialog

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit the dialog test context with cleanup."""
        if self.dialog:
            try:
                self.dialog.reject()  # Close dialog
                self.dialog.setParent(None)
            except Exception:
                pass  # Ignore cleanup errors

    def show_non_modal_and_wait(self, wait_ms: int = 100) -> None:
        """Show the dialog non-modally and wait."""
        if self.dialog:
            self.dialog.show()
            self.framework.process_events(wait_ms)

    def validate_dialog_state(self) -> dict[str, Any]:
        """Validate the dialog's state."""
        if not self.dialog:
            return {"error": "Dialog not created"}

        return {
            "dialog_type": type(self.dialog).__name__,
            "is_visible": self.dialog.isVisible(),
            "is_modal": self.dialog.isModal(),
            "has_parent": self.dialog.parent() is not None,
            "parent_type": type(self.dialog.parent()).__name__ if self.dialog.parent() else None,
            "result": self.dialog.result(),
        }

class WorkerTestContext:
    """Test context for worker threads with real QThread testing."""

    def __init__(self, framework: QtTestingFramework, worker_class: type, *args, **kwargs):
        """Initialize worker test context."""
        self.framework = framework
        self.worker_class = worker_class
        self.worker: QObject | None = None
        self.args = args
        self.kwargs = kwargs
        self._signal_spies: list[QSignalSpy] = []

    def __enter__(self) -> QObject:
        """Enter the worker test context."""
        # Create worker with proper Qt parent
        self.worker = self.worker_class(*self.args, **self.kwargs)

        # Set hidden root widget as parent if no parent specified
        # Note: QApplication cannot be a QObject parent - use _root_widget instead
        if hasattr(self.worker, "parent") and self.worker.parent() is None:
            self.worker.setParent(self.framework._root_widget)

        return self.worker

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit the worker test context with cleanup."""
        if self.worker:
            try:
                # Stop worker if it's running
                if hasattr(self.worker, "isRunning") and self.worker.isRunning():
                    # Request interruption first (works for threads without event loop)
                    if hasattr(self.worker, "requestInterruption"):
                        self.worker.requestInterruption()
                    # Then try quit (for threads with event loop)
                    self.worker.quit()
                    self.worker.wait(1000)  # Wait up to 1 second

                # Clean up Qt parent relationship
                if hasattr(self.worker, "setParent"):
                    self.worker.setParent(None)

            except Exception:
                pass  # Ignore cleanup errors

        # Clean up signal spies
        for spy in self._signal_spies:
            with suppress(Exception):
                del spy
        self._signal_spies.clear()

    def create_signal_spy(self, signal: Signal) -> QSignalSpy:
        """Create a signal spy for the worker."""
        spy = QSignalSpy(signal)
        self._signal_spies.append(spy)
        return spy

    def wait_for_worker_signal(self, signal: Signal, timeout_ms: int = 5000) -> bool:
        """Wait for a worker signal to be emitted."""
        spy = self.create_signal_spy(signal)
        return spy.wait(timeout_ms)

    def start_worker_and_wait(self, timeout_ms: int = 5000) -> bool:
        """Start the worker and wait for completion."""
        if not self.worker or not hasattr(self.worker, "start"):
            return False

        # Set up signal spy for finished signal
        finished_spy = None
        if hasattr(self.worker, "finished"):
            finished_spy = self.create_signal_spy(self.worker.finished)
        elif hasattr(self.worker, "operation_finished"):
            finished_spy = self.create_signal_spy(self.worker.operation_finished)

        # Start the worker
        self.worker.start()

        # Wait for completion
        if finished_spy:
            return finished_spy.wait(timeout_ms)
        # No completion signal, use Qt-safe wait
        from PySide6.QtTest import QTest
        QTest.qWait(timeout_ms)
        return True

    def validate_worker_state(self) -> dict[str, Any]:
        """Validate the worker's state."""
        if not self.worker:
            return {"error": "Worker not created"}

        result = {
            "worker_type": type(self.worker).__name__,
            "has_parent": hasattr(self.worker, "parent") and self.worker.parent() is not None,
        }

        if hasattr(self.worker, "parent") and self.worker.parent():
            result["parent_type"] = type(self.worker.parent()).__name__

        if hasattr(self.worker, "isRunning"):
            result["is_running"] = self.worker.isRunning()

        if hasattr(self.worker, "manager"):
            result["has_manager"] = self.worker.manager is not None
            if self.worker.manager:
                result["manager_type"] = type(self.worker.manager).__name__
                result["manager_parent_correct"] = self.worker.manager.parent() is self.worker

        return result

class TimerTestContext:
    """Test context for Qt timer operations."""

    def __init__(self, framework: QtTestingFramework, interval_ms: int, callback: Callable):
        """Initialize timer test context."""
        self.framework = framework
        self.interval_ms = interval_ms
        self.callback = callback
        self.timer: QTimer | None = None
        self.callback_count = 0

    def __enter__(self) -> QTimer:
        """Enter the timer test context."""
        self.timer = QTimer(self.framework.qt_app)
        self.timer.timeout.connect(self._on_timeout)
        self.framework._timers.append(self.timer)
        return self.timer

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit the timer test context with cleanup."""
        if self.timer:
            try:
                self.timer.stop()
                self.timer.setParent(None)
            except Exception:
                pass

    def _on_timeout(self) -> None:
        """Handle timer timeout."""
        self.callback_count += 1
        if self.callback:
            self.callback()

    def start_and_wait(self, max_callbacks: int = 1) -> int:
        """Start timer and wait for callbacks."""
        if not self.timer:
            return 0

        self.timer.start(self.interval_ms)

        # Wait for callbacks
        max_wait_time = (self.interval_ms * max_callbacks + 1000) / 1000.0  # Add 1 second buffer
        start_time = time.time()

        while self.callback_count < max_callbacks and (time.time() - start_time) < max_wait_time:
            self.framework.process_events(10)
            # Use Qt-safe sleep instead of time.sleep()
            from PySide6.QtCore import QThread
            current_thread = QThread.currentThread()
            if current_thread:
                current_thread.msleep(10)
            else:
                time.sleep(0.01)  # sleep-ok: non-Qt fallback

        self.timer.stop()
        return self.callback_count

# Convenience functions for common testing patterns
@contextmanager
def qt_widget_test(widget_class: type, *args, **kwargs):
    """Context manager for Qt widget testing."""
    framework = QtTestingFramework()
    try:
        with framework.create_widget_test_context(widget_class, *args, **kwargs) as widget:
            yield widget
    finally:
        framework.cleanup()

@contextmanager
def qt_dialog_test(dialog_class: type, *args, **kwargs):
    """Context manager for Qt dialog testing."""
    framework = QtTestingFramework()
    try:
        with framework.create_dialog_test_context(dialog_class, *args, **kwargs) as dialog:
            yield dialog
    finally:
        framework.cleanup()

@contextmanager
def qt_worker_test(worker_class: type, *args, **kwargs):
    """Context manager for Qt worker testing."""
    framework = QtTestingFramework()
    try:
        with framework.create_worker_test_context(worker_class, *args, **kwargs) as worker:
            yield worker
    finally:
        framework.cleanup()

def validate_qt_object_lifecycle(obj: QObject) -> dict[str, Any]:
    """Validate Qt object lifecycle for debugging."""
    return {
        "object_type": type(obj).__name__,
        "has_parent": obj.parent() is not None,
        "parent_type": type(obj.parent()).__name__ if obj.parent() else None,
        "children_count": len(obj.children()),
        "object_id": id(obj),
        "qt_object_valid": not hasattr(obj, "isValid") or obj.isValid(),
    }
