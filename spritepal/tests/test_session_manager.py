"""
Tests for SessionManager
"""
from __future__ import annotations

import pytest

from core.managers import SessionError, SessionManager, ValidationError

# Test characteristics: Real GUI components requiring display
pytestmark = [
    pytest.mark.file_io,
    pytest.mark.gui,
    pytest.mark.integration,
    pytest.mark.qt_app,
    pytest.mark.qt_real,
    pytest.mark.rom_data,
    pytest.mark.slow,
    pytest.mark.ci_safe,
    pytest.mark.headless,
    pytest.mark.signals_slots,
]

class TestSessionManager:
    """Test SessionManager functionality"""

    @pytest.fixture
    def temp_settings_dir(self, tmp_path, monkeypatch):
        """Create temporary directory for settings"""
        monkeypatch.chdir(tmp_path)
        return tmp_path

    @pytest.fixture
    def session_manager(self, temp_settings_dir):
        """Create SessionManager instance"""
        return SessionManager("TestApp")

    def test_initialization(self, session_manager):
        """Test SessionManager initialization"""
        assert session_manager.is_initialized()
        assert session_manager.get_name() == "SessionManager"
        assert session_manager._app_name == "TestApp"

    def test_default_settings(self, session_manager):
        """Test default settings structure"""
        # Check session defaults
        assert session_manager.get("session", "vram_path") == ""
        assert session_manager.get("session", "create_grayscale") is True
        assert session_manager.get("session", "create_metadata") is True

        # Check UI defaults
        assert session_manager.get("ui", "window_width") == 900
        assert session_manager.get("ui", "window_height") == 600

        # Check recent files
        assert session_manager.get_recent_files("vram") == []
        assert session_manager.get_recent_files("cgram") == []

    def test_get_and_set(self, session_manager):
        """Test getting and setting values"""
        # Set value
        session_manager.set("session", "vram_path", "/test/path.dmp")
        assert session_manager.get("session", "vram_path") == "/test/path.dmp"

        # Set in new category
        session_manager.set("custom", "key", "value")
        assert session_manager.get("custom", "key") == "value"

        # Get with default
        assert session_manager.get("missing", "key", "default") == "default"

    def test_session_data(self, session_manager):
        """Test session data management"""
        # Get initial session data
        data = session_manager.get_session_data()
        assert isinstance(data, dict)
        assert "vram_path" in data

        # Update session data
        new_data = {
            "vram_path": "/new/vram.dmp",
            "cgram_path": "/new/cgram.dmp",
            "output_name": "test_output"
        }
        session_manager.update_session_data(new_data)

        # Verify updates
        updated = session_manager.get_session_data()
        assert updated["vram_path"] == "/new/vram.dmp"
        assert updated["cgram_path"] == "/new/cgram.dmp"
        assert updated["output_name"] == "test_output"

    def test_file_paths_update(self, session_manager, qtbot):
        """Test file path updates"""
        # Connect to signal
        with qtbot.waitSignal(session_manager.files_updated) as blocker:
            session_manager.update_file_paths(
                vram="/test/vram.dmp",
                cgram="/test/cgram.dmp"
            )

        # Check signal data
        assert blocker.args[0] == {
            "vram_path": "/test/vram.dmp",
            "cgram_path": "/test/cgram.dmp"
        }

        # Check values were set
        assert session_manager.get("session", "vram_path") == "/test/vram.dmp"
        assert session_manager.get("session", "cgram_path") == "/test/cgram.dmp"

    def test_window_geometry(self, session_manager):
        """Test window geometry management"""
        # Get default geometry
        geometry = session_manager.get_window_geometry()
        assert geometry == {"width": 900, "height": 600, "x": -1, "y": -1}

        # Update geometry
        session_manager.update_window_state({
            "width": 1200,
            "height": 800,
            "x": 100,
            "y": 50
        })

        # Get updated geometry
        geometry = session_manager.get_window_geometry()
        assert geometry == {"width": 1200, "height": 800, "x": 100, "y": 50}

    def test_recent_files(self, session_manager, tmp_path):
        """Test recent files management"""
        # Create test files
        file1 = tmp_path / "file1.dmp"
        file2 = tmp_path / "file2.dmp"
        file3 = tmp_path / "file3.dmp"
        file1.touch()
        file2.touch()
        file3.touch()

        # Add files to recent
        session_manager._add_recent_file("vram", str(file1))
        session_manager._add_recent_file("vram", str(file2))
        session_manager._add_recent_file("vram", str(file3))

        # Check order (most recent first)
        recent = session_manager.get_recent_files("vram")
        assert recent == [str(file3), str(file2), str(file1)]

        # Add duplicate (should move to front)
        session_manager._add_recent_file("vram", str(file1))
        recent = session_manager.get_recent_files("vram")
        assert recent == [str(file1), str(file3), str(file2)]

        # Non-existent files should be filtered out
        session_manager._add_recent_file("vram", "/non/existent/file.dmp")
        recent = session_manager.get_recent_files("vram")
        assert "/non/existent/file.dmp" not in recent

    def test_save_and_restore(self, session_manager, temp_settings_dir, qtbot):
        """Test saving and restoring session"""
        # Set some values
        session_manager.set("session", "vram_path", "/test/vram.dmp")
        session_manager.set("ui", "window_width", 1024)

        # Save session
        with qtbot.waitSignal(session_manager.settings_saved):
            session_manager.save_session()

        # Verify file exists
        settings_file = temp_settings_dir / ".testapp_settings.json"
        assert settings_file.exists()

        # Create new manager and verify it loads saved settings
        new_manager = SessionManager("TestApp")
        assert new_manager.get("session", "vram_path") == "/test/vram.dmp"
        assert new_manager.get("ui", "window_width") == 1024

        # Test restore
        with qtbot.waitSignal(new_manager.session_restored):
            data = new_manager.restore_session()

        assert data["vram_path"] == "/test/vram.dmp"

    def test_clear_session(self, session_manager, qtbot):
        """Test clearing session"""
        # Set some values
        session_manager.set("session", "vram_path", "/test/vram.dmp")
        session_manager.set("session", "output_name", "test")

        # Clear session
        with qtbot.waitSignal(session_manager.session_changed):
            session_manager.clear_session()

        # Check values reset to defaults
        assert session_manager.get("session", "vram_path") == ""
        assert session_manager.get("session", "output_name") == ""
        assert session_manager.get("session", "create_grayscale") is True

    def test_clear_recent_files(self, session_manager, tmp_path):
        """Test clearing recent files"""
        # Add some files
        file1 = tmp_path / "file1.dmp"
        file1.touch()
        session_manager._add_recent_file("vram", str(file1))
        session_manager._add_recent_file("cgram", str(file1))

        # Clear specific type
        session_manager.clear_recent_files("vram")
        assert session_manager.get_recent_files("vram") == []
        assert session_manager.get_recent_files("cgram") == [str(file1)]

        # Clear all
        session_manager.clear_recent_files()
        assert session_manager.get_recent_files("cgram") == []

    def test_export_import_settings(self, session_manager, tmp_path):
        """Test exporting and importing settings"""
        # Set some custom values
        session_manager.set("session", "vram_path", "/custom/vram.dmp")
        session_manager.set("ui", "window_width", 1280)

        # Export settings
        export_file = tmp_path / "exported_settings.json"
        session_manager.export_settings(str(export_file))
        assert export_file.exists()

        # Create new manager with defaults
        new_manager = SessionManager("TestApp2")
        assert new_manager.get("session", "vram_path") == ""

        # Import settings
        new_manager.import_settings(str(export_file))
        assert new_manager.get("session", "vram_path") == "/custom/vram.dmp"
        assert new_manager.get("ui", "window_width") == 1280

    def test_import_invalid_settings(self, session_manager, tmp_path):
        """Test importing invalid settings"""
        # Create invalid settings file
        invalid_file = tmp_path / "invalid.json"
        invalid_file.write_text("not json")

        with pytest.raises(SessionError, match="Could not import settings"):
            session_manager.import_settings(str(invalid_file))

        # Create settings with wrong format
        wrong_format = tmp_path / "wrong_format.json"
        wrong_format.write_text("[]")  # Array instead of object

        with pytest.raises(ValidationError, match="Invalid settings file format"):
            session_manager.import_settings(str(wrong_format))

    def test_signal_emissions(self, session_manager, qtbot):
        """Test various signal emissions"""
        # Test session_changed signal
        with qtbot.waitSignal(session_manager.session_changed):
            session_manager.set("session", "vram_path", "/new/path.dmp")

        # Test files_updated signal
        with qtbot.waitSignal(session_manager.files_updated) as blocker:
            session_manager.set("session", "cgram_path", "/new/cgram.dmp")
        assert blocker.args[0] == {"cgram_path": "/new/cgram.dmp"}

        # Setting same value shouldn't emit signal
        with qtbot.assertNotEmitted(session_manager.session_changed):
            session_manager.set("session", "cgram_path", "/new/cgram.dmp")

    def test_cleanup(self, session_manager):
        """Test cleanup saves dirty session"""
        # Make session dirty
        session_manager.set("session", "vram_path", "/test/path.dmp")
        assert session_manager._session_dirty

        # Cleanup should save
        session_manager.cleanup()

        # Create new manager and verify saved
        new_manager = SessionManager("TestApp")
        assert new_manager.get("session", "vram_path") == "/test/path.dmp"

    def test_recent_files_limit(self, session_manager, tmp_path):
        """Test recent files limit is respected"""
        # Create many test files
        files = []
        for i in range(15):
            file = tmp_path / f"file{i}.dmp"
            file.touch()
            files.append(str(file))

        # Add all files
        for file in files:
            session_manager._add_recent_file("vram", file)

        # Should only keep max_recent (10 by default)
        recent = session_manager.get_recent_files("vram")
        assert len(recent) == 10

        # Most recent files should be kept
        expected = list(reversed(files[-10:]))
        assert recent == expected

    def test_empty_and_null_values(self, session_manager):
        """Test handling of empty and null values"""
        # Empty string
        session_manager.set("session", "vram_path", "")
        assert session_manager.get("session", "vram_path") == ""

        # None value
        session_manager.set("session", "output_name", None)
        assert session_manager.get("session", "output_name") is None

        # Empty dict
        session_manager.update_session_data({})
        # Should not crash, values unchanged
        assert session_manager.get("session", "vram_path") == ""

    def test_invalid_file_paths(self, session_manager):
        """Test handling of invalid file paths"""
        # Non-existent file
        session_manager.update_file_paths(vram="/non/existent/path.dmp")
        # Should accept it (path validation is done elsewhere)
        assert session_manager.get("session", "vram_path") == "/non/existent/path.dmp"

        # Empty path
        session_manager.update_file_paths(vram="", cgram=None)
        assert session_manager.get("session", "vram_path") == ""
        # None should not update
        assert session_manager.get("session", "cgram_path") is not None

    def test_concurrent_modifications(self, session_manager):
        """Test concurrent modifications don't cause issues"""
        # Simulate rapid changes
        for i in range(100):
            session_manager.set("session", "counter", i)

        assert session_manager.get("session", "counter") == 99
        assert session_manager._session_dirty

    def test_corrupted_settings_file_recovery(self, temp_settings_dir):
        """Test recovery from corrupted settings file"""
        # Create corrupted settings file
        settings_file = temp_settings_dir / ".testapp_settings.json"
        settings_file.write_text('{"session": {"vram_path": "/test"')  # Incomplete JSON

        # Should load defaults without crashing
        manager = SessionManager("TestApp")
        assert manager.get("session", "vram_path") == ""  # Default value

    def test_large_settings_file(self, session_manager, tmp_path):
        """Test handling of large settings"""
        # Add many recent files
        for i in range(100):
            file = tmp_path / f"large_file_{i}.dmp"
            file.touch()
            for file_type in ["vram", "cgram", "oam", "rom"]:
                session_manager._add_recent_file(file_type, str(file))

        # Add large custom data
        large_data = {f"key_{i}": f"value_{i}" * 100 for i in range(100)}
        session_manager.set("large_category", "data", large_data)

        # Save and reload
        session_manager.save_session()

        # Should handle large file without issues
        new_manager = SessionManager("TestApp")
        assert new_manager.get("large_category", "data") == large_data

    def test_special_characters_in_paths(self, session_manager, tmp_path):
        """Test handling of special characters in file paths"""
        # Create file with special characters
        special_file = tmp_path / "file with spaces & special!@#$%.dmp"
        special_file.touch()

        session_manager.update_file_paths(vram=str(special_file))
        assert session_manager.get("session", "vram_path") == str(special_file)

        # Add to recent files
        session_manager._add_recent_file("vram", str(special_file))
        recent = session_manager.get_recent_files("vram")
        assert str(special_file) in recent

    def test_export_to_invalid_location(self, session_manager):
        """Test exporting to invalid location"""
        with pytest.raises(SessionError, match="Could not export settings"):
            session_manager.export_settings("/invalid/path/that/does/not/exist/settings.json")

    def test_import_missing_sections(self, session_manager, tmp_path):
        """Test importing settings with missing sections"""
        # Create settings with only partial data
        partial_file = tmp_path / "partial.json"
        partial_file.write_text('{"session": {"vram_path": "/custom/path.dmp"}}')

        # Should import and merge with defaults
        session_manager.import_settings(str(partial_file))
        assert session_manager.get("session", "vram_path") == "/custom/path.dmp"
        assert session_manager.get("ui", "window_width") == 900  # Default

    def test_window_state_partial_update(self, session_manager):
        """Test partial window state updates"""
        # Set initial state
        session_manager.update_window_state({"width": 1000, "height": 700})

        # Partial update
        session_manager.update_window_state({"x": 50, "y": 100})

        # All values should be present
        geometry = session_manager.get_window_geometry()
        assert geometry == {"width": 1000, "height": 700, "x": 50, "y": 100}

    def test_session_changed_signal_batching(self, session_manager, qtbot):
        """Test that multiple changes in update_session_data emit single signal"""
        data = {
            "vram_path": "/new/vram.dmp",
            "cgram_path": "/new/cgram.dmp",
            "oam_path": "/new/oam.dmp",
            "output_name": "new_output"
        }

        # Should emit only one session_changed signal
        with qtbot.waitSignal(session_manager.session_changed, timeout=1000) as blocker:
            session_manager.update_session_data(data)

        # Should emit files_updated with all file changes
        with qtbot.waitSignal(session_manager.files_updated) as blocker:
            # Need to change values for signal to be emitted
            session_manager.update_session_data({
                "vram_path": "/another/vram.dmp",
                "cgram_path": "/another/cgram.dmp",
                "oam_path": "/another/oam.dmp"
            })
        assert len(blocker.args[0]) == 3  # vram, cgram, oam paths
