"""Signal utilities for frame mapping UI."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtCore import QObject


@contextmanager
def block_signals(*widgets: QObject) -> Iterator[None]:
    """Temporarily block signals from widgets. Exception-safe.

    Args:
        *widgets: One or more QObject instances to block signals on.

    Example:
        with block_signals(self._checkbox, self._slider):
            self._checkbox.setChecked(True)
            self._slider.setValue(50)
    """
    for widget in widgets:
        widget.blockSignals(True)
    try:
        yield
    finally:
        for widget in widgets:
            widget.blockSignals(False)
