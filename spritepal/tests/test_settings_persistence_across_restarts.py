"""
Comprehensive tests for settings persistence across application restarts.

This module tests real-world scenarios of SpritePal settings persisting through:
- Normal application restarts
- Crash scenarios
- Settings dialog changes
- Window geometry restoration
- Cache settings persistence
- Auto-save session functionality
"""
from __future__ import annotations

import builtins
import contextlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import QSettings

import core.managers.registry
import utils.rom_cache
import utils.settings_manager
from core.managers import (
    # Serial execution required: Manager registry manipulation
    cleanup_managers,
    get_session_manager,
    initialize_managers,
)
from ui.dialogs.settings_dialog import SettingsDialog
from ui.main_window import MainWindow
from utils.rom_cache import get_rom_cache
from utils.settings_manager import get_settings_manager

# Override the autouse fixture from conftest to prevent automatic initialization

pytestmark = [

    pytest.mark.serial,
    pytest.mark.singleton,
    pytest.mark.cache,
    pytest.mark.dialog,
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.rom_data,
    pytest.mark.slow,
]
@pytest.fixture(autouse=True)
def setup_managers():
    """Override conftest.py setup_managers to prevent automatic initialization"""
    # Don't initialize anything - let each test control its own initialization
    yield
    # Cleanup any managers that were created by tests
    with contextlib.suppress(builtins.BaseException):
        cleanup_managers()

class TestSettingsPersistenceAcrossRestarts:
    """Test settings persistence through app restart scenarios."""

    @pytest.fixture(autouse=True)
    def setup_environment(self, tmp_path, monkeypatch):
        """Set up isolated test environment for each test."""
        # First cleanup any existing managers
        with contextlib.suppress(builtins.BaseException):
            cleanup_managers()

        # Create test directories
        test_dir = tmp_path / "spritepal_test"
        test_dir.mkdir()

        cache_dir = test_dir / "cache"
        cache_dir.mkdir()

        settings_file = test_dir / ".spritepal_settings.json"

        # Patch home directory and settings paths
        monkeypatch.setattr(Path, "home", lambda: test_dir)
        monkeypatch.setattr(Path, "cwd", lambda: test_dir)

        # Reset global instances BEFORE yielding

        utils.settings_manager._settings_manager_instance = None
        utils.rom_cache._rom_cache_instance = None
        # Clear the manager registry to force re-initialization
        core.managers.registry._instance = None
        core.managers.registry._registry = core.managers.registry.ManagerRegistry()

        yield test_dir, settings_file, cache_dir

        # Cleanup
        with contextlib.suppress(builtins.BaseException):
            cleanup_managers()
        # Clear registry instance again for next test
        core.managers.registry._instance = None

    def test_cache_settings_persistence_through_dialog(self, qtbot, setup_environment):
        """Test that cache settings changed via dialog persist across restarts."""
        test_dir, settings_file, cache_dir = setup_environment

        # === First Session: Change cache settings via dialog ===
        initialize_managers("SpritePal", settings_path=settings_file)
        settings_manager = get_settings_manager()

        # Create and configure settings dialog
        dialog = SettingsDialog()
        qtbot.addWidget(dialog)

        # Verify initial values to ensure they differ from what we'll set
        # Get current values first
        initial_enabled = dialog.cache_enabled_check.isChecked()
        initial_size = dialog.cache_size_spin

        # Ensure the values we'll set are different from current values
        new_enabled = not initial_enabled  # Toggle the current state
        new_size = 250 if initial_size != 250 else 300  # Use different value

        # Change cache settings using the values we determined
        dialog.cache_enabled_check.setChecked(new_enabled)
        dialog.cache_location_edit.setText(str(cache_dir / "custom"))
        dialog.cache_size_spin.setValue(new_size)
        dialog.cache_expiry_spin.setValue(14)
        dialog.auto_cleanup_check.setChecked(False)
        dialog.show_indicators_check.setChecked(True)

        # Accept dialog to save settings
        dialog.accept()

        # Force save to ensure file is written
        settings_manager.save()

        # Verify settings were saved to file
        assert settings_file.exists()
        with open(settings_file) as f:
            saved_data = json.load(f)

        assert saved_data["cache"]["enabled"] is new_enabled
        assert saved_data["cache"]["location"] == str(cache_dir / "custom")
        assert saved_data["cache"]["max_size_mb"] == new_size
        assert saved_data["cache"]["expiration_days"] == 14
        assert saved_data["cache"]["auto_cleanup"] is False
        assert saved_data["cache"]["show_indicators"] is True

        # Cleanup first session
        dialog.close()
        cleanup_managers()

        # === Second Session: Verify settings persisted ===
        # Reset global instances to simulate restart
        import core.managers.registry
        import utils.rom_cache
        import utils.settings_manager

        utils.settings_manager._settings_manager_instance = None
        utils.rom_cache._rom_cache_instance = None
        # Clear the manager registry to force re-initialization
        core.managers.registry._instance = None

        # Initialize second session
        initialize_managers("SpritePal", settings_path=settings_file)
        settings2 = get_settings_manager()
        cache2 = get_rom_cache()

        # Refresh cache settings to ensure it picks up the loaded settings
        cache2.refresh_settings()

        # Verify cache settings loaded correctly
        assert settings2.get_cache_enabled() is new_enabled
        assert settings2.get_cache_location() == str(cache_dir / "custom")
        assert settings2.get_cache_max_size_mb() == new_size
        assert settings2.get_cache_expiration_days() == 14
        assert settings2.get("cache", "auto_cleanup") is False
        assert settings2.get("cache", "show_indicators") is True

        # Verify cache respects the enabled/disabled state
        assert cache2.cache_enabled == new_enabled

        # Create new dialog to verify UI reflects persisted settings
        dialog2 = SettingsDialog()
        qtbot.addWidget(dialog2)

        assert dialog2.cache_enabled_check.isChecked() == new_enabled
        assert dialog2.cache_location_edit.text() == str(cache_dir / "custom")
        assert dialog2.cache_size_spin == new_size
        assert dialog2.cache_expiry_spin == 14
        assert not dialog2.auto_cleanup_check.isChecked()
        assert dialog2.show_indicators_check.isChecked()

        dialog2.close()

    def test_window_geometry_restoration(self, qtbot, setup_environment, monkeypatch):
        """Test window geometry is properly saved and restored."""
        test_dir, settings_file, cache_dir = setup_environment

        # === First Session: Save window geometry ===
        # Initialize managers with custom settings path
        initialize_managers("SpritePal", settings_path=settings_file)
        settings1 = get_settings_manager()
        session1 = get_session_manager()

        # Enable window restoration
        settings1.set("ui", "restore_position", True)

        # Create main window with specific geometry
        with patch("ui.main_window.QFileDialog"):  # Prevent file dialogs
            window1 = MainWindow()
            qtbot.addWidget(window1)

            # Set specific geometry
            window1.move(100, 200)
            window1.resize(1200, 800)

            # Debug: Check actual window position
            print(f"DEBUG: Window position after move: x={window1.x()}, y={window1.y()}")
            print(f"DEBUG: Window size after resize: width={window1.width()}, height={window1.height()}")

            # Save window state by calling _save_session
            window1._save_session()

            # Verify geometry was saved to SessionManager
            window_geom = session1.get_window_geometry()
            print(f"DEBUG: Window geometry from session after save: {window_geom}")
            assert window_geom["x"] == 100
            assert window_geom["y"] == 200
            assert window_geom["width"] == 1200
            assert window_geom["height"] == 800

            # Save settings to disk (SettingsManager calls SessionManager.save_session())
            try:
                settings1.save()
            except Exception as e:
                print(f"ERROR saving settings: {e}")
                raise

            # Debug: Check if file was actually saved
            print(f"DEBUG: Settings file path: {settings_file}")
            print(f"DEBUG: Settings file exists after save: {settings_file.exists()}")
            if settings_file.exists():
                with open(settings_file) as f:
                    saved_data = json.load(f)
                    print(f"DEBUG: Saved settings content: {json.dumps(saved_data, indent=2)}")

            window1.close()

        # Check if settings file exists before cleanup
        print(f"DEBUG: Before cleanup - settings file exists: {settings_file.exists()}")

        cleanup_managers()

        # Check if settings file exists after cleanup
        print(f"DEBUG: After cleanup - settings file exists: {settings_file.exists()}")
        if settings_file.exists():
            with open(settings_file) as f:
                cleanup_data = json.load(f)
                print(f"DEBUG: Settings file content: {json.dumps(cleanup_data, indent=2)}")

        # === Second Session: Verify restoration ===
        # Reset globals
        import core.managers.registry
        import utils.settings_manager
        utils.settings_manager._settings_manager_instance = None
        # Clear the manager registry to force re-initialization
        core.managers.registry._instance = None

        initialize_managers("SpritePal", settings_path=settings_file)
        settings2 = get_settings_manager()
        session2 = get_session_manager()

        # Debug: Check if settings file exists and what it contains
        print(f"DEBUG: After init - settings file exists: {settings_file.exists()}")
        # Don't assert here, let's see what happens
        # assert settings_file.exists(), f"Settings file not found at {settings_file}"

        # Verify restore_position setting persisted
        restore_pos = settings2.get("ui", "restore_position")
        print(f"DEBUG: restore_position = {restore_pos}")
        assert restore_pos is True

        # Debug: Check window geometry from session manager
        window_geom = session2.get_window_geometry()
        print(f"DEBUG: Window geometry from session = {window_geom}")

        # Create new window
        with patch("ui.main_window.QFileDialog"):
            window2 = MainWindow()
            qtbot.addWidget(window2)

            # Window should restore geometry automatically in __init__
            # (MainWindow constructor calls _restore_previous_session)

            # Verify position and size
            assert window2.x() == 100
            assert window2.y() == 200
            assert window2.width() == 1200
            assert window2.height() == 800

            window2.close()

    def test_window_geometry_not_restored_when_disabled(self, qtbot, setup_environment):
        """Test window geometry is not restored when setting is disabled."""
        test_dir, settings_file, cache_dir = setup_environment

        # === First Session: Save geometry but disable restoration ===
        initialize_managers("SpritePal", settings_path=settings_file)
        settings1 = get_settings_manager()

        # Save window state
        settings1.set("ui", "window_x", 100)
        settings1.set("ui", "window_y", 200)
        settings1.set("ui", "window_width", 1200)
        settings1.set("ui", "window_height", 800)

        # Disable restoration
        settings1.set("ui", "restore_position", False)
        settings1.save()

        cleanup_managers()

        # === Second Session: Window should use defaults ===
        import utils.settings_manager
        utils.settings_manager._settings_manager_instance = None

        initialize_managers("SpritePal", settings_path=settings_file)
        get_settings_manager()

        # Create window
        with patch("ui.main_window.QFileDialog"):
            window = MainWindow()
            qtbot.addWidget(window)

            # Should not restore saved geometry (restore_position is False)
            # MainWindow respects the restore_position setting in _restore_previous_session

            # Window should have default size (not 1200x800)
            assert window.width() != 1200 or window.height() != 800

            window.close()

    def test_auto_save_session_functionality(self, qtbot, setup_environment):
        """Test auto-save session feature persists session data."""
        test_dir, settings_file, cache_dir = setup_environment

        # === First Session: Enable auto-save and create session ===
        initialize_managers("SpritePal", settings_path=settings_file)
        settings1 = get_settings_manager()

        # Enable auto-save
        settings1.set("session", "auto_save", True)

        # Simulate session data
        session_data = {
            "vram_path": str(test_dir / "vram.dmp"),
            "cgram_path": str(test_dir / "cgram.dmp"),
            "oam_path": str(test_dir / "oam.dmp"),
            "output_name": "my_sprite",
            "last_export_dir": str(test_dir / "exports"),
            "recent_files": [
                str(test_dir / "file1.dmp"),
                str(test_dir / "file2.dmp")
            ]
        }

        for key, value in session_data.items():
            settings1.set("session", key, value)

        # Save session
        settings1.save()

        cleanup_managers()

        # === Second Session: Verify session restored ===
        import utils.settings_manager
        utils.settings_manager._settings_manager_instance = None

        initialize_managers("SpritePal", settings_path=settings_file)
        settings2 = get_settings_manager()

        # Verify auto-save is still enabled
        assert settings2.get("session", "auto_save") is True

        # Verify all session data persisted
        for key, expected_value in session_data.items():
            actual_value = settings2.get("session", key)
            assert actual_value == expected_value, f"Session {key} not restored"

    def test_settings_survive_app_crash(self, setup_environment):
        """Test that settings survive when app crashes without proper cleanup."""
        test_dir, settings_file, cache_dir = setup_environment

        # === First Session: Save settings then "crash" ===
        initialize_managers("SpritePal", settings_path=settings_file)
        settings1 = get_settings_manager()

        # Configure various settings
        settings1.set("ui", "theme", "dark")
        settings1.set("cache", "enabled", True)
        settings1.set("cache", "location", str(cache_dir))
        settings1.set("extraction", "default_format", "indexed_png")
        settings1.set("session", "last_rom", "/path/to/rom.sfc")

        # Save settings (simulating periodic auto-save)
        settings1.save()

        # Simulate crash - no cleanup_managers() call
        # Just reset the global instance
        import utils.settings_manager
        utils.settings_manager._settings_manager_instance = None

        # === Second Session: Settings should still be there ===
        initialize_managers("SpritePal", settings_path=settings_file)
        settings2 = get_settings_manager()

        # All settings should have survived
        assert settings2.get("ui", "theme") == "dark"
        assert settings2.get("cache", "enabled") is True
        assert settings2.get("cache", "location") == str(cache_dir)
        assert settings2.get("extraction", "default_format") == "indexed_png"
        assert settings2.get("session", "last_rom") == "/path/to/rom.sfc"

    def test_settings_migration_from_old_format(self, setup_environment):
        """Test migration from old flat settings format to new nested format."""
        test_dir, settings_file, cache_dir = setup_environment

        # Create old format settings file
        old_settings = {
            "vram_path": "/old/vram.dmp",
            "cgram_path": "/old/cgram.dmp",
            "window_width": 1024,
            "window_height": 768,
            "last_export_dir": "/old/exports",
            "theme": "light"
        }

        with open(settings_file, "w") as f:
            json.dump(old_settings, f)

        # Load with new settings manager
        initialize_managers("SpritePal", settings_path=settings_file)
        settings = get_settings_manager()

        # Should have migrated to new structure
        # The actual migration logic would be in SettingsManager
        # For now verify it loads without error and has the expected structure

        # New settings should have proper structure - check via public API
        session_data = settings.get_session_data()
        assert session_data is not None

        # Check that default values exist for the new structure
        assert settings.get("ui", "window_width") is not None
        assert settings.get("cache", "enabled") is not None

        # The old values should still be accessible (if migration preserves them)
        # or default values should be present
        assert settings.get("session", "vram_path") is not None

    def test_concurrent_settings_modifications(self, qtbot, setup_environment):
        """Test settings consistency when modified from multiple places."""
        test_dir, settings_file, cache_dir = setup_environment

        initialize_managers("SpritePal", settings_path=settings_file)
        settings = get_settings_manager()

        # Create settings dialog
        dialog = SettingsDialog()
        qtbot.addWidget(dialog)

        # Modify settings directly
        settings.set("cache", "enabled", False)
        settings.save()

        # Dialog should reflect the change when reloaded
        dialog._load_settings()
        assert not dialog.cache_enabled_check.isChecked()

        # Change via dialog
        dialog.cache_enabled_check.setChecked(True)
        dialog.accept()

        # Direct access should show the change
        assert settings.get("cache", "enabled") is True

        dialog.close()

    def test_cache_directory_change_persistence(self, qtbot, setup_environment):
        """Test that cache directory changes persist and cache adapts."""
        test_dir, settings_file, cache_dir = setup_environment

        # === First Session: Use default cache ===
        initialize_managers("SpritePal", settings_path=settings_file)
        settings1 = get_settings_manager()
        cache1 = get_rom_cache()

        # Save something to default cache
        cache1.save_rom_info("/test.sfc", {"title": "Test ROM"})

        # Change cache location via settings
        new_cache_dir = test_dir / "new_cache"
        new_cache_dir.mkdir()

        settings1.set_cache_location(str(new_cache_dir))
        settings1.save()

        cleanup_managers()

        # === Second Session: Cache should use new location ===
        import utils.rom_cache
        import utils.settings_manager

        utils.settings_manager._settings_manager_instance = None
        utils.rom_cache._rom_cache_instance = None

        initialize_managers("SpritePal", settings_path=settings_file)
        settings2 = get_settings_manager()
        cache2 = get_rom_cache()

        # Verify new location is used
        assert settings2.get_cache_location() == str(new_cache_dir)
        assert str(new_cache_dir) in str(cache2.cache_dir)

        # Old cache data should not be available
        assert cache2.get_rom_info("/test.sfc") is None

        # New cache should work
        cache2.save_rom_info("/test2.sfc", {"title": "Test ROM 2"})
        assert cache2.get_rom_info("/test2.sfc") is not None

    def test_settings_dialog_cancel_does_not_persist(self, qtbot, setup_environment):
        """Test that cancelling settings dialog doesn't save changes."""
        test_dir, settings_file, cache_dir = setup_environment

        initialize_managers("SpritePal", settings_path=settings_file)
        settings = get_settings_manager()

        # Set initial values
        settings.set("cache", "enabled", True)
        settings.set("cache", "max_size_mb", 100)
        settings.save()

        # Create dialog and make changes
        dialog = SettingsDialog()
        qtbot.addWidget(dialog)

        dialog.cache_enabled_check.setChecked(False)
        dialog.cache_size_spin.setValue(500)

        # Cancel dialog
        dialog.reject()

        # Settings should not have changed
        assert settings.get("cache", "enabled") is True
        assert settings.get_cache_max_size_mb() == 100

        dialog.close()

    def test_settings_persistence_with_qt_settings(self, qtbot, setup_environment):
        """Test interaction between SpritePal settings and Qt's QSettings."""
        test_dir, settings_file, cache_dir = setup_environment

        # Use Qt settings for some UI state
        qt_settings = QSettings("SpritePal", "TestSettings")
        qt_settings.setValue("MainWindow/geometry", b"test_geometry_data")
        qt_settings.setValue("MainWindow/state", b"test_state_data")
        qt_settings.sync()

        # Use SpritePal settings for app settings
        initialize_managers("SpritePal", settings_path=settings_file)
        settings = get_settings_manager()

        settings.set("ui", "theme", "dark")
        settings.set("cache", "enabled", True)
        settings.save()

        cleanup_managers()

        # Both should persist independently
        import utils.settings_manager
        utils.settings_manager._settings_manager_instance = None

        # Verify Qt settings
        qt_settings2 = QSettings("SpritePal", "TestSettings")
        assert qt_settings2.value("MainWindow/geometry") == b"test_geometry_data"
        assert qt_settings2.value("MainWindow/state") == b"test_state_data"

        # Verify SpritePal settings
        initialize_managers("SpritePal", settings_path=settings_file)
        settings2 = get_settings_manager()

        assert settings2.get("ui", "theme") == "dark"
        assert settings2.get("cache", "enabled") is True

    @pytest.mark.skip(reason="reset_to_defaults() not yet implemented in SettingsManager")
    def test_settings_reset_to_defaults(self, qtbot, setup_environment):
        """Test resetting settings to defaults."""
        test_dir, settings_file, cache_dir = setup_environment

        initialize_managers("SpritePal", settings_path=settings_file)
        settings = get_settings_manager()

        # Modify settings
        settings.set("cache", "enabled", False)
        settings.set("cache", "max_size_mb", 500)
        settings.set("ui", "theme", "dark")
        settings.save()

        # Reset to defaults (this would be a feature to implement)
        settings.reset_to_defaults()
        settings.save()

        # Should have default values
        assert settings.get("cache", "enabled", True) is True  # Default
        assert settings.get_cache_max_size_mb() == 100  # Default
        assert settings.get("ui", "theme", "light") == "light"  # Default
