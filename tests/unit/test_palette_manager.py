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
    pytest.mark.headless,
    pytest.mark.integration,
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
        palette_manager.refresh_palettes()

        # Check we have 16 palettes
        assert len(palette_manager.palettes) == 16

        # Check palette 8 colors
        pal8 = palette_manager.palettes[8]
        assert len(pal8) == COLORS_PER_PALETTE

        # Check specific colors
        assert pal8[0] == [0, 0, 0]  # Black
        assert pal8[1] == [255, 156, 156]  # Pink
        assert pal8[2] == [255, 255, 255]  # White

    def test_get_palette(self, palette_manager, sample_cgram_data):
        """Test getting specific palette"""
        palette_manager.cgram_data = sample_cgram_data
        palette_manager.refresh_palettes()

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
        palette_manager.refresh_palettes()

        sprite_pals = palette_manager.get_sprite_palettes()

        # Should only have palettes 8-15
        assert len(sprite_pals) == 8
        assert all(idx in range(SPRITE_PALETTE_START, SPRITE_PALETTE_END) for idx in sprite_pals)

    def test_create_palette_json(self, palette_manager, sample_cgram_data):
        """Test creating palette JSON file"""
        palette_manager.cgram_data = sample_cgram_data
        palette_manager.refresh_palettes()

        with tempfile.NamedTemporaryFile(suffix=".pal.json", delete=False) as f:
            output_path = f.name

        try:
            palette_manager.create_palette_json(8, output_path, "test_sprite.png")

            # Check file exists
            assert Path(output_path).exists()

            # Load and validate JSON
            with Path(output_path).open() as f:
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
    def test_palette_info(self, palette_manager, sample_cgram_data, pal_idx, expected_name):
        """Test palette naming from PALETTE_INFO"""
        palette_manager.cgram_data = sample_cgram_data
        palette_manager.refresh_palettes()

        with tempfile.NamedTemporaryFile(suffix=".pal.json", delete=False) as f:
            palette_manager.create_palette_json(pal_idx, f.name)

        try:
            with Path(f.name).open() as file:
                data = json.load(file)
            assert data["palette"]["name"] == expected_name
        finally:
            Path(f.name).unlink(missing_ok=True)


class TestPaletteManagerExtended:
    """Extended tests for PaletteManager functionality (coverage improvements)"""

    @pytest.fixture
    def palette_manager(self):
        """Create a PaletteManager instance"""
        return PaletteManager()

    @pytest.fixture
    def sample_cgram_data(self):
        """Create sample CGRAM data for testing"""
        cgram_data = bytearray(512)

        # Set up test colors for palette 8
        cgram_data[256] = 0x00  # Black
        cgram_data[257] = 0x00
        cgram_data[258] = 0x1F  # Red
        cgram_data[259] = 0x00
        cgram_data[260] = 0xE0  # Green
        cgram_data[261] = 0x03
        cgram_data[262] = 0x00  # Blue
        cgram_data[263] = 0x7C

        return bytes(cgram_data)

    def test_extract_palettes_with_no_data(self, palette_manager):
        """Test extracting palettes when no CGRAM data is loaded"""
        palette_manager.refresh_palettes()
        assert palette_manager.palettes == {}

    def test_extract_palettes_with_truncated_data(self, palette_manager):
        """Test extracting palettes with truncated CGRAM data"""
        # Create truncated CGRAM data (less than 512 bytes)
        truncated_data = bytearray(100)
        palette_manager.cgram_data = bytes(truncated_data)

        palette_manager.refresh_palettes()

        # Should handle truncated data gracefully
        assert len(palette_manager.palettes) == 16
        # Colors beyond available data should be black
        assert palette_manager.palettes[0][15] == [0, 0, 0]

    def test_create_metadata_json(self, palette_manager, sample_cgram_data):
        """Test creating metadata.json file"""
        palette_manager.cgram_data = sample_cgram_data
        palette_manager.refresh_palettes()

        with tempfile.TemporaryDirectory() as temp_dir:
            output_base = Path(temp_dir) / "test_sprites"

            # Create sample palette files
            palette_files = {}
            for i in range(SPRITE_PALETTE_START, SPRITE_PALETTE_END):
                pal_file = f"{output_base}_pal{i}.pal.json"
                palette_files[i] = pal_file
                Path(pal_file).touch()  # Create empty file

            # Create metadata
            metadata_path = palette_manager.create_metadata_json(str(output_base), palette_files)

            # Verify metadata file exists
            assert Path(metadata_path).exists()

            # Load and verify metadata content
            with Path(metadata_path).open() as f:
                metadata = json.load(f)

            assert metadata["format_version"] == "1.0"
            assert metadata["default_palette"] == 8
            assert "palettes" in metadata
            assert "palette_info" in metadata

            # Check palette references
            assert str(SPRITE_PALETTE_START) in metadata["palettes"]
            assert metadata["palettes"][str(SPRITE_PALETTE_START)].endswith(".pal.json")

    def test_analyze_oam_palettes_success(self, palette_manager):
        """Test successful OAM palette analysis"""
        # Create mock OAM data (544 bytes is the expected OAM size)
        oam_data = bytearray(544)

        # Create some test OAM entries
        # Entry 1: Y=50, palette=0 (sprite on-screen)
        oam_data[0] = 0x00  # X low
        oam_data[1] = 50  # Y
        oam_data[2] = 0x00  # Tile
        oam_data[3] = 0x00  # Attrs (palette 0)

        # Entry 2: Y=100, palette=3 (sprite on-screen)
        oam_data[4] = 0x00  # X low
        oam_data[5] = 100  # Y
        oam_data[6] = 0x00  # Tile
        oam_data[7] = 0x03  # Attrs (palette 3)

        # Entry 3: Y=240, palette=1 (sprite off-screen)
        oam_data[8] = 0x00  # X low
        oam_data[9] = 240  # Y
        oam_data[10] = 0x00  # Tile
        oam_data[11] = 0x01  # Attrs (palette 1)

        with tempfile.NamedTemporaryFile(suffix=".dmp", delete=False) as f:
            f.write(oam_data)
            f.flush()

            try:
                active_palettes = palette_manager.analyze_oam_palettes(f.name)

                # Should include palettes from on-screen sprites (0+8=8, 3+8=11)
                # Should exclude off-screen sprite (1+8=9)
                assert 8 in active_palettes  # palette 0 -> CGRAM 8
                assert 11 in active_palettes  # palette 3 -> CGRAM 11
                assert 9 not in active_palettes  # palette 1 -> CGRAM 9 (off-screen)

            finally:
                Path(f.name).unlink()

    def test_analyze_oam_palettes_error_handling(self, palette_manager):
        """Test OAM palette analysis error handling"""
        # Test with non-existent file
        active_palettes = palette_manager.analyze_oam_palettes("/nonexistent/file.oam")

        # Should return all sprite palettes on error
        expected_palettes = list(range(SPRITE_PALETTE_START, SPRITE_PALETTE_END))
        assert active_palettes == expected_palettes

    def test_analyze_oam_palettes_short_data(self, palette_manager):
        """Test OAM analysis with truncated data"""
        # Create very short OAM data
        oam_data = bytearray(10)  # Less than one full entry

        with tempfile.NamedTemporaryFile(suffix=".dmp", delete=False) as f:
            f.write(oam_data)
            f.flush()

            try:
                active_palettes = palette_manager.analyze_oam_palettes(f.name)

                # Should handle short data gracefully
                assert isinstance(active_palettes, list)

            finally:
                Path(f.name).unlink()

    def test_create_palette_json_without_companion_image(self, palette_manager, sample_cgram_data):
        """Test creating palette JSON without companion image"""
        palette_manager.cgram_data = sample_cgram_data
        palette_manager.refresh_palettes()

        with tempfile.NamedTemporaryFile(suffix=".pal.json", delete=False) as f:
            output_path = f.name

        try:
            palette_manager.create_palette_json(8, output_path)

            # Load and verify JSON
            with Path(output_path).open() as f:
                data = json.load(f)

            # Should not have source info
            assert "source" not in data

        finally:
            Path(output_path).unlink(missing_ok=True)

    def test_load_cgram_file_error(self, palette_manager):
        """Test loading CGRAM file with error"""
        # FileValidator correctly rejects non-existent files
        with pytest.raises(ValueError, match="Invalid CGRAM file"):
            palette_manager.load_cgram("/nonexistent/file.cgram")

    def test_palette_json_with_io_error(self, palette_manager, sample_cgram_data):
        """Test palette JSON creation with I/O error"""
        palette_manager.cgram_data = sample_cgram_data
        palette_manager.refresh_palettes()

        # Try to write to invalid path
        # atomic_write tries to create parent directories first, so we get
        # PermissionError when trying to create /invalid directory
        with pytest.raises(OSError):  # PermissionError or FileNotFoundError
            palette_manager.create_palette_json(8, "/invalid/path/file.json")

    def test_metadata_json_with_io_error(self, palette_manager):
        """Test metadata JSON creation with I/O error"""
        # Try to write to invalid path
        # atomic_write tries to create parent directories first, so we get
        # PermissionError when trying to create /invalid directory
        with pytest.raises(OSError):  # PermissionError or FileNotFoundError
            palette_manager.create_metadata_json("/invalid/path/file", {})

    def test_get_palette_boundary_conditions(self, palette_manager, sample_cgram_data):
        """Test get_palette with boundary conditions"""
        palette_manager.cgram_data = sample_cgram_data
        palette_manager.refresh_palettes()

        # Test valid palette
        pal8 = palette_manager.get_palette(8)
        assert len(pal8) == 16

        # Test invalid palette indices
        pal_negative = palette_manager.get_palette(-1)
        assert len(pal_negative) == 16
        assert all(color == [0, 0, 0] for color in pal_negative)

        pal_too_high = palette_manager.get_palette(999)
        assert len(pal_too_high) == 16
        assert all(color == [0, 0, 0] for color in pal_too_high)

    def test_get_sprite_palettes_empty(self, palette_manager):
        """Test get_sprite_palettes with no loaded data"""
        result = palette_manager.get_sprite_palettes()
        assert result == {}

    def test_get_sprite_palettes_partial_data(self, palette_manager):
        """Test get_sprite_palettes with partial data"""
        # Create CGRAM data with only some palettes
        cgram_data = bytearray(256)  # Only first 8 palettes
        palette_manager.cgram_data = bytes(cgram_data)
        palette_manager.refresh_palettes()

        sprite_palettes = palette_manager.get_sprite_palettes()

        # Should handle missing sprite palettes gracefully
        assert isinstance(sprite_palettes, dict)
        # All requested palette indices should be present but might be empty
        for i in range(SPRITE_PALETTE_START, SPRITE_PALETTE_END):
            if i in sprite_palettes:
                assert isinstance(sprite_palettes[i], list)
