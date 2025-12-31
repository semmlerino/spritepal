"""
Modernized Qt mock components for SpritePal tests.

This module provides realistic Qt mock implementations that behave consistently
across all test environments, including headless setups.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import Mock

try:
    from PySide6.QtCore import QObject, Signal
    from PySide6.QtWidgets import QApplication  # noqa: F401

    QT_AVAILABLE = True
except ImportError:
    # Fallback for environments where Qt is not available
    QT_AVAILABLE = False
    QObject = object
    Signal = Mock

# For backward compatibility, MockSignal is now an alias to Signal
if QT_AVAILABLE:
    MockSignal = Signal
else:
    # Minimal fallback implementation for non-Qt environments
    class MockSignal:
        """Fallback signal implementation when Qt is not available."""

        def __init__(self, *args):
            """Initialize MockSignal, accepting any type arguments like real Signal."""
            self._callbacks: list[Callable] = []
            self.emit = Mock(side_effect=self._emit)
            self.connect = Mock(side_effect=self._connect)
            self.disconnect = Mock(side_effect=self._disconnect)

        def _connect(self, callback: Callable) -> None:
            """Internal connect implementation that maintains callback list."""
            self._callbacks.append(callback)

        def _disconnect(self, callback: Callable | None = None) -> None:
            """Internal disconnect implementation."""
            if callback is None:
                self._callbacks.clear()
            elif callback in self._callbacks:
                self._callbacks.remove(callback)

        def _emit(self, *args: Any) -> None:
            """Internal emit implementation that calls all connected callbacks."""
            for callback in self._callbacks:
                try:
                    callback(*args)
                except Exception:
                    # In real Qt, signal emission doesn't crash on callback errors
                    pass


class CommonSignalHolder(QObject):
    """Signal holder with signals used by mock Qt components.

    Qt signals must be class attributes. This class provides commonly
    needed signals for mocks like MockQThread.
    """

    # Thread signals (used by MockQThread)
    started = Signal()
    finished = Signal()


class RealTestMainWindow(QObject):
    """
    QObject-based test double for MainWindow.

    This provides real Qt signals while mocking other functionality.
    Use this ONLY for integration tests that require real Qt signal behavior.
    For unit tests, use TestMainWindowPure instead.
    """

    # Define signals as class attributes (required by Qt)
    extract_requested = Signal()
    open_in_editor_requested = Signal(str)
    arrange_rows_requested = Signal(str)
    arrange_grid_requested = Signal(str)
    inject_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # Mock methods
        self.show = Mock()
        self.close = Mock()
        self.extraction_complete = Mock()
        self.extraction_failed = Mock()
        self.get_extraction_params = Mock(
            return_value={
                "vram_path": "/test/vram.dmp",
                "cgram_path": "/test/cgram.dmp",
                "output_base": "/test/output",
                "create_grayscale": True,
                "create_metadata": True,
                "oam_path": None,
            }
        )

        # Mock UI components
        self.status_bar = Mock()
        self.status_bar.showMessage = Mock()
        self.sprite_preview = Mock()
        self.palette_preview = Mock()
        self.preview_info = Mock()
        self.output_name_edit = Mock()
        self.output_name_edit.text = Mock(return_value="test_output")

        # Create TestExtractionPanel with real signals
        self.extraction_panel = RealTestExtractionPanel()

        # Add preview_coordinator mock (needed by controller tests)
        self.preview_coordinator = Mock()
        self.preview_coordinator.update_preview_info = Mock()

        # Add get_output_path method (needed by injection tests)
        self.get_output_path = Mock(return_value="/test/output")


class RealTestExtractionPanel(QObject):
    """
    QObject-based test double for ExtractionPanel.

    Provides real Qt signals for extraction panel functionality.
    Use this ONLY for integration tests that require real Qt signals.
    """

    # Define signals as class attributes
    file_dropped = Signal(str)
    files_changed = Signal()
    extraction_ready = Signal(bool, str)  # (ready, reason_if_not_ready)
    offset_changed = Signal(int)
    mode_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Mock methods and attributes
        self.get_vram_path = Mock(return_value="/test/vram.dmp")
        self.get_cgram_path = Mock(return_value="/test/cgram.dmp")
        self.get_oam_path = Mock(return_value=None)
        self.get_output_base = Mock(return_value="/test/output")
        self.get_vram_offset = Mock(return_value=0xC000)
        self.set_vram_offset = Mock()


class MockQWidget:
    """Comprehensive mock implementation of QWidget."""

    def __init__(self, parent=None):
        self.parent = Mock(return_value=parent)
        self.show = Mock()
        self.hide = Mock()
        self.close = Mock()
        self.setVisible = Mock()
        self.isVisible = Mock(return_value=False)
        self.update = Mock()
        self.repaint = Mock()
        self.setMinimumSize = Mock()
        self.setMaximumSize = Mock()
        self.resize = Mock()
        self.setWindowTitle = Mock()
        self.setWindowFlags = Mock()
        self.windowFlags = Mock(return_value=Mock())
        self.isModal = Mock(return_value=False)
        self.setModal = Mock()
        self.deleteLater = Mock()

        # Layout support
        self.setLayout = Mock()
        self.layout = Mock(return_value=None)


class MockQDialog(MockQWidget):
    """Mock implementation of QDialog extending QWidget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.accept = Mock()
        self.reject = Mock()
        self.exec = Mock(return_value=0)
        self.result = Mock(return_value=0)


class MockQPixmap:
    """Mock implementation of QPixmap for image handling tests."""

    def __init__(self, width: int = 100, height: int = 100):
        self._width = width
        self._height = height
        self.width = Mock(return_value=width)
        self.height = Mock(return_value=height)
        self.loadFromData = Mock(return_value=True)
        self.save = Mock(return_value=True)
        self.isNull = Mock(return_value=False)
        self.scaled = Mock(return_value=self)


class MockQLabel(MockQWidget):
    """Mock implementation of QLabel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._text = ""
        self.setText = Mock(side_effect=self._set_text)
        self.text = Mock(side_effect=self._get_text)
        self.setPixmap = Mock()
        self.setAlignment = Mock()
        self.setStyleSheet = Mock()

    def _set_text(self, text: str) -> None:
        self._text = text

    def _get_text(self) -> str:
        return self._text


class MockQThread:
    """Mock implementation of QThread for worker thread tests."""

    def __init__(self):
        self.start = Mock()
        self.quit = Mock()
        self.wait = Mock(return_value=True)
        self.isRunning = Mock(return_value=False)
        self.terminate = Mock()

        # Create signal holder for thread signals
        if QT_AVAILABLE:
            signal_holder = CommonSignalHolder()
            self.finished = signal_holder.finished
            self.started = signal_holder.started
        else:
            self.finished = MockSignal()
            self.started = MockSignal()


class MockQApplication:
    """Mock implementation of QApplication."""

    def __init__(self):
        self.processEvents = Mock()
        self.quit = Mock()
        self.exit = Mock()

    @classmethod
    def instance(cls):
        """Mock class method that returns a mock app instance."""
        return cls()


def create_real_test_main_window(**kwargs):
    """
    Create a real Qt-based test main window for integration testing.

    Use this ONLY when you need real Qt signal behavior for integration tests.
    """
    return RealTestMainWindow(**kwargs)


# Backward compatibility aliases - use RealTest* versions (QObject-based with real signals)
TestMainWindow = RealTestMainWindow
TestExtractionPanel = RealTestExtractionPanel
