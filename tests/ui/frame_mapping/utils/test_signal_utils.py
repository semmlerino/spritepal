"""Tests for signal utilities."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from PySide6.QtCore import QObject, Signal

from ui.frame_mapping.utils.signal_utils import block_signals

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class SimpleWidget(QObject):
    """Test widget with a signal."""

    value_changed = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.value = 0

    def set_value(self, value: int) -> None:
        """Set value and emit signal if not blocked."""
        self.value = value
        self.value_changed.emit(value)


class TestBlockSignals:
    """Tests for block_signals context manager."""

    def test_blocks_signals_during_context(self, qtbot: QtBot) -> None:
        """Signals are blocked during the with block."""
        widget = SimpleWidget()
        emissions: list[int] = []

        widget.value_changed.connect(lambda v: emissions.append(v))

        # Normal emission works
        widget.set_value(10)
        assert emissions == [10]

        # Blocked emission does not trigger handler
        with block_signals(widget):
            widget.set_value(20)

        # Should still be 10 (no emission during block)
        assert emissions == [10]

    def test_restores_signals_after_context(self, qtbot: QtBot) -> None:
        """Signals are restored after the with block."""
        widget = SimpleWidget()
        emissions: list[int] = []

        widget.value_changed.connect(lambda v: emissions.append(v))

        with block_signals(widget):
            widget.set_value(10)

        # After the block, signals should work again
        widget.set_value(20)
        assert emissions == [20]

    def test_restores_signals_on_exception(self, qtbot: QtBot) -> None:
        """Signals are restored even if exception occurs in with block."""
        widget = SimpleWidget()
        emissions: list[int] = []

        widget.value_changed.connect(lambda v: emissions.append(v))

        with pytest.raises(ValueError, match="test error"):
            with block_signals(widget):
                widget.set_value(10)
                raise ValueError("test error")

        # After the block (even with exception), signals should work
        widget.set_value(20)
        assert emissions == [20]

    def test_blocks_multiple_widgets(self, qtbot: QtBot) -> None:
        """Can block signals on multiple widgets simultaneously."""
        widget1 = SimpleWidget()
        widget2 = SimpleWidget()
        emissions1: list[int] = []
        emissions2: list[int] = []

        widget1.value_changed.connect(lambda v: emissions1.append(v))
        widget2.value_changed.connect(lambda v: emissions2.append(v))

        with block_signals(widget1, widget2):
            widget1.set_value(10)
            widget2.set_value(20)

        # Both were blocked
        assert emissions1 == []
        assert emissions2 == []

        # Both restored after context
        widget1.set_value(30)
        widget2.set_value(40)
        assert emissions1 == [30]
        assert emissions2 == [40]

    def test_always_restores_to_unblocked(self, qtbot: QtBot) -> None:
        """Context manager always restores to unblocked state (False)."""
        widget = SimpleWidget()
        emissions: list[int] = []

        widget.value_changed.connect(lambda v: emissions.append(v))

        # Even if signals were manually blocked before...
        widget.blockSignals(True)

        with block_signals(widget):
            widget.set_value(10)

        # ...they are unblocked after context (not preserved)
        widget.set_value(20)
        assert emissions == [20]
