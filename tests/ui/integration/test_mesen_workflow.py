"""
Consolidated Mesen workflow tests: widgets, modules, and integration.

Consolidated from:
- tests/ui/rom_extraction/test_manual_offset_section.py
- tests/ui/rom_extraction/test_mesen_captures_section.py
- tests/ui/rom_extraction/test_mesen2_module.py
- tests/ui/rom_extraction/test_mesen2_integration.py

Note: Regression tests preserved separately in:
- tests/ui/rom_extraction/test_rom_workflow_controller.py (capture persistence)
- tests/ui/rom_extraction/test_mesen_capture_offset_sync.py (offset sync)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, Mock

import pytest
from PySide6.QtCore import QCoreApplication, QObject, Qt, Signal
from PySide6.QtWidgets import QListWidget, QPushButton, QToolButton

from core.mesen_integration.log_watcher import CapturedOffset
from tests.fixtures.timeouts import signal_timeout
from ui.rom_extraction.modules import Mesen2Module
from ui.rom_extraction.widgets.manual_offset_section import ManualOffsetSection
from ui.rom_extraction.widgets.mesen_captures_section import MesenCapturesSection

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

pytestmark = [pytest.mark.integration, pytest.mark.headless]


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_capture():
    """Create a sample CapturedOffset for testing."""
    return CapturedOffset(
        offset=0x3C6EF1,
        frame=1800,
        timestamp=datetime.now(UTC),
        raw_line="FILE OFFSET: 0x3C6EF1 frame=1800",
    )


@pytest.fixture
def sample_captures():
    """Create multiple sample captures for testing."""
    return [
        CapturedOffset(
            offset=0x3C6EF1,
            frame=1800,
            timestamp=datetime.now(UTC),
            raw_line="FILE OFFSET: 0x3C6EF1 frame=1800",
        ),
        CapturedOffset(
            offset=0x3C7000,
            frame=1900,
            timestamp=datetime.now(UTC),
            raw_line="FILE OFFSET: 0x3C7000 frame=1900",
        ),
        CapturedOffset(
            offset=0x3C7200,
            frame=2000,
            timestamp=datetime.now(UTC),
            raw_line="FILE OFFSET: 0x3C7200 frame=2000",
        ),
    ]


class MockLogWatcher(QObject):
    """Mock LogWatcher with real Qt signals for testing."""

    offset_discovered = Signal(object)
    offset_rediscovered = Signal(object)
    watch_started = Signal()
    watch_stopped = Signal()
    error_occurred = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._watching = False
        self.start_watching_mock = Mock(return_value=True)
        self.stop_watching_mock = Mock()
        self.load_persistent_clicks_mock = Mock(return_value=[])

    @property
    def is_watching(self) -> bool:
        return self._watching

    @is_watching.setter
    def is_watching(self, value: bool) -> None:
        self._watching = value

    def start_watching(self) -> bool:
        self._watching = True
        self.watch_started.emit()
        self.start_watching_mock()
        return True

    def stop_watching(self) -> None:
        self._watching = False
        self.watch_stopped.emit()
        self.stop_watching_mock()

    def load_persistent_clicks(self) -> list[CapturedOffset]:
        return self.load_persistent_clicks_mock()


@pytest.fixture
def mock_log_watcher(qapp: QObject) -> MockLogWatcher:
    """Create a mock LogWatcher with Qt signals."""
    return MockLogWatcher()


@pytest.fixture
def mock_widget() -> Mock:
    """Create a mock MesenCapturesSection widget."""
    widget = Mock()
    widget.add_capture = Mock()
    widget.set_watching = Mock()
    widget.load_persistent = Mock()
    return widget


# =============================================================================
# ManualOffsetSection Widget Tests
# =============================================================================


class TestManualOffsetSectionWidget:
    """Test ManualOffsetSection widget UI behavior."""

    def test_initial_state(self, qtbot):
        """Test widget initial state."""
        widget = ManualOffsetSection()
        qtbot.addWidget(widget)

        assert not widget.is_expanded()
        assert not widget.is_browse_visible()
        assert not widget.is_offset_display_visible()
        assert widget.get_toggle_arrow_type() == Qt.ArrowType.RightArrow

    def test_toggle_expand_collapse(self, qtbot):
        """Test expanding and collapsing the section."""
        widget = ManualOffsetSection()
        qtbot.addWidget(widget)
        widget.show()
        qtbot.waitExposed(widget)

        widget.set_expanded(True)
        assert widget.is_expanded()
        assert widget.is_browse_visible()
        assert widget.get_toggle_arrow_type() == Qt.ArrowType.DownArrow

        widget.set_expanded(False)
        assert not widget.is_expanded()
        assert not widget.is_browse_visible()
        assert widget.get_toggle_arrow_type() == Qt.ArrowType.RightArrow

    def test_toggle_signal_emission(self, qtbot):
        """Test that toggled signal is emitted correctly."""
        widget = ManualOffsetSection()
        qtbot.addWidget(widget)

        with qtbot.waitSignal(widget.toggled, timeout=1000) as blocker:
            widget.set_expanded(True)
        assert blocker.args == [True]

        with qtbot.waitSignal(widget.toggled, timeout=1000) as blocker:
            widget.set_expanded(False)
        assert blocker.args == [False]

    def test_browse_button_click(self, qtbot):
        """Test browse button click emits signal."""
        widget = ManualOffsetSection()
        qtbot.addWidget(widget)
        widget.set_expanded(True)

        browse_btn = widget.findChild(QPushButton)
        with qtbot.waitSignal(widget.browse_clicked, timeout=1000):
            qtbot.mouseClick(browse_btn, Qt.MouseButton.LeftButton)

    def test_offset_display_update(self, qtbot):
        """Test offset display updates correctly."""
        widget = ManualOffsetSection()
        qtbot.addWidget(widget)
        widget.show()
        qtbot.waitExposed(widget)

        assert not widget.is_offset_display_visible()

        widget.set_offset_display("0x200000")
        assert widget.is_offset_display_visible()
        assert widget.get_offset_display_text() == "0x200000"

        widget.set_offset_display("")
        assert not widget.is_offset_display_visible()

    def test_browse_enabled_state(self, qtbot):
        """Test browse button enable/disable."""
        widget = ManualOffsetSection()
        qtbot.addWidget(widget)
        widget.set_expanded(True)

        assert widget.is_browse_enabled()
        widget.set_browse_enabled(False)
        assert not widget.is_browse_enabled()
        widget.set_browse_enabled(True)
        assert widget.is_browse_enabled()

    def test_user_toggle_interaction(self, qtbot):
        """Test user clicking the toggle button."""
        widget = ManualOffsetSection()
        qtbot.addWidget(widget)
        widget.show()
        qtbot.waitExposed(widget)

        toggle_btn = widget.findChild(QToolButton)

        with qtbot.waitSignal(widget.toggled, timeout=1000) as blocker:
            qtbot.mouseClick(toggle_btn, Qt.MouseButton.LeftButton)
        assert widget.is_expanded()
        assert blocker.args == [True]

        with qtbot.waitSignal(widget.toggled, timeout=1000) as blocker:
            qtbot.mouseClick(toggle_btn, Qt.MouseButton.LeftButton)
        assert not widget.is_expanded()
        assert blocker.args == [False]

    def test_offset_display_persists_across_toggle(self, qtbot):
        """Test that offset display persists when toggling section."""
        widget = ManualOffsetSection()
        qtbot.addWidget(widget)
        widget.show()
        qtbot.waitExposed(widget)

        widget.set_offset_display("0x300000")
        assert widget.get_offset_display_text() == "0x300000"

        widget.set_expanded(True)
        assert widget.get_offset_display_text() == "0x300000"

        widget.set_expanded(False)
        assert widget.get_offset_display_text() == "0x300000"


# =============================================================================
# MesenCapturesSection Widget Tests
# =============================================================================


class TestMesenCapturesSectionWidget:
    """Test MesenCapturesSection widget functionality."""

    @pytest.fixture
    def captures_section(self, app_context, qtbot):
        """Create a MesenCapturesSection widget for testing."""
        widget = MesenCapturesSection()
        qtbot.addWidget(widget)
        return widget

    def test_initialization(self, captures_section):
        """Test widget initializes correctly."""
        assert captures_section is not None
        assert captures_section.get_capture_count() == 0

    def test_add_capture(self, captures_section, sample_capture):
        """Test adding a capture to the widget."""
        assert captures_section.get_selected_offset() is None
        captures_section.add_capture(sample_capture)
        assert captures_section.get_capture_count() == 1

    def test_add_multiple_captures(self, captures_section, sample_captures):
        """Test adding multiple captures."""
        for capture in sample_captures:
            captures_section.add_capture(capture)
        assert captures_section.get_capture_count() == len(sample_captures)

    def test_load_persistent(self, captures_section, sample_captures):
        """Test loading persistent captures."""
        captures_section.load_persistent(sample_captures)
        assert captures_section.get_capture_count() == len(sample_captures)

    def test_clear(self, captures_section, sample_captures):
        """Test clearing all captures."""
        for capture in sample_captures:
            captures_section.add_capture(capture)
        assert captures_section.get_capture_count() > 0

        captures_section.clear()
        assert captures_section.get_capture_count() == 0
        assert captures_section.get_selected_offset() is None

    def test_get_selected_offset(self, captures_section, sample_capture, qtbot):
        """Test getting selected offset after user selection."""
        captures_section.add_capture(sample_capture)

        list_widget = captures_section.findChild(QListWidget)
        item = list_widget.item(0)
        list_widget.setCurrentItem(item)

        selected = captures_section.get_selected_offset()
        assert selected == sample_capture.offset

    def test_set_watching_signals(self, captures_section, qtbot):
        """Test setting watching state emits signals."""
        with qtbot.waitSignal(captures_section.watching_changed, timeout=signal_timeout()) as blocker:
            captures_section.set_watching(True)
        assert blocker.args == [True]

        with qtbot.waitSignal(captures_section.watching_changed, timeout=signal_timeout()) as blocker:
            captures_section.set_watching(False)
        assert blocker.args == [False]

    def test_offset_selected_signal_forwarding(self, captures_section, sample_capture, qtbot):
        """Test that offset_selected signal is forwarded from internal widget."""
        captures_section.add_capture(sample_capture)

        list_widget = captures_section.findChild(QListWidget)
        item = list_widget.item(0)

        with qtbot.waitSignal(captures_section.offset_selected, timeout=signal_timeout()) as blocker:
            list_widget.itemClicked.emit(item)
        assert blocker.args == [sample_capture.offset]

    def test_offset_activated_signal_forwarding(self, captures_section, sample_capture, qtbot):
        """Test that offset_activated signal is forwarded on double-click."""
        captures_section.add_capture(sample_capture)

        list_widget = captures_section.findChild(QListWidget)
        item = list_widget.item(0)

        with qtbot.waitSignal(captures_section.offset_activated, timeout=signal_timeout()) as blocker:
            list_widget.itemDoubleClicked.emit(item)
        assert blocker.args == [sample_capture.offset]


# =============================================================================
# Mesen2Module Tests
# =============================================================================


class TestMesen2ModuleLifecycle:
    """Test Mesen2Module lifecycle and properties."""

    @pytest.fixture
    def mesen2_module(self, mock_log_watcher: MockLogWatcher) -> Mesen2Module:
        """Create a Mesen2Module with mock log watcher."""
        return Mesen2Module(log_watcher=mock_log_watcher)

    def test_init_stores_log_watcher(self, mock_log_watcher: MockLogWatcher) -> None:
        """Module stores log watcher reference."""
        module = Mesen2Module(log_watcher=mock_log_watcher)
        assert module.log_watcher is mock_log_watcher

    def test_is_watching_delegates_to_log_watcher(
        self, mesen2_module: Mesen2Module, mock_log_watcher: MockLogWatcher
    ) -> None:
        """is_watching property delegates to log watcher."""
        mock_log_watcher.is_watching = False
        assert mesen2_module.is_watching is False

        mock_log_watcher.is_watching = True
        assert mesen2_module.is_watching is True

    def test_start_watching(self, mesen2_module: Mesen2Module, mock_log_watcher: MockLogWatcher) -> None:
        """start_watching delegates to log watcher."""
        result = mesen2_module.start_watching()
        assert result is True
        mock_log_watcher.start_watching_mock.assert_called_once()

    def test_stop_watching(self, mesen2_module: Mesen2Module, mock_log_watcher: MockLogWatcher) -> None:
        """stop_watching delegates to log watcher."""
        mesen2_module.stop_watching()
        mock_log_watcher.stop_watching_mock.assert_called_once()

    def test_load_persistent_clicks(self, mesen2_module: Mesen2Module, mock_log_watcher: MockLogWatcher) -> None:
        """load_persistent_clicks delegates to log watcher."""
        test_captures = [
            CapturedOffset(offset=0x100000, frame=1800, timestamp=datetime.now(UTC), raw_line="test line 1"),
            CapturedOffset(offset=0x200000, frame=1900, timestamp=datetime.now(UTC), raw_line="test line 2"),
        ]
        mock_log_watcher.load_persistent_clicks_mock.return_value = test_captures

        result = mesen2_module.load_persistent_clicks()
        assert result == test_captures


class TestMesen2ModuleWidgetConnection:
    """Test Mesen2Module widget connection wiring."""

    @pytest.fixture
    def mesen2_module(self, mock_log_watcher: MockLogWatcher) -> Mesen2Module:
        """Create a Mesen2Module with mock log watcher."""
        return Mesen2Module(log_watcher=mock_log_watcher)

    def test_connect_to_widget_wires_signals(
        self, mesen2_module: Mesen2Module, mock_log_watcher: MockLogWatcher, mock_widget: Mock, qtbot: QtBot
    ) -> None:
        """connect_to_widget wires log_watcher signals to widget methods."""
        mock_log_watcher.is_watching = False
        mesen2_module.connect_to_widget(mock_widget)

        # Should start watching
        mock_log_watcher.start_watching_mock.assert_called_once()

        # Emit offset_discovered - widget should receive it
        capture = CapturedOffset(offset=0x100000, frame=1800, timestamp=datetime.now(UTC), raw_line="test line")
        mock_log_watcher.offset_discovered.emit(capture)
        qtbot.waitUntil(lambda: mock_widget.add_capture.called, timeout=signal_timeout())
        mock_widget.add_capture.assert_called_once_with(capture)

    def test_connect_to_widget_prevents_duplicate(
        self, mesen2_module: Mesen2Module, mock_log_watcher: MockLogWatcher, mock_widget: Mock
    ) -> None:
        """connect_to_widget prevents duplicate connections."""
        mock_log_watcher.is_watching = False

        mesen2_module.connect_to_widget(mock_widget)
        assert mock_log_watcher.start_watching_mock.call_count == 1

        mesen2_module.connect_to_widget(mock_widget)
        assert mock_log_watcher.start_watching_mock.call_count == 1

    def test_disconnect_widget_removes_connections(
        self, mesen2_module: Mesen2Module, mock_log_watcher: MockLogWatcher, mock_widget: Mock, qtbot: QtBot
    ) -> None:
        """disconnect_widget removes signal connections."""
        mock_log_watcher.is_watching = False
        mesen2_module.connect_to_widget(mock_widget)
        mock_widget.reset_mock()

        mesen2_module.disconnect_widget(mock_widget)

        # Emit signal - widget should NOT receive it
        capture = CapturedOffset(offset=0x100000, frame=1800, timestamp=datetime.now(UTC), raw_line="test line")
        mock_log_watcher.offset_discovered.emit(capture)
        QCoreApplication.processEvents()
        mock_widget.add_capture.assert_not_called()


# =============================================================================
# Mesen2Module Integration Tests
# =============================================================================


class TestMesen2ModuleIntegration:
    """Integration tests with real widgets."""

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
        mesen2_module.connect_to_widget(captures_widget)
        assert mesen2_module.is_watching
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

        capture = CapturedOffset(
            offset=0x100000, frame=1800, timestamp=datetime.now(UTC), raw_line="FILE OFFSET: 0x100000"
        )
        mock_log_watcher.offset_discovered.emit(capture)
        qtbot.wait(50)

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
        assert mesen2_module.is_watching

        with qtbot.waitSignal(mock_log_watcher.watch_stopped, timeout=1000):
            mesen2_module.stop_watching()
        assert not mesen2_module.is_watching

        with qtbot.waitSignal(mock_log_watcher.watch_started, timeout=1000):
            mesen2_module.start_watching()
        assert mesen2_module.is_watching

    def test_widget_signals_still_work(
        self, qtbot: QtBot, mesen2_module: Mesen2Module, captures_widget: MesenCapturesSection
    ) -> None:
        """Widget signals still work after module connection."""
        mesen2_module.connect_to_widget(captures_widget)

        capture = CapturedOffset(
            offset=0x200000, frame=1900, timestamp=datetime.now(UTC), raw_line="FILE OFFSET: 0x200000"
        )
        captures_widget.add_capture(capture)

        with qtbot.waitSignal(captures_widget.offset_selected, timeout=1000):
            list_widget = captures_widget.findChild(QListWidget)
            item = list_widget.item(0)
            list_widget.itemClicked.emit(item)


# =============================================================================
# Mesen Capture Sync Tests
# Source: tests/ui/test_mesen_sync.py
# =============================================================================


class TestMesenCaptureSync:
    """Tests for Mesen capture synchronization on workspace switch.

    Source: tests/ui/test_mesen_sync.py
    """

    def test_mesen_captures_synced_on_workspace_switch(self, qtbot, app_context):
        """
        Test that Mesen captures are synchronized from LogWatcher
        to the Asset Browser when switching to the Sprite Editor workspace.
        """
        from ui.main_window import MainWindow, WorkspaceMode

        # 1. Setup: Create real MainWindow with mocked dependencies
        # Note: app_context is required because MainWindow._setup_managers() calls get_app_context()
        mock_settings = MagicMock()
        mock_rom_cache = MagicMock()
        mock_session = MagicMock()
        mock_session.get_session_data.return_value = {}
        mock_session.get_window_geometry.return_value = {}
        mock_core_ops = MagicMock()
        mock_log_watcher = MagicMock()
        mock_preview = MagicMock()
        mock_rom_ext = MagicMock()
        mock_library = MagicMock()

        # Configure log_watcher to have a capture
        capture = CapturedOffset(
            offset=0x1234, frame=100, timestamp=datetime.now(UTC), raw_line="FILE OFFSET: 0x001234 frame=100"
        )
        mock_log_watcher.recent_captures = [capture]
        mock_log_watcher.load_persistent_clicks.return_value = []

        window = MainWindow(
            settings_manager=mock_settings,
            rom_cache=mock_rom_cache,
            session_manager=mock_session,
            core_operations_manager=mock_core_ops,
            log_watcher=mock_log_watcher,
            preview_generator=mock_preview,
            rom_extractor=mock_rom_ext,
            sprite_library=mock_library,
        )
        qtbot.addWidget(window)

        # 2. Action: Switch to Sprite Editor workspace (Mode 1)
        window.switch_to_workspace(WorkspaceMode.SPRITE_EDITOR)

        # 3. Verify: Asset browser should have been synced
        browser = window._sprite_editor_workspace.rom_page.asset_browser
        assert browser.has_mesen_capture(0x1234)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
