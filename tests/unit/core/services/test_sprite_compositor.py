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


class TestTransparentPolicyMasking:
    """Test that transparent policy masks AI content to sprite tile boundaries.

    Bug: When uncovered_policy="transparent", the AI image was shown for the
    entire bounding box, not just where sprite tiles exist. This caused
    AI content to appear in gaps between sprite tiles.
    """

    def test_ai_content_masked_to_sprite_tiles_only(self) -> None:
        """AI content should only appear where original sprite has opaque pixels.

        Creates a sprite with two 8x8 tiles separated by an 8-pixel gap.
        The bounding box is 24x8, but only pixels 0-7 and 16-23 have tiles.
        The AI image fills the entire box with red.

        Expected: Gap (pixels 8-15) should be transparent, not red.
        """
        from dataclasses import dataclass, field

        @dataclass
        class MockTileData:
            tile_index: int
            vram_addr: int
            pos_x: int
            pos_y: int
            data_hex: str
            rom_offset: int | None = None

            @property
            def data_bytes(self) -> bytes:
                return bytes.fromhex(self.data_hex)

        @dataclass
        class MockOAMEntry:
            id: int
            x: int
            y: int
            width: int
            height: int
            palette: int
            flip_h: bool = False
            flip_v: bool = False
            priority: int = 0
            tile: int = 0
            name_table: int = 0
            size_large: bool = False
            rom_offset: int = 0x10000
            tiles: list = field(default_factory=list)

            @property
            def tiles_wide(self) -> int:
                return self.width // 8

            @property
            def tiles_high(self) -> int:
                return self.height // 8

        @dataclass
        class MockCaptureBoundingBox:
            x: int
            y: int
            width: int
            height: int

        @dataclass
        class MockCaptureResultFull:
            frame: int
            visible_count: int
            obsel: int
            entries: list
            palettes: dict
            timestamp: str = ""

            @property
            def bounding_box(self) -> MockCaptureBoundingBox:
                if not self.entries:
                    return MockCaptureBoundingBox(0, 0, 0, 0)
                min_x = min(e.x for e in self.entries)
                min_y = min(e.y for e in self.entries)
                max_x = max(e.x + e.width for e in self.entries)
                max_y = max(e.y + e.height for e in self.entries)
                return MockCaptureBoundingBox(min_x, min_y, max_x - min_x, max_y - min_y)

        # Create a solid 8x8 tile (all opaque white pixels)
        # 4bpp tile data: 32 bytes, each pixel is color index 15 (fully opaque white)
        # For simplicity, create tile data that renders as solid when decoded
        solid_tile_hex = "ff" * 32  # All bits set = color index 15

        # Two entries: one at x=0, one at x=16, both 8x8
        # This creates a gap at x=8-15
        entry1 = MockOAMEntry(
            id=0,
            x=0,
            y=0,
            width=8,
            height=8,
            palette=0,
            tiles=[
                MockTileData(
                    tile_index=0,
                    vram_addr=0,
                    pos_x=0,
                    pos_y=0,
                    data_hex=solid_tile_hex,
                )
            ],
        )
        entry2 = MockOAMEntry(
            id=1,
            x=16,  # 8-pixel gap from entry1
            y=0,
            width=8,
            height=8,
            palette=0,
            tiles=[
                MockTileData(
                    tile_index=1,
                    vram_addr=0,
                    pos_x=0,
                    pos_y=0,
                    data_hex=solid_tile_hex,
                )
            ],
        )

        # Palette 0: 16 colors, all white for simplicity
        palettes = {0: [(255, 255, 255)] * 16}

        capture = MockCaptureResultFull(
            frame=0,
            visible_count=2,
            obsel=0,
            entries=[entry1, entry2],
            palettes=palettes,
        )

        # Bounding box is 24x8 (from x=0 to x=24)
        assert capture.bounding_box.width == 24
        assert capture.bounding_box.height == 8

        # AI image: solid red, fills entire bounding box
        ai_image = Image.new("RGBA", (24, 8), (255, 0, 0, 255))

        # Composite with transparent policy
        compositor = SpriteCompositor(uncovered_policy="transparent")
        transform = TransformParams(offset_x=0, offset_y=0)

        result = compositor.composite_frame(
            ai_image=ai_image,
            capture_result=capture,  # type: ignore[arg-type]
            transform=transform,
            quantize=False,  # Don't quantize to preserve exact colors
        )

        composited = result.composited_image

        # Check that gap region (x=8-15) is transparent
        # The bug: currently these pixels are red (from AI image)
        # Expected: these pixels should be transparent (alpha=0)
        for x in range(8, 16):
            pixel = composited.getpixel((x, 0))
            assert pixel[3] == 0, (
                f"Pixel at ({x}, 0) should be transparent (alpha=0), "
                f"but got alpha={pixel[3]}. The AI content is leaking into "
                f"areas outside the sprite tiles."
            )

        # Verify that tile regions do have AI content (sanity check)
        # Left tile region (x=0-7) should have red from AI
        pixel_left = composited.getpixel((4, 4))
        assert pixel_left[3] > 0, "Left tile region should have opaque content"

        # Right tile region (x=16-23) should have red from AI
        pixel_right = composited.getpixel((20, 4))
        assert pixel_right[3] > 0, "Right tile region should have opaque content"


class TestSheetPaletteQuantization:
    """Test that sheet_palette parameter takes priority over capture palette.

    The preview should match injection behavior: sheet_palette > capture palette.
    """

    def test_sheet_palette_used_when_provided(self) -> None:
        """composite_frame should use sheet_palette colors when provided."""
        from dataclasses import dataclass, field

        from core.frame_mapping_project import SheetPalette

        @dataclass
        class MockTileData:
            tile_index: int
            vram_addr: int
            pos_x: int
            pos_y: int
            data_hex: str
            rom_offset: int | None = None

            @property
            def data_bytes(self) -> bytes:
                return bytes.fromhex(self.data_hex)

        @dataclass
        class MockOAMEntry:
            id: int
            x: int
            y: int
            width: int
            height: int
            palette: int
            flip_h: bool = False
            flip_v: bool = False
            priority: int = 0
            tile: int = 0
            name_table: int = 0
            size_large: bool = False
            rom_offset: int = 0x10000
            tiles: list = field(default_factory=list)

            @property
            def tiles_wide(self) -> int:
                return self.width // 8

            @property
            def tiles_high(self) -> int:
                return self.height // 8

        @dataclass
        class MockCaptureBoundingBox:
            x: int
            y: int
            width: int
            height: int

        @dataclass
        class MockCaptureResultFull:
            frame: int
            visible_count: int
            obsel: int
            entries: list
            palettes: dict
            timestamp: str = ""

            @property
            def bounding_box(self) -> MockCaptureBoundingBox:
                if not self.entries:
                    return MockCaptureBoundingBox(0, 0, 0, 0)
                min_x = min(e.x for e in self.entries)
                min_y = min(e.y for e in self.entries)
                max_x = max(e.x + e.width for e in self.entries)
                max_y = max(e.y + e.height for e in self.entries)
                return MockCaptureBoundingBox(min_x, min_y, max_x - min_x, max_y - min_y)

        # Create a solid 8x8 tile
        solid_tile_hex = "ff" * 32

        entry = MockOAMEntry(
            id=0,
            x=0,
            y=0,
            width=8,
            height=8,
            palette=0,
            tiles=[
                MockTileData(
                    tile_index=0,
                    vram_addr=0,
                    pos_x=0,
                    pos_y=0,
                    data_hex=solid_tile_hex,
                )
            ],
        )

        # Capture palette: all red
        capture_palettes = {0: [(0, 255, 0, 255)] * 16}

        capture = MockCaptureResultFull(
            frame=0,
            visible_count=1,
            obsel=0,
            entries=[entry],
            palettes=capture_palettes,
        )

        # Sheet palette: different colors (blue-ish)
        sheet_palette = SheetPalette(
            colors=[
                (0, 0, 0),  # 0: transparent
                (0, 0, 255),  # 1: blue
                (0, 0, 200),  # 2: dark blue
                (0, 0, 150),  # 3: darker blue
            ]
            + [(100, 100, 100)] * 12,  # pad to 16
            color_mappings={(255, 0, 0): 1},  # Map red to index 1 (blue)
        )

        # AI image: solid red
        ai_image = Image.new("RGBA", (8, 8), (255, 0, 0, 255))

        compositor = SpriteCompositor(uncovered_policy="transparent")
        transform = TransformParams(offset_x=0, offset_y=0)

        result = compositor.composite_frame(
            ai_image=ai_image,
            capture_result=capture,  # type: ignore[arg-type]
            transform=transform,
            quantize=True,
            sheet_palette=sheet_palette,
        )

        composited = result.composited_image

        # The red AI pixels should have been mapped to index 1 (blue)
        # via the sheet_palette color_mappings
        pixel = composited.getpixel((4, 4))
        assert pixel[:3] == (0, 0, 255), (
            f"Expected blue (0,0,255) from sheet_palette mapping, "
            f"but got {pixel[:3]}. Sheet palette should take priority."
        )

    def test_capture_palette_used_without_sheet_palette(self) -> None:
        """composite_frame should fall back to capture palette when no sheet_palette."""
        from dataclasses import dataclass, field

        @dataclass
        class MockTileData:
            tile_index: int
            vram_addr: int
            pos_x: int
            pos_y: int
            data_hex: str
            rom_offset: int | None = None

            @property
            def data_bytes(self) -> bytes:
                return bytes.fromhex(self.data_hex)

        @dataclass
        class MockOAMEntry:
            id: int
            x: int
            y: int
            width: int
            height: int
            palette: int
            flip_h: bool = False
            flip_v: bool = False
            priority: int = 0
            tile: int = 0
            name_table: int = 0
            size_large: bool = False
            rom_offset: int = 0x10000
            tiles: list = field(default_factory=list)

            @property
            def tiles_wide(self) -> int:
                return self.width // 8

            @property
            def tiles_high(self) -> int:
                return self.height // 8

        @dataclass
        class MockCaptureBoundingBox:
            x: int
            y: int
            width: int
            height: int

        @dataclass
        class MockCaptureResultFull:
            frame: int
            visible_count: int
            obsel: int
            entries: list
            palettes: dict
            timestamp: str = ""

            @property
            def bounding_box(self) -> MockCaptureBoundingBox:
                if not self.entries:
                    return MockCaptureBoundingBox(0, 0, 0, 0)
                min_x = min(e.x for e in self.entries)
                min_y = min(e.y for e in self.entries)
                max_x = max(e.x + e.width for e in self.entries)
                max_y = max(e.y + e.height for e in self.entries)
                return MockCaptureBoundingBox(min_x, min_y, max_x - min_x, max_y - min_y)

        # Create a solid 8x8 tile
        solid_tile_hex = "ff" * 32

        entry = MockOAMEntry(
            id=0,
            x=0,
            y=0,
            width=8,
            height=8,
            palette=0,
            tiles=[
                MockTileData(
                    tile_index=0,
                    vram_addr=0,
                    pos_x=0,
                    pos_y=0,
                    data_hex=solid_tile_hex,
                )
            ],
        )

        # SNES palette format: 16-bit BGR555 values (not RGB tuples)
        # Green (R=0, G=31, B=0) in BGR555: 0000 0011 1110 0000 = 0x03E0
        snes_palettes = {0: [0x03E0] * 16}  # All green

        capture = MockCaptureResultFull(
            frame=0,
            visible_count=1,
            obsel=0,
            entries=[entry],
            palettes=snes_palettes,
        )

        # AI image: solid red
        ai_image = Image.new("RGBA", (8, 8), (255, 0, 0, 255))

        compositor = SpriteCompositor(uncovered_policy="transparent")
        transform = TransformParams(offset_x=0, offset_y=0)

        # No sheet_palette provided - should fall back to capture palette
        result = compositor.composite_frame(
            ai_image=ai_image,
            capture_result=capture,  # type: ignore[arg-type]
            transform=transform,
            quantize=True,
            sheet_palette=None,
        )

        composited = result.composited_image

        # The result should be quantized to the capture palette (green)
        pixel = composited.getpixel((4, 4))
        # Should be green since that's the only color in capture palette
        # SNES green (31 in 5-bit) expands to 255 in 8-bit using full scaling:
        # (31 << 3) | (31 >> 2) = 248 | 7 = 255
        assert pixel[:3] == (0, 255, 0), (
            f"Expected green (0,255,0) from capture palette (SNES 5-bit fully scaled), "
            f"but got {pixel[:3]}. Should fall back to capture palette."
        )
