"""Tests for settings manager"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from core.di_container import inject
from core.protocols.manager_protocols import SettingsManagerProtocol
from utils.settings_manager import SettingsManager


def get_settings_manager():
    """Get settings manager from DI container (replaces deprecated function)."""
    return inject(SettingsManagerProtocol)

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.mock_only,
    pytest.mark.no_qt,
    pytest.mark.parallel_safe,
    pytest.mark.rom_data,
    pytest.mark.ci_safe,
]

class TestSettingsManager:
    """Test the SettingsManager class"""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for settings"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def settings_manager(self, temp_dir):
        """Create a SettingsManager in temp directory"""
        from core.managers.session_manager import SessionManager

        # Create temp settings file path
        settings_file = Path(temp_dir) / ".testapp_settings.json"

        # Create a session manager with our temp settings file
        session_manager = SessionManager(settings_path=settings_file)

        # Pass session_manager directly to SettingsManager (replaces deprecated get_session_manager patch)
        manager = SettingsManager("TestApp", session_manager=session_manager)
        # Store session manager reference for tests
        manager._test_session_manager = session_manager
        manager._test_settings_file = settings_file

        yield manager
        # Cleanup
        if settings_file.exists():
            settings_file.unlink()

    def test_init_creates_default_settings(self, settings_manager):
        """Test initialization creates default settings"""
        # Use public API to check settings
        assert settings_manager.get("session", "vram_path") == ""
        assert settings_manager.get("session", "cgram_path") == ""
        assert settings_manager.get("session", "oam_path") == ""
        assert settings_manager.get("session", "create_grayscale") is True
        assert settings_manager.get("session", "create_metadata") is True

        # Check UI defaults
        assert settings_manager.get("ui", "window_width") == 900
        assert settings_manager.get("ui", "window_height") == 600

    def test_settings_file_path(self, temp_dir):
        """Test settings file path generation"""
        from core.managers.session_manager import SessionManager

        settings_file = Path(temp_dir) / ".testapp_settings.json"

        # Pass session_manager directly (replaces deprecated get_session_manager patch)
        session_manager = SessionManager(settings_path=settings_file)
        manager = SettingsManager("TestApp", session_manager=session_manager)
        # Force saving to create the file
        manager.save_settings()
        # Verify the file was created
        assert settings_file.exists()

    def test_load_existing_settings(self, temp_dir):
        """Test loading existing settings file"""
        from core.managers.session_manager import SessionManager

        # Create settings file
        settings_data = {
            "session": {"vram_path": "/test/vram.dmp"},
            "ui": {"window_width": 1000},
        }
        settings_file = Path(temp_dir) / ".testapp_settings.json"
        with open(settings_file, "w") as f:
            json.dump(settings_data, f)

        # Load settings - pass session_manager directly (replaces deprecated get_session_manager patch)
        session_manager = SessionManager(settings_path=settings_file)
        manager = SettingsManager("TestApp", session_manager=session_manager)

        assert manager.get("session", "vram_path") == "/test/vram.dmp"
        assert manager.get("ui", "window_width") == 1000

    def test_load_corrupted_settings(self, temp_dir):
        """Test loading corrupted settings file"""
        from core.managers.session_manager import SessionManager

        # Create corrupted settings file
        settings_file = Path(temp_dir) / ".testapp_settings.json"
        with open(settings_file, "w") as f:
            f.write("{ invalid json }")

        # Should return default settings - pass session_manager directly (replaces deprecated patch)
        session_manager = SessionManager(settings_path=settings_file)
        manager = SettingsManager("TestApp", session_manager=session_manager)

        assert manager.get("session", "vram_path") == ""
        assert manager.get("ui", "window_width") == 900

    def test_save_settings(self, settings_manager, temp_dir):
        """Test saving settings"""
        # Modify settings using public API
        settings_manager.set("session", "vram_path", "/test/path.dmp")
        settings_manager.set("ui", "window_width", 1200)

        # Save
        settings_manager.save_settings()

        # Verify file contents
        with open(settings_manager._test_settings_file) as f:
            saved_data = json.load(f)

        assert saved_data["session"]["vram_path"] == "/test/path.dmp"
        assert saved_data["ui"]["window_width"] == 1200

    def test_get_setting(self, settings_manager):
        """Test getting individual settings"""
        # Use public API to set a value
        settings_manager.set("session", "test_key", "test_value")

        value = settings_manager.get("session", "test_key")
        assert value == "test_value"

        # Test with default
        value = settings_manager.get("session", "nonexistent", "default")
        assert value == "default"

        # Test missing category
        value = settings_manager.get("missing_category", "key", "default")
        assert value == "default"

    def test_set_setting(self, settings_manager):
        """Test setting individual values"""
        settings_manager.set("session", "new_key", "new_value")
        assert settings_manager.get("session", "new_key") == "new_value"

        # Test new category
        settings_manager.set("custom", "key", "value")
        assert settings_manager.get("custom", "key") == "value"

    def test_get_session_data(self, settings_manager):
        """Test getting session data"""
        settings_manager.set("session", "vram_path", "/test.dmp")

        session = settings_manager.get_session_data()
        assert session["vram_path"] == "/test.dmp"
        assert isinstance(session, dict)

    def test_save_session_data(self, settings_manager):
        """Test saving session data"""
        new_session = {
            "vram_path": "/new/vram.dmp",
            "cgram_path": "/new/cgram.dmp",
            "output_name": "output",
        }

        settings_manager.save_session_data(new_session)

        # Verify using public API
        assert settings_manager.get("session", "vram_path") == "/new/vram.dmp"
        assert settings_manager.get("session", "cgram_path") == "/new/cgram.dmp"
        assert settings_manager.get("session", "output_name") == "output"

        # Force save to file
        settings_manager.save_settings()
        # Should also save to file
        assert settings_manager._test_settings_file.exists()

    def test_get_ui_data(self, settings_manager):
        """Test getting UI data"""
        ui_data = settings_manager.get_ui_data()

        assert ui_data["window_width"] == 900
        assert ui_data["window_height"] == 600
        assert isinstance(ui_data, dict)

    def test_save_ui_data(self, settings_manager):
        """Test saving UI data"""
        new_ui = {
            "window_width": 1024,
            "window_height": 768,
            "window_x": 100,
            "window_y": 100,
        }

        settings_manager.save_ui_data(new_ui)

        # Verify using public API
        assert settings_manager.get("ui", "window_width") == 1024
        assert settings_manager.get("ui", "window_height") == 768
        assert settings_manager.get("ui", "window_x") == 100
        assert settings_manager.get("ui", "window_y") == 100
        assert settings_manager._test_settings_file.exists()

    def test_validate_file_paths(self, settings_manager, temp_dir):
        """Test file path validation"""
        # Create test files
        vram_file = Path(temp_dir) / "test.vram"
        vram_file.write_text("data")

        # Use public API to set paths
        settings_manager.set("session", "vram_path", str(vram_file))
        settings_manager.set("session", "cgram_path", "/nonexistent.cgram")
        settings_manager.set("session", "oam_path", "")

        validated = settings_manager.validate_file_paths()

        assert validated["vram_path"] == str(vram_file)
        assert validated["cgram_path"] == ""  # Nonexistent file
        assert validated["oam_path"] == ""

    def test_has_valid_session(self, settings_manager, temp_dir):
        """Test checking for valid session"""
        # No valid files
        assert not settings_manager.has_valid_session()

        # Create valid file
        vram_file = Path(temp_dir) / "test.vram"
        vram_file.write_text("data")

        settings_manager.set("session", "vram_path", str(vram_file))
        assert settings_manager.has_valid_session()

    def test_clear_session(self, settings_manager):
        """Test clearing session data"""
        # Set some data
        settings_manager.set("session", "vram_path", "/test.vram")
        settings_manager.set("session", "output_name", "test")

        # Clear
        settings_manager.clear_session()

        # Check defaults restored using public API
        assert settings_manager.get("session", "vram_path") == ""
        assert settings_manager.get("session", "cgram_path") == ""
        assert settings_manager.get("session", "output_name") == ""
        assert settings_manager.get("session", "create_grayscale") is True
        assert settings_manager.get("session", "create_metadata") is True

class TestGlobalSettingsInstance:
    """Test the global settings instance"""

    def test_get_settings_manager_singleton(self, isolated_managers):
        """Test that get_settings_manager returns singleton"""
        # Get instance twice - should return same object
        manager1 = get_settings_manager()
        manager2 = get_settings_manager()

        assert manager1 is manager2
        assert isinstance(manager1, SettingsManager)

    def test_get_settings_manager_preserves_state(self, isolated_managers):
        """Test that singleton preserves state"""
        manager1 = get_settings_manager()
        manager1.set("custom", "key", "value")

        manager2 = get_settings_manager()
        assert manager2.get("custom", "key") == "value"
