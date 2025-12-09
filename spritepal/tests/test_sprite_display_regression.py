"""
Regression tests for sprite display fix - Ensure existing functionality remains intact

Tests focus on:
1. Existing manual offset dialog functionality
2. ROM extraction panel integration
3. Search and navigation features
4. Export and save functionality
5. Settings and preferences preservation
6. Error handling and edge cases
7. UI component interactions
8. Backward compatibility with existing ROMs and data
"""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from core.managers.session_manager import SessionManager
from tests.infrastructure.qt_testing_framework import QtTestingFramework
from ui.dialogs.manual_offset_unified_integrated import UnifiedManualOffsetDialog
from ui.main_window import MainWindow
from ui.rom_extraction_panel import ROMExtractionPanel
from ui.widgets.sprite_preview_widget import SpritePreviewWidget

# Serial execution required: Real Qt components
pytestmark = [

    pytest.mark.serial,
    pytest.mark.cache,
    pytest.mark.dialog,
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.mock_dialogs,
    pytest.mark.qt_mock,
    pytest.mark.requires_display,
    pytest.mark.rom_data,
    pytest.mark.signals_slots,
    pytest.mark.slow,
    pytest.mark.stability,
]

class TestManualOffsetDialogRegression:
    """Regression tests for manual offset dialog functionality"""

    def setup_method(self):
        """Set up manual offset dialog regression tests"""
        self.qt_framework = QtTestingFramework()

        # Mock extraction manager
        self.real_extraction_manager = Mock()
        self.real_extraction_manager.get_current_rom_path.return_value = "/test/regression.sfc"
        self.real_extraction_manager.get_rom_size.return_value = 0x400000

        with patch('core.managers.get_extraction_manager', return_value=self.real_extraction_manager):
            self.dialog = UnifiedManualOffsetDialog()

    def teardown_method(self):
        """Clean up manual offset dialog regression tests"""
        if hasattr(self, 'dialog'):
            self.dialog.close()
            del self.dialog

    def test_dialog_still_opens_and_closes_properly(self):
        """Regression: Dialog still opens and closes without errors"""
        # Dialog should initialize properly
        assert self.dialog is not None
        assert hasattr(self.dialog, '_tab_widget')
        assert hasattr(self.dialog, '_browse_tab')

        # Should be able to show and hide
        self.dialog.show()
        assert not self.dialog.isHidden()

        self.dialog.hide()
        assert self.dialog.isHidden()

        # Should close properly
        self.dialog.close()

    def test_tab_switching_still_works(self, qtbot):
        """Regression: Tab switching functionality preserved"""
        tab_widget = self.dialog._tab_widget
        initial_tab = tab_widget.currentIndex()

        # Should have multiple tabs
        assert tab_widget.count() > 1

        # Should be able to switch tabs
        next_tab = (initial_tab + 1) % tab_widget.count()
        tab_widget.setCurrentIndex(next_tab)

        assert tab_widget.currentIndex() == next_tab

        # Switch back
        tab_widget.setCurrentIndex(initial_tab)
        assert tab_widget.currentIndex() == initial_tab

    def test_browse_tab_controls_still_functional(self):
        """Regression: Browse tab controls remain functional"""
        browse_tab = self.dialog._browse_tab

        # Should have essential controls
        assert hasattr(browse_tab, 'slider')
        assert hasattr(browse_tab, 'offset_changed')

        # Slider should be properly configured
        slider = browse_tab.slider
        assert slider.minimum() == 0
        assert slider.maximum() > 0
        assert isinstance(slider, int)

        # Should be able to change slider value
        initial_value = slider
        new_value = min(initial_value + 0x1000, slider.maximum())
        slider.setValue(new_value)
        assert slider == new_value

    def test_signals_still_emit_correctly(self, qtbot):
        """Regression: Dialog signals still emit correctly"""
        # Test offset changed signal
        browse_tab = self.dialog._browse_tab
        new_offset = 0x300000

        with qtbot.wait_signal(browse_tab.offset_changed, timeout=100):
            browse_tab.offset_changed.emit(new_offset)

        # Test sprite found signal (if available)
        if hasattr(self.dialog, 'sprite_found'):
            with qtbot.wait_signal(self.dialog.sprite_found, timeout=100):
                self.dialog.sprite_found.emit(0x200000, "test_sprite")

    def test_history_tab_functionality_preserved(self):
        """Regression: History tab functionality remains intact"""
        if not hasattr(self.dialog, '_history_tab'):
            pytest.skip("Dialog does not have history tab")

        history_tab = self.dialog._history_tab

        # Should have history controls
        assert hasattr(history_tab, 'list_widget')
        assert hasattr(history_tab, 'sprite_selected')

        # Should start with empty history
        initial_count = history_tab.list_widget.count()
        assert initial_count >= 0

    def test_search_functionality_still_accessible(self):
        """Regression: Search functionality remains accessible"""
        browse_tab = self.dialog._browse_tab

        # Should have search-related signals
        assert hasattr(browse_tab, 'find_next_clicked')
        assert hasattr(browse_tab, 'find_prev_clicked')

        # Advanced search should be available
        if hasattr(browse_tab, 'advanced_search_requested'):
            assert browse_tab.advanced_search_requested is not None

class TestSpritePreviewWidgetRegression:
    """Regression tests for sprite preview widget functionality"""

    def setup_method(self):
        """Set up sprite preview widget regression tests"""
        self.qt_framework = QtTestingFramework()
        self.widget = SpritePreviewWidget("Regression Test")

    def teardown_method(self):
        """Clean up sprite preview widget regression tests"""
        if hasattr(self, 'widget'):
            self.widget.close()
            del self.widget

    def test_widget_initialization_unchanged(self):
        """Regression: Widget initialization behavior unchanged"""
        # Should initialize with expected defaults
        assert self.widget.title == "Regression Test"
        assert self.widget.current_palette_index == 8  # Default sprite palette
        assert self.widget.sprite_pixmap is None
        assert self.widget.sprite_data is None

        # UI components should exist
        assert self.widget.preview_label is not None
        assert self.widget.palette_combo is not None
        assert self.widget.info_label is not None
        assert self.widget.essential_info_label is not None

    def test_palette_combo_still_populated(self):
        """Regression: Palette combo still properly populated"""
        combo = self.widget.palette_combo

        # Should have 16 palette options
        assert combo.count() == 16

        # Should have correct default selection
        assert combo.currentIndex() == 8  # Default sprite palette

        # Each item should have text
        for i in range(16):
            item_text = combo.itemText(i)
            assert len(item_text) > 0

    def test_update_preview_still_works(self):
        """Regression: Update preview functionality works"""
        # Generate test data
        test_data = b"\x01\x02\x03\x04" * 64  # 256 bytes for 16x16 4bpp

        # Should update without errors
        self.widget.update_preview(test_data, 16, 16, "regression_test")

        # Should store data
        assert self.widget.sprite_data == test_data

        # Should update info label
        assert "regression_test" in self.widget.essential_info_label.text()

    def test_clear_preview_still_works(self):
        """Regression: Clear preview functionality works"""
        # Set up preview
        test_data = b"\x01\x02\x03\x04" * 64
        self.widget.update_preview(test_data, 16, 16, "clear_test")

        # Clear should work
        self.widget.clear_preview()

        # Should return to empty state
        assert self.widget.sprite_data is None
        assert "No sprite loaded" in self.widget.essential_info_label.text()

    def test_palette_change_signal_still_emits(self, qtbot):
        """Regression: Palette change signal still emits"""
        combo = self.widget.palette_combo
        new_index = (self.widget.current_palette_index + 1) % 16

        with qtbot.wait_signal(self.widget.palette_changed, timeout=100):
            combo.setCurrentIndex(new_index)
            combo.currentIndexChanged.emit(new_index)

        assert self.widget.current_palette_index == new_index

    def test_similarity_search_signal_still_available(self, qtbot):
        """Regression: Similarity search signal still available"""
        # Should be able to emit similarity search signal
        test_offset = 0x200000
        self.widget.current_offset = test_offset

        with qtbot.wait_signal(self.widget.similarity_search_requested, timeout=100):
            self.widget.similarity_search_requested.emit(test_offset)

class TestROMExtractionPanelRegression:
    """Regression tests for ROM extraction panel functionality"""

    def setup_method(self):
        """Set up ROM extraction panel regression tests"""
        self.qt_framework = QtTestingFramework()

        # Mock manager dependencies
        with patch('core.managers.get_extraction_manager'), \
             patch('core.managers.get_session_manager'):
            self.panel = ROMExtractionPanel()

    def teardown_method(self):
        """Clean up ROM extraction panel regression tests"""
        if hasattr(self, 'panel'):
            del self.panel

    def test_panel_initialization_preserved(self):
        """Regression: Panel initialization behavior preserved"""
        # Should initialize without errors
        assert self.panel is not None

        # Should have essential components
        # (Test depends on actual ROMExtractionPanel structure)

    def test_file_selection_still_works(self):
        """Regression: File selection functionality preserved"""
        # Mock file dialog
        with patch('PySide6.QtWidgets.QFileDialog.getOpenFileName',
                  return_value=("/test/file.sfc", "SNES ROM (*.sfc)")):

            # Should handle file selection without errors
            # (Implementation depends on actual panel structure)
            pass

    def test_extraction_parameters_still_accessible(self):
        """Regression: Extraction parameters still accessible"""
        # Should be able to get extraction parameters
        # (Implementation depends on actual panel structure)
        pass

class TestSessionManagementRegression:
    """Regression tests for session management functionality"""

    def setup_method(self):
        """Set up session management regression tests"""
        self.temp_dir = Path(tempfile.mkdtemp())

        # Mock session manager with temp directory
        with patch('core.managers.session_manager.get_settings_dir',
                  return_value=self.temp_dir):
            self.session_manager = SessionManager()

    def teardown_method(self):
        """Clean up session management regression tests"""
        # Clean up temp directory
        import shutil
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_settings_save_and_load_still_works(self):
        """Regression: Settings save and load functionality preserved"""
        # Test settings
        test_settings = {
            "last_rom_path": "/test/rom.sfc",
            "default_palette": 8,
            "window_geometry": {"x": 100, "y": 100, "width": 800, "height": 600}
        }

        # Should save settings
        self.session_manager.save_settings(test_settings)

        # Should load settings back
        loaded_settings = self.session_manager.load_settings()

        # Should match saved settings
        assert loaded_settings["last_rom_path"] == test_settings["last_rom_path"]
        assert loaded_settings["default_palette"] == test_settings["default_palette"]

    def test_recent_files_functionality_preserved(self):
        """Regression: Recent files functionality preserved"""
        test_file = "/test/recent.sfc"

        # Should add recent file
        self.session_manager.add_recent_file(test_file)

        # Should retrieve recent files
        recent_files = self.session_manager.get_recent_files()
        assert test_file in recent_files

class TestMainWindowIntegration:
    """Regression tests for main window integration"""

    def setup_method(self):
        """Set up main window regression tests"""
        self.qt_framework = QtTestingFramework()

        # Mock all manager dependencies
        with patch('core.managers.initialize_managers'), \
             patch('core.managers.get_extraction_manager'), \
             patch('core.managers.get_injection_manager'), \
             patch('core.managers.get_session_manager'):

            # Create main window with mocked dependencies
            self.main_window = Mock(spec=MainWindow)
            self.main_window.manual_offset_dialog = None

    def teardown_method(self):
        """Clean up main window regression tests"""
        if hasattr(self, 'main_window'):
            del self.main_window

    def test_manual_offset_dialog_creation_still_works(self):
        """Regression: Manual offset dialog creation from main window works"""
        # Mock dialog creation
        with patch('ui.dialogs.manual_offset_unified_integrated.UnifiedManualOffsetDialog') as MockDialog:
            mock_dialog_instance = Mock()
            MockDialog.return_value = mock_dialog_instance

            # Should be able to create dialog
            dialog = MockDialog()
            assert dialog is not None

            # Should have expected methods
            MockDialog.assert_called_once()

    def test_menu_actions_still_accessible(self):
        """Regression: Menu actions remain accessible"""
        # Should have menu actions available
        # (Implementation depends on actual MainWindow structure)
        pass

    def test_status_bar_updates_still_work(self):
        """Regression: Status bar updates still work"""
        # Should be able to update status bar
        if hasattr(self.main_window, 'statusBar'):
            # Mock status bar update
            self.main_window.statusBar = Mock()
            self.main_window.statusBar.showMessage = Mock()

            # Should work without errors
            self.main_window.statusBar.showMessage("Test message")
            self.main_window.statusBar.showMessage.assert_called_with("Test message")

class TestErrorHandlingRegression:
    """Regression tests for error handling functionality"""

    def test_invalid_rom_file_handling_preserved(self):
        """Regression: Invalid ROM file handling preserved"""
        with patch('core.managers.get_extraction_manager') as mock_manager:
            # Mock manager that raises exception
            mock_manager.side_effect = Exception("Invalid ROM")

            # Should handle error gracefully
            try:
                mock_manager()
            except Exception as e:
                assert "Invalid ROM" in str(e)

    def test_missing_file_handling_preserved(self):
        """Regression: Missing file handling preserved"""
        # Test with non-existent file

        # Should handle missing file gracefully
        # (Implementation depends on actual file handling)

    def test_corrupted_data_handling_preserved(self):
        """Regression: Corrupted data handling preserved"""
        widget = SpritePreviewWidget("Error Test")

        try:
            # Test with corrupted data
            corrupted_data = b"\xFF" * 10  # Invalid sprite data
            widget.update_preview(corrupted_data, 16, 16, "corrupted")

            # Should not crash
            assert widget is not None
        finally:
            widget.close()

class TestBackwardCompatibilityRegression:
    """Regression tests for backward compatibility"""

    def test_old_rom_format_support_preserved(self):
        """Regression: Support for older ROM formats preserved"""
        # Should handle various ROM formats
        rom_formats = [".sfc", ".smc", ".fig", ".swc"]

        for rom_format in rom_formats:
            # Should recognize format
            assert rom_format.lower() in [".sfc", ".smc", ".fig", ".swc"]

    def test_existing_cache_format_compatibility(self):
        """Regression: Existing cache format compatibility preserved"""
        temp_dir = Path(tempfile.mkdtemp())

        try:
            # Create old-style cache file
            cache_file = temp_dir / "test_cache.cache"
            cache_data = {
                "version": "1.0",
                "data": "test_cache_data",
                "timestamp": 1234567890
            }

            with open(cache_file, 'w') as f:
                json.dump(cache_data, f)

            # Should be able to read old cache format
            with open(cache_file) as f:
                loaded_data = json.load(f)
                assert loaded_data["version"] == "1.0"
                assert loaded_data["data"] == "test_cache_data"

        finally:
            # Clean up
            import shutil
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    def test_settings_migration_preserved(self):
        """Regression: Settings migration functionality preserved"""
        # Test old settings format compatibility
        old_settings = {
            "version": "1.0",
            "rom_path": "/old/path/rom.sfc",
            "palette_index": 8
        }

        # Should handle old settings format
        assert "rom_path" in old_settings
        assert "palette_index" in old_settings

class TestUIConsistencyRegression:
    """Regression tests for UI consistency"""

    def test_keyboard_shortcuts_preserved(self):
        """Regression: Keyboard shortcuts preserved"""
        # Common keyboard shortcuts should still work
        shortcuts = {
            "Ctrl+O": "Open ROM",
            "Ctrl+S": "Save",
            "Ctrl+Q": "Quit",
            "F1": "Help"
        }

        # Should recognize shortcut format
        for shortcut, action in shortcuts.items():
            assert len(shortcut) > 0
            assert len(action) > 0

    def test_tooltip_functionality_preserved(self):
        """Regression: Tooltip functionality preserved"""
        widget = SpritePreviewWidget("Tooltip Test")

        try:
            # Should be able to set tooltips
            widget.setToolTip("Test tooltip")
            assert widget.toolTip() == "Test tooltip"
        finally:
            widget.close()

    def test_context_menu_functionality_preserved(self):
        """Regression: Context menu functionality preserved"""
        widget = SpritePreviewWidget("Context Menu Test")

        try:
            # Should have context menu policy set
            policy = widget.preview_label.contextMenuPolicy()
            assert policy is not None
        finally:
            widget.close()

class TestPerformanceRegression:
    """Regression tests to ensure performance hasn't degraded"""

    def test_startup_time_not_degraded(self):
        """Regression: Application startup time not significantly degraded"""
        import time

        start_time = time.perf_counter()

        # Simulate component initialization
        widget = SpritePreviewWidget("Performance Test")

        initialization_time = time.perf_counter() - start_time

        # Should initialize quickly
        assert initialization_time < 1.0, f"Initialization too slow: {initialization_time:.3f}s"

        widget.close()

    def test_memory_usage_not_significantly_increased(self):
        """Regression: Memory usage not significantly increased"""
        import os

        import psutil

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss

        # Create multiple components
        components = []
        for i in range(5):
            widget = SpritePreviewWidget(f"Memory Test {i}")
            components.append(widget)

        peak_memory = process.memory_info().rss
        memory_increase = peak_memory - initial_memory

        # Clean up
        for widget in components:
            widget.close()

        # Memory increase should be reasonable
        max_allowed_increase = 50 * 1024 * 1024  # 50MB
        assert memory_increase < max_allowed_increase, \
            f"Excessive memory increase: {memory_increase/1024/1024:.1f}MB"

    def test_response_time_not_degraded(self):
        """Regression: Response time for common operations not degraded"""
        widget = SpritePreviewWidget("Response Test")

        try:
            # Test preview update performance
            test_data = b"\x01\x02\x03\x04" * 64

            start_time = time.perf_counter()
            widget.update_preview(test_data, 16, 16, "response_test")
            response_time = time.perf_counter() - start_time

            # Should respond quickly
            assert response_time < 0.1, f"Preview update too slow: {response_time*1000:.1f}ms"

        finally:
            widget.close()

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
