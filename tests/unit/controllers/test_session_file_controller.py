"""Unit tests for SessionFileController."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import SignalInstance

from ui.controllers.session_file_controller import (
    EXTRACTION_PANEL_CONFIG,
    ROM_PANEL_CONFIG,
    SessionFileConfig,
    SessionFileController,
    SessionFileEntry,
    ValidatedSessionData,
    create_extraction_panel_controller,
    create_rom_panel_controller,
)


class TestSessionFileEntry:
    """Tests for SessionFileEntry dataclass."""

    def test_creation(self) -> None:
        """Should create entry with all fields."""
        entry = SessionFileEntry(key="vram_path", path="/path/to/file.bin", exists=True)
        assert entry.key == "vram_path"
        assert entry.path == "/path/to/file.bin"
        assert entry.exists is True

    def test_missing_file(self) -> None:
        """Should track non-existent file."""
        entry = SessionFileEntry(key="cgram_path", path="/missing.bin", exists=False)
        assert entry.exists is False


class TestValidatedSessionData:
    """Tests for ValidatedSessionData dataclass."""

    def test_valid_files_property(self) -> None:
        """Should return only files that exist."""
        files = [
            SessionFileEntry(key="a", path="/a", exists=True),
            SessionFileEntry(key="b", path="/b", exists=False),
            SessionFileEntry(key="c", path="/c", exists=True),
        ]
        data = ValidatedSessionData(files=files, extras={})

        valid = data.valid_files
        assert len(valid) == 2
        assert all(f.exists for f in valid)

    def test_missing_files_property(self) -> None:
        """Should return only files that don't exist."""
        files = [
            SessionFileEntry(key="a", path="/a", exists=True),
            SessionFileEntry(key="b", path="/b", exists=False),
        ]
        data = ValidatedSessionData(files=files, extras={})

        missing = data.missing_files
        assert len(missing) == 1
        assert missing[0].key == "b"

    def test_has_any_valid(self) -> None:
        """Should indicate if any files are valid."""
        files_with_valid = [SessionFileEntry(key="a", path="/a", exists=True)]
        data_valid = ValidatedSessionData(files=files_with_valid, extras={})
        assert data_valid.has_any_valid is True

        files_none_valid = [SessionFileEntry(key="a", path="/a", exists=False)]
        data_invalid = ValidatedSessionData(files=files_none_valid, extras={})
        assert data_invalid.has_any_valid is False


class TestSessionFileConfig:
    """Tests for SessionFileConfig dataclass."""

    def test_default_config(self) -> None:
        """Should create empty config by default."""
        config = SessionFileConfig()
        assert config.file_keys == []
        assert config.extra_keys == []

    def test_custom_config(self) -> None:
        """Should accept custom keys."""
        config = SessionFileConfig(
            file_keys=["file1", "file2"],
            extra_keys=["mode"],
        )
        assert len(config.file_keys) == 2
        assert len(config.extra_keys) == 1


class TestPredefinedConfigs:
    """Tests for predefined configurations."""

    def test_extraction_panel_config(self) -> None:
        """Should have correct extraction panel keys."""
        assert "vram_path" in EXTRACTION_PANEL_CONFIG.file_keys
        assert "cgram_path" in EXTRACTION_PANEL_CONFIG.file_keys
        assert "oam_path" in EXTRACTION_PANEL_CONFIG.file_keys
        assert "extraction_mode" in EXTRACTION_PANEL_CONFIG.extra_keys

    def test_rom_panel_config(self) -> None:
        """Should have correct ROM panel keys."""
        assert "rom_path" in ROM_PANEL_CONFIG.file_keys
        assert "output_path" in ROM_PANEL_CONFIG.file_keys
        assert "sprite_name" in ROM_PANEL_CONFIG.extra_keys
        assert "manual_mode" in ROM_PANEL_CONFIG.extra_keys


class TestSessionFileControllerInit:
    """Tests for controller initialization."""

    def test_default_initialization(self) -> None:
        """Should initialize with empty config."""
        controller = SessionFileController()
        assert controller.config.file_keys == []

    def test_custom_config(self) -> None:
        """Should accept custom configuration."""
        config = SessionFileConfig(file_keys=["path1"])
        controller = SessionFileController(config=config)
        assert controller.config.file_keys == ["path1"]

    def test_has_signals(self) -> None:
        """Should have expected signals."""
        controller = SessionFileController()
        assert isinstance(controller.validation_complete, SignalInstance)


class TestValidateSessionData:
    """Tests for validate_session_data method."""

    def test_validates_existing_files(self, tmp_path) -> None:
        """Should validate file existence."""
        # Create a real file
        real_file = tmp_path / "real.bin"
        real_file.write_bytes(b"test")

        config = SessionFileConfig(file_keys=["file1", "file2"])
        controller = SessionFileController(config=config)

        data = {
            "file1": str(real_file),
            "file2": "/nonexistent/path.bin",
        }

        result = controller.validate_session_data(data)

        assert len(result.files) == 2
        file1 = next(f for f in result.files if f.key == "file1")
        file2 = next(f for f in result.files if f.key == "file2")

        assert file1.exists is True
        assert file2.exists is False

    def test_handles_empty_paths(self) -> None:
        """Should handle empty or missing paths."""
        config = SessionFileConfig(file_keys=["file1"])
        controller = SessionFileController(config=config)

        result = controller.validate_session_data({})

        assert len(result.files) == 1
        assert result.files[0].path == ""
        assert result.files[0].exists is False

    def test_collects_extras(self) -> None:
        """Should collect extra data."""
        config = SessionFileConfig(
            file_keys=["path"],
            extra_keys=["mode", "count"],
        )
        controller = SessionFileController(config=config)

        data = {"path": "", "mode": 1, "count": 5, "unrelated": "ignored"}

        result = controller.validate_session_data(data)

        assert result.extras["mode"] == 1
        assert result.extras["count"] == 5
        assert "unrelated" not in result.extras

    def test_emits_signal(self, qtbot) -> None:
        """Should emit validation_complete signal."""
        config = SessionFileConfig(file_keys=["file"])
        controller = SessionFileController(config=config)

        with qtbot.waitSignal(controller.validation_complete, timeout=1000) as blocker:
            controller.validate_session_data({"file": "/test"})

        assert isinstance(blocker.args[0], ValidatedSessionData)


class TestBuildSessionData:
    """Tests for build_session_data method."""

    def test_builds_session_data(self) -> None:
        """Should build complete session data."""
        config = SessionFileConfig(
            file_keys=["path1", "path2"],
            extra_keys=["mode"],
        )
        controller = SessionFileController(config=config)

        result = controller.build_session_data(
            file_paths={"path1": "/file1.bin", "path2": "/file2.bin"},
            extras={"mode": 2},
        )

        assert result["path1"] == "/file1.bin"
        assert result["path2"] == "/file2.bin"
        assert result["mode"] == 2

    def test_handles_missing_keys(self) -> None:
        """Should use empty string for missing file keys."""
        config = SessionFileConfig(file_keys=["path1", "path2"])
        controller = SessionFileController(config=config)

        result = controller.build_session_data(file_paths={"path1": "/file1.bin"})

        assert result["path1"] == "/file1.bin"
        assert result["path2"] == ""

    def test_filters_extra_keys(self) -> None:
        """Should only include configured extra keys."""
        config = SessionFileConfig(extra_keys=["mode"])
        controller = SessionFileController(config=config)

        result = controller.build_session_data(
            file_paths={},
            extras={"mode": 1, "other": "ignored"},
        )

        assert result.get("mode") == 1
        assert "other" not in result


class TestGetValidPaths:
    """Tests for get_valid_paths method."""

    def test_returns_only_existing(self, tmp_path) -> None:
        """Should return only paths that exist."""
        real_file = tmp_path / "real.bin"
        real_file.write_bytes(b"test")

        config = SessionFileConfig(file_keys=["file1", "file2"])
        controller = SessionFileController(config=config)

        data = {
            "file1": str(real_file),
            "file2": "/nonexistent.bin",
        }

        result = controller.get_valid_paths(data)

        assert "file1" in result
        assert "file2" not in result


class TestStaticMethods:
    """Tests for static utility methods."""

    def test_check_file_exists_true(self, tmp_path) -> None:
        """Should return True for existing file."""
        real_file = tmp_path / "test.bin"
        real_file.write_bytes(b"data")

        assert SessionFileController.check_file_exists(str(real_file)) is True
        assert SessionFileController.check_file_exists(real_file) is True

    def test_check_file_exists_false(self) -> None:
        """Should return False for non-existing file."""
        assert SessionFileController.check_file_exists("/nonexistent") is False
        assert SessionFileController.check_file_exists(None) is False
        assert SessionFileController.check_file_exists("") is False

    def test_normalize_path(self, tmp_path) -> None:
        """Should normalize paths to strings."""
        path = tmp_path / "test.bin"

        assert SessionFileController.normalize_path(path) == str(path)
        assert SessionFileController.normalize_path(str(path)) == str(path)
        assert SessionFileController.normalize_path(None) == ""
        assert SessionFileController.normalize_path("") == ""


class TestFactoryFunctions:
    """Tests for factory functions."""

    def test_create_extraction_panel_controller(self) -> None:
        """Should create controller with extraction config."""
        controller = create_extraction_panel_controller()

        assert "vram_path" in controller.config.file_keys
        assert "extraction_mode" in controller.config.extra_keys

    def test_create_rom_panel_controller(self) -> None:
        """Should create controller with ROM config."""
        controller = create_rom_panel_controller()

        assert "rom_path" in controller.config.file_keys
        assert "manual_mode" in controller.config.extra_keys


class TestSetConfig:
    """Tests for set_config method."""

    def test_updates_config(self) -> None:
        """Should update controller configuration."""
        controller = SessionFileController()
        assert controller.config.file_keys == []

        new_config = SessionFileConfig(file_keys=["new_key"])
        controller.set_config(new_config)

        assert controller.config.file_keys == ["new_key"]
