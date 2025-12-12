"""Integration tests for settings persistence across components"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.controller import ExtractionController
from core.di_container import inject
from core.managers import cleanup_managers, initialize_managers
from core.protocols.dialog_protocols import DialogFactoryProtocol
from core.protocols.manager_protocols import (
    ExtractionManagerProtocol,
    InjectionManagerProtocol,
    SessionManagerProtocol,
    SettingsManagerProtocol,
)
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

class TestSettingsIntegration:
    """Test settings integration across application components"""

    @pytest.fixture
    def temp_settings_dir(self):
        """Create temporary directory for settings"""
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch("pathlib.Path.cwd", return_value=Path(tmpdir)),
        ):
            yield tmpdir

    @pytest.fixture
    def mock_main_window(self):
        """Create mock main window for controller"""
        mock = MagicMock()
        mock.vram_input.text.return_value = ""
        mock.cgram_input.text.return_value = ""
        mock.oam_input.text.return_value = ""
        mock.output_name_input.text.return_value = "output"
        mock.grayscale_checkbox.isChecked.return_value = True
        mock.metadata_checkbox.isChecked.return_value = True
        mock.sprite_preview = MagicMock()
        mock.extraction_panel = MagicMock()
        mock.palette_list = MagicMock()
        return mock

    def test_settings_persistence_across_sessions(self, temp_settings_dir):
        """Test that settings persist across application restarts"""
        # Initialize managers first
        initialize_managers("TestApp")

        # Session 1: Save settings
        settings1 = SettingsManager("TestApp")

        # Set various settings
        settings1.set("session", "vram_path", "/test/vram.dmp")
        settings1.set("session", "cgram_path", "/test/cgram.dmp")
        settings1.set("session", "output_name", "my_sprite")
        settings1.set("ui", "window_width", 1024)
        settings1.set("ui", "window_height", 768)
        settings1.set("custom", "last_export_dir", "/exports")

        settings1.save_settings()

        # Clean up first session
        cleanup_managers()

        # Initialize for session 2
        initialize_managers("TestApp")

        # Session 2: Load settings in new instance
        settings2 = SettingsManager("TestApp")

        # Verify settings persisted
        assert settings2.get("session", "vram_path") == "/test/vram.dmp"
        assert settings2.get("session", "cgram_path") == "/test/cgram.dmp"
        assert settings2.get("session", "output_name") == "my_sprite"
        assert settings2.get("ui", "window_width") == 1024
        assert settings2.get("ui", "window_height") == 768
        assert settings2.get("custom", "last_export_dir") == "/exports"

    def test_controller_settings_integration(self, temp_settings_dir, mock_main_window):
        """Test controller interaction with settings manager"""
        # Reset global instance to ensure it uses temp directory
        import utils.settings_manager

        utils.settings_manager._settings_instance = None

        settings = get_settings_manager()

        # Pre-populate settings
        settings.set("session", "last_extraction_offset", 0xC000)
        settings.set("session", "last_tile_count", 64)
        settings.save_settings()

        # Initialize managers before creating controller
        initialize_managers("TestApp")

        try:
            # Create controller with all required dependencies
            ExtractionController(
                main_window=mock_main_window,
                extraction_manager=inject(ExtractionManagerProtocol),
                session_manager=inject(SessionManagerProtocol),
                injection_manager=inject(InjectionManagerProtocol),
                settings_manager=settings,
                dialog_factory=inject(DialogFactoryProtocol),
            )

            # Controller should be able to access settings
            # (In real implementation, controller would use settings)
            last_offset = settings.get("session", "last_extraction_offset", 0)
            assert last_offset == 0xC000
        finally:
            # Clean up managers
            cleanup_managers()

    def test_window_geometry_persistence(self, temp_settings_dir):
        """Test UI geometry settings persistence"""
        # Initialize managers first
        initialize_managers("SpritePal")

        # Create fresh settings instance to avoid conflicts
        settings = SettingsManager("SpritePal")

        # Simulate saving window state
        window_state = {
            "x": 100,
            "y": 200,
            "width": 1200,
            "height": 800,
            "maximized": False,
            "splitter_sizes": [300, 900],
        }

        for key, value in window_state.items():
            settings.set("ui", f"window_{key}", value)

        settings.save_settings()

        # Clean up first session
        cleanup_managers()

        # Initialize for second session
        initialize_managers("SpritePal")

        # Load in new instance
        new_settings = SettingsManager("SpritePal")

        # Verify all geometry saved
        assert new_settings.get("ui", "window_x") == 100
        assert new_settings.get("ui", "window_y") == 200
        assert new_settings.get("ui", "window_width") == 1200
        assert new_settings.get("ui", "window_height") == 800
        assert not new_settings.get("ui", "window_maximized")
        assert new_settings.get("ui", "window_splitter_sizes") == [300, 900]

    def test_recent_files_management(self, temp_settings_dir):
        """Test recent files list in settings"""
        # Initialize managers first
        initialize_managers("TestApp")
        settings = get_settings_manager()

        # Add recent files
        recent_files = []
        for i in range(5):
            file_path = f"/path/to/file{i}.dmp"
            recent_files.append(file_path)

        settings.set("session", "recent_vram_files", recent_files)
        settings.save_settings()

        # Verify persistence
        loaded_files = settings.get("session", "recent_vram_files", [])
        assert loaded_files == recent_files

        # Test FIFO behavior (simulate in app logic)
        new_file = "/path/to/new_file.dmp"
        loaded_files.insert(0, new_file)
        if len(loaded_files) > 5:
            loaded_files.pop()

        settings.set("session", "recent_vram_files", loaded_files)

        final_list = settings.get("session", "recent_vram_files")
        assert final_list[0] == new_file
        assert len(final_list) == 5

    def test_extraction_preferences_persistence(self, temp_settings_dir):
        """Test extraction preference settings"""
        # Initialize managers first
        initialize_managers("TestApp")
        settings = get_settings_manager()

        # Set extraction preferences
        prefs = {
            "default_tile_width": 256,
            "auto_detect_size": True,
            "preserve_transparency": True,
            "compression_level": 6,
            "palette_format": "rgb888",
            "include_unused_palettes": False,
        }

        for key, value in prefs.items():
            settings.set("extraction", key, value)

        settings.save_settings()

        # Clean up first session
        cleanup_managers()

        # Initialize for second session
        initialize_managers("TestApp")

        # Verify in new session
        new_settings = get_settings_manager()
        for key, expected in prefs.items():
            actual = new_settings.get("extraction", key)
            assert actual == expected, f"Preference {key} not persisted"

    def test_color_scheme_persistence(self, temp_settings_dir):
        """Test UI color scheme settings"""
        # Initialize managers first
        initialize_managers("TestApp")
        settings = get_settings_manager()

        # Save color scheme
        color_scheme = {
            "theme": "dark",
            "preview_background": "#2b2b2b",
            "grid_color": "#555555",
            "selection_color": "#4a90e2",
            "transparency_pattern": "checkerboard",
        }

        settings.set("appearance", "color_scheme", color_scheme)
        settings.save_settings()

        # Load and verify
        loaded_scheme = settings.get("appearance", "color_scheme", {})
        assert loaded_scheme == color_scheme

    def test_settings_migration(self, temp_settings_dir):
        """Test settings migration from old format"""
        # Create old format settings
        old_settings = {
            "vram_path": "/old/path.dmp",
            "window_width": 800,
            "window_height": 600,
        }

        settings_file = Path(temp_settings_dir) / ".spritepal_settings.json"
        with open(settings_file, "w") as f:
            json.dump(old_settings, f)

        # Need to ensure SessionManager loads from our temp file
        from core.managers.session_manager import SessionManager

        # Create a session manager with our temp settings file
        # Pass session_manager directly to SettingsManager (replaces deprecated get_session_manager patch)
        session_manager = SessionManager(settings_path=settings_file)
        settings = SettingsManager(session_manager=session_manager)

        # Verify migration worked through the public API
        assert settings.get("session", "vram_path") == "/old/path.dmp"
        assert settings.get("ui", "window_width") == 800
        assert settings.get("ui", "window_height") == 600

    def test_concurrent_settings_access(self, temp_settings_dir):
        """Test concurrent access to settings"""
        # Initialize managers first
        initialize_managers("TestApp")
        settings1 = get_settings_manager()
        settings2 = get_settings_manager()

        # Both should reference same instance
        assert settings1 is settings2

        # Changes in one should be visible in other
        settings1.set("test", "key", "value")
        assert settings2.get("test", "key") == "value"

    def test_settings_corruption_recovery(self, temp_settings_dir):
        """Test recovery from corrupted settings file"""
        # Create corrupted settings file
        settings_file = Path(temp_settings_dir) / ".spritepal_settings.json"
        with open(settings_file, "w") as f:
            f.write("{ corrupted json }")

        # Need to ensure SessionManager loads from our temp file
        from core.managers.session_manager import SessionManager

        # Create a session manager with our temp settings file
        # Pass session_manager directly to SettingsManager (replaces deprecated get_session_manager patch)
        session_manager = SessionManager(settings_path=settings_file)
        settings = SettingsManager(session_manager=session_manager)

        # Should load defaults without crashing
        # Verify defaults loaded (since file was corrupted)
        assert settings.get("session", "vram_path") == ""
        assert settings.get("ui", "window_width") == 900

        # Should be able to save valid settings
        settings.set("session", "vram_path", "/new/path.dmp")
        settings.save_settings()

        # Verify file is now valid JSON
        with open(settings_file) as f:
            data = json.load(f)
            assert data["session"]["vram_path"] == "/new/path.dmp"

    def test_settings_permission_handling(self, temp_settings_dir):
        """Test handling of permission errors"""
        # Initialize managers first
        initialize_managers("TestApp")
        settings = get_settings_manager()

        # Set some data
        settings.set("test", "data", "value")

        # Make settings file read-only
        settings.save_settings()  # Save first

        # Mock permission error
        with patch("builtins.open", side_effect=PermissionError("No write access")):
            # Should handle gracefully
            settings.set("test", "new_data", "new_value")
            settings.save_settings()  # Should not crash

        # Settings should still be in memory
        assert settings.get("test", "new_data") == "new_value"

    def test_export_import_settings(self, temp_settings_dir):
        """Test exporting and importing settings"""
        # Initialize managers first
        initialize_managers("TestApp")
        settings = get_settings_manager()

        # Configure settings
        settings.set("session", "vram_path", "/test/vram.dmp")
        settings.set("extraction", "tile_width", 256)
        settings.set("appearance", "theme", "dark")

        # Export to dict (for backup/sharing)
        export_data = {
            "session": settings.get_session_data(),
            "extraction": {"tile_width": settings.get("extraction", "tile_width", 256)},
            "appearance": {"theme": settings.get("appearance", "theme", "dark")},
        }

        # Clear settings
        settings.clear_session()
        settings.set("extraction", "tile_width", 128)  # Set to different value
        settings.set("appearance", "theme", "light")  # Set to different value

        # Import back - use the public API to restore settings
        # Session data has its own method
        settings.save_session_data(export_data["session"])
        # Other settings use set method
        settings.set("extraction", "tile_width", export_data["extraction"]["tile_width"])
        settings.set("appearance", "theme", export_data["appearance"]["theme"])

        # Verify imported correctly
        assert settings.get("session", "vram_path") == "/test/vram.dmp"
        assert settings.get("extraction", "tile_width") == 256
        assert settings.get("appearance", "theme") == "dark"
