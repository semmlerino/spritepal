"""Tests for PaletteManager class"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

# NOTE: pythonpath configured in pyproject.toml - no sys.path manipulation needed
from core.palette_manager import PaletteManager
from utils.constants import (
    COLORS_PER_PALETTE,
    SPRITE_PALETTE_END,
    SPRITE_PALETTE_START,
)

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.no_qt,
    pytest.mark.rom_data,
]

class TestPaletteManager:
    """Test the PaletteManager functionality"""

    @pytest.fixture
    def palette_manager(self):
        """Create a PaletteManager instance"""
        return PaletteManager()

    @pytest.fixture
    def sample_cgram_data(self):
        """Create sample CGRAM data for testing"""
        # CGRAM contains 256 colors (16 palettes x 16 colors)
        # Each color is 2 bytes in BGR555 format
        cgram_data = bytearray(512)  # 256 colors * 2 bytes

        # Set up palette 8 (Kirby) with some test colors
        # Color 0: Black (0, 0, 0)
        cgram_data[256] = 0x00
        cgram_data[257] = 0x00

        # Color 1: Pink (255, 156, 156) -> BGR555
        # R=31, G=19, B=19 -> 0x4E7F
        cgram_data[258] = 0x7F
        cgram_data[259] = 0x4E

        # Color 2: White (255, 255, 255) -> BGR555
        # R=31, G=31, B=31 -> 0x7FFF
        cgram_data[260] = 0xFF
        cgram_data[261] = 0x7F

        return bytes(cgram_data)

    def test_init(self, palette_manager):
        """Test palette manager initialization"""
        assert palette_manager.cgram_data is None
        assert palette_manager.palettes == {}

    def test_load_cgram(self, palette_manager, sample_cgram_data):
        """Test loading CGRAM data"""
        with tempfile.NamedTemporaryFile(suffix=".dmp", delete=False) as f:
            f.write(sample_cgram_data)
            f.flush()

        try:
            palette_manager.load_cgram(f.name)
            assert palette_manager.cgram_data == sample_cgram_data
            assert len(palette_manager.palettes) == 16
        finally:
            Path(f.name).unlink()

    def test_extract_palettes(self, palette_manager, sample_cgram_data):
        """Test palette extraction from CGRAM"""
        palette_manager.cgram_data = sample_cgram_data
        palette_manager._extract_palettes()

        # Check we have 16 palettes
        assert len(palette_manager.palettes) == 16

        # Check palette 8 colors
        pal8 = palette_manager.palettes[8]
        assert len(pal8) == COLORS_PER_PALETTE

        # Check specific colors
        assert pal8[0] == [0, 0, 0]  # Black
        assert pal8[1] == [255, 156, 156]  # Pink
        assert pal8[2] == [255, 255, 255]  # White

    def test_bgr555_conversion(self, palette_manager):
        """Test BGR555 to RGB888 conversion"""
        # Create minimal CGRAM with one color
        cgram_data = bytearray(2)

        # Test cases: BGR555 -> RGB888
        test_cases = [
            (0x00, 0x00, [0, 0, 0]),  # Black
            (0xFF, 0x7F, [255, 255, 255]),  # White
            (0x1F, 0x00, [255, 0, 0]),  # Red
            (0xE0, 0x03, [0, 255, 0]),  # Green
            (0x00, 0x7C, [0, 0, 255]),  # Blue
        ]

        for low, high, expected in test_cases:
            cgram_data[0] = low
            cgram_data[1] = high
            palette_manager.cgram_data = bytes(cgram_data + bytearray(510))
            palette_manager._extract_palettes()

            assert palette_manager.palettes[0][0] == expected

    def test_get_palette(self, palette_manager, sample_cgram_data):
        """Test getting specific palette"""
        palette_manager.cgram_data = sample_cgram_data
        palette_manager._extract_palettes()

        # Get existing palette
        pal8 = palette_manager.get_palette(8)
        assert len(pal8) == COLORS_PER_PALETTE
        assert pal8[0] == [0, 0, 0]

        # Get non-existing palette (should return default)
        pal_invalid = palette_manager.get_palette(99)
        assert len(pal_invalid) == COLORS_PER_PALETTE
        assert all(color == [0, 0, 0] for color in pal_invalid)

    def test_get_sprite_palettes(self, palette_manager, sample_cgram_data):
        """Test getting only sprite palettes (8-15)"""
        palette_manager.cgram_data = sample_cgram_data
        palette_manager._extract_palettes()

        sprite_pals = palette_manager.get_sprite_palettes()

        # Should only have palettes 8-15
        assert len(sprite_pals) == 8
        assert all(
            idx in range(SPRITE_PALETTE_START, SPRITE_PALETTE_END)
            for idx in sprite_pals
        )

    def test_create_palette_json(self, palette_manager, sample_cgram_data):
        """Test creating palette JSON file"""
        palette_manager.cgram_data = sample_cgram_data
        palette_manager._extract_palettes()

        with tempfile.NamedTemporaryFile(suffix=".pal.json", delete=False) as f:
            output_path = f.name

        try:
            palette_manager.create_palette_json(8, output_path, "test_sprite.png")

            # Check file exists
            assert Path(output_path).exists()

            # Load and validate JSON
            with open(output_path) as f:
                data = json.load(f)

            assert data["format_version"] == "1.0"
            assert data["palette"]["name"] == "Kirby (Pink)"
            assert data["palette"]["colors"][0] == [0, 0, 0]
            assert data["palette"]["color_count"] == 16
            assert data["source"]["palette_index"] == 8
            assert data["source"]["companion_image"] == "test_sprite.png"
            assert data["editor_compatibility"]["indexed_pixel_editor"] is True

        finally:
            Path(output_path).unlink(missing_ok=True)

    @pytest.mark.parametrize(
        ("pal_idx", "expected_name"),
        [
            (8, "Kirby (Pink)"),
            (12, "UI/HUD"),
            (14, "Boss/Enemy"),
            (99, "Palette 99"),  # Unknown palette
        ],
    )
    def test_palette_info(
        self, palette_manager, sample_cgram_data, pal_idx, expected_name
    ):
        """Test palette naming from PALETTE_INFO"""
        palette_manager.cgram_data = sample_cgram_data
        palette_manager._extract_palettes()

        with tempfile.NamedTemporaryFile(suffix=".pal.json", delete=False) as f:
            palette_manager.create_palette_json(pal_idx, f.name)

        try:
            with open(f.name) as f:
                data = json.load(f)
            assert data["palette"]["name"] == expected_name
        finally:
            Path(f.name).unlink(missing_ok=True)
