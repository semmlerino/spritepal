"""Tests for PaletteOffsetCalculator service."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.frame_mapping_project import GameFrame
from core.services.palette_offset_calculator import (
    PaletteOffsetCalculator,
    parse_offset,
)


class TestParseOffset:
    """Tests for parse_offset utility function."""

    def test_parse_hex_string(self) -> None:
        assert parse_offset("0x1234") == 0x1234

    def test_parse_decimal_string(self) -> None:
        assert parse_offset("1234") == 1234

    def test_parse_int(self) -> None:
        assert parse_offset(0x1234) == 0x1234


class TestPaletteOffsetCalculator:
    """Tests for PaletteOffsetCalculator."""

    @pytest.fixture
    def mock_rom_extractor(self) -> MagicMock:
        """Create mock ROM extractor."""
        extractor = MagicMock()
        header = MagicMock()
        header.title = "KIRBY SUPER DX"
        header.checksum = 0x1234
        extractor.read_rom_header.return_value = header
        return extractor

    @pytest.fixture
    def mock_config_loader(self) -> MagicMock:
        """Create mock config loader."""
        return MagicMock()

    @pytest.fixture
    def calculator(self, mock_rom_extractor: MagicMock, mock_config_loader: MagicMock) -> PaletteOffsetCalculator:
        """Create calculator with mocked dependencies."""
        return PaletteOffsetCalculator(mock_rom_extractor, mock_config_loader)

    @pytest.fixture
    def game_frame(self) -> GameFrame:
        """Create a test game frame."""
        return GameFrame(
            id="F1234",
            rom_offsets=[0x80000, 0x80100],
            palette_index=2,
        )

    def test_returns_none_when_no_game_config(
        self,
        calculator: PaletteOffsetCalculator,
        mock_config_loader: MagicMock,
        game_frame: GameFrame,
        tmp_path: Path,
    ) -> None:
        """Should return None when no game config found."""
        mock_config_loader.find_game_config.return_value = (None, None)

        result = calculator.calculate(tmp_path / "rom.smc", game_frame)

        assert result is None

    def test_generic_palette_calculation(
        self,
        calculator: PaletteOffsetCalculator,
        mock_config_loader: MagicMock,
        game_frame: GameFrame,
        tmp_path: Path,
    ) -> None:
        """Should calculate offset from base + palette_index * 32."""
        mock_config_loader.find_game_config.return_value = (
            "Kirby Super Star",
            {"palettes": {"offset": "0x10000"}},
        )

        result = calculator.calculate(tmp_path / "rom.smc", game_frame)

        # base 0x10000 + palette_index 2 * 32 = 0x10040
        assert result == 0x10040

    def test_character_specific_offset_via_hint(
        self,
        calculator: PaletteOffsetCalculator,
        mock_config_loader: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Should use character-specific offset when ROM offset matches hint."""
        mock_config_loader.find_game_config.return_value = (
            "Kirby Super Star",
            {
                "palettes": {
                    "offset": "0x10000",
                    "character_offsets": {
                        "King Dedede": {
                            "offset": "0x20000",
                            "rom_offset_hints": ["0x80000", "0x80100"],
                        }
                    },
                }
            },
        )

        game_frame = GameFrame(
            id="F1234",
            rom_offsets=[0x80000],  # Matches hint
            palette_index=0,
        )

        result = calculator.calculate(tmp_path / "rom.smc", game_frame)

        assert result == 0x20000

    def test_character_offset_single_character_default(
        self,
        calculator: PaletteOffsetCalculator,
        mock_config_loader: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Should use single character offset as default when no hint match."""
        mock_config_loader.find_game_config.return_value = (
            "Kirby Super Star",
            {
                "palettes": {
                    "offset": "0x10000",
                    "character_offsets": {
                        "King Dedede": {
                            "offset": "0x20000",
                            "rom_offset_hints": ["0x90000"],  # Different from game_frame
                        }
                    },
                }
            },
        )

        game_frame = GameFrame(
            id="F1234",
            rom_offsets=[0x80000],  # Doesn't match hint
            palette_index=0,
        )

        result = calculator.calculate(tmp_path / "rom.smc", game_frame)

        # Single character default should be used
        assert result == 0x20000

    def test_falls_back_to_generic_when_multiple_characters_no_match(
        self,
        calculator: PaletteOffsetCalculator,
        mock_config_loader: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Should fall back to generic when multiple characters and no hint match."""
        mock_config_loader.find_game_config.return_value = (
            "Kirby Super Star",
            {
                "palettes": {
                    "offset": "0x10000",
                    "character_offsets": {
                        "King Dedede": {
                            "offset": "0x20000",
                            "rom_offset_hints": ["0x90000"],
                        },
                        "Meta Knight": {
                            "offset": "0x30000",
                            "rom_offset_hints": ["0xA0000"],
                        },
                    },
                }
            },
        )

        game_frame = GameFrame(
            id="F1234",
            rom_offsets=[0x80000],  # Doesn't match any hint
            palette_index=1,
        )

        result = calculator.calculate(tmp_path / "rom.smc", game_frame)

        # Falls back to generic: 0x10000 + 1 * 32 = 0x10020
        assert result == 0x10020

    def test_returns_none_when_no_palette_config(
        self,
        calculator: PaletteOffsetCalculator,
        mock_config_loader: MagicMock,
        game_frame: GameFrame,
        tmp_path: Path,
    ) -> None:
        """Should return None when palettes config is missing."""
        mock_config_loader.find_game_config.return_value = (
            "Kirby Super Star",
            {"sprites": {}},  # No palettes key
        )

        result = calculator.calculate(tmp_path / "rom.smc", game_frame)

        assert result is None

    def test_returns_none_on_exception(
        self,
        calculator: PaletteOffsetCalculator,
        mock_rom_extractor: MagicMock,
        game_frame: GameFrame,
        tmp_path: Path,
    ) -> None:
        """Should return None and log warning on exception."""
        mock_rom_extractor.read_rom_header.side_effect = FileNotFoundError("ROM not found")

        result = calculator.calculate(tmp_path / "rom.smc", game_frame)

        assert result is None

    def test_handles_int_hints(
        self,
        calculator: PaletteOffsetCalculator,
        mock_config_loader: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Should handle int hints (not just string)."""
        mock_config_loader.find_game_config.return_value = (
            "Kirby Super Star",
            {
                "palettes": {
                    "character_offsets": {
                        "King Dedede": {
                            "offset": "0x20000",
                            "rom_offset_hints": [0x80000],  # Int, not string
                        }
                    },
                }
            },
        )

        game_frame = GameFrame(
            id="F1234",
            rom_offsets=[0x80000],
            palette_index=0,
        )

        result = calculator.calculate(tmp_path / "rom.smc", game_frame)

        assert result == 0x20000
