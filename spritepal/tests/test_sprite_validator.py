"""
Test sprite validation functionality
"""
from __future__ import annotations

import json
import os
import tempfile

import pytest
from PIL import Image

from core.sprite_validator import SpriteValidator

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.no_qt,
    pytest.mark.rom_data,
    pytest.mark.no_manager_setup,  # Pure unit tests for sprite validation
]

class TestSpriteValidator:
    """Test sprite validation"""

    def test_validate_valid_indexed_sprite(self):
        """Test validation of a valid indexed sprite"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create valid indexed sprite
            sprite_path = os.path.join(tmpdir, "valid_sprite.png")
            img = Image.new("P", (16, 16))

            # Set palette with 16 colors
            palette = []
            for i in range(16):
                palette.extend([i * 16, i * 16, i * 16])
            for i in range(240):  # Fill rest of palette
                palette.extend([0, 0, 0])
            img.putpalette(palette)

            # Fill with valid indices
            pixels = []
            for y in range(16):
                for x in range(16):
                    pixels.append((x + y) % 16)
            img.putdata(pixels)
            img.save(sprite_path)

            # Validate
            is_valid, errors, warnings = SpriteValidator.validate_sprite_comprehensive(
                sprite_path
            )

            assert is_valid
            assert len(errors) == 0
            # May have warnings about transparency

    def test_validate_invalid_dimensions(self):
        """Test validation catches invalid dimensions"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create sprite with invalid dimensions
            sprite_path = os.path.join(tmpdir, "bad_dims.png")
            img = Image.new("P", (15, 17))  # Not multiples of 8
            img.save(sprite_path)

            # Validate
            is_valid, errors, warnings = SpriteValidator.validate_sprite_comprehensive(
                sprite_path
            )

            assert not is_valid
            assert any("Width must be a multiple of 8" in e for e in errors)
            assert any("Height must be a multiple of 8" in e for e in errors)

    def test_validate_too_many_colors(self):
        """Test validation catches too many colors"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create sprite with too many colors
            sprite_path = os.path.join(tmpdir, "many_colors.png")
            img = Image.new("P", (16, 16))

            # Set up palette first
            palette = []
            for i in range(256):
                palette.extend([i, i, i])
            img.putpalette(palette)

            # Use 20 different color indices
            pixels = []
            for i in range(256):
                pixels.append(i % 20)
            img.putdata(pixels)
            img.save(sprite_path)

            # Validate
            is_valid, errors, warnings = SpriteValidator.validate_sprite_comprehensive(
                sprite_path
            )

            assert not is_valid
            assert any("uses 20 colors" in e for e in errors)
            assert any("uses color index 19" in e for e in errors)

    def test_validate_grayscale_sprite(self):
        """Test validation of grayscale sprite"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sprite_path = os.path.join(tmpdir, "gray_sprite.png")
            img = Image.new("L", (16, 16))

            # Fill with standard grayscale values (multiples of 17)
            pixels = []
            for i in range(256):
                pixels.append((i % 16) * 17)
            img.putdata(pixels)
            img.save(sprite_path)

            # Validate
            is_valid, errors, warnings = SpriteValidator.validate_sprite_comprehensive(
                sprite_path
            )

            assert is_valid
            assert len(errors) == 0

    def test_validate_non_standard_grayscale(self):
        """Test validation warns about non-standard grayscale values"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sprite_path = os.path.join(tmpdir, "nonstandard_gray.png")
            img = Image.new("L", (16, 16))

            # Fill with non-standard values
            pixels = []
            for i in range(256):
                pixels.append(i % 256)  # All values 0-255
            img.putdata(pixels)
            img.save(sprite_path)

            # Validate
            is_valid, errors, warnings = SpriteValidator.validate_sprite_comprehensive(
                sprite_path
            )

            assert is_valid  # Still valid, just has warnings
            assert any("non-standard grayscale values" in w for w in warnings)

    def test_validate_large_sprite_warning(self):
        """Test validation warns about large sprites"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sprite_path = os.path.join(tmpdir, "large_sprite.png")
            img = Image.new("P", (512, 512))  # Very large
            img.save(sprite_path)

            # Validate
            is_valid, errors, warnings = SpriteValidator.validate_sprite_comprehensive(
                sprite_path
            )

            assert is_valid
            assert any("larger than typical" in w for w in warnings)
            assert any("quite large" in w for w in warnings)

    def test_estimate_compressed_size(self):
        """Test compressed size estimation"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create sprite with few colors (should compress well)
            sprite_path = os.path.join(tmpdir, "simple_sprite.png")
            img = Image.new("P", (128, 128))

            # Fill with only 2 colors
            pixels = []
            for y in range(128):
                for x in range(128):
                    pixels.append(0 if (x + y) % 2 == 0 else 1)
            img.putdata(pixels)
            img.save(sprite_path)

            # Estimate size
            uncompressed, compressed = SpriteValidator.estimate_compressed_size(
                sprite_path
            )

            # 128x128 pixels = 16x16 tiles = 256 tiles = 8192 bytes uncompressed
            assert uncompressed == 256 * 32  # 8192
            # With only 2 colors, should estimate good compression
            assert compressed < uncompressed * 0.5

    def test_check_sprite_compatibility(self):
        """Test sprite compatibility checking"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create two compatible sprites
            sprite1_path = os.path.join(tmpdir, "sprite1.png")
            sprite2_path = os.path.join(tmpdir, "sprite2.png")

            img1 = Image.new("P", (16, 16))
            img1.save(sprite1_path)

            img2 = Image.new("P", (16, 16))
            img2.save(sprite2_path)

            # Check compatibility
            compatible, reasons = SpriteValidator.check_sprite_compatibility(
                sprite1_path, sprite2_path
            )
            assert compatible
            assert len(reasons) == 0

            # Create incompatible sprite
            sprite3_path = os.path.join(tmpdir, "sprite3.png")
            img3 = Image.new("P", (32, 32))  # Different size
            img3.save(sprite3_path)

            compatible, reasons = SpriteValidator.check_sprite_compatibility(
                sprite1_path, sprite3_path
            )
            assert not compatible
            assert any("Different dimensions" in r for r in reasons)

    def test_validate_against_metadata(self):
        """Test validation against metadata"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create sprite
            sprite_path = os.path.join(tmpdir, "sprite.png")
            img = Image.new("P", (128, 128))  # 256 tiles
            img.save(sprite_path)

            # Create metadata
            metadata_path = os.path.join(tmpdir, "sprite.metadata.json")
            metadata = {"extraction": {"tile_count": 300}}  # Mismatch
            with open(metadata_path, "w") as f:
                json.dump(metadata, f)

            # Validate
            is_valid, errors, warnings = SpriteValidator.validate_sprite_comprehensive(
                sprite_path, metadata_path
            )

            assert is_valid  # Still valid, just warning
            assert any("Tile count mismatch" in w for w in warnings)

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
