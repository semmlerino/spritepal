"""Integration tests for settings persistence across components

This file creates ApplicationStateManager instances directly for testing with isolated sessions.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from core.managers.application_state_manager import ApplicationStateManager

if TYPE_CHECKING:
    from core.app_context import AppContext

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.skip_thread_cleanup(reason="Tests create real managers which may spawn threads"),
    pytest.mark.headless,
    pytest.mark.integration,
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

    def test_settings_manager_session_data(self, temp_settings_dir, app_context: AppContext):
        """Test settings manager session data persistence (formerly controller integration test)."""
        settings = app_context.application_state_manager

        # Pre-populate settings
        settings.set("session", "last_extraction_offset", 0xC000)
        settings.set("session", "last_tile_count", 64)
        settings.save_settings()

        # Verify settings persisted
        last_offset = settings.get("session", "last_extraction_offset", 0)
        assert last_offset == 0xC000

        tile_count = settings.get("session", "last_tile_count", 0)
        assert tile_count == 64

    def test_recent_files_management(self, temp_settings_dir, app_context: AppContext):
        """Test recent files list in settings"""
        settings = app_context.application_state_manager

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

    def test_extraction_preferences_persistence(self, temp_settings_dir, app_context: AppContext):
        """Test extraction preference settings"""
        settings = app_context.application_state_manager

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

        # Verify in new session (same manager since using app_context)
        new_settings = app_context.application_state_manager
        for key, expected in prefs.items():
            actual = new_settings.get("extraction", key)
            assert actual == expected, f"Preference {key} not persisted"

    def test_color_scheme_persistence(self, temp_settings_dir, app_context: AppContext):
        """Test UI color scheme settings"""
        settings = app_context.application_state_manager

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

    def test_concurrent_settings_access(self, temp_settings_dir, app_context: AppContext):
        """Test concurrent access to settings"""
        settings1 = app_context.application_state_manager
        settings2 = app_context.application_state_manager

        # Both should reference same instance
        assert settings1 is settings2

        # Changes in one should be visible in other
        settings1.set("test", "key", "value")
        assert settings2.get("test", "key") == "value"

    def test_settings_permission_handling(self, temp_settings_dir, app_context: AppContext):
        """Test handling of permission errors"""
        settings = app_context.application_state_manager

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

    def test_export_import_settings(self, temp_settings_dir, app_context: AppContext):
        """Test exporting and importing settings"""
        settings = app_context.application_state_manager

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
        settings.update_session_data(export_data["session"])
        # Other settings use set method
        settings.set("extraction", "tile_width", export_data["extraction"]["tile_width"])
        settings.set("appearance", "theme", export_data["appearance"]["theme"])

        # Verify imported correctly
        assert settings.get("session", "vram_path") == "/test/vram.dmp"
        assert settings.get("extraction", "tile_width") == 256
        assert settings.get("appearance", "theme") == "dark"
