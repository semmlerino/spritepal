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
