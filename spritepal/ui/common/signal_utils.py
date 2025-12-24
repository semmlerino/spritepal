"""
Signal utilities for safe Qt signal handling.

Provides utilities for safely disconnecting signals and checking Qt object validity.
"""
from __future__ import annotations

import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from PySide6.QtCore import QObject


def safe_disconnect(signal: Any) -> None:  # pyright: ignore[reportExplicitAny] - Qt signal object
    """Disconnect all slots from a signal, ignoring warnings if no connections exist.

    PySide6 emits RuntimeWarning when disconnect() is called on a signal
    with no connections. This helper suppresses those warnings.

    Args:
        signal: A Qt signal to disconnect all slots from.

    Example:
        from ui.common.signal_utils import safe_disconnect

        safe_disconnect(self.my_widget.clicked)
    """
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", "Failed to disconnect", RuntimeWarning)
        try:
            signal.disconnect()
        except (TypeError, RuntimeError):
            pass  # Already disconnected or no connections


def is_valid_qt(obj: Any) -> bool:  # pyright: ignore[reportExplicitAny] - Qt object or None
    """Check if a Qt object is still valid (not deleted on the C++ side).

    Args:
        obj: Any object, potentially a Qt object.

    Returns:
        True if obj is a valid Qt object, False if None or deleted.

    Example:
        from ui.common.signal_utils import is_valid_qt

        if is_valid_qt(self.dialog):
            self.dialog.close()
    """
    if obj is None:
        return False
    try:
        from shiboken6 import isValid

        return isValid(obj)
    except (ImportError, TypeError):
        # Not a Qt object or shiboken6 not available
        return True


def is_valid_pixmap(pixmap: object) -> bool:
    """Check if a QPixmap is valid and not null.

    Args:
        pixmap: A QPixmap object or None.

    Returns:
        True if pixmap is not None and not null, False otherwise.

    Example:
        from ui.common.signal_utils import is_valid_pixmap

        if is_valid_pixmap(self.sprite_pixmap):
            self.label.setPixmap(self.sprite_pixmap)
    """
    if pixmap is None:
        return False
    # QPixmap has isNull() method - use getattr to satisfy type checker
    is_null_method = getattr(pixmap, "isNull", None)
    if is_null_method is None:
        return False
    return not is_null_method()


@contextmanager
def blocked_signals(widget: QObject) -> Iterator[None]:
    """Context manager to temporarily block signals from a QObject.

    Useful for updating widget values without triggering connected slots,
    which is a common pattern when synchronizing slider/spinbox pairs.

    Args:
        widget: Any QObject whose signals should be temporarily blocked.

    Yields:
        None. The widget's signals are blocked for the duration of the context.

    Example:
        from ui.common.signal_utils import blocked_signals

        # Update spinbox without triggering valueChanged signal
        with blocked_signals(self.spinbox):
            self.spinbox.setValue(new_value)

        # Sync slider and spinbox without infinite recursion
        def _on_slider_changed(self, value: int) -> None:
            with blocked_signals(self.spinbox):
                self.spinbox.setValue(value)
    """
    widget.blockSignals(True)
    try:
        yield
    finally:
        widget.blockSignals(False)
