"""
Unit tests for refactored UI components

Uses isolated_managers fixture from core_fixtures.py for test isolation.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from ui.components.visualization.rom_map_widget import ROMMapWidget

# NOTE: pythonpath configured in pyproject.toml - no sys.path manipulation needed

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.skip_thread_cleanup(reason="UI tests may involve managers that spawn threads"),
    pytest.mark.headless,
]

# Note: initialize_managers and cleanup_managers are no longer needed here
# as we use the isolated_managers fixture


@pytest.mark.usefixtures("isolated_managers")
class TestROMMapWidget:
    """Test ROMMapWidget functionality"""

    # Uses isolated_managers fixture for test isolation

    # Using parent_widget fixture from qt_test_helpers instead of mock_parent

    def test_rom_map_widget_creation(self, qtbot):
        """Test ROMMapWidget can be created with proper Qt parent"""
        # Test component creation with real Qt parent
        from PySide6.QtWidgets import QWidget

        parent_widget = QWidget()
        qtbot.addWidget(parent_widget)

        # Create widget with proper parent
        widget = ROMMapWidget(parent_widget)
        qtbot.addWidget(widget)

        assert widget.parent() == parent_widget

    def test_add_sprite_data(self, qtbot):
        """Test adding sprite data to ROM map"""
        from PySide6.QtWidgets import QWidget

        from ui.components.visualization.rom_map_widget import ROMMapWidget

        parent_widget = QWidget()
        qtbot.addWidget(parent_widget)

        widget = ROMMapWidget(parent_widget)
        qtbot.addWidget(widget)

        # Test adding sprite with quality
        offset = 0x1000
        quality = 0.95

        widget.add_found_sprite(offset, quality)

        # Verify sprite was added
        assert len(widget.found_sprites) == 1
        assert widget.found_sprites[0] == (offset, quality)

    def test_sprite_count_limits(self, qtbot):
        """Test sprite count limits prevent memory leaks"""
        from PySide6.QtWidgets import QWidget

        from ui.components.visualization.rom_map_widget import (
            SPRITE_CLEANUP_TARGET,
            SPRITE_CLEANUP_THRESHOLD,
            ROMMapWidget,
        )

        parent_widget = QWidget()
        qtbot.addWidget(parent_widget)

        widget = ROMMapWidget(parent_widget)
        qtbot.addWidget(widget)

        # Add many sprites to test limits
        for i in range(SPRITE_CLEANUP_THRESHOLD + 100):  # More than the cleanup threshold
            widget.add_found_sprite(0x1000 + i * 32, 1.0)

        # Should have cleaned up to around target count (allow small variation)
        # The cleanup happens when exceeding threshold, so count should be close to target
        assert len(widget.found_sprites) <= SPRITE_CLEANUP_TARGET + 100  # Allow small buffer
        assert len(widget.found_sprites) < SPRITE_CLEANUP_THRESHOLD  # But definitely below threshold

    def test_cleanup_method(self, qtbot):
        """Test cleanup method clears resources"""
        from PySide6.QtWidgets import QWidget

        from ui.components.visualization.rom_map_widget import ROMMapWidget

        parent_widget = QWidget()
        qtbot.addWidget(parent_widget)

        widget = ROMMapWidget(parent_widget)
        qtbot.addWidget(widget)

        # Add some sprite data
        widget.add_found_sprite(0x1000, 1.0)
        widget.add_found_sprite(0x2000, 0.8)
        assert len(widget.found_sprites) > 0

        # Clear sprites
        widget.clear_sprites()

        # Verify resources cleared
        assert len(widget.found_sprites) == 0

@pytest.mark.usefixtures("isolated_managers")
class TestScanControlsPanel:
    """Test ScanControlsPanel functionality"""

    # Uses isolated_managers fixture for test isolation

    # Using parent_widget fixture from qt_test_helpers instead of mock_parent

    def test_scan_controls_creation(self, qtbot):
        """Test ScanControlsPanel creation"""
        from PySide6.QtWidgets import QWidget

        from core.di_container import inject
        from core.services.rom_cache import ROMCache
        from ui.components.panels.scan_controls_panel import ScanControlsPanel

        parent_widget = QWidget()
        qtbot.addWidget(parent_widget)

        panel = ScanControlsPanel(parent_widget, rom_cache=inject(ROMCache))
        qtbot.addWidget(panel)


    def test_scan_parameters_validation(self, qtbot):
        """Test scan parameter validation"""
        from PySide6.QtWidgets import QWidget

        from core.di_container import inject
        from core.services.rom_cache import ROMCache
        from ui.components.panels.scan_controls_panel import ScanControlsPanel

        parent_widget = QWidget()
        qtbot.addWidget(parent_widget)

        panel = ScanControlsPanel(parent_widget, rom_cache=inject(ROMCache))
        qtbot.addWidget(panel)

        # Test the validation method directly with mock parameters
        start_offset = 0x1000
        end_offset = 0x2000

        # Test parameter validation - use the actual validation method from the implementation
        is_valid = panel._validate_scan_parameters(start_offset, end_offset)

        assert is_valid is True, "Valid scan parameters should pass validation"
        assert end_offset > start_offset, "End offset should be greater than start offset"

@pytest.mark.usefixtures("isolated_managers")
class TestImportExportPanel:
    """Test ImportExportPanel functionality"""

    # Uses isolated_managers fixture for test isolation

    # Using parent_widget fixture from qt_test_helpers instead of mock_parent

    def test_import_export_creation(self, qtbot):
        """Test ImportExportPanel creation"""
        from PySide6.QtWidgets import QWidget

        from ui.components.panels.import_export_panel import ImportExportPanel

        parent_widget = QWidget()
        qtbot.addWidget(parent_widget)

        panel = ImportExportPanel(parent_widget)
        qtbot.addWidget(panel)


    def test_file_operations(self, qtbot):
        """Test file import/export operations"""
        from PySide6.QtWidgets import QWidget

        from ui.components.panels.import_export_panel import ImportExportPanel

        parent_widget = QWidget()
        qtbot.addWidget(parent_widget)

        panel = ImportExportPanel(parent_widget)
        qtbot.addWidget(panel)

        # Test setting ROM data
        panel.set_rom_data("/test/path/test_rom.smc", 0x400000)
        assert panel.rom_path == "/test/path/test_rom.smc"
        assert panel.rom_size == 0x400000

        # Test setting sprite data
        test_sprites = [(0x1000, 0.8), (0x2000, 0.9)]
        panel.set_found_sprites(test_sprites)
        assert panel.found_sprites == test_sprites

@pytest.mark.usefixtures("isolated_managers")
class TestStatusPanel:
    """Test StatusPanel functionality"""

    # Uses isolated_managers fixture for test isolation

    # Using parent_widget fixture from qt_test_helpers instead of mock_parent

    def test_status_panel_creation(self, qtbot):
        """Test StatusPanel creation"""
        from PySide6.QtWidgets import QWidget

        from core.di_container import inject
        from core.managers.application_state_manager import ApplicationStateManager
        from core.services.rom_cache import ROMCache
        from ui.components.panels.status_panel import StatusPanel

        parent_widget = QWidget()
        qtbot.addWidget(parent_widget)

        panel = StatusPanel(
            parent_widget,
            settings_manager=inject(ApplicationStateManager),
            rom_cache=inject(ROMCache)
        )
        qtbot.addWidget(panel)


    def test_status_updates(self, qtbot):
        """Test status message updates"""
        from PySide6.QtWidgets import QWidget

        from core.di_container import inject
        from core.managers.application_state_manager import ApplicationStateManager
        from core.services.rom_cache import ROMCache
        from ui.components.panels.status_panel import StatusPanel

        parent_widget = QWidget()
        qtbot.addWidget(parent_widget)

        panel = StatusPanel(
            parent_widget,
            settings_manager=inject(ApplicationStateManager),
            rom_cache=inject(ROMCache)
        )
        qtbot.addWidget(panel)

        # Ensure the parent widget is shown so the entire hierarchy is visible
        parent_widget.show()
        panel.show()

        # Test status update - use actual StatusPanel methods and attributes
        panel.update_status("Scanning ROM...")
        assert panel.detection_info.text() == "Scanning ROM..."

        # Test progress bar functionality
        panel.show_progress(0, 100)

        # Test the actual progress bar state directly
        assert panel.scan_progress.minimum() == 0
        assert panel.scan_progress.maximum() == 100
        assert panel.scan_progress.value() == 0  # setValue(minimum) in show_progress

        # Test update_progress method - should work since show_progress makes it visible
        # and the parent hierarchy is shown
        panel.update_progress(50)
        assert panel.scan_progress.value() == 50

        # Test hide functionality
        panel.hide_progress()
        # Progress bar should still have the value even when hidden
        assert panel.scan_progress.value() == 50

        # Test update_progress when progress bar is hidden (should not update)
        panel.update_progress(25)  # Should not change value since bar is hidden
        assert panel.scan_progress.value() == 50  # Should still be 50

        # Show again and test update works
        panel.show_progress(0, 100)
        panel.update_progress(75)
        assert panel.scan_progress.value() == 75


@pytest.mark.usefixtures("isolated_managers")
class TestRangeScanDialog:
    """Test RangeScanDialog functionality"""

    # Uses isolated_managers fixture for test isolation

    # Using parent_widget fixture from qt_test_helpers instead of mock_parent

    def test_range_scan_dialog_creation(self, qtbot):
        """Test RangeScanDialog creation"""
        from PySide6.QtWidgets import QWidget

        from ui.components.dialogs.range_scan_dialog import RangeScanDialog

        parent_widget = QWidget()
        qtbot.addWidget(parent_widget)

        dialog = RangeScanDialog(current_offset=0x10000, rom_size=0x400000, parent=parent_widget)
        qtbot.addWidget(dialog)

        # Check that attributes are set correctly
        assert dialog.current_offset == 0x10000
        assert dialog.rom_size == 0x400000

    def test_scan_parameters(self, qtbot):
        """Test scan parameter collection"""
        from PySide6.QtWidgets import QWidget

        from ui.components.dialogs.range_scan_dialog import RangeScanDialog

        parent_widget = QWidget()
        qtbot.addWidget(parent_widget)

        dialog = RangeScanDialog(current_offset=0x10000, rom_size=0x400000, parent=parent_widget)
        qtbot.addWidget(dialog)

        # Test default range selection (index 2 = ±16KB)
        start_offset, end_offset = dialog.get_range()

        # The dialog should calculate the range based on current_offset and selected range size
        # Default is ±16KB (0x4000), so from 0x10000:
        # start = max(0, 0x10000 - 0x4000) = 0xC000
        # end = min(0x3FFFFF, 0x10000 + 0x4000) = 0x14000
        assert start_offset == 0xC000
        assert end_offset == 0x14000

    def test_validation_with_large_range(self, qtbot):
        """Test dialog can handle large range selection"""
        from PySide6.QtWidgets import QWidget

        from ui.components.dialogs.range_scan_dialog import RangeScanDialog

        parent_widget = QWidget()
        qtbot.addWidget(parent_widget)

        # Create dialog with offset near the beginning of a large ROM
        dialog = RangeScanDialog(current_offset=0x10000, rom_size=0x400000, parent=parent_widget)
        qtbot.addWidget(dialog)

        # Select the largest range option (±256KB = index 4)
        dialog.range_combo.setCurrentIndex(4)

        # Get the calculated range
        start_offset, end_offset = dialog.get_range()

        # With ±256KB (0x40000) from 0x10000:
        # start = max(0, 0x10000 - 0x40000) = 0
        # end = min(0x3FFFFF, 0x10000 + 0x40000) = 0x50000
        assert start_offset == 0
        assert end_offset == 0x50000

        # Verify the range is large but valid
        range_size = end_offset - start_offset
        assert range_size == 0x50000  # 320KB range
        assert range_size <= 0x1000000  # Less than 16MB max
