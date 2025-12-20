"""
Signal utilities for safe Qt signal handling.

Provides utilities for safely disconnecting signals and checking Qt object validity.
"""
from __future__ import annotations

import warnings
from typing import Any


def safe_disconnect(signal: Any) -> None:
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


def is_valid_qt(obj: Any) -> bool:
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
