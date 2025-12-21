"""
Qt test helpers for proper widget parent handling in tests.

This module provides proper QWidget parents for testing instead of using Mock objects,
which can hide real bugs and don't provide proper Qt functionality.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

if TYPE_CHECKING:
    from collections.abc import Iterator

    from PySide6.QtGui import QCloseEvent, QShowEvent


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
