"""
Test PNG round-trip conversion accuracy
Ensures sprites survive the extract -> edit -> inject cycle without corruption
"""
from __future__ import annotations

import os
import tempfile

import pytest
from PIL import Image

from core.injector import SpriteInjector, encode_4bpp_tile
from core.rom_extractor import ROMExtractor

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.no_qt,
    pytest.mark.rom_data,
]

class TestPNGRoundTrip:
    """Test PNG conversion accuracy for both grayscale and indexed modes"""

    def setup_method(self):
        """Set up test fixtures"""
        self.injector = SpriteInjector()
        self.extractor = ROMExtractor()

    def create_test_tile_data(self) -> bytes:
        """Create test 4bpp tile data with known pattern"""
        # Create a simple 8x8 tile with gradient pattern (0-15)
        tile_pixels = []
        for y in range(8):
            for x in range(8):
                # Create a pattern that uses all 16 colors
                pixel_value = (y * 2 + (x // 4)) % 16
                tile_pixels.append(pixel_value)

        return encode_4bpp_tile(tile_pixels)

    def test_grayscale_round_trip(self):
        """Test round-trip conversion through grayscale PNG (ROM extraction workflow)"""
        # Create test tile data (single tile)
        original_data = self.create_test_tile_data()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Step 1: Convert 4bpp to grayscale PNG (simulating ROM extraction)
            png_path = os.path.join(tmpdir, "test_sprite.png")
            self.extractor._convert_4bpp_to_png(original_data, png_path)

            # Verify grayscale image properties
            img = Image.open(png_path)
            assert img.mode == "P"  # Should be indexed after conversion
            # ROM extractor creates sheets with 16 tiles per row
            assert img.size == (128, 8)  # Single tile padded to 16 tiles width

            # Check first tile's pixel values
            first_tile_pixels = []
            for y in range(8):
                for x in range(8):
                    pixel = img.getpixel((x, y))
                    first_tile_pixels.append(pixel)

            # Verify grayscale conversion (index * 17)
            for i, pixel in enumerate(first_tile_pixels):
                expected = ((i // 8) * 2 + ((i % 8) // 4)) % 16
                # In indexed mode after save, should be the actual value
                assert pixel == expected * 17

            # Step 2: Convert back to 4bpp (simulating injection)
            # First convert to grayscale to simulate what happens after editing
            img = img.convert("L")
            img.save(png_path)

            converted_data = self.injector.convert_png_to_4bpp(png_path)

            # Extract just the first tile for comparison
            first_tile_converted = converted_data[:32]  # 32 bytes per tile

            # Verify first tile matches original
            assert len(first_tile_converted) == len(original_data)
            assert (
                first_tile_converted == original_data
            ), "Round-trip conversion failed!"

    def test_indexed_round_trip(self):
        """Test round-trip conversion through indexed PNG (pixel editor workflow)"""
        # Create test tile data
        original_data = self.create_test_tile_data()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create indexed PNG directly (simulating pixel editor save)
            png_path = os.path.join(tmpdir, "test_indexed.png")
            img = Image.new("P", (8, 8))

            # Set pixels with palette indices
            pixels = []
            for y in range(8):
                for x in range(8):
                    pixel_value = (y * 2 + (x // 4)) % 16
                    pixels.append(pixel_value)

            img.putdata(pixels)
            # Need to set a palette for indexed mode
            palette = []
            for i in range(256):
                palette.extend([i, i, i])  # Grayscale palette
            img.putpalette(palette)
            img.save(png_path)

            # Convert back to 4bpp
            converted_data = self.injector.convert_png_to_4bpp(png_path)

            # Verify data matches original
            assert len(converted_data) == len(original_data)
            # Debug output if they don't match
            if converted_data != original_data:
                print(f"\nOriginal: {original_data.hex()}")
                print(f"Converted: {converted_data.hex()}")
                # Decode both to see pixel values
                orig_pixels = []
                for i in range(64):
                    # Decode original
                    y = i // 8
                    x = i % 8
                    bit = 7 - x
                    orig_pixel = 0
                    orig_pixel |= ((original_data[y * 2] >> bit) & 1) << 0
                    orig_pixel |= ((original_data[y * 2 + 1] >> bit) & 1) << 1
                    orig_pixel |= ((original_data[16 + y * 2] >> bit) & 1) << 2
                    orig_pixel |= ((original_data[16 + y * 2 + 1] >> bit) & 1) << 3
                    orig_pixels.append(orig_pixel)
                print(f"Original pixels: {orig_pixels[:16]}")  # First 2 rows
            assert converted_data == original_data, "Indexed round-trip failed!"

    def test_edge_cases(self):
        """Test edge cases in conversion"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Test all black (index 0)
            black_tile = encode_4bpp_tile([0] * 64)
            png_path = os.path.join(tmpdir, "black.png")
            self.extractor._convert_4bpp_to_png(black_tile, png_path)

            # Convert to grayscale and back
            img = Image.open(png_path).convert("L")
            img.save(png_path)
            converted = self.injector.convert_png_to_4bpp(png_path)
            # Extract first tile only
            first_tile = converted[:32]
            assert first_tile == black_tile

            # Test all white (index 15)
            white_tile = encode_4bpp_tile([15] * 64)
            png_path = os.path.join(tmpdir, "white.png")
            self.extractor._convert_4bpp_to_png(white_tile, png_path)

            # Convert to grayscale and back
            img = Image.open(png_path).convert("L")
            img.save(png_path)
            converted = self.injector.convert_png_to_4bpp(png_path)
            # Extract first tile only
            first_tile = converted[:32]
            assert first_tile == white_tile

    def test_multi_tile_round_trip(self):
        """Test round-trip with multiple tiles (full sprite sheet)"""
        # Create 4x4 tile grid (16 tiles)
        tiles_data = bytearray()
        for tile_idx in range(16):
            # Each tile has a different pattern
            tile_pixels = [(tile_idx + i) % 16 for i in range(64)]
            tiles_data.extend(encode_4bpp_tile(tile_pixels))

        with tempfile.TemporaryDirectory() as tmpdir:
            # Convert to PNG
            png_path = os.path.join(tmpdir, "sprite_sheet.png")
            self.extractor._convert_4bpp_to_png(bytes(tiles_data), png_path)

            # Verify dimensions
            img = Image.open(png_path)
            assert img.size == (128, 8)  # 16 tiles in one row (16*8, 8)

            # Convert to grayscale and back
            img = img.convert("L")
            img.save(png_path)
            converted_data = self.injector.convert_png_to_4bpp(png_path)

            # Verify all tiles preserved
            assert len(converted_data) == len(tiles_data)
            assert converted_data == bytes(tiles_data)

    def test_validate_sprite_modes(self):
        """Test sprite validation accepts both grayscale and indexed modes"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Test grayscale mode
            gray_path = os.path.join(tmpdir, "gray.png")
            img = Image.new("L", (16, 16), 128)
            img.save(gray_path)
            valid, msg = self.injector.validate_sprite(gray_path)
            assert valid, f"Grayscale validation failed: {msg}"

            # Test indexed mode
            indexed_path = os.path.join(tmpdir, "indexed.png")
            img = Image.new("P", (16, 16))
            img.putpalette([i % 256 for i in range(768)])  # Dummy palette
            img.save(indexed_path)
            valid, msg = self.injector.validate_sprite(indexed_path)
            assert valid, f"Indexed validation failed: {msg}"

            # Test RGB mode (should fail)
            rgb_path = os.path.join(tmpdir, "rgb.png")
            img = Image.new("RGB", (16, 16))
            img.save(rgb_path)
            valid, msg = self.injector.validate_sprite(rgb_path)
            assert not valid
            assert "must be in indexed (P) or grayscale (L) mode" in msg

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
