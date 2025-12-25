"""Unit tests for ROMSessionController."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import SignalInstance

from ui.controllers.rom_session_controller import (
    HeaderDisplayInfo,
    ROMInfo,
    ROMSessionController,
    SETTINGS_KEY_LAST_INPUT_ROM,
    SETTINGS_NS_ROM_INJECTION,
)


class TestROMInfo:
    """Tests for ROMInfo dataclass."""

    def test_creation(self) -> None:
        """Should create info with all fields."""
        info = ROMInfo(
            path="/path/to/rom.sfc",
            size=2097152,
            suggested_output="rom_sprites",
        )
        assert info.path == "/path/to/rom.sfc"
        assert info.size == 2097152
        assert info.suggested_output == "rom_sprites"

    def test_frozen(self) -> None:
        """Info should be immutable."""
        info = ROMInfo(
            path="/path/to/rom.sfc",
            size=2097152,
            suggested_output="rom_sprites",
        )
        with pytest.raises(AttributeError):
            info.path = "/other/path"  # type: ignore[misc]


class TestHeaderDisplayInfo:
    """Tests for HeaderDisplayInfo dataclass."""

    def test_creation(self) -> None:
        """Should create display info with all fields."""
        info = HeaderDisplayInfo(
            title="Super Game",
            checksum="0x1234",
            has_config=True,
            html="<b>Title:</b> Super Game",
        )
        assert info.title == "Super Game"
        assert info.checksum == "0x1234"
        assert info.has_config is True
        assert "<b>Title:</b>" in info.html


class TestROMSessionControllerInit:
    """Tests for controller initialization."""

    def test_initial_state(self) -> None:
        """Should initialize with empty state."""
        controller = ROMSessionController()
        assert controller.rom_path == ""
        assert controller.rom_size == 0

    def test_has_signals(self) -> None:
        """Should have expected signals."""
        controller = ROMSessionController()
        assert isinstance(controller.rom_loaded, SignalInstance)
        assert isinstance(controller.header_formatted, SignalInstance)
        assert isinstance(controller.error_occurred, SignalInstance)


class TestGetLastRomPath:
    """Tests for get_last_rom_path method."""

    def test_returns_path_if_exists(self, tmp_path) -> None:
        """Should return path if file exists."""
        rom_file = tmp_path / "test.sfc"
        rom_file.write_bytes(b"test rom")

        controller = ROMSessionController()

        mock_settings = MagicMock()
        mock_settings.get.return_value = str(rom_file)

        with patch("core.di_container.inject", return_value=mock_settings):
            result = controller.get_last_rom_path()

        assert result == str(rom_file)
        mock_settings.get.assert_called_once_with(
            SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_INPUT_ROM, ""
        )

    def test_returns_none_if_not_exists(self, tmp_path) -> None:
        """Should return None if file doesn't exist."""
        controller = ROMSessionController()

        mock_settings = MagicMock()
        mock_settings.get.return_value = str(tmp_path / "nonexistent.sfc")

        with patch("core.di_container.inject", return_value=mock_settings):
            result = controller.get_last_rom_path()

        assert result is None

    def test_returns_none_if_empty(self) -> None:
        """Should return None if no ROM in settings."""
        controller = ROMSessionController()

        mock_settings = MagicMock()
        mock_settings.get.return_value = ""

        with patch("core.di_container.inject", return_value=mock_settings):
            result = controller.get_last_rom_path()

        assert result is None

    def test_handles_exception(self) -> None:
        """Should return None on exception."""
        controller = ROMSessionController()

        with patch(
            "core.di_container.inject",
            side_effect=Exception("Settings error"),
        ):
            result = controller.get_last_rom_path()

        assert result is None


class TestLoadRomFile:
    """Tests for load_rom_file method."""

    def test_loads_valid_rom(self, qtbot, tmp_path) -> None:
        """Should load ROM and emit signal."""
        rom_file = tmp_path / "test.sfc"
        rom_data = b"x" * 2097152  # 2MB
        rom_file.write_bytes(rom_data)

        controller = ROMSessionController()
        mock_settings = MagicMock()

        with patch("core.di_container.inject", return_value=mock_settings):
            with qtbot.waitSignal(controller.rom_loaded, timeout=1000) as blocker:
                result = controller.load_rom_file(str(rom_file))

        assert result is not None
        assert result.path == str(rom_file)
        assert result.size == 2097152
        assert result.suggested_output == "test_sprites"

        # Signal should emit ROMInfo
        emitted_info = blocker.args[0]
        assert isinstance(emitted_info, ROMInfo)
        assert emitted_info.path == str(rom_file)

    def test_updates_internal_state(self, tmp_path) -> None:
        """Should update internal ROM state."""
        rom_file = tmp_path / "test.sfc"
        rom_file.write_bytes(b"x" * 1024)

        controller = ROMSessionController()
        mock_settings = MagicMock()

        with patch("core.di_container.inject", return_value=mock_settings):
            controller.load_rom_file(str(rom_file))

        assert controller.rom_path == str(rom_file)
        assert controller.rom_size == 1024

    def test_saves_to_settings(self, tmp_path) -> None:
        """Should save ROM path to settings."""
        rom_file = tmp_path / "test.sfc"
        rom_file.write_bytes(b"x" * 1024)

        controller = ROMSessionController()
        mock_settings = MagicMock()

        with patch("core.di_container.inject", return_value=mock_settings):
            controller.load_rom_file(str(rom_file))

        mock_settings.set.assert_any_call(
            SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_INPUT_ROM, str(rom_file)
        )
        mock_settings.set_last_used_directory.assert_called_once_with(str(tmp_path))

    def test_returns_none_for_empty_path(self) -> None:
        """Should return None for empty path."""
        controller = ROMSessionController()
        result = controller.load_rom_file("")
        assert result is None

    def test_returns_none_for_nonexistent_file(self, qtbot, tmp_path) -> None:
        """Should return None and emit error for nonexistent file."""
        controller = ROMSessionController()

        with qtbot.waitSignal(controller.error_occurred, timeout=1000):
            result = controller.load_rom_file(str(tmp_path / "nonexistent.sfc"))

        assert result is None

    def test_generates_correct_output_name(self, tmp_path) -> None:
        """Should generate output name from ROM filename."""
        rom_file = tmp_path / "kirby_super_star.sfc"
        rom_file.write_bytes(b"x" * 1024)

        controller = ROMSessionController()
        mock_settings = MagicMock()

        with patch("core.di_container.inject", return_value=mock_settings):
            result = controller.load_rom_file(str(rom_file))

        assert result is not None
        assert result.suggested_output == "kirby_super_star_sprites"


class TestFormatHeader:
    """Tests for format_header method."""

    def test_formats_valid_header(self, qtbot) -> None:
        """Should format header with all info."""
        # Create a mock header
        @dataclass
        class MockHeader:
            title: str = "KIRBY SUPER STAR"
            checksum: int = 0x1234

        controller = ROMSessionController()
        header = MockHeader()

        with qtbot.waitSignal(controller.header_formatted, timeout=1000) as blocker:
            result = controller.format_header(header, has_sprite_configs=True)

        assert result.title == "KIRBY SUPER STAR"
        assert result.checksum == "0x1234"
        assert result.has_config is True
        assert "<b>Title:</b> KIRBY SUPER STAR" in result.html
        assert "0x1234" in result.html
        assert "Configuration found" in result.html

        # Signal should emit HeaderDisplayInfo
        emitted_info = blocker.args[0]
        assert isinstance(emitted_info, HeaderDisplayInfo)

    def test_formats_header_without_config(self, qtbot) -> None:
        """Should show warning for unknown ROM."""
        @dataclass
        class MockHeader:
            title: str = "UNKNOWN ROM"
            checksum: int = 0x5678

        controller = ROMSessionController()
        header = MockHeader()

        with qtbot.waitSignal(controller.header_formatted, timeout=1000):
            result = controller.format_header(header, has_sprite_configs=False)

        assert result.has_config is False
        assert "Unknown ROM version" in result.html
        assert "Find Sprites" in result.html

    def test_formats_none_header(self, qtbot) -> None:
        """Should show error for None header."""
        controller = ROMSessionController()

        with qtbot.waitSignal(controller.header_formatted, timeout=1000):
            result = controller.format_header(None, has_sprite_configs=False)

        assert result.title == "Unknown"
        assert result.has_config is False
        assert "Error reading ROM header" in result.html


class TestClear:
    """Tests for clear method."""

    def test_clears_state(self, tmp_path) -> None:
        """Should clear ROM state."""
        rom_file = tmp_path / "test.sfc"
        rom_file.write_bytes(b"x" * 1024)

        controller = ROMSessionController()
        controller._current_rom_path = str(rom_file)
        controller._current_rom_size = 1024

        controller.clear()

        assert controller.rom_path == ""
        assert controller.rom_size == 0
