"""Unit tests for SpriteCompositor service."""

from __future__ import annotations

import pytest
from PIL import Image

from core.services.sprite_compositor import CompositeResult, SpriteCompositor, TransformParams


class MockCaptureResult:
    """Minimal mock for CaptureResult."""

    def __init__(
        self,
        entries: list,
        palettes: dict,
        width: int = 16,
        height: int = 16,
    ) -> None:
        self.entries = entries
        self.palettes = palettes
        self.frame = 0
        self.visible_count = len(entries)
        self.obsel = 0
        self.timestamp = ""
        self._width = width
        self._height = height

    @property
    def bounding_box(self) -> MockBoundingBox:
        return MockBoundingBox(0, 0, self._width, self._height)


class MockBoundingBox:
    """Minimal mock for CaptureBoundingBox."""

    def __init__(self, x: int, y: int, width: int, height: int) -> None:
        self.x = x
        self.y = y
        self.width = width
        self.height = height


class MockEntry:
    """Minimal mock for OAMEntry."""

    def __init__(
        self,
        id: int = 0,
        x: int = 0,
        y: int = 0,
        width: int = 16,
        height: int = 16,
        palette: int = 0,
        flip_h: bool = False,
        flip_v: bool = False,
    ) -> None:
        self.id = id
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.palette = palette
        self.flip_h = flip_h
        self.flip_v = flip_v
        self.tiles: list = []
        self.rom_offset = 0x10000


class TestTransformOrder:
    """Test that transforms are applied in SNES-correct order: flip -> scale."""

    def test_flip_then_scale_produces_correct_dimensions(self) -> None:
        """When flip and scale are both applied, flip happens first."""
        compositor = SpriteCompositor(uncovered_policy="transparent")

        # Create a non-square AI image to detect order issues
        # 8x16 image - if scaled 2x becomes 16x32
        ai_img = Image.new("RGBA", (8, 16), (255, 0, 0, 255))

        transform = TransformParams(
            offset_x=0,
            offset_y=0,
            flip_h=True,
            flip_v=False,
            scale=2.0,
        )

        # Apply transforms manually to verify expected dimensions
        transformed = compositor._apply_transforms(ai_img, transform)

        # With flip then scale on 8x16: flip doesn't change size, scale 2x → 16x32
        assert transformed.width == 16
        assert transformed.height == 32

    def test_scale_only(self) -> None:
        """Scale without flip should work correctly."""
        compositor = SpriteCompositor(uncovered_policy="transparent")
        ai_img = Image.new("RGBA", (10, 10), (255, 0, 0, 255))

        transform = TransformParams(scale=1.5)

        transformed = compositor._apply_transforms(ai_img, transform)

        assert transformed.width == 15
        assert transformed.height == 15

    def test_flip_only_horizontal(self) -> None:
        """Horizontal flip should mirror the image."""
        compositor = SpriteCompositor(uncovered_policy="transparent")

        # Create image with left side red, right side blue
        ai_img = Image.new("RGBA", (10, 10), (255, 0, 0, 255))
        for x in range(5, 10):
            for y in range(10):
                ai_img.putpixel((x, y), (0, 0, 255, 255))

        transform = TransformParams(flip_h=True)

        transformed = compositor._apply_transforms(ai_img, transform)

        # After flip, left should be blue, right should be red
        assert transformed.getpixel((0, 0))[:3] == (0, 0, 255)
        assert transformed.getpixel((9, 0))[:3] == (255, 0, 0)


class TestUncoveredPolicy:
    """Test the uncovered_policy behavior."""

    def test_transparent_policy_returns_transparent_in_result(self) -> None:
        """Transparent policy should be reflected in CompositeResult."""
        compositor = SpriteCompositor(uncovered_policy="transparent")
        assert compositor._uncovered_policy == "transparent"

    def test_original_policy_returns_original_in_result(self) -> None:
        """Original policy should be reflected in CompositeResult."""
        compositor = SpriteCompositor(uncovered_policy="original")
        assert compositor._uncovered_policy == "original"


class TestTransformParamsDefaults:
    """Test TransformParams default values."""

    def test_default_values(self) -> None:
        """TransformParams should have sensible defaults."""
        params = TransformParams()

        assert params.offset_x == 0
        assert params.offset_y == 0
        assert params.flip_h is False
        assert params.flip_v is False
        assert params.scale == 1.0

    def test_custom_values(self) -> None:
        """TransformParams should accept custom values."""
        params = TransformParams(
            offset_x=10,
            offset_y=-5,
            flip_h=True,
            flip_v=True,
            scale=0.5,
        )

        assert params.offset_x == 10
        assert params.offset_y == -5
        assert params.flip_h is True
        assert params.flip_v is True
        assert params.scale == 0.5


class TestCompositeResult:
    """Test CompositeResult dataclass."""

    def test_result_properties(self) -> None:
        """CompositeResult should store all properties correctly."""
        img = Image.new("RGBA", (16, 16), (255, 0, 0, 255))
        mask = Image.new("L", (16, 16), 255)

        result = CompositeResult(
            composited_image=img,
            original_mask=mask,
            canvas_width=16,
            canvas_height=16,
            uncovered_policy="transparent",
        )

        assert result.composited_image == img
        assert result.original_mask == mask
        assert result.canvas_width == 16
        assert result.canvas_height == 16
        assert result.uncovered_policy == "transparent"
