"""
Qt test helpers for proper widget parent handling in tests.

This module provides proper QWidget parents for testing instead of using Mock objects,
which can hide real bugs and don't provide proper Qt functionality.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

if TYPE_CHECKING:
    from collections.abc import Iterator

    from PySide6.QtGui import QCloseEvent, QShowEvent

# Type variable for widget factory
WidgetT = TypeVar('WidgetT', bound=QWidget)

class ParentWidget(QWidget):
    """
    A proper QWidget subclass for use as a parent in tests.

    This provides real Qt widget functionality that child widgets may depend on,
    including proper event handling, lifecycle management, and styling.
    """

    def __init__(self) -> None:
        super().__init__()
        # Set a reasonable default size for testing
        self.resize(800, 600)
        # Set window flags to prevent showing on screen
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        # Ensure the widget is hidden by default
        self.hide()

    def showEvent(self, event: QShowEvent) -> None:
        """Override to prevent actual showing during tests."""
        # Don't call super() to prevent actual display
        event.accept()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Ensure proper cleanup of child widgets."""
        # Let Qt handle child widget cleanup properly
        super().closeEvent(event)
        event.accept()

@pytest.fixture
def parent_widget(qapp: QApplication) -> Iterator[ParentWidget]:
    """
    Fixture providing a proper QWidget parent for tests.

    This replaces the problematic pattern of using Mock() as a parent,
    ensuring that widgets get a real Qt parent with proper functionality.

    Args:
        qapp: The Qt application fixture

    Yields:
        TestParentWidget: A proper parent widget for testing
    """
    widget = ParentWidget()
    yield widget
    # Ensure proper cleanup
    widget.close()
    widget.deleteLater()
    # Process events to ensure deletion
    QApplication.processEvents()

@pytest.fixture
def widget_factory(qapp: QApplication) -> Iterator[Callable[..., WidgetT]]:
    """
    Factory fixture for creating widgets with proper parents.

    This fixture helps create multiple widgets in a test with proper
    parent management and cleanup.

    Args:
        qapp: The Qt application fixture

    Yields:
        callable: Factory function for creating widgets
    """
    created_widgets = []

    def _create_widget(widget_class: type[WidgetT], *args: Any, **kwargs: Any) -> WidgetT:
        """
        Create a widget with a proper test parent.

        Args:
            widget_class: The widget class to instantiate
            *args: Positional arguments for the widget
            **kwargs: Keyword arguments for the widget

        Returns:
            The created widget instance
        """
        # Create a parent if not provided
        if "parent" not in kwargs or kwargs["parent"] is None:
            parent = ParentWidget()
            created_widgets.append(parent)
            kwargs["parent"] = parent

        widget = widget_class(*args, **kwargs)
        created_widgets.append(widget)
        return widget

    yield _create_widget

    # Cleanup all created widgets
    for widget in reversed(created_widgets):
        if widget and not widget.isHidden():
            widget.hide()
        widget.close()
        widget.deleteLater()

    # Process events to ensure deletion
    QApplication.processEvents()

def ensure_qt_app() -> QApplication:
    """
    Ensure a QApplication instance exists for testing.

    This is useful for tests that need Qt but might not use the qapp fixture.
    """
    if not QApplication.instance():
        app = QApplication([])
        # Set application name for testing
        app.setApplicationName("SpritePal-Test")
        return app
    return QApplication.instance()

class MockableParentWidget(ParentWidget):
    """
    A parent widget that can have some methods mocked while maintaining Qt functionality.

    This is useful when you need to mock specific behaviors while keeping
    the core Qt parent functionality intact.
    """

    def __init__(self) -> None:
        super().__init__()
        # These can be overridden in tests
        self.mock_width = None
        self.mock_height = None

    def width(self) -> int:
        """Return mocked width if set, otherwise real width."""
        if self.mock_width is not None:
            return self.mock_width
        return super().width()

    def height(self) -> int:
        """Return mocked height if set, otherwise real height."""
        if self.mock_height is not None:
            return self.mock_height
        return super().height()

@pytest.fixture
def mockable_parent_widget(qapp: QApplication) -> Iterator[MockableParentWidget]:
    """
    Fixture providing a parent widget that supports selective mocking.

    This allows tests to mock specific behaviors while maintaining
    core Qt functionality.

    Args:
        qapp: The Qt application fixture

    Yields:
        MockableParentWidget: A parent widget with mockable methods
    """
    widget = MockableParentWidget()
    yield widget
    widget.close()
    widget.deleteLater()
    QApplication.processEvents()
