"""
Integration tests for StatusPanel cache statistics display.

This module provides comprehensive testing of StatusPanel's cache functionality:
- Cache status indicators (enabled/disabled/error states)
- Real-time cache statistics updates
- Settings integration (show_indicators setting)

import utils.rom_cache as rom_cache_module

import utils.rom_cache as rom_cache_module

import utils.rom_cache as rom_cache_module

import utils.rom_cache as rom_cache_module
- Error handling and edge cases
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication

from core.managers import cleanup_managers, initialize_managers
from ui.components.panels.status_panel import StatusPanel
from utils.rom_cache import ROMCache

# ============================================================================
# Test Fixtures
# ============================================================================

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.qt_mock,
    pytest.mark.rom_data,
    pytest.mark.widget,
    pytest.mark.cache,
    pytest.mark.ci_safe,
    pytest.mark.qt_real,
    pytest.mark.requires_display,
]

@pytest.fixture(autouse=True)
def setup_teardown():
    """Initialize and cleanup managers for each test."""
    initialize_managers("TestStatusPanelCache")
    yield
    cleanup_managers()
    # Reset global cache instance
    import utils.rom_cache as rom_cache_module
    rom_cache_module._rom_cache_instance = None

@pytest.fixture
def temp_cache_dir(tmp_path):
    """Create a temporary cache directory."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    return str(cache_dir)

@pytest.fixture
def rom_cache(temp_cache_dir):
    """Create a ROM cache instance with test directory."""
    return ROMCache(cache_dir=temp_cache_dir)

@pytest.fixture
def mock_rom_cache(rom_cache):
    """Automatically patch get_rom_cache to return test instance."""
    with patch("utils.rom_cache.get_rom_cache") as mock_get:
        mock_get.return_value = rom_cache
        yield rom_cache

@pytest.fixture
def mock_settings_manager():
    """Create a mock settings manager with cache enabled by default."""
    with patch("utils.settings_manager.get_settings_manager") as mock_get:
        mock_manager = MagicMock()
        mock_manager.get.return_value = True  # show_indicators = True
        mock_manager.get_cache_enabled.return_value = True
        mock_get.return_value = mock_manager
        yield mock_manager

# ============================================================================
# Basic Cache Status Display Tests
# ============================================================================

class TestStatusPanelCacheBasics:
    """Test basic cache status display functionality."""

    def test_cache_status_widget_creation(self, qtbot, mock_settings_manager, mock_rom_cache):
        """Test that cache status widget is created when indicators are enabled."""
        panel = StatusPanel()
        qtbot.addWidget(panel)

        # Should have cache status widget
        assert hasattr(panel, "cache_status_widget")
        assert panel.cache_status_widget is not None
        assert hasattr(panel, "cache_icon_label")
        assert hasattr(panel, "cache_info_label")

    def test_cache_status_widget_hidden_when_disabled(self, qtbot, mock_settings_manager, mock_rom_cache):
        """Test that cache status widget is not created when indicators are disabled."""
        # Disable cache indicators in settings
        mock_settings_manager.get.return_value = False  # show_indicators = False

        panel = StatusPanel()
        qtbot.addWidget(panel)

        # Should not have cache status widget
        assert not hasattr(panel, "cache_status_widget")

    def test_cache_enabled_display(self, qtbot, mock_settings_manager, mock_rom_cache):
        """Test cache status display when cache is enabled."""
        panel = StatusPanel()
        qtbot.addWidget(panel)

        # Check initial state (cache enabled, empty)
        assert panel.cache_icon_label.text() == "✓"
        assert "green" in panel.cache_icon_label.styleSheet()
        assert "0 items" in panel.cache_info_label.text()
        assert "0.0MB" in panel.cache_info_label.text()

    def test_cache_disabled_display(self, qtbot, mock_settings_manager, mock_rom_cache):
        """Test cache status display when cache is disabled."""
        # Disable cache
        mock_settings_manager.get_cache_enabled.return_value = False

        panel = StatusPanel()
        qtbot.addWidget(panel)

        # Check disabled state
        assert panel.cache_icon_label.text() == "✗"
        assert "gray" in panel.cache_icon_label.styleSheet()
        assert panel.cache_info_label.text() == "Disabled"
        assert panel.cache_status_widget.toolTip() == "ROM caching is disabled"

# ============================================================================
# Cache Statistics Update Tests
# ============================================================================

class TestStatusPanelCacheStatistics:
    """Test cache statistics display and updates."""

    def test_cache_stats_with_data(self, qtbot, mock_settings_manager, mock_rom_cache):
        """Test cache statistics display with actual cached data."""
        panel = StatusPanel()
        qtbot.addWidget(panel)

        # Add test data to cache
        test_file1 = "/tmp/test1.sfc"
        test_file2 = "/tmp/test2.sfc"

        mock_rom_cache.save_sprite_locations(test_file1, {
            "Sprite1": {"offset": 0x1000, "bank": 0x20, "address": 0x8000, "compressed_size": 256}
        })
        mock_rom_cache.save_rom_info(test_file1, {"title": "Test ROM 1", "size": 1048576})
        mock_rom_cache.save_sprite_locations(test_file2, {
            "Sprite2": {"offset": 0x2000, "bank": 0x21, "address": 0x8000, "compressed_size": 512}
        })

        # Update cache status
        panel.update_cache_status()

        # Check updated display
        assert panel.cache_icon_label.text() == "✓"
        assert "green" in panel.cache_icon_label.styleSheet()

        # Should show correct item count
        info_text = panel.cache_info_label.text()
        assert "3 items" in info_text  # 2 sprite locations + 1 rom info

        # Check tooltip for detailed breakdown
        tooltip = panel.cache_status_widget.toolTip()
        assert "ROM Cache Statistics:" in tooltip
        assert "Total items: 3" in tooltip
        assert "Sprite locations: 2" in tooltip
        assert "ROM info: 1" in tooltip
        assert "Total size:" in tooltip

    def test_cache_stats_realtime_update(self, qtbot, mock_settings_manager, mock_rom_cache):
        """Test that cache statistics update in real-time as cache changes."""
        panel = StatusPanel()
        qtbot.addWidget(panel)

        # Initial state
        assert "0 items" in panel.cache_info_label.text()

        # Add data and update
        mock_rom_cache.save_sprite_locations("/tmp/test.sfc", {
            "Sprite1": {"offset": 0x1000, "bank": 0x20, "address": 0x8000, "compressed_size": 256}
        })
        panel.update_cache_status()

        # Should reflect the change
        assert "1 items" in panel.cache_info_label.text()

        # Add more data
        mock_rom_cache.save_rom_info("/tmp/test.sfc", {"title": "Test ROM", "size": 1048576})
        panel.update_cache_status()

        # Should show updated count
        assert "2 items" in panel.cache_info_label.text()

    def test_cache_size_formatting(self, qtbot, mock_settings_manager, mock_rom_cache):
        """Test that cache size is properly formatted in MB."""
        panel = StatusPanel()
        qtbot.addWidget(panel)

        # Mock cache stats with specific size
        def mock_get_cache_stats():
            return {
                "total_files": 5,
                "total_size_bytes": 5 * 1024 * 1024 + 512 * 1024,  # 5.5 MB
                "sprite_location_caches": 3,
                "rom_info_caches": 1,
                "scan_progress_caches": 1,
                "cache_dir": "/test/cache"
            }

        mock_rom_cache.get_cache_stats = mock_get_cache_stats

        # Update display
        panel.update_cache_status()

        # Check size formatting
        assert "5 items" in panel.cache_info_label.text()
        assert "5.5MB" in panel.cache_info_label.text()

# ============================================================================
# Error Handling Tests
# ============================================================================

class TestStatusPanelCacheErrorHandling:
    """Test error handling in cache status display."""

    def test_cache_stats_error_display(self, qtbot, mock_settings_manager, mock_rom_cache):
        """Test display when cache statistics cannot be retrieved."""
        panel = StatusPanel()
        qtbot.addWidget(panel)

        # Make get_cache_stats raise an exception
        mock_rom_cache.get_cache_stats = MagicMock(side_effect=RuntimeError("Cache error"))

        # Update should handle the error gracefully
        panel.update_cache_status()

        # Should show error state
        assert panel.cache_icon_label.text() == "⚠"
        assert "orange" in panel.cache_icon_label.styleSheet()
        assert panel.cache_info_label.text() == "Error"
        assert panel.cache_status_widget.toolTip() == "Error reading cache statistics"

    def test_cache_creation_error_handling(self, qtbot, mock_settings_manager):
        """Test handling when cache cannot be created."""
        # Make get_rom_cache raise an exception
        with patch("utils.rom_cache.get_rom_cache", side_effect=RuntimeError("Cache init failed")):
            panel = StatusPanel()
            qtbot.addWidget(panel)

            # Should show error state
            assert panel.cache_icon_label.text() == "⚠"
            assert panel.cache_info_label.text() == "Error"

# ============================================================================
# Settings Integration Tests
# ============================================================================

class TestStatusPanelSettingsIntegration:
    """Test integration with settings manager."""

    def test_cache_status_respects_show_indicators_setting(self, qtbot, mock_rom_cache):
        """Test that cache status respects the show_indicators setting."""
        # Test with indicators enabled
        with patch("utils.settings_manager.get_settings_manager") as mock_get:
            mock_manager = MagicMock()
            mock_manager.get.return_value = True  # show_indicators = True
            mock_manager.get_cache_enabled.return_value = True
            mock_get.return_value = mock_manager

            panel1 = StatusPanel()
            qtbot.addWidget(panel1)
            assert hasattr(panel1, "cache_status_widget")

        # Test with indicators disabled
        with patch("utils.settings_manager.get_settings_manager") as mock_get:
            mock_manager = MagicMock()
            mock_manager.get.return_value = False  # show_indicators = False
            mock_manager.get_cache_enabled.return_value = True
            mock_get.return_value = mock_manager

            panel2 = StatusPanel()
            qtbot.addWidget(panel2)
            assert not hasattr(panel2, "cache_status_widget")

    def test_cache_enabled_setting_changes(self, qtbot, mock_settings_manager, mock_rom_cache):
        """Test that status updates when cache enabled setting changes."""
        panel = StatusPanel()
        qtbot.addWidget(panel)

        # Initially enabled
        assert panel.cache_icon_label.text() == "✓"

        # Change to disabled
        mock_settings_manager.get_cache_enabled.return_value = False
        panel.update_cache_status()

        # Should show disabled state
        assert panel.cache_icon_label.text() == "✗"
        assert panel.cache_info_label.text() == "Disabled"

        # Change back to enabled
        mock_settings_manager.get_cache_enabled.return_value = True
        panel.update_cache_status()

        # Should show enabled state again
        assert panel.cache_icon_label.text() == "✓"

# ============================================================================
# Integration with Other Panel Features
# ============================================================================

class TestStatusPanelIntegration:
    """Test integration of cache status with other StatusPanel features."""

    def test_cache_status_with_progress_bar(self, qtbot, mock_settings_manager, mock_rom_cache):
        """Test that cache status works alongside progress bar."""
        panel = StatusPanel()
        qtbot.addWidget(panel)
        panel.show()  # Ensure widget is shown

        # Show progress bar
        panel.show_progress(0, 100)

        # Process events to ensure visibility updates
        QApplication.processEvents()

        assert panel.scan_progress.isVisible()

        # Cache status should still be visible
        assert panel.cache_status_widget.isVisible()

        # Update progress
        panel.update_progress(50)
        assert panel.scan_progress == 50

        # Hide progress
        panel.hide_progress()
        QApplication.processEvents()

        assert not panel.scan_progress.isVisible()

        # Cache status should remain visible
        assert panel.cache_status_widget.isVisible()

    def test_status_updates_with_cache_info(self, qtbot, mock_settings_manager, mock_rom_cache):
        """Test that general status updates work alongside cache display."""
        panel = StatusPanel()
        qtbot.addWidget(panel)

        # Update general status
        panel.update_status("Scanning for sprites...")
        assert panel.detection_info.text() == "Scanning for sprites..."

        # Cache status should be independent
        assert panel.cache_icon_label.text() == "✓"

        # Update with cache-related status
        panel.update_status("💾 Loading from cache...")
        assert "Loading from cache" in panel.detection_info.text()

        # Cache icon should remain the same
        assert panel.cache_icon_label.text() == "✓"

# ============================================================================
# Visual and Layout Tests
# ============================================================================

class TestStatusPanelVisualLayout:
    """Test visual aspects and layout of cache status display."""

    def test_cache_status_layout(self, qtbot, mock_settings_manager, mock_rom_cache):
        """Test the layout of cache status components."""
        panel = StatusPanel()
        qtbot.addWidget(panel)

        # Get layout
        cache_layout = panel.cache_status_widget.layout()
        assert cache_layout is not None

        # Should have label, icon, info, and stretch
        assert cache_layout.count() >= 4

        # First item should be "ROM Cache:" label
        label_item = cache_layout.itemAt(0)
        assert label_item is not None
        label_widget = label_item.widget()
        assert label_widget.text() == "ROM Cache:"

    def test_cache_tooltip_formatting(self, qtbot, mock_settings_manager, mock_rom_cache):
        """Test that cache tooltip is properly formatted."""
        panel = StatusPanel()
        qtbot.addWidget(panel)

        # Add varied data
        mock_rom_cache.save_sprite_locations("/tmp/test1.sfc", {
            "Sprite1": {"offset": 0x1000, "bank": 0x20, "address": 0x8000, "compressed_size": 256}
        })
        mock_rom_cache.save_rom_info("/tmp/test2.sfc", {"title": "Test", "size": 1048576})
        scan_params = {"start_offset": 0, "end_offset": 0x100000, "alignment": 0x100}
        mock_rom_cache.save_partial_scan_results("/tmp/test3.sfc", scan_params, [], 0x50000, False)

        panel.update_cache_status()

        # Check tooltip structure
        tooltip = panel.cache_status_widget.toolTip()
        lines = tooltip.split("\n")

        assert len(lines) >= 5
        assert lines[0] == "ROM Cache Statistics:"
        assert "Total items:" in lines[1]
        assert "- Sprite locations:" in lines[2]
        assert "- ROM info:" in lines[3]
        assert "- Scan progress:" in lines[4]
