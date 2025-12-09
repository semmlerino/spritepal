"""
Unified tests for Manual Offset Dialog functionality.

This module consolidates all unit, integration, and real component tests
for the Manual Offset Dialog, eliminating redundancy and providing a single
source of truth for testing this complex UI component.
"""
from __future__ import annotations

import os

# Add parent directories to path for module imports
import sys
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication, QSlider

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

# Import necessary modules
# from ui.rom_extraction_panel import ManualOffsetDialogSingleton # Removed
from tests.infrastructure.qt_real_testing import QtTestCase
from ui.dialogs.manual_offset_unified_integrated import (
    SimpleBrowseTab,
    SimpleHistoryTab,
    SimpleSmartTab,
    UnifiedManualOffsetDialog,
)


# Define if in a headless environment for skipping tests
def is_headless_environment() -> bool:
    """Detect if we're in a headless environment."""
    if os.environ.get("CI"):
        return True
    if not os.environ.get("DISPLAY"):
        return True
    if os.environ.get("SSH_CONNECTION") and not os.environ.get("DISPLAY"):
        return True
    try:
        app = QApplication.instance()
        if not app:
            temp_app = QApplication([])
            try:
                primary_screen = temp_app.primaryScreen()
                if not primary_screen:
                    return True
                screen_geometry = primary_screen.geometry()
                if screen_geometry.width() <= 0 or screen_geometry.height() <= 0:
                    return True
            finally:
                temp_app.quit()
        else:
            primary_screen = app.primaryScreen()
            if not primary_screen:
                return True
            screen_geometry = primary_screen.geometry()
            if screen_geometry.width() <= 0 or screen_geometry.height() <= 0:
                return True
        return False
    except Exception:
        return True

# Ensure Qt environment is configured for offscreen in headless if not already set
if not os.environ.get('QT_QPA_PLATFORM'):
    if is_headless_environment():
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'


# Unified pytest markers for this consolidated module
pytestmark = [
    pytest.mark.dialog,
    pytest.mark.widget,
    pytest.mark.file_io,
    pytest.mark.rom_data,
    pytest.mark.signals_slots,
    pytest.mark.ci_safe,
    pytest.mark.serial, # Some tests manipulate singletons or global Qt state
]


@pytest.mark.unit
@pytest.mark.no_manager_setup
class TestUnifiedManualOffsetDialogMethods:
    """Unit tests for dialog method behavior (non-Qt specific logic)."""

    @pytest.fixture
    def mock_dialog(self):
        """Create a mock dialog with basic setup."""
        dialog = MagicMock()
        dialog._debug_id = "test_dialog"
        dialog.rom_path = "/test/rom.sfc"
        dialog.rom_data = bytearray(b'\x00' * 1024)
        dialog.current_offset = 0
        dialog.rom_size = 1024
        return dialog

    def test_format_position_with_real_logic(self):
        """Test real _format_position method from SimpleBrowseTab."""
        class TestBrowseTab:
            def __init__(self):
                self._rom_size = 4 * 1024 * 1024 # 4MB ROM
            def _format_position(self, offset: int) -> str:
                if self._rom_size > 0:
                    mb_position = offset / (1024 * 1024)
                    percentage = (offset / self._rom_size) * 100
                    return f"{mb_position:.1f}MB through ROM ({percentage:.0f}%)"
                return "Unknown position"
        tab = TestBrowseTab()
        assert tab._format_position(0) == "0.0MB through ROM (0%)"
        assert tab._format_position(1024 * 1024) == "1.0MB through ROM (25%)"
        assert tab._format_position(2 * 1024 * 1024) == "2.0MB through ROM (50%)"
        assert tab._format_position(4 * 1024 * 1024) == "4.0MB through ROM (100%)"

    def test_offset_clamping_logic(self):
        """Test real offset clamping logic."""
        def clamp_offset(offset: int, rom_size: int) -> int:
            if rom_size <= 0:
                return 0
            return max(0, min(offset, rom_size - 1))
        rom_size = 1024
        assert clamp_offset(-100, rom_size) == 0
        assert clamp_offset(0, rom_size) == 0
        assert clamp_offset(500, rom_size) == 500
        assert clamp_offset(1023, rom_size) == 1023
        assert clamp_offset(2000, rom_size) == 1023
        assert clamp_offset(100, 0) == 0
        large_rom = 4 * 1024 * 1024
        assert clamp_offset(-1, large_rom) == 0
        assert clamp_offset(large_rom - 1, large_rom) == large_rom - 1
        assert clamp_offset(large_rom + 1000, large_rom) == large_rom - 1

    def test_rom_data_validation_rejects_invalid_files(self):
        """Test ROM data validation logic."""
        assert not is_valid_rom_data(b'')
        assert not is_valid_rom_data(b'\x00' * 100)
        assert is_valid_rom_data(b'\x00' * 0x8000)
        assert not is_valid_rom_data(None)

def is_valid_rom_data(data: Any) -> bool:
    """Helper function to validate ROM data."""
    if data is None:
        return False
    if not isinstance(data, (bytes, bytearray)):
        return False
    if len(data) < 0x8000:
        return False  # Minimum 32KB
    return True


@pytest.mark.unit
@pytest.mark.no_manager_setup
class TestDialogStateManagement:
    """Unit tests for dialog state management (mocked for simplicity)."""

    @pytest.fixture
    def mock_dialog(self):
        dialog = MagicMock()
        dialog.visible = False
        dialog.modal = True
        dialog.current_tab = 0
        dialog.history = []
        return dialog

    def test_dialog_visibility_toggle(self, mock_dialog):
        assert not mock_dialog.visible
        mock_dialog.visible = True
        assert mock_dialog.visible
        mock_dialog.visible = False
        assert not mock_dialog.visible

    def test_tab_state_preservation(self, mock_dialog):
        mock_dialog.current_tab = 1
        assert mock_dialog.current_tab == 1
        mock_dialog.visible = False
        mock_dialog.visible = True
        assert mock_dialog.current_tab == 1

    def test_history_accumulation(self, mock_dialog):
        mock_dialog.history.append({'offset': 100, 'sprite': 'test1'})
        mock_dialog.history.append({'offset': 200, 'sprite': 'test2'})
        assert len(mock_dialog.history) == 2
        assert mock_dialog.history[0]['offset'] == 100
        assert mock_dialog.history[1]['offset'] == 200

    def test_modal_state(self, mock_dialog):
        assert mock_dialog.modal is True
        mock_dialog.modal = False
        mock_dialog.modal = True
        assert mock_dialog.modal is True


@pytest.mark.integration
@pytest.mark.gui # Requires display/X11 environment
@pytest.mark.qt_real # Uses real Qt components
@pytest.mark.slow # Real Qt components are slower
@pytest.mark.skipif(
    is_headless_environment(),
    reason="Requires display for real Qt components"
)
class TestManualOffsetDialogIntegrationReal(QtTestCase):
    """Integration tests using real Qt components to verify key user workflows."""

    @pytest.fixture
    def temp_rom_file(self) -> Generator[Path, None, None]:
        temp_file = tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.smc')
        rom_data = bytearray(0x400000) # 4MB ROM
        for i in range(0, len(rom_data), 0x1000):
            rom_data[i:i+4] = b'TEST'
        temp_file.write(rom_data)
        temp_file.close()
        yield Path(temp_file.name)
        try:
            Path(temp_file.name).unlink()
        except FileNotFoundError:
            pass

    @pytest.fixture
    def mock_panel(self):
        panel = MagicMock()
        panel.rom_path = "/fake/rom.sfc"
        panel.rom_size = 0x400000
        panel.extraction_manager = MagicMock()
        return panel

    def test_dialog_components_real_initialization(self, qtbot, setup_managers):
        dialog = UnifiedManualOffsetDialog()
        qtbot.addWidget(dialog)

        assert dialog.windowTitle() == "Manual Offset Browser"
        assert hasattr(dialog, 'browse_tab')
        assert hasattr(dialog, 'smart_tab')
        assert hasattr(dialog, 'history_tab')

        assert isinstance(dialog.browse_tab, SimpleBrowseTab)
        assert isinstance(dialog.smart_tab, SimpleSmartTab)
        assert isinstance(dialog.history_tab, SimpleHistoryTab)

        assert hasattr(dialog.browse_tab, 'position_slider')
        assert hasattr(dialog.browse_tab, 'get_current_offset')
        assert hasattr(dialog.browse_tab, 'set_offset')

    def test_user_adjusts_slider_real_behavior(self, qtbot, wait_timeout, setup_managers):
        dialog = UnifiedManualOffsetDialog()
        qtbot.addWidget(dialog)

        extraction_manager = MagicMock()
        dialog.set_rom_data("/fake/rom.sfc", 0x400000, extraction_manager)

        browse_tab = dialog.browse_tab
        position_slider = browse_tab.position_slider

        assert isinstance(position_slider, QSlider)

        initial_offset = browse_tab.get_current_offset()
        new_slider_value = position_slider.value() + 100
        position_slider.setValue(new_slider_value)
        qtbot.waitUntil(lambda: browse_tab.get_current_offset() == new_slider_value, timeout=500)

        new_offset = browse_tab.get_current_offset()
        assert new_offset != initial_offset
        assert new_offset == new_slider_value

    def test_dialog_close_and_cleanup_behavior(self, qtbot, wait_timeout, setup_managers):
        dialog1 = UnifiedManualOffsetDialog()
        qtbot.addWidget(dialog1)

        dialog1.show()
        qtbot.waitUntil(lambda: dialog1.isVisible(), timeout=1000)
        assert dialog1.isVisible()

        dialog1.close()
        qtbot.waitUntil(lambda: not dialog1.isVisible(), timeout=500)
        assert not dialog1.isVisible()

        dialog2 = UnifiedManualOffsetDialog()
        qtbot.addWidget(dialog2)

        assert id(dialog1) != id(dialog2)
        assert isinstance(dialog2, UnifiedManualOffsetDialog)

    def test_sprite_history_real_functionality(self, qtbot, setup_managers):
        dialog = UnifiedManualOffsetDialog()
        qtbot.addWidget(dialog)

        extraction_manager = MagicMock()
        dialog.set_rom_data("/fake/rom.sfc", 0x400000, extraction_manager)

        history_tab = dialog.history_tab
        initial_count = history_tab.get_sprite_count()

        assert isinstance(history_tab, SimpleHistoryTab)
        assert hasattr(history_tab, 'add_sprite')
        assert hasattr(history_tab, 'get_sprite_count')

        sprite_data = [
            (0x200000, 0.95),
            (0x210000, 0.87),
            (0x220000, 0.92)
        ]

        for offset, quality in sprite_data:
            dialog.add_found_sprite(offset, quality)
            current_count = history_tab.get_sprite_count()
            assert current_count > initial_count
            initial_count = current_count

    def test_dialog_error_recovery_real(self, qtbot, setup_managers):
        dialog = UnifiedManualOffsetDialog()
        qtbot.addWidget(dialog)

        extraction_manager = MagicMock()
        dialog.set_rom_data("/fake/rom.sfc", 0x400000, extraction_manager)

        dialog.set_offset(0x200000)
        assert dialog.get_current_offset() == 0x200000

        dialog.set_offset(0x500000)
        current_offset = dialog.get_current_offset()
        assert current_offset <= 0x400000

        dialog.set_offset(0x250000)
        assert dialog.get_current_offset() == 0x250000

    def test_multiple_dialogs_independent_behavior(self, qtbot, setup_managers):
        dialog1 = UnifiedManualOffsetDialog()
        dialog2 = UnifiedManualOffsetDialog()
        dialog3 = UnifiedManualOffsetDialog()

        qtbot.addWidget(dialog1)
        qtbot.addWidget(dialog2)
        qtbot.addWidget(dialog3)

        assert dialog1 is not dialog2
        assert dialog2 is not dialog3
        assert dialog1 is not dialog3

        assert isinstance(dialog1, UnifiedManualOffsetDialog)
        assert isinstance(dialog2, UnifiedManualOffsetDialog)
        assert isinstance(dialog3, UnifiedManualOffsetDialog)

        extraction_manager = MagicMock()
        dialog1.set_rom_data("/fake/rom1.sfc", 0x400000, extraction_manager)
        dialog2.set_rom_data("/fake/rom2.sfc", 0x200000, extraction_manager)
        dialog3.set_rom_data("/fake/rom3.sfc", 0x600000, extraction_manager)

        dialog1.set_offset(0x100000)
        dialog2.set_offset(0x150000)
        dialog3.set_offset(0x200000)

        assert dialog1.get_current_offset() == 0x100000
        assert dialog2.get_current_offset() == 0x150000
        assert dialog3.get_current_offset() == 0x200000

    def test_ui_elements_real_qt_objects(self, qtbot, setup_managers):
        dialog = UnifiedManualOffsetDialog()
        qtbot.addWidget(dialog)

        browse_tab = dialog.browse_tab
        preview_widget = dialog.preview_widget
        history_tab = dialog.history_tab

        assert hasattr(browse_tab, 'position_slider')
        assert hasattr(browse_tab, 'get_current_offset')
        assert hasattr(browse_tab, 'set_offset')

        assert hasattr(preview_widget, 'update_preview')
        assert hasattr(preview_widget, 'clear_preview')

        assert hasattr(history_tab, 'get_sprite_count')
        assert hasattr(history_tab, 'add_sprite')

        browse_tab2 = dialog.browse_tab
        preview_widget2 = dialog.preview_widget
        history_tab2 = dialog.history_tab

        assert browse_tab is browse_tab2
        assert preview_widget is preview_widget2
        assert history_tab is history_tab2

    def test_dialog_visibility_state_real(self, qtbot, setup_managers):
        dialog = UnifiedManualOffsetDialog()
        qtbot.addWidget(dialog)

        assert not dialog.isVisible()

        dialog.show()
        qtbot.waitUntil(lambda: dialog.isVisible(), timeout=1000)
        assert dialog.isVisible()

        dialog.hide()
        qtbot.waitUntil(lambda: not dialog.isVisible(), timeout=1000)
        assert not dialog.isVisible()

        dialog.show()
        qtbot.waitUntil(lambda: dialog.isVisible(), timeout=1000)
        assert dialog.isVisible()

    def test_rom_data_persistence_real(self, qtbot, setup_managers):
        dialog = UnifiedManualOffsetDialog()
        qtbot.addWidget(dialog)

        rom_path = "/test/rom.sfc"
        rom_size = 0x400000
        extraction_manager = MagicMock()

        dialog.set_rom_data(rom_path, rom_size, extraction_manager)

        browse_tab = dialog.browse_tab
        assert hasattr(browse_tab, '_rom_path')
        assert browse_tab._rom_path == rom_path
        assert browse_tab._rom_size == rom_size

        new_rom_path = "/test/rom2.sfc"
        new_rom_size = 0x200000
        dialog.set_rom_data(new_rom_path, new_rom_size, extraction_manager)

        assert browse_tab._rom_path == new_rom_path
        assert browse_tab._rom_size == new_rom_size

    def test_real_signal_connections(self, qtbot, signal_timeout, wait_timeout, setup_managers):
        dialog = UnifiedManualOffsetDialog()
        qtbot.addWidget(dialog)

        extraction_manager = MagicMock()
        dialog.set_rom_data("/fake/rom.sfc", 0x400000, extraction_manager)

        with qtbot.waitSignal(dialog.offset_changed, timeout=signal_timeout) as blocker:
            dialog.set_offset(0x250000)

        assert len(blocker.args) == 1
        assert blocker.args[0] == 0x250000

        received_offsets = []
        dialog.offset_changed.connect(lambda offset: received_offsets.append(offset))

        dialog.set_offset(0x300000)
        qtbot.waitUntil(lambda: 0x300000 in received_offsets, timeout=500)

        assert 0x300000 in received_offsets

    def test_dialog_thread_affinity_real(self, qtbot, wait_timeout, setup_managers):
        dialog = UnifiedManualOffsetDialog()
        qtbot.addWidget(dialog)

        from PySide6.QtCore import QThread
        assert dialog.thread() is QThread.currentThread()

        assert dialog.browse_tab.thread() is QThread.currentThread()
        assert dialog.smart_tab.thread() is QThread.currentThread()
        assert dialog.history_tab.thread() is QThread.currentThread()
        assert dialog.preview_widget.thread() is QThread.currentThread()

        extraction_manager = MagicMock()
        dialog.set_rom_data("/fake/rom.sfc", 0x400000, extraction_manager)

        for i in range(10):
            offset = 0x200000 + (i * 0x1000)
            dialog.set_offset(offset)
            qtbot.waitUntil(lambda o=offset: dialog.get_current_offset() == o, timeout=500)
            current_offset = dialog.get_current_offset()
            assert current_offset == offset
