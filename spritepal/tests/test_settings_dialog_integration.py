"""
Integration tests for SettingsDialog functionality.

This module provides comprehensive testing of settings dialog integration with:
- Settings persistence and loading
- Cache system integration
- UI component interactions
- Error handling scenarios
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from core.managers import cleanup_managers, initialize_managers
from ui.dialogs.settings_dialog import SettingsDialog
from utils.rom_cache import ROMCache
from utils.settings_manager import SettingsManager

# ============================================================================
# Test Fixtures
# ============================================================================

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.dialog,
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.mock_dialogs,
    pytest.mark.qt_mock,
    pytest.mark.rom_data,
    pytest.mark.widget,
    pytest.mark.cache,
    pytest.mark.ci_safe,
    pytest.mark.signals_slots,
    pytest.mark.slow,
]

@pytest.fixture(autouse=True)
def setup_teardown():
    """Initialize and cleanup managers for each test."""
    initialize_managers("TestSettingsDialog")
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
def temp_dumps_dir(tmp_path):
    """Create a temporary dumps directory."""
    dumps_dir = tmp_path / "dumps"
    dumps_dir.mkdir()
    return str(dumps_dir)

@pytest.fixture
def mock_settings_manager():
    """Create a mock settings manager with default values."""
    mock_manager = MagicMock(spec=SettingsManager)

    # Set up default return values with side_effect for different keys
    def mock_get(section, key, default=None):
        """Mock get method that returns appropriate types based on key."""
        settings_map = {
            ("ui", "restore_position"): True,
            ("session", "auto_save"): True,
            ("paths", "default_dumps_dir"): "",
            ("cache", "auto_cleanup"): True,
            ("cache", "show_indicators"): True,
        }
        return settings_map.get((section, key), default)

    mock_manager.get.side_effect = mock_get
    mock_manager.get_cache_enabled.return_value = True
    mock_manager.get_cache_location.return_value = ""
    mock_manager.get_cache_max_size_mb.return_value = 100
    mock_manager.get_cache_expiration_days.return_value = 30

    return mock_manager

@pytest.fixture
def rom_cache(temp_cache_dir):
    """Create a ROM cache instance."""
    return ROMCache(cache_dir=temp_cache_dir)

@pytest.fixture
def settings_dialog(qtbot, mock_settings_manager, rom_cache):
    """Create a settings dialog with mocked dependencies."""
    with patch("ui.dialogs.settings_dialog.get_settings_manager") as mock_get_settings:
        with patch("ui.dialogs.settings_dialog.get_rom_cache") as mock_get_cache:
            mock_get_settings.return_value = mock_settings_manager
            mock_get_cache.return_value = rom_cache

            dialog = SettingsDialog()
            qtbot.addWidget(dialog)

            yield dialog, mock_settings_manager, rom_cache

# ============================================================================
# Settings Loading and Initialization Tests
# ============================================================================

class TestSettingsDialogInitialization:
    """Test settings dialog initialization and loading."""

    def test_dialog_creation(self, settings_dialog):
        """Test that settings dialog creates successfully."""
        dialog, mock_settings, cache = settings_dialog

        # Dialog should be created
        assert dialog is not None
        assert dialog.windowTitle() == "SpritePal Settings"

        # Should have tab widget with correct tabs
        assert dialog.tab_widget.count() == 2
        assert dialog.tab_widget.tabText(0) == "General"
        assert dialog.tab_widget.tabText(1) == "Cache"

    def test_settings_loading(self, qtbot, mock_settings_manager, rom_cache):
        """Test that settings are loaded into UI components."""
        # Set up specific mock values for this test
        def mock_get_custom(section, key, default=None):
            settings_map = {
                ("ui", "restore_position"): True,
                ("session", "auto_save"): False,
                ("paths", "default_dumps_dir"): "/test/dumps",
                ("cache", "auto_cleanup"): True,
                ("cache", "show_indicators"): False,
            }
            return settings_map.get((section, key), default)

        mock_settings_manager.get.side_effect = mock_get_custom
        mock_settings_manager.get_cache_enabled.return_value = False
        mock_settings_manager.get_cache_location.return_value = "/custom/cache"
        mock_settings_manager.get_cache_max_size_mb.return_value = 250
        mock_settings_manager.get_cache_expiration_days.return_value = 14

        # Create dialog with the custom mocked settings
        with patch("ui.dialogs.settings_dialog.get_settings_manager") as mock_get_settings:
            with patch("ui.dialogs.settings_dialog.get_rom_cache") as mock_get_cache:
                mock_get_settings.return_value = mock_settings_manager
                mock_get_cache.return_value = rom_cache

                dialog = SettingsDialog()
                qtbot.addWidget(dialog)

        # Verify UI reflects the custom settings
        assert dialog.restore_window_check.isChecked()
        assert not dialog.auto_save_session_check.isChecked()
        assert dialog.dumps_dir_edit.text() == "/test/dumps"
        assert not dialog.cache_enabled_check.isChecked()
        assert dialog.cache_location_edit.text() == "/custom/cache"
        assert dialog.cache_size_spin == 250
        assert dialog.cache_expiry_spin == 14
        assert dialog.auto_cleanup_check.isChecked()
        assert not dialog.show_indicators_check.isChecked()

    def test_original_settings_storage(self, settings_dialog):
        """Test that original settings are stored for change detection."""
        dialog, mock_settings, cache = settings_dialog

        # Original settings should be stored
        assert dialog._original_settings is not None
        assert isinstance(dialog._original_settings, dict)

        # Should contain expected keys
        expected_keys = {
            "restore_window", "auto_save_session", "dumps_dir",
            "cache_enabled", "cache_location", "cache_max_size",
            "cache_expiry", "auto_cleanup", "show_indicators"
        }
        assert set(dialog._original_settings.keys()) == expected_keys

# ============================================================================
# Settings Saving and Persistence Tests
# ============================================================================

class TestSettingsSavingAndPersistence:
    """Test settings saving and persistence functionality."""

    def test_settings_saving(self, qtbot, settings_dialog):
        """Test that settings are saved when dialog is accepted."""
        dialog, mock_settings, cache = settings_dialog

        # Change some settings
        dialog.restore_window_check.setChecked(False)
        dialog.auto_save_session_check.setChecked(True)
        dialog.dumps_dir_edit.setText("/new/dumps")
        dialog.cache_enabled_check.setChecked(False)
        dialog.cache_location_edit.setText("/new/cache")
        dialog.cache_size_spin.setValue(500)
        dialog.cache_expiry_spin.setValue(7)
        dialog.auto_cleanup_check.setChecked(False)
        dialog.show_indicators_check.setChecked(True)

        # Accept dialog
        dialog.accept()

        # Verify settings were saved
        mock_settings.set.assert_any_call("ui", "restore_position", False)
        mock_settings.set.assert_any_call("session", "auto_save", True)
        mock_settings.set.assert_any_call("paths", "default_dumps_dir", "/new/dumps")
        mock_settings.set_cache_enabled.assert_called_with(False)
        mock_settings.set_cache_location.assert_called_with("/new/cache")
        mock_settings.set_cache_max_size_mb.assert_called_with(500)
        mock_settings.set_cache_expiration_days.assert_called_with(7)
        mock_settings.set.assert_any_call("cache", "auto_cleanup", False)
        mock_settings.set.assert_any_call("cache", "show_indicators", True)

        # Should save to disk
        mock_settings.save.assert_called()

    def test_settings_change_detection(self, settings_dialog):
        """Test that settings change detection works properly."""
        dialog, mock_settings, cache = settings_dialog

        # Initially no changes
        assert not dialog._has_settings_changed()

        # Make a change
        dialog.restore_window_check.setChecked(not dialog.restore_window_check.isChecked())

        # Should detect change
        assert dialog._has_settings_changed()

    def test_no_save_when_no_changes(self, settings_dialog):
        """Test that settings aren't saved when no changes are made."""
        dialog, mock_settings, cache = settings_dialog

        # Accept dialog without changes
        dialog.accept()

        # Should not call save methods
        mock_settings.save.assert_not_called()

    def test_settings_changed_signal(self, qtbot, settings_dialog):
        """Test that settings_changed signal is emitted when settings are saved."""
        dialog, mock_settings, cache = settings_dialog

        # Connect signal
        signal_emitted = []
        dialog.settings_changed.connect(lambda: signal_emitted.append(True))

        # Change a setting and accept
        dialog.cache_enabled_check.setChecked(False)
        dialog.accept()

        # Signal should be emitted
        assert len(signal_emitted) == 1

# ============================================================================
# Cache Integration Tests
# ============================================================================

class TestCacheIntegration:
    """Test cache system integration in settings dialog."""

    def test_cache_enable_disable_controls(self, qtbot, mock_settings_manager, rom_cache):
        """Test that cache controls are enabled/disabled based on cache checkbox."""
        # Start with cache disabled
        mock_settings_manager.get_cache_enabled.return_value = False

        with patch("ui.dialogs.settings_dialog.get_settings_manager") as mock_get_settings:
            with patch("ui.dialogs.settings_dialog.get_rom_cache") as mock_get_cache:
                mock_get_settings.return_value = mock_settings_manager
                mock_get_cache.return_value = rom_cache

                dialog = SettingsDialog()
                qtbot.addWidget(dialog)

        # Initially cache should be disabled, so controls should be disabled
        assert not dialog.cache_enabled_check.isChecked()
        assert not dialog.cache_location_edit.isEnabled()
        assert not dialog.cache_location_button.isEnabled()
        assert not dialog.cache_size_spin.isEnabled()
        assert not dialog.cache_expiry_spin.isEnabled()
        assert not dialog.auto_cleanup_check.isEnabled()
        assert not dialog.show_indicators_check.isEnabled()
        assert not dialog.clear_cache_button.isEnabled()

        # Enable cache
        dialog.cache_enabled_check.setChecked(True)

        # Cache controls should now be enabled
        assert dialog.cache_enabled_check.isChecked()
        assert dialog.cache_location_edit.isEnabled()
        assert dialog.cache_location_button.isEnabled()
        assert dialog.cache_size_spin.isEnabled()
        assert dialog.cache_expiry_spin.isEnabled()
        assert dialog.auto_cleanup_check.isEnabled()
        assert dialog.show_indicators_check.isEnabled()
        assert dialog.clear_cache_button.isEnabled()

        # Disable cache again
        dialog.cache_enabled_check.setChecked(False)

        # Cache controls should be disabled again
        assert not dialog.cache_enabled_check.isChecked()
        assert not dialog.cache_location_edit.isEnabled()
        assert not dialog.cache_location_button.isEnabled()
        assert not dialog.cache_size_spin.isEnabled()
        assert not dialog.cache_expiry_spin.isEnabled()
        assert not dialog.auto_cleanup_check.isEnabled()
        assert not dialog.show_indicators_check.isEnabled()
        assert not dialog.clear_cache_button.isEnabled()

    def test_cache_stats_display(self, settings_dialog):
        """Test that cache statistics are displayed correctly."""
        dialog, mock_settings, cache = settings_dialog

        # Add some test data to cache
        test_file = "/tmp/test.sfc"
        cache.save_sprite_locations(test_file, {"Sprite1": {"offset": 0x1000}})
        cache.save_rom_info(test_file, {"title": "Test ROM"})

        # Update stats
        dialog._update_cache_stats()

        # Should display cache information
        assert "cache" in dialog.cache_dir_label.text().lower()
        assert "files" in dialog.cache_files_label.text()
        assert "MB" in dialog.cache_size_label.text()

    def test_cache_stats_refresh(self, qtbot, settings_dialog):
        """Test that cache statistics refresh button works."""
        dialog, mock_settings, cache = settings_dialog

        # Click refresh button
        qtbot.mouseClick(dialog.refresh_stats_button, Qt.MouseButton.LeftButton)

        # Should update stats (no exception should occur)
        assert dialog.cache_files_label.text()  # Should have some text

    def test_cache_stats_error_handling(self, settings_dialog):
        """Test that cache statistics handle errors gracefully."""
        dialog, mock_settings, cache = settings_dialog

        # Make cache stats raise an exception
        cache.get_cache_stats = MagicMock(side_effect=RuntimeError("Cache error"))

        # Update stats should not crash
        dialog._update_cache_stats()

        # Should show error indicators
        assert "error" in dialog.cache_dir_label.text().lower()
        assert dialog.cache_files_label.text() == "N/A"
        assert dialog.cache_size_label.text() == "N/A"

# ============================================================================
# Cache Clearing Tests
# ============================================================================

class TestCacheClearingFunctionality:
    """Test cache clearing functionality."""

    def test_clear_cache_confirmation(self, qtbot, settings_dialog):
        """Test that clear cache asks for confirmation."""
        dialog, mock_settings, cache = settings_dialog

        # Mock message box to return No
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
            # Click clear cache button
            qtbot.mouseClick(dialog.clear_cache_button, Qt.MouseButton.LeftButton)

            # Cache should not be cleared
            assert not hasattr(cache, "clear_cache_called")

    def test_clear_cache_execution(self, qtbot, settings_dialog):
        """Test that cache is actually cleared when confirmed."""
        dialog, mock_settings, cache = settings_dialog

        # Add test data to cache
        test_file = "/tmp/test.sfc"
        cache.save_sprite_locations(test_file, {"Sprite1": {"offset": 0x1000}})

        # Verify cache has data
        initial_stats = cache.get_cache_stats()
        assert initial_stats["total_files"] > 0

        # Mock message box to return Yes and information box
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            with patch.object(QMessageBox, "information") as mock_info:
                # Click clear cache button
                qtbot.mouseClick(dialog.clear_cache_button, Qt.MouseButton.LeftButton)

                # Should show success message
                mock_info.assert_called_once()
                args = mock_info.call_args[0]
                assert "Successfully removed" in args[2]  # Message text

        # Cache should be cleared
        final_stats = cache.get_cache_stats()
        assert final_stats["total_files"] == 0

    def test_clear_cache_signal(self, qtbot, settings_dialog):
        """Test that cache_cleared signal is emitted."""
        dialog, mock_settings, cache = settings_dialog

        # Connect signal
        signal_emitted = []
        dialog.cache_cleared.connect(lambda: signal_emitted.append(True))

        # Mock message box to return Yes and information box
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            with patch.object(QMessageBox, "information"):
                # Click clear cache button
                qtbot.mouseClick(dialog.clear_cache_button, Qt.MouseButton.LeftButton)

        # Signal should be emitted
        assert len(signal_emitted) == 1

    def test_clear_cache_error_handling(self, qtbot, settings_dialog):
        """Test error handling during cache clearing."""
        dialog, mock_settings, cache = settings_dialog

        # Make clear_cache raise an exception
        cache.clear_cache = MagicMock(side_effect=RuntimeError("Clear failed"))

        # Mock message boxes
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            with patch.object(QMessageBox, "critical") as mock_error:
                # Click clear cache button
                qtbot.mouseClick(dialog.clear_cache_button, Qt.MouseButton.LeftButton)

                # Should show error message
                mock_error.assert_called_once()
                args = mock_error.call_args[0]
                assert "Failed to clear cache" in args[2]

# ============================================================================
# Directory Selection Tests
# ============================================================================

class TestDirectorySelection:
    """Test directory selection functionality."""

    def test_browse_dumps_directory(self, qtbot, settings_dialog, temp_dumps_dir):
        """Test browsing for dumps directory."""
        dialog, mock_settings, cache = settings_dialog

        # Mock file dialog to return test directory
        with patch("ui.dialogs.settings_dialog.QFileDialog.getExistingDirectory") as mock_dialog:
            mock_dialog.return_value = temp_dumps_dir

            # Click browse button
            qtbot.mouseClick(dialog.dumps_dir_button, Qt.MouseButton.LeftButton)

            # Directory should be set
            assert dialog.dumps_dir_edit.text() == temp_dumps_dir

            # Dialog should be called with correct parameters
            mock_dialog.assert_called_once()
            args = mock_dialog.call_args[0]
            assert "Select Default Dumps Directory" in args[1]

    def test_browse_cache_location(self, qtbot, settings_dialog, temp_cache_dir):
        """Test browsing for cache directory."""
        dialog, mock_settings, cache = settings_dialog

        # Mock file dialog to return test directory
        with patch("ui.dialogs.settings_dialog.QFileDialog.getExistingDirectory") as mock_dialog:
            mock_dialog.return_value = temp_cache_dir

            # Click browse button
            qtbot.mouseClick(dialog.cache_location_button, Qt.MouseButton.LeftButton)

            # Directory should be set
            assert dialog.cache_location_edit.text() == temp_cache_dir

            # Dialog should be called with correct parameters
            mock_dialog.assert_called_once()
            args = mock_dialog.call_args[0]
            assert "Select Cache Directory" in args[1]

    def test_browse_directory_cancellation(self, qtbot, settings_dialog):
        """Test that directory selection handles cancellation."""
        dialog, mock_settings, cache = settings_dialog

        # Set initial value
        initial_value = "/initial/path"
        dialog.dumps_dir_edit.setText(initial_value)

        # Mock file dialog to return empty string (cancelled)
        with patch("ui.dialogs.settings_dialog.QFileDialog.getExistingDirectory") as mock_dialog:
            mock_dialog.return_value = ""

            # Click browse button
            qtbot.mouseClick(dialog.dumps_dir_button, Qt.MouseButton.LeftButton)

            # Value should remain unchanged
            assert dialog.dumps_dir_edit.text() == initial_value

# ============================================================================
# Settings Validation and Edge Cases
# ============================================================================

class TestSettingsValidationAndEdgeCases:
    """Test settings validation and edge case handling."""

    def test_invalid_cache_size_limits(self, settings_dialog):
        """Test cache size spin box limits."""
        dialog, mock_settings, cache = settings_dialog

        # Test minimum limit
        dialog.cache_size_spin.setValue(5)  # Below minimum
        assert dialog.cache_size_spin == 10  # Should clamp to minimum

        # Test maximum limit
        dialog.cache_size_spin.setValue(15000)  # Above maximum
        assert dialog.cache_size_spin == 10000  # Should clamp to maximum

    def test_invalid_cache_expiry_limits(self, settings_dialog):
        """Test cache expiry spin box limits."""
        dialog, mock_settings, cache = settings_dialog

        # Test minimum limit
        dialog.cache_expiry_spin.setValue(0)  # Below minimum
        assert dialog.cache_expiry_spin == 1  # Should clamp to minimum

        # Test maximum limit
        dialog.cache_expiry_spin.setValue(400)  # Above maximum
        assert dialog.cache_expiry_spin == 365  # Should clamp to maximum

    def test_empty_paths_handling(self, qtbot, mock_settings_manager, rom_cache):
        """Test handling of empty directory paths."""
        # Start with non-empty paths
        def mock_get_with_paths(section, key, default=None):
            settings_map = {
                ("ui", "restore_position"): True,
                ("session", "auto_save"): True,
                ("paths", "default_dumps_dir"): "/initial/dumps",
                ("cache", "auto_cleanup"): True,
                ("cache", "show_indicators"): True,
            }
            return settings_map.get((section, key), default)

        mock_settings_manager.get.side_effect = mock_get_with_paths
        mock_settings_manager.get_cache_location.return_value = "/initial/cache"

        with patch("ui.dialogs.settings_dialog.get_settings_manager") as mock_get_settings:
            with patch("ui.dialogs.settings_dialog.get_rom_cache") as mock_get_cache:
                mock_get_settings.return_value = mock_settings_manager
                mock_get_cache.return_value = rom_cache

                dialog = SettingsDialog()
                qtbot.addWidget(dialog)

        # Verify initial values are loaded
        assert dialog.dumps_dir_edit.text() == "/initial/dumps"
        assert dialog.cache_location_edit.text() == "/initial/cache"

        # Set empty paths
        dialog.dumps_dir_edit.setText("")
        dialog.cache_location_edit.setText("")

        # Accept dialog
        dialog.accept()

        # Should save empty strings (valid - means use defaults)
        mock_settings_manager.set.assert_any_call("paths", "default_dumps_dir", "")
        mock_settings_manager.set_cache_location.assert_called_with("")

    def test_long_path_truncation_in_stats(self, settings_dialog):
        """Test that long paths are truncated in cache stats display."""
        dialog, mock_settings, cache = settings_dialog

        # Mock cache stats with very long path
        long_path = "/very/long/path/that/exceeds/fifty/characters/and/should/be/truncated/cache"
        cache.get_cache_stats = MagicMock(return_value={
            "cache_dir": long_path,
            "total_files": 5,
            "total_size_bytes": 1024 * 1024,  # 1MB
            "sprite_location_caches": 3,
            "rom_info_caches": 1,
            "scan_progress_caches": 1,
        })

        # Update stats
        dialog._update_cache_stats()

        # Path should be truncated
        displayed_path = dialog.cache_dir_label.text()
        assert len(displayed_path) <= 50
        assert displayed_path.startswith("...")

# ============================================================================
# Integration with Other Components
# ============================================================================

class TestComponentIntegration:
    """Test integration with other application components."""

    def test_status_bar_updates(self, settings_dialog):
        """Test that status bar is updated during operations."""
        dialog, mock_settings, cache = settings_dialog

        # Dialog should have status bar
        assert dialog.status_bar is not None

        # Update cache stats should update status bar
        dialog._update_cache_stats()

        # Status bar should show some message
        status_message = dialog.status_bar.currentMessage()
        assert status_message  # Should not be empty
        assert "cache" in status_message.lower()

    def test_settings_manager_integration(self, settings_dialog):
        """Test proper integration with settings manager."""
        dialog, mock_settings, cache = settings_dialog

        # Dialog should use the same settings manager instance
        assert dialog.settings_manager is mock_settings

        # Should call appropriate settings manager methods
        dialog._load_original_settings()

        # Verify methods were called
        mock_settings.get.assert_called()
        mock_settings.get_cache_enabled.assert_called()
        mock_settings.get_cache_location.assert_called()
        mock_settings.get_cache_max_size_mb.assert_called()
        mock_settings.get_cache_expiration_days.assert_called()

    def test_rom_cache_integration(self, settings_dialog):
        """Test proper integration with ROM cache."""
        dialog, mock_settings, cache = settings_dialog

        # Dialog should use the cache instance
        assert dialog.rom_cache is cache

        # Should be able to get cache stats
        stats = dialog.rom_cache.get_cache_stats()
        assert isinstance(stats, dict)
        assert "total_files" in stats
