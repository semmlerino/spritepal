"""Tests for the overlay layer component."""

from __future__ import annotations

import pytest
from PIL import Image

from ui.row_arrangement.overlay_layer import OverlayLayer

pytestmark = [
    pytest.mark.headless,
    pytest.mark.unit,
]


class TestOverlayLayerBasic:
    """Test basic overlay layer operations."""

    def test_init_defaults(self):
        """Test default initialization values."""
        layer = OverlayLayer()
        assert layer.image is None
        assert layer.image_path is None
        assert layer.x == 0
        assert layer.y == 0
        assert layer.opacity == 0.5
        assert layer.visible is True
        assert not layer.has_image()

    def test_import_image(self, tmp_path):
        """Test importing an image."""
        # Create a test image file
        img_path = tmp_path / "test.png"
        img = Image.new("RGB", (100, 100), color="red")
        img.save(img_path)

        layer = OverlayLayer()
        result = layer.import_image(str(img_path))

        assert result is True
        assert layer.has_image()
        assert layer.image is not None
        assert layer.image.mode == "RGBA"  # Should be converted
        assert layer.image.size == (100, 100)
        assert layer.image_path is not None

    def test_import_nonexistent_file(self):
        """Test importing a nonexistent file."""
        layer = OverlayLayer()
        result = layer.import_image("/nonexistent/path/image.png")

        assert result is False
        assert not layer.has_image()

    def test_clear_image(self, tmp_path):
        """Test clearing the overlay image."""
        img_path = tmp_path / "test.png"
        img = Image.new("RGB", (100, 100), color="red")
        img.save(img_path)

        layer = OverlayLayer()
        layer.import_image(str(img_path))
        assert layer.has_image()

        layer.clear_image()
        assert not layer.has_image()
        assert layer.image is None
        assert layer.image_path is None


class TestOverlayLayerPositioning:
    """Test overlay positioning operations."""

    def test_set_position(self):
        """Test setting position."""
        layer = OverlayLayer()
        layer.set_position(100, 200)

        assert layer.x == 100
        assert layer.y == 200
        assert layer.position == (100, 200)

    def test_nudge(self):
        """Test nudging position."""
        layer = OverlayLayer()
        layer.set_position(50, 50)

        layer.nudge(10, -5)
        assert layer.position == (60, 45)

        layer.nudge(-20, 15)
        assert layer.position == (40, 60)


class TestOverlayLayerOpacity:
    """Test opacity operations."""

    def test_set_opacity(self):
        """Test setting opacity."""
        layer = OverlayLayer()

        layer.set_opacity(0.75)
        assert layer.opacity == 0.75

    def test_opacity_clamping(self):
        """Test that opacity is clamped to 0-1."""
        layer = OverlayLayer()

        layer.set_opacity(1.5)
        assert layer.opacity == 1.0

        layer.set_opacity(-0.5)
        assert layer.opacity == 0.0


class TestOverlayLayerVisibility:
    """Test visibility operations."""

    def test_toggle_visibility(self):
        """Test toggling visibility."""
        layer = OverlayLayer()
        assert layer.visible is True

        result = layer.toggle_visibility()
        assert result is False
        assert layer.visible is False

        result = layer.toggle_visibility()
        assert result is True
        assert layer.visible is True

    def test_set_visible(self):
        """Test setting visibility directly."""
        layer = OverlayLayer()

        layer.set_visible(False)
        assert layer.visible is False

        layer.set_visible(True)
        assert layer.visible is True


class TestOverlayLayerState:
    """Test state persistence operations."""

    def test_get_state(self, tmp_path):
        """Test getting state for persistence."""
        img_path = tmp_path / "test.png"
        img = Image.new("RGB", (100, 100), color="red")
        img.save(img_path)

        layer = OverlayLayer()
        layer.import_image(str(img_path))
        layer.set_position(10, 20)
        layer.set_opacity(0.75)
        layer.set_visible(False)

        state = layer.get_state()

        assert state["x"] == 10
        assert state["y"] == 20
        assert state["opacity"] == 0.75
        assert state["visible"] is False
        assert state["image_path"] is not None

    def test_restore_state(self, tmp_path):
        """Test restoring state from persistence."""
        img_path = tmp_path / "test.png"
        img = Image.new("RGB", (100, 100), color="red")
        img.save(img_path)

        # Save state from first layer
        layer1 = OverlayLayer()
        layer1.import_image(str(img_path))
        layer1.set_position(10, 20)
        layer1.set_opacity(0.75)
        layer1.set_visible(False)
        state = layer1.get_state()

        # Restore to new layer
        layer2 = OverlayLayer()
        result = layer2.restore_state(state)

        assert result is True
        assert layer2.x == 10
        assert layer2.y == 20
        assert layer2.opacity == 0.75
        assert layer2.visible is False
        assert layer2.has_image()


class TestOverlayLayerSampling:
    """Test tile sampling operations for Apply."""

    def test_sample_region(self, tmp_path):
        """Test sampling a region from the overlay."""
        # Create a test image with distinct colors
        img_path = tmp_path / "test.png"
        img = Image.new("RGBA", (32, 32), color=(255, 0, 0, 255))
        img.save(img_path)

        layer = OverlayLayer()
        layer.import_image(str(img_path))
        layer.set_position(0, 0)

        # Sample a tile-sized region
        region = layer.sample_region(0, 0, 8, 8)

        assert region is not None
        assert region.size == (8, 8)

    def test_sample_region_out_of_bounds(self, tmp_path):
        """Test sampling outside overlay bounds returns None."""
        img_path = tmp_path / "test.png"
        img = Image.new("RGBA", (32, 32), color=(255, 0, 0, 255))
        img.save(img_path)

        layer = OverlayLayer()
        layer.import_image(str(img_path))
        layer.set_position(0, 0)

        # Try to sample outside the image
        region = layer.sample_region(100, 100, 8, 8)
        assert region is None

    def test_sample_region_with_offset(self, tmp_path):
        """Test sampling when overlay has an offset."""
        img_path = tmp_path / "test.png"
        img = Image.new("RGBA", (32, 32), color=(255, 0, 0, 255))
        img.save(img_path)

        layer = OverlayLayer()
        layer.import_image(str(img_path))
        layer.set_position(10, 10)

        # Sample at overlay position (10, 10) - should be (0, 0) in overlay coords
        region = layer.sample_region(10, 10, 8, 8)
        assert region is not None
        assert region.size == (8, 8)

        # Sample at canvas position (0, 0) - before overlay starts
        region = layer.sample_region(0, 0, 8, 8)
        assert region is None  # Out of bounds

    def test_covers_tile(self, tmp_path):
        """Test checking if overlay covers a tile."""
        img_path = tmp_path / "test.png"
        img = Image.new("RGBA", (32, 32), color=(255, 0, 0, 255))
        img.save(img_path)

        layer = OverlayLayer()
        layer.import_image(str(img_path))
        layer.set_position(0, 0)

        # Tile fully covered
        assert layer.covers_tile(0, 0, 8, 8) is True
        assert layer.covers_tile(8, 8, 8, 8) is True

        # Tile partially outside
        assert layer.covers_tile(28, 0, 8, 8) is False
        assert layer.covers_tile(0, 28, 8, 8) is False

    def test_covers_tile_no_image(self):
        """Test covers_tile returns False when no image."""
        layer = OverlayLayer()
        assert layer.covers_tile(0, 0, 8, 8) is False


class TestOverlayLayerResamplingMode:
    """Test resampling mode operations for detail preservation."""

    def test_resampling_mode_default(self):
        """Test default resampling mode is NEAREST for pixel art."""
        layer = OverlayLayer()
        assert layer.resampling_mode == Image.Resampling.NEAREST

    def test_set_resampling_mode(self):
        """Test setting resampling mode."""
        layer = OverlayLayer()

        layer.set_resampling_mode(Image.Resampling.BOX)
        assert layer.resampling_mode == Image.Resampling.BOX

        layer.set_resampling_mode(Image.Resampling.LANCZOS)
        assert layer.resampling_mode == Image.Resampling.LANCZOS

        layer.set_resampling_mode(Image.Resampling.NEAREST)
        assert layer.resampling_mode == Image.Resampling.NEAREST

    def test_resampling_mode_in_state(self, tmp_path):
        """Test resampling mode is persisted in state."""
        img_path = tmp_path / "test.png"
        img = Image.new("RGB", (100, 100), color="red")
        img.save(img_path)

        layer = OverlayLayer()
        layer.import_image(str(img_path))
        layer.set_resampling_mode(Image.Resampling.LANCZOS)

        state = layer.get_state()
        assert "resampling_mode" in state

        # Restore to new layer
        layer2 = OverlayLayer()
        layer2.restore_state(state)
        assert layer2.resampling_mode == Image.Resampling.LANCZOS

    def test_sample_region_preserves_sharp_edges_with_nearest(self, tmp_path):
        """Test that NEAREST resampling preserves sharp pixel edges.

        Bug: BOX resampling averages neighboring pixels, softening edges.
        NEAREST should preserve pixel-perfect edges for pixel art.

        This test creates a checkerboard pattern and verifies that sampling
        preserves the sharp transitions between black and white pixels.
        """
        # Create a small checkerboard pattern (high contrast for edge detection)
        img_path = tmp_path / "checkerboard.png"
        img = Image.new("RGBA", (16, 16), color=(0, 0, 0, 0))
        pixels = img.load()
        assert pixels is not None
        for y in range(16):
            for x in range(16):
                if (x + y) % 2 == 0:
                    pixels[x, y] = (255, 255, 255, 255)  # White
                else:
                    pixels[x, y] = (0, 0, 0, 255)  # Black
        img.save(img_path)

        layer = OverlayLayer()
        layer.import_image(str(img_path))
        layer.set_position(0, 0)
        layer.set_resampling_mode(Image.Resampling.NEAREST)

        # Sample at 1:1 scale - should preserve exact pattern
        region = layer.sample_region(0, 0, 8, 8)
        assert region is not None
        assert region.size == (8, 8)

        # Check that we have both pure white (255) and pure black (0) pixels
        # If BOX resampling was used, we'd get gray values instead
        region_pixels = region.load()
        assert region_pixels is not None

        has_white = False
        has_black = False
        for y in range(8):
            for x in range(8):
                r, g, b, a = region_pixels[x, y]
                if a > 0:  # Only check opaque pixels
                    if r == 255 and g == 255 and b == 255:
                        has_white = True
                    elif r == 0 and g == 0 and b == 0:
                        has_black = True

        assert has_white, "Should have pure white pixels (255,255,255)"
        assert has_black, "Should have pure black pixels (0,0,0)"

    def test_sample_region_uses_configured_resampling_mode(self, tmp_path):
        """Test that sample_region uses the configured resampling mode.

        This test uses scaling to verify that different resampling modes
        produce different results. At non-integer scaling ratios, NEAREST
        and BILINEAR produce visibly different output.
        """
        # Create a sharp-edged image with high contrast
        img_path = tmp_path / "sharp_edges.png"
        img = Image.new("RGBA", (20, 20), (0, 0, 0, 255))  # Black background
        pixels = img.load()
        assert pixels is not None
        # Draw a white square in the center
        for y in range(5, 15):
            for x in range(5, 15):
                pixels[x, y] = (255, 255, 255, 255)
        img.save(img_path)

        # Test with NEAREST - should preserve sharp edges
        layer_nearest = OverlayLayer()
        layer_nearest.import_image(str(img_path))
        layer_nearest.set_resampling_mode(Image.Resampling.NEAREST)
        # Scale to 1.5x to force non-integer resampling
        layer_nearest.set_scale(1.5)
        region_nearest = layer_nearest.sample_region(0, 0, 16, 16)

        # Test with BILINEAR - should produce interpolated values
        layer_bilinear = OverlayLayer()
        layer_bilinear.import_image(str(img_path))
        layer_bilinear.set_resampling_mode(Image.Resampling.BILINEAR)
        layer_bilinear.set_scale(1.5)
        region_bilinear = layer_bilinear.sample_region(0, 0, 16, 16)

        assert region_nearest is not None
        assert region_bilinear is not None

        # With NEAREST, pixels should be either pure black or pure white
        # With BILINEAR, there should be intermediate gray values at edges
        nearest_pixels = list(region_nearest.getdata())
        bilinear_pixels = list(region_bilinear.getdata())

        # Count unique brightness values (R channel)
        nearest_unique = {p[0] for p in nearest_pixels if p[3] > 0}  # Opaque only
        bilinear_unique = {p[0] for p in bilinear_pixels if p[3] > 0}

        # BILINEAR should have more unique values due to interpolation
        # NEAREST should only have 0 (black) and 255 (white)
        assert len(bilinear_unique) > len(nearest_unique), (
            f"BILINEAR should have more unique values ({len(bilinear_unique)}) "
            f"than NEAREST ({len(nearest_unique)}) due to interpolation"
        )
