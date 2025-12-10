"""
Base mock dialog infrastructure for testing.

This module provides lightweight mock dialogs that prevent blocking operations
while maintaining realistic Qt signal behavior.

NOTE: Callbacks are invoked with proper error handling:
- AssertionError is NEVER suppressed (test assertions must propagate)
- Other exceptions are logged as warnings to aid debugging
"""
from __future__ import annotations

import logging
import warnings
from collections.abc import Callable
from typing import Any

_logger = logging.getLogger(__name__)


def _invoke_callback_safe(callback: Callable, *args: Any) -> None:
    """
    Invoke a callback with proper error handling.

    - AssertionError: Re-raised (test assertions must fail tests)
    - Other exceptions: Logged as warning (aids debugging without crashing)
    """
    try:
        callback(*args)
    except AssertionError:
        # Never suppress test assertions - they must fail the test
        raise
    except Exception as e:
        # Log other exceptions as warnings so developers can see them
        _logger.warning(f"Exception in callback {callback}: {e}", exc_info=True)
        warnings.warn(
            f"Callback {callback} raised {type(e).__name__}: {e}",
            UserWarning,
            stacklevel=3
        )


class MockDialogBase:
    """
    Pure Python base class for all mock dialogs.

    Provides:
    - Non-blocking exec() method
    - Callback-based signals
    - Configurable return values
    - Automatic cleanup
    """

    # Dialog result constants (replaces QDialog.DialogCode)
    class DialogCode:
        Accepted = 1
        Rejected = 0

    def __init__(self, parent: Any | None = None):
        self.parent_widget = parent
        self.result_value = self.DialogCode.Accepted
        self._exec_called = False
        self._show_called = False

        # Callback-based signal system
        self.accepted_callbacks: list[Callable[[], None]] = []
        self.rejected_callbacks: list[Callable[[], None]] = []
        self.finished_callbacks: list[Callable[[int], None]] = []
        self.destroyed_callbacks: list[Callable[[], None]] = []

    def exec(self) -> int:
        """Non-blocking exec replacement."""
        self._exec_called = True
        # Emit finished signal via callbacks
        for callback in self.finished_callbacks:
            _invoke_callback_safe(callback, self.result_value)
        return self.result_value

    def show(self) -> None:
        """Non-blocking show method."""
        self._show_called = True

    def accept(self) -> None:
        """Accept the dialog."""
        self.result_value = self.DialogCode.Accepted
        # Emit accepted signal via callbacks
        for callback in self.accepted_callbacks:
            _invoke_callback_safe(callback)
        # Emit finished signal via callbacks
        for callback in self.finished_callbacks:
            _invoke_callback_safe(callback, self.result_value)

    def reject(self) -> None:
        """Reject the dialog."""
        self.result_value = self.DialogCode.Rejected
        # Emit rejected signal via callbacks
        for callback in self.rejected_callbacks:
            _invoke_callback_safe(callback)
        # Emit finished signal via callbacks
        for callback in self.finished_callbacks:
            _invoke_callback_safe(callback, self.result_value)

    def close(self) -> bool:
        """Close the dialog."""
        return True

    def deleteLater(self) -> None:
        """Schedule deletion."""
        pass

    def setStyleSheet(self, style: str) -> None:
        """Mock setStyleSheet method."""
        pass

    # Signal-like interface for compatibility
    @property
    def accepted(self):
        """Accepted signal interface."""
        return CallbackSignal(self.accepted_callbacks)

    @property
    def rejected(self):
        """Rejected signal interface."""
        return CallbackSignal(self.rejected_callbacks)

    @property
    def finished(self):
        """Finished signal interface."""
        return CallbackSignal(self.finished_callbacks)

    @property
    def destroyed(self):
        """Destroyed signal interface (QObject standard signal)."""
        return CallbackSignal(self.destroyed_callbacks)

class CallbackSignal:
    """Signal-like interface for callbacks."""

    def __init__(self, callbacks: list[Callable]):
        self.callbacks = callbacks

    def connect(self, callback: Callable) -> None:
        """Connect a callback."""
        if callback not in self.callbacks:
            self.callbacks.append(callback)

    def disconnect(self, callback: Callable | None = None) -> None:
        """Disconnect callback(s)."""
        if callback is None:
            self.callbacks.clear()
        elif callback in self.callbacks:
            self.callbacks.remove(callback)

    def emit(self, *args) -> None:
        """Emit signal to all callbacks."""
        for callback in self.callbacks:
            _invoke_callback_safe(callback, *args)

class MockMessageBox(MockDialogBase):
    """Test QMessageBox for testing."""

    def __init__(self, parent: Any | None = None):
        super().__init__(parent)
        self.text = ""
        self.informative_text = ""
        self.detailed_text = ""
        self.icon = None
        self.standard_buttons = None

    @staticmethod
    def information(parent: Any, title: str, text: str) -> int:
        """Mock information dialog."""
        return MockDialogBase.DialogCode.Accepted

    @staticmethod
    def warning(parent: Any, title: str, text: str) -> int:
        """Mock warning dialog."""
        return MockDialogBase.DialogCode.Accepted

    @staticmethod
    def critical(parent: Any, title: str, text: str) -> int:
        """Mock critical dialog."""
        return MockDialogBase.DialogCode.Accepted

    @staticmethod
    def question(parent: Any, title: str, text: str,
                 buttons: Any = None, defaultButton: Any = None) -> int:
        """Mock question dialog."""
        return MockDialogBase.DialogCode.Accepted

class MockFileDialog(MockDialogBase):
    """Test QFileDialog for testing."""

    def __init__(self, parent: Any | None = None):
        super().__init__(parent)
        self.selected_files = []
        self.selected_directory = ""

    @staticmethod
    def getOpenFileName(parent: Any, caption: str = "",
                        directory: str = "", filter: str = "") -> tuple[str, str]:
        """Mock file open dialog."""
        return "/test/file.txt", "All Files (*)"

    @staticmethod
    def getSaveFileName(parent: Any, caption: str = "",
                       directory: str = "", filter: str = "") -> tuple[str, str]:
        """Mock file save dialog."""
        return "/test/output.txt", "All Files (*)"

    @staticmethod
    def getExistingDirectory(parent: Any, caption: str = "",
                           directory: str = "") -> str:
        """Mock directory selection dialog."""
        return "/test/directory"

class MockInputDialog(MockDialogBase):
    """Test QInputDialog for testing."""

    @staticmethod
    def getText(parent: Any, title: str, label: str,
                text: str = "") -> tuple[str, bool]:
        """Mock text input dialog."""
        return "test_input", True

    @staticmethod
    def getInt(parent: Any, title: str, label: str,
               value: int = 0, min: int = -2147483647,
               max: int = 2147483647, step: int = 1) -> tuple[int, bool]:
        """Mock integer input dialog."""
        return 42, True

    @staticmethod
    def getDouble(parent: Any, title: str, label: str,
                  value: float = 0.0, min: float = -2147483647.0,
                  max: float = 2147483647.0, decimals: int = 1) -> tuple[float, bool]:
        """Mock double input dialog."""
        return 3.14, True

class MockProgressDialog(MockDialogBase):
    """Test QProgressDialog for testing."""

    def __init__(self, parent: Any | None = None):
        super().__init__(parent)
        # Progress dialog specific callbacks
        self.canceled_callbacks: list[Callable[[], None]] = []
        self.value = 0
        self.minimum = 0
        self.maximum = 100
        self.label_text = ""
        self._was_canceled = False

    def setValue(self, value: int) -> None:
        """Set progress value."""
        self.value = value

    def setLabelText(self, text: str) -> None:
        """Set label text."""
        self.label_text = text

    def wasCanceled(self) -> bool:
        """Check if canceled."""
        return self._was_canceled

    def cancel(self) -> None:
        """Cancel the dialog."""
        self._was_canceled = True
        # Emit canceled signal via callbacks
        for callback in self.canceled_callbacks:
            _invoke_callback_safe(callback)

    @property
    def canceled(self):
        """Canceled signal interface."""
        return CallbackSignal(self.canceled_callbacks)

def create_mock_dialog(dialog_type: str, **kwargs) -> MockDialogBase:
    """
    Factory function to create mock dialogs.

    Args:
        dialog_type: Type of dialog ('message', 'file', 'input', 'progress')
        **kwargs: Additional arguments for dialog creation

    Returns:
        Mock dialog instance
    """
    dialog_map = {
        'message': MockMessageBox,
        'file': MockFileDialog,
        'input': MockInputDialog,
        'progress': MockProgressDialog,
    }

    dialog_class = dialog_map.get(dialog_type, MockDialogBase)
    return dialog_class(**kwargs)

# Convenience function for patching
def patch_all_dialogs(monkeypatch):
    """
    Patch all Qt dialogs with mocks.

    Args:
        monkeypatch: pytest monkeypatch fixture
    """
    try:
        import PySide6.QtWidgets as widgets
    except ImportError:
        return  # Skip patching if Qt not available

    monkeypatch.setattr(widgets, 'QMessageBox', MockMessageBox)
    monkeypatch.setattr(widgets, 'QFileDialog', MockFileDialog)
    monkeypatch.setattr(widgets, 'QInputDialog', MockInputDialog)
    monkeypatch.setattr(widgets, 'QProgressDialog', MockProgressDialog)
