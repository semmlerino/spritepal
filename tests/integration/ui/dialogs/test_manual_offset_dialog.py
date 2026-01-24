"""Tests for UnifiedManualOffsetDialog signal connections.

Extracted from test_qt_signal_slot_integration.py to focus on
application-specific dialog testing rather than framework patterns.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pytest
from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot

from core.app_context import get_app_context
from tests.fixtures.timeouts import SHORT, signal_timeout
from ui.dialogs.manual_offset_dialog import UnifiedManualOffsetDialog
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

logger = get_logger(__name__)


def _create_dialog(parent=None) -> UnifiedManualOffsetDialog:
    """Create UnifiedManualOffsetDialog with injected dependencies.

    Used by tests that have managers_initialized fixture.
    """
    context = get_app_context()
    return UnifiedManualOffsetDialog(
        parent,
        rom_cache=context.rom_cache,
        settings_manager=context.application_state_manager,
        extraction_manager=context.core_operations_manager,
    )


class SignalRecorder(QObject):
    """Helper class to record signal emissions with parameters."""

    def __init__(self):
        super().__init__()
        self.emissions: list[tuple[str, tuple, float]] = []
        self.lock = QThread.currentThread()  # Thread safety check

    @Slot(int)
    def record_offset_changed(self, offset: int):
        """Record offset_changed signal."""
        self._record_signal("offset_changed", (offset,))

    @Slot(int, str)
    def record_sprite_found(self, offset: int, name: str):
        """Record sprite_found signal."""
        self._record_signal("sprite_found", (offset, name))

    def _record_signal(self, signal_name: str, args: tuple):
        """Record a signal emission with timestamp."""
        # Verify we're in the correct thread
        current_thread = QThread.currentThread()
        if current_thread != self.lock:
            logger.warning(f"Signal {signal_name} received in different thread!")

        timestamp = time.time()
        self.emissions.append((signal_name, args, timestamp))
        logger.debug(f"Recorded signal: {signal_name}{args} at {timestamp}")

    def clear(self):
        """Clear recorded emissions."""
        self.emissions.clear()

    def get_emissions(self, signal_name: str | None = None) -> list[tuple[tuple, float]]:
        """Get emissions for a specific signal or all."""
        if signal_name:
            return [(args, ts) for name, args, ts in self.emissions if name == signal_name]
        return [(args, ts) for _, args, ts in self.emissions]

    def count(self, signal_name: str | None = None) -> int:
        """Count emissions for a specific signal or all."""
        if signal_name:
            return sum(1 for name, _, _ in self.emissions if name == signal_name)
        return len(self.emissions)


@pytest.mark.gui
@pytest.mark.usefixtures("session_app_context")
@pytest.mark.shared_state_safe
class TestDialogSignalConnections:
    """Test UnifiedManualOffsetDialog signal connections."""

    def test_dialog_signals_exist(self, qtbot: QtBot, managers_initialized):
        """Test that dialog has required signals."""
        dialog = _create_dialog(None)
        qtbot.addWidget(dialog)

        # Check signals exist
        assert hasattr(dialog, "offset_changed")
        assert hasattr(dialog, "sprite_found")

        # Check they are Qt signals
        assert isinstance(dialog.offset_changed, Signal)
        assert isinstance(dialog.sprite_found, Signal)

    def test_offset_changed_emission(self, qtbot: QtBot, managers_initialized):
        """Test offset_changed signal is emitted with correct value."""
        dialog = _create_dialog(None)
        qtbot.addWidget(dialog)

        # Create signal spy
        with qtbot.waitSignal(dialog.offset_changed, timeout=signal_timeout()) as blocker:
            # Trigger offset change
            dialog.set_offset(0x1000)

        # Verify signal was emitted with correct value
        assert blocker.args == [0x1000]

    def test_sprite_found_emission(self, qtbot: QtBot, managers_initialized):
        """Test sprite_found signal is emitted with correct parameters."""
        dialog = _create_dialog(None)
        qtbot.addWidget(dialog)

        # Create signal spy
        with qtbot.waitSignal(dialog.sprite_found, timeout=signal_timeout()) as blocker:
            # Trigger sprite found (simulate Apply button)
            dialog._apply_offset()

        # Verify signal was emitted with offset and name
        assert len(blocker.args) == 2
        assert isinstance(blocker.args[0], int)  # offset
        assert isinstance(blocker.args[1], str)  # sprite name

    def test_multiple_rapid_emissions(self, qtbot: QtBot, managers_initialized, wait_for_signal_processed):
        """Test handling of multiple rapid signal emissions."""
        dialog = _create_dialog(None)
        qtbot.addWidget(dialog)

        recorder = SignalRecorder()
        dialog.offset_changed.connect(recorder.record_offset_changed)

        # Emit multiple signals rapidly
        offsets = [0x1000, 0x2000, 0x3000, 0x4000, 0x5000]
        for offset in offsets:
            dialog.set_offset(offset)

        # Wait for all signals to be processed
        qtbot.waitUntil(lambda: recorder.count("offset_changed") == len(offsets), timeout=signal_timeout())

        # Verify all signals were received
        emissions = recorder.get_emissions("offset_changed")
        received_offsets = [args[0] for args, _ in emissions]
        assert received_offsets == offsets

    def test_signal_connection_types(self, qtbot: QtBot, managers_initialized, wait_for_signal_processed):
        """Test different Qt connection types for cross-thread safety."""
        dialog = _create_dialog(None)
        qtbot.addWidget(dialog)

        recorder = SignalRecorder()

        # Test AutoConnection (default)
        dialog.offset_changed.connect(recorder.record_offset_changed)

        # Test QueuedConnection (for cross-thread)
        dialog.sprite_found.connect(recorder.record_sprite_found, Qt.ConnectionType.QueuedConnection)

        # Emit signals
        dialog.set_offset(0x1000)
        dialog._apply_offset()

        # Wait for queued connections to be processed
        qtbot.waitUntil(lambda: recorder.count() == 2, timeout=signal_timeout())

        # Verify both signals received
        assert recorder.count("offset_changed") == 1
        assert recorder.count("sprite_found") == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
