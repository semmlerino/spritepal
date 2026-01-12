"""Tests for MesenCaptureParser validation.

Verifies that the parser correctly validates:
- Coordinate bounds (X, Y)
- Palette index range
- Tile hex length and characters
- VRAM address bounds
"""

from __future__ import annotations

import json

import pytest

from core.mesen_integration.click_extractor import (
    CaptureValidationError,
    MesenCaptureParser,
)


@pytest.fixture
def parser() -> MesenCaptureParser:
    """Create parser instance."""
    return MesenCaptureParser()


def create_minimal_capture(
    *,
    x: int = 100,
    y: int = 100,
    palette: int = 0,
    data_hex: str = "00" * 32,  # 64 hex chars = 32 bytes
    vram_addr: int = 0x1000,
) -> dict:
    """Create minimal valid capture data for testing."""
    return {
        "frame": 1,
        "obsel": {},
        "entries": [
            {
                "id": 0,
                "x": x,
                "y": y,
                "tile": 0,
                "width": 8,
                "height": 8,
                "palette": palette,
                "tiles": [
                    {
                        "tile_index": 0,
                        "vram_addr": vram_addr,
                        "pos_x": 0,
                        "pos_y": 0,
                        "data_hex": data_hex,
                    }
                ],
            }
        ],
        "palettes": {},
    }


class TestCoordinateValidation:
    """Test OAM coordinate validation."""

    def test_valid_x_range_accepted(self, parser):
        """Verify valid X coordinates pass validation."""
        # Test boundary values
        for x in [-256, -100, 0, 100, 255]:
            data = create_minimal_capture(x=x)
            result = parser.parse_string(json.dumps(data))
            assert result.entries[0].x == x

    def test_x_below_minimum_rejected(self, parser):
        """Verify X coordinate below -256 raises error."""
        data = create_minimal_capture(x=-257)
        with pytest.raises(CaptureValidationError) as exc_info:
            parser.parse_string(json.dumps(data))
        assert "x=-257 out of range" in str(exc_info.value)

    def test_x_above_maximum_rejected(self, parser):
        """Verify X coordinate above 255 raises error."""
        data = create_minimal_capture(x=256)
        with pytest.raises(CaptureValidationError) as exc_info:
            parser.parse_string(json.dumps(data))
        assert "x=256 out of range" in str(exc_info.value)

    def test_valid_y_range_accepted(self, parser):
        """Verify valid Y coordinates pass validation."""
        for y in [0, 100, 255]:
            data = create_minimal_capture(y=y)
            result = parser.parse_string(json.dumps(data))
            assert result.entries[0].y == y

    def test_y_below_minimum_rejected(self, parser):
        """Verify Y coordinate below 0 raises error."""
        data = create_minimal_capture(y=-1)
        with pytest.raises(CaptureValidationError) as exc_info:
            parser.parse_string(json.dumps(data))
        assert "y=-1 out of range" in str(exc_info.value)

    def test_y_above_maximum_rejected(self, parser):
        """Verify Y coordinate above 255 raises error."""
        data = create_minimal_capture(y=256)
        with pytest.raises(CaptureValidationError) as exc_info:
            parser.parse_string(json.dumps(data))
        assert "y=256 out of range" in str(exc_info.value)


class TestPaletteValidation:
    """Test palette index validation."""

    def test_valid_palette_range_accepted(self, parser):
        """Verify valid palette indices (0-7) pass validation."""
        for palette in range(8):
            data = create_minimal_capture(palette=palette)
            result = parser.parse_string(json.dumps(data))
            assert result.entries[0].palette == palette

    def test_palette_below_minimum_rejected(self, parser):
        """Verify palette index below 0 raises error."""
        data = create_minimal_capture(palette=-1)
        with pytest.raises(CaptureValidationError) as exc_info:
            parser.parse_string(json.dumps(data))
        assert "palette=-1 out of range" in str(exc_info.value)

    def test_palette_above_maximum_rejected(self, parser):
        """Verify palette index above 7 raises error."""
        data = create_minimal_capture(palette=8)
        with pytest.raises(CaptureValidationError) as exc_info:
            parser.parse_string(json.dumps(data))
        assert "palette=8 out of range" in str(exc_info.value)


class TestTileHexValidation:
    """Test tile data hex string validation."""

    def test_valid_hex_data_accepted(self, parser):
        """Verify valid 64-char hex string passes validation."""
        # All zeros
        data = create_minimal_capture(data_hex="00" * 32)
        result = parser.parse_string(json.dumps(data))
        assert result.entries[0].tiles[0].data_hex == "00" * 32

        # Mixed valid hex
        data = create_minimal_capture(data_hex="0123456789ABCDEF" * 4)
        result = parser.parse_string(json.dumps(data))
        assert result.entries[0].tiles[0].data_hex == "0123456789ABCDEF" * 4

    def test_hex_too_short_rejected(self, parser):
        """Verify hex string shorter than 64 chars raises error."""
        data = create_minimal_capture(data_hex="00" * 31)  # 62 chars
        with pytest.raises(CaptureValidationError) as exc_info:
            parser.parse_string(json.dumps(data))
        assert "data_hex must be exactly 64 chars" in str(exc_info.value)
        assert "got 62" in str(exc_info.value)

    def test_hex_too_long_rejected(self, parser):
        """Verify hex string longer than 64 chars raises error."""
        data = create_minimal_capture(data_hex="00" * 33)  # 66 chars
        with pytest.raises(CaptureValidationError) as exc_info:
            parser.parse_string(json.dumps(data))
        assert "data_hex must be exactly 64 chars" in str(exc_info.value)
        assert "got 66" in str(exc_info.value)

    def test_invalid_hex_characters_rejected(self, parser):
        """Verify non-hex characters raise error."""
        # 'G' is not valid hex
        data = create_minimal_capture(data_hex="00" * 31 + "GG")
        with pytest.raises(CaptureValidationError) as exc_info:
            parser.parse_string(json.dumps(data))
        assert "invalid characters" in str(exc_info.value)

    def test_lowercase_hex_accepted(self, parser):
        """Verify lowercase hex chars are accepted (HEX_PATTERN allows a-f)."""
        data = create_minimal_capture(data_hex="abcdef0123456789" * 4)
        result = parser.parse_string(json.dumps(data))
        assert result.entries[0].tiles[0].data_hex == "abcdef0123456789" * 4

    def test_empty_hex_accepted(self, parser):
        """Verify empty hex string passes validation (no tile data)."""
        data = create_minimal_capture(data_hex="")
        result = parser.parse_string(json.dumps(data))
        assert result.entries[0].tiles[0].data_hex == ""


class TestVRAMAddressValidation:
    """Test VRAM address validation."""

    def test_valid_vram_range_accepted(self, parser):
        """Verify valid VRAM addresses pass validation."""
        for addr in [0x0000, 0x1000, 0x7FFF, 0xFFFF]:
            data = create_minimal_capture(vram_addr=addr)
            result = parser.parse_string(json.dumps(data))
            assert result.entries[0].tiles[0].vram_addr == addr

    def test_vram_below_minimum_rejected(self, parser):
        """Verify VRAM address below 0 raises error."""
        data = create_minimal_capture(vram_addr=-1)
        with pytest.raises(CaptureValidationError) as exc_info:
            parser.parse_string(json.dumps(data))
        assert "vram_addr=" in str(exc_info.value)
        assert "out of range" in str(exc_info.value)

    def test_vram_above_maximum_rejected(self, parser):
        """Verify VRAM address above 0xFFFF raises error."""
        data = create_minimal_capture(vram_addr=0x10000)
        with pytest.raises(CaptureValidationError) as exc_info:
            parser.parse_string(json.dumps(data))
        assert "vram_addr=" in str(exc_info.value)
        assert "out of range" in str(exc_info.value)


class TestTileCountValidation:
    """Test tile count vs dimensions validation (warning, not error)."""

    def test_matching_tile_count_no_warning(self, parser, caplog):
        """Verify correct tile count doesn't log warning."""
        # 16x16 sprite should have 4 tiles (2x2 of 8x8)
        data = {
            "frame": 1,
            "obsel": {},
            "entries": [
                {
                    "id": 0,
                    "x": 100,
                    "y": 100,
                    "tile": 0,
                    "width": 16,
                    "height": 16,
                    "palette": 0,
                    "tiles": [
                        {"tile_index": i, "vram_addr": 0x1000 + i * 16, "pos_x": 0, "pos_y": 0, "data_hex": "00" * 32}
                        for i in range(4)
                    ],
                }
            ],
            "palettes": {},
        }
        parser.parse_string(json.dumps(data))
        assert "tile count mismatch" not in caplog.text

    def test_mismatched_tile_count_logs_warning(self, parser, caplog):
        """Verify incorrect tile count logs warning but doesn't fail."""
        # 16x16 sprite should have 4 tiles, but we provide only 2
        data = {
            "frame": 1,
            "obsel": {},
            "entries": [
                {
                    "id": 0,
                    "x": 100,
                    "y": 100,
                    "tile": 0,
                    "width": 16,
                    "height": 16,
                    "palette": 0,
                    "tiles": [
                        {"tile_index": i, "vram_addr": 0x1000 + i * 16, "pos_x": 0, "pos_y": 0, "data_hex": "00" * 32}
                        for i in range(2)  # Only 2 tiles instead of 4
                    ],
                }
            ],
            "palettes": {},
        }
        result = parser.parse_string(json.dumps(data))
        # Should still parse successfully
        assert len(result.entries) == 1
        assert len(result.entries[0].tiles) == 2
        # But should log warning
        assert "tile count mismatch" in caplog.text
        assert "expected 4" in caplog.text
        assert "got 2" in caplog.text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
