from __future__ import annotations

import pytest

pytestmark = [
    pytest.mark.headless,
]
#!/usr/bin/env python3
"""
Test palette application to see why we get black boxes.
"""

import os

# NOTE: pythonpath configured in pyproject.toml - no sys.path manipulation needed

import numpy as np
from PIL import Image


def test_palette_application():
    """Test applying a palette to grayscale data."""

    # Create test grayscale image with values 0-15 (4bpp range)
    print("Creating test grayscale image...")
    width, height = 128, 64

    # Create image with various grayscale values
    grayscale_img = Image.new("L", (width, height))
    pixels = []
    for y in range(height):
        for x in range(width):
            # Create a pattern with values 0-15 scaled to 0-255
            value = ((x // 8) + (y // 8)) % 16
            pixel_value = value * 17  # Scale 0-15 to 0-255
            pixels.append(pixel_value)

    grayscale_img.putdata(pixels)
    print(f"Grayscale image created: {width}x{height}")
    print(f"Pixel value range: {min(pixels)} - {max(pixels)}")
    print(f"Unique values: {sorted(set(pixels))}")

    # Define test palette (Kirby Pink)
    palette_colors = [
        [0, 0, 0],        # 0 - Black (transparent)
        [255, 192, 192],  # 1 - Light pink
        [255, 128, 128],  # 2 - Pink
        [224, 64, 64],    # 3 - Dark pink
        [255, 255, 255],  # 4 - White
        [255, 224, 224],  # 5 - Light white
        [192, 0, 0],      # 6 - Dark red
        [128, 0, 0],      # 7 - Darker red
        [255, 128, 0],    # 8 - Orange
        [192, 64, 0],     # 9 - Dark orange
        [128, 32, 0],     # 10 - Brown
        [255, 255, 128],  # 11 - Light yellow
        [255, 224, 64],   # 12 - Yellow
        [224, 192, 0],    # 13 - Dark yellow
        [160, 128, 0],    # 14 - Olive
        [96, 64, 0]       # 15 - Dark olive
    ]

    print(f"\nApplying palette with {len(palette_colors)} colors...")

    # Method 1: Direct indexed image creation
    print("\nMethod 1: Direct indexed image")
    indexed = Image.new("P", (width, height))

    # Put the grayscale data as indices
    indexed.putdata([p // 17 for p in pixels])  # Convert back to 0-15 range

    # Create palette array
    full_palette = []
    for i in range(256):
        if i < len(palette_colors):
            full_palette.extend(palette_colors[i])
        else:
            full_palette.extend([0, 0, 0])

    indexed.putpalette(full_palette)

    # Convert to RGBA
    img_rgba = indexed.convert("RGBA")

    # Check result
    rgba_pixels = list(img_rgba.getdata())
    non_black = sum(1 for p in rgba_pixels[:100] if p != (0, 0, 0, 255))
    print(f"Non-black pixels in first 100: {non_black}")
    print(f"First 10 RGBA pixels: {rgba_pixels[:10]}")

    # Method 2: Using numpy for palette mapping
    print("\nMethod 2: Numpy palette mapping")
    img_array = np.array(grayscale_img)

    # Scale down to 0-15 range
    indices = img_array // 17

    # Create RGB image
    rgb_array = np.zeros((height, width, 3), dtype=np.uint8)
    for i in range(16):
        mask = indices == i
        if i < len(palette_colors):
            rgb_array[mask] = palette_colors[i]

    # Convert to PIL Image
    img_rgb = Image.fromarray(rgb_array, 'RGB')

    # Check result
    rgb_pixels = list(img_rgb.getdata())
    non_black_np = sum(1 for p in rgb_pixels[:100] if p != (0, 0, 0))
    print(f"Non-black pixels in first 100: {non_black_np}")
    print(f"First 10 RGB pixels: {rgb_pixels[:10]}")

    # Assertions
    assert non_black > 0, "Method 1: Should have non-black pixels after palette application"
    assert non_black_np > 0, "Method 2: Should have non-black pixels after numpy palette mapping"

    print("\nPalette application test complete!")
    print("Both methods produced non-black pixels, palette application works correctly.")


if __name__ == "__main__":
    test_palette_application()
