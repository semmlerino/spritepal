"""
Integration tests for Mesen2Module with ROMExtractionPanel.

Validates that the module properly wires up to the panel and widget.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from PySide6.QtCore import QObject

from core.mesen_integration.log_watcher import CapturedOffset
from ui.rom_extraction.modules import Mesen2Module
from ui.rom_extraction.widgets import MesenCapturesSection

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class MockLogWatcher(QObject):
    """Mock LogWatcher for testing."""

    from PySide6.QtCore import Signal

    offset_discovered = Signal(object)
    watch_started = Signal()
    watch_stopped = Signal()
    error_occurred = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._watching = False

    @property
    def is_watching(self) -> bool:
        return self._watching

    def start_watching(self) -> bool:
        self._watching = True
        self.watch_started.emit()
        return True

    def stop_watching(self) -> None:
        self._watching = False
        self.watch_stopped.emit()

    def load_persistent_clicks(self) -> list[CapturedOffset]:
        # Return empty list for testing
        return []


class TestMesen2Integration:
    """Integration tests for Mesen2Module with widgets."""

    @pytest.fixture
    def mock_log_watcher(self, qapp: QObject) -> MockLogWatcher:
        """Create a mock log watcher."""
        return MockLogWatcher()

    @pytest.fixture
    def mesen2_module(self, mock_log_watcher: MockLogWatcher) -> Mesen2Module:
        """Create Mesen2Module with mock log watcher."""
        return Mesen2Module(log_watcher=mock_log_watcher)

    @pytest.fixture
    def captures_widget(self, qapp: QObject) -> MesenCapturesSection:
        """Create a real MesenCapturesSection widget."""
        return MesenCapturesSection()

    def test_module_connects_to_widget(
        self, qtbot: QtBot, mesen2_module: Mesen2Module, captures_widget: MesenCapturesSection
    ) -> None:
        """Module successfully connects to widget."""
        # Connect widget
        mesen2_module.connect_to_widget(captures_widget)

        # Should start watching
        assert mesen2_module.is_watching

        # Widget is registered in module
        assert mesen2_module.is_widget_connected(captures_widget)

    def test_offset_discovered_propagates_to_widget(
        self,
        qtbot: QtBot,
        mesen2_module: Mesen2Module,
        mock_log_watcher: MockLogWatcher,
        captures_widget: MesenCapturesSection,
    ) -> None:
        """Offset discovered signal propagates to widget."""
        mesen2_module.connect_to_widget(captures_widget)

        # Create test capture
        capture = CapturedOffset(
            offset=0x100000,
            frame=1800,
            timestamp=datetime.now(UTC),
            raw_line="FILE OFFSET: 0x100000",
        )

        # Emit signal
        mock_log_watcher.offset_discovered.emit(capture)
        qtbot.wait(50)  # Allow signal to propagate

        # Widget should have received the capture via public has_capture check
        assert captures_widget.has_capture(0x100000)
        assert captures_widget.get_capture_count() == 1

    def test_watch_state_changes_propagate(
        self,
        qtbot: QtBot,
        mesen2_module: Mesen2Module,
        mock_log_watcher: MockLogWatcher,
        captures_widget: MesenCapturesSection,
    ) -> None:
        """Watch state changes propagate correctly."""
        mesen2_module.connect_to_widget(captures_widget)

        # Initially watching
        assert mesen2_module.is_watching

        # Stop watching - verify via LogWatcher signal directly
        with qtbot.waitSignal(mock_log_watcher.watch_stopped, timeout=1000):
            mesen2_module.stop_watching()

        # Module should not be watching
        assert not mesen2_module.is_watching

        # Start watching again - verify via LogWatcher signal directly
        with qtbot.waitSignal(mock_log_watcher.watch_started, timeout=1000):
            mesen2_module.start_watching()

        # Module should be watching
        assert mesen2_module.is_watching

    def test_widget_signals_still_work(
        self, qtbot: QtBot, mesen2_module: Mesen2Module, captures_widget: MesenCapturesSection
    ) -> None:
        """Widget signals still work after module connection."""
        from PySide6.QtWidgets import QListWidget

        mesen2_module.connect_to_widget(captures_widget)

        # Add a capture manually
        capture = CapturedOffset(
            offset=0x200000,
            frame=1900,
            timestamp=datetime.now(UTC),
            raw_line="FILE OFFSET: 0x200000",
        )
        captures_widget.add_capture(capture)

        # Listen for widget signal
        with qtbot.waitSignal(captures_widget.offset_selected, timeout=1000):
            # Simulate user clicking on the capture via findChild
            list_widget = captures_widget.findChild(QListWidget)
            item = list_widget.item(0)
            list_widget.itemClicked.emit(item)
