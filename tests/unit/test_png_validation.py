"""Tests for PNG palette index validation.

Bug: `validate_sprite()` checks unique color count but does NOT validate
palette indices are 0-15 for 4bpp compatibility.

`convert_png_to_4bpp()` has recovery logic (lines 193-202) that runs AFTER
validation passes, masking invalid input.

Expected behavior: Validation should reject PNGs with palette indices > 15.
"""

import numpy as np
import pytest
from PIL import Image

from core.injector import SpriteInjector


@pytest.fixture
def sprite_injector() -> SpriteInjector:
    """Create a SpriteInjector instance."""
    return SpriteInjector()


@pytest.fixture
def valid_indexed_png(tmp_path) -> str:
    """Create a valid indexed PNG with 16 colors and indices 0-15."""
    img = Image.new("P", (8, 8))

    # Create a simple 16-color palette (grayscale)
    palette = []
    for i in range(16):
        val = i * 17  # 0, 17, 34, ..., 255
        palette.extend([val, val, val])
    # Pad to 256 colors (required by PIL)
    palette.extend([0, 0, 0] * (256 - 16))
    img.putpalette(palette)

    # Fill with valid indices (0-15)
    pixels = []
    for i in range(64):
        pixels.append(i % 16)
    img.putdata(pixels)

    path = tmp_path / "valid_indexed.png"
    img.save(str(path))
    return str(path)


@pytest.fixture
def png_with_index_16(tmp_path) -> str:
    """Create an indexed PNG with 16 unique colors but one index is 20 (invalid for 4bpp).

    Uses indices: 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 20
    This passes the "16 unique colors" check but should fail index validation.
    """
    img = Image.new("P", (8, 8))

    # Create a 32-color palette
    palette = []
    for i in range(32):
        val = i * 8
        palette.extend([val, val, val])
    # Pad to 256 colors
    palette.extend([0, 0, 0] * (256 - 32))
    img.putpalette(palette)

    # Use 16 unique indices: 0-14 plus 20 (one invalid index)
    # This passes color count check (16 colors) but fails index validation (20 > 15)
    valid_indices = list(range(15))  # 0-14 (15 values)
    invalid_index = 20

    pixels = []
    for i in range(64):
        if i < 60:
            # Use valid indices (0-14)
            pixels.append(valid_indices[i % 15])
        else:
            # Use invalid index (20) for last 4 pixels
            pixels.append(invalid_index)
    img.putdata(pixels)

    path = tmp_path / "png_with_index_20.png"
    img.save(str(path))
    return str(path)


@pytest.fixture
def png_with_index_255(tmp_path) -> str:
    """Create an indexed PNG with index 255 (way beyond 4bpp limit)."""
    img = Image.new("P", (8, 8))

    # Create a full 256-color palette
    palette = []
    for i in range(256):
        palette.extend([i, i, i])
    img.putpalette(palette)

    # Fill with high indices including 255
    pixels = []
    for i in range(64):
        pixels.append(255 - (i % 256))  # Includes index 255
    img.putdata(pixels)

    path = tmp_path / "png_with_index_255.png"
    img.save(str(path))
    return str(path)


@pytest.fixture
def grayscale_png(tmp_path) -> str:
    """Create a valid grayscale PNG (mode 'L')."""
    img = Image.new("L", (8, 8))

    # Fill with grayscale values (0-255)
    pixels = []
    for i in range(64):
        pixels.append((i * 4) % 256)
    img.putdata(pixels)

    path = tmp_path / "grayscale.png"
    img.save(str(path))
    return str(path)


class TestValidateSpriteIndexValidation:
    """Tests for validate_sprite() palette index checking."""

    def test_valid_indexed_png_passes_validation(self, sprite_injector: SpriteInjector, valid_indexed_png: str) -> None:
        """Valid indexed PNG with indices 0-15 should pass validation."""
        is_valid, message = sprite_injector.validate_sprite(valid_indexed_png)

        assert is_valid is True, f"Valid PNG should pass validation: {message}"
        assert "successful" in message.lower()

    def test_png_with_index_16_fails_validation(self, sprite_injector: SpriteInjector, png_with_index_16: str) -> None:
        """PNG with palette index 16 should fail validation (only 0-15 valid)."""
        is_valid, message = sprite_injector.validate_sprite(png_with_index_16)

        assert is_valid is False, (
            "PNG with index 16 should fail validation. Only indices 0-15 are valid for 4bpp SNES sprites."
        )
        assert "index" in message.lower() or "palette" in message.lower(), (
            f"Error message should mention palette indices: {message}"
        )

    def test_png_with_index_255_fails_validation(
        self, sprite_injector: SpriteInjector, png_with_index_255: str
    ) -> None:
        """PNG with palette index 255 should fail validation."""
        is_valid, message = sprite_injector.validate_sprite(png_with_index_255)

        assert is_valid is False, (
            "PNG with index 255 should fail validation. Only indices 0-15 are valid for 4bpp SNES sprites."
        )

    def test_grayscale_png_passes_validation(self, sprite_injector: SpriteInjector, grayscale_png: str) -> None:
        """Grayscale PNG (mode 'L') should pass validation."""
        is_valid, message = sprite_injector.validate_sprite(grayscale_png)

        assert is_valid is True, f"Grayscale PNG should pass validation: {message}"


class TestConvertPngTo4bppStrictValidation:
    """Tests for convert_png_to_4bpp() strict validation (no recovery)."""

    def test_convert_valid_indexed_png_succeeds(self, sprite_injector: SpriteInjector, valid_indexed_png: str) -> None:
        """Validated PNG should convert successfully."""
        # First validate
        is_valid, _ = sprite_injector.validate_sprite(valid_indexed_png)
        assert is_valid

        # Then convert
        data = sprite_injector.convert_png_to_4bpp(valid_indexed_png)

        # Should produce 32 bytes per 8x8 tile (1 tile for 8x8 image)
        assert len(data) == 32, f"Expected 32 bytes for one 8x8 tile, got {len(data)}"

    def test_convert_invalid_indexed_png_raises(self, sprite_injector: SpriteInjector, png_with_index_16: str) -> None:
        """PNG with invalid indices should raise ValueError when converted."""
        # This test expects the conversion to raise an error for invalid PNGs
        # Currently the code has recovery logic that silently converts to grayscale
        # After the fix, it should raise ValueError

        with pytest.raises(ValueError) as exc_info:
            sprite_injector.convert_png_to_4bpp(png_with_index_16)

        error_message = str(exc_info.value).lower()
        assert "index" in error_message or "4bpp" in error_message or "palette" in error_message, (
            f"Error should mention palette/index/4bpp limit: {exc_info.value}"
        )

    def test_convert_grayscale_png_succeeds(self, sprite_injector: SpriteInjector, grayscale_png: str) -> None:
        """Grayscale PNG should convert successfully."""
        data = sprite_injector.convert_png_to_4bpp(grayscale_png)

        assert len(data) == 32, f"Expected 32 bytes for one 8x8 tile, got {len(data)}"


class TestColorCountValidation:
    """Tests for existing color count validation (should still work)."""

    def test_png_with_17_unique_colors_fails_validation(self, sprite_injector: SpriteInjector, tmp_path) -> None:
        """PNG with 17 unique colors should fail (max 16 for 4bpp)."""
        img = Image.new("P", (8, 8))

        # Create a 32-color palette
        palette = []
        for i in range(32):
            val = i * 8
            palette.extend([val, val, val])
        palette.extend([0, 0, 0] * (256 - 32))
        img.putpalette(palette)

        # Use 17 unique indices (0-16)
        pixels = []
        for i in range(64):
            # Distribute 17 unique colors across 64 pixels
            pixels.append(i % 17)  # Uses indices 0-16 (17 unique values)
        img.putdata(pixels)

        path = tmp_path / "17_colors.png"
        img.save(str(path))

        is_valid, message = sprite_injector.validate_sprite(str(path))

        assert is_valid is False, "PNG with 17 colors should fail validation"
        assert "color" in message.lower() or "17" in message, f"Error should mention color count: {message}"
