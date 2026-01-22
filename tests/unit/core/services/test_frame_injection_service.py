"""Unit tests for FrameInjectionService."""

from __future__ import annotations

import pytest
from PIL import Image

from core.services.frame_injection_service import (
    FrameInjectionService,
    TileGroup,
    TileInfo,
    TileInjectionBatch,
)


class MockTile:
    """Minimal mock for TileData."""

    def __init__(
        self,
        rom_offset: int | None = 0x10000,
        vram_addr: int = 0x0000,
        pos_x: int = 0,
        pos_y: int = 0,
        tile_index_in_block: int | None = None,
    ) -> None:
        self.rom_offset = rom_offset
        self.vram_addr = vram_addr
        self.pos_x = pos_x
        self.pos_y = pos_y
        self.tile_index_in_block = tile_index_in_block
        self.data_bytes = bytes(32)
        self.data_hex = "0" * 64


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
        tiles: list | None = None,
    ) -> None:
        self.id = id
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.palette = palette
        self.flip_h = flip_h
        self.flip_v = flip_v
        self.tiles = tiles if tiles is not None else []
        self.rom_offset = 0x10000


class MockBoundingBox:
    """Minimal mock for CaptureBoundingBox."""

    def __init__(self, x: int, y: int, width: int, height: int) -> None:
        self.x = x
        self.y = y
        self.width = width
        self.height = height


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


class TestTileInfo:
    """Test TileInfo dataclass."""

    def test_tile_info_creation(self) -> None:
        """TileInfo should store all properties correctly."""
        info = TileInfo(
            vram_addr=0x1234,
            screen_x=100,
            screen_y=50,
            palette_index=3,
            tile_index_in_block=5,
            flip_h=True,
            flip_v=False,
        )

        assert info.vram_addr == 0x1234
        assert info.screen_x == 100
        assert info.screen_y == 50
        assert info.palette_index == 3
        assert info.tile_index_in_block == 5
        assert info.flip_h is True
        assert info.flip_v is False


class TestTileGroup:
    """Test TileGroup dataclass."""

    def test_add_tile_new(self) -> None:
        """Adding a new tile should succeed."""
        group = TileGroup(rom_offset=0x10000)

        tile = TileInfo(
            vram_addr=0x100,
            screen_x=0,
            screen_y=0,
            palette_index=0,
            tile_index_in_block=None,
            flip_h=False,
            flip_v=False,
        )
        group.add_tile(tile)

        assert 0x100 in group.tiles
        assert group.tiles[0x100] == tile

    def test_add_tile_duplicate_ignored(self) -> None:
        """Adding a duplicate vram_addr should be ignored."""
        group = TileGroup(rom_offset=0x10000)

        tile1 = TileInfo(
            vram_addr=0x100,
            screen_x=0,
            screen_y=0,
            palette_index=0,
            tile_index_in_block=None,
            flip_h=False,
            flip_v=False,
        )
        tile2 = TileInfo(
            vram_addr=0x100,  # Same vram_addr
            screen_x=8,
            screen_y=8,
            palette_index=1,
            tile_index_in_block=None,
            flip_h=True,
            flip_v=True,
        )

        group.add_tile(tile1)
        group.add_tile(tile2)

        # Should still be tile1
        assert group.tiles[0x100].screen_x == 0
        assert group.tiles[0x100].palette_index == 0


class TestTileInjectionBatch:
    """Test TileInjectionBatch dataclass."""

    def test_batch_creation(self) -> None:
        """TileInjectionBatch should store all properties correctly."""
        img = Image.new("RGBA", (8, 8), (255, 0, 0, 255))

        batch = TileInjectionBatch(
            rom_offset=0x20000,
            tile_image=img,
            tile_count=4,
            palette_index=2,
            is_raw=True,
        )

        assert batch.rom_offset == 0x20000
        assert batch.tile_image == img
        assert batch.tile_count == 4
        assert batch.palette_index == 2
        assert batch.is_raw is True

    def test_batch_default_is_raw(self) -> None:
        """is_raw should default to False."""
        img = Image.new("RGBA", (8, 8), (255, 0, 0, 255))

        batch = TileInjectionBatch(
            rom_offset=0x20000,
            tile_image=img,
            tile_count=1,
            palette_index=0,
        )

        assert batch.is_raw is False


class TestFrameInjectionService:
    """Test FrameInjectionService methods."""

    def test_sort_tiles_by_tile_index(self) -> None:
        """Tiles should be sorted by tile_index_in_block when available."""
        service = FrameInjectionService()

        tiles = {
            0x200: TileInfo(0x200, 0, 0, 0, tile_index_in_block=2, flip_h=False, flip_v=False),
            0x100: TileInfo(0x100, 0, 8, 0, tile_index_in_block=0, flip_h=False, flip_v=False),
            0x300: TileInfo(0x300, 8, 0, 0, tile_index_in_block=1, flip_h=False, flip_v=False),
        }

        sorted_addrs = service._sort_tiles(tiles)

        # Should be sorted by tile_index_in_block: 0, 1, 2
        assert sorted_addrs == [0x100, 0x300, 0x200]

    def test_sort_tiles_by_vram_addr_fallback(self) -> None:
        """When tile_index_in_block is None, sort by vram_addr."""
        service = FrameInjectionService()

        tiles = {
            0x300: TileInfo(0x300, 0, 0, 0, tile_index_in_block=None, flip_h=False, flip_v=False),
            0x100: TileInfo(0x100, 8, 0, 0, tile_index_in_block=None, flip_h=False, flip_v=False),
            0x200: TileInfo(0x200, 0, 8, 0, tile_index_in_block=None, flip_h=False, flip_v=False),
        }

        sorted_addrs = service._sort_tiles(tiles)

        # Should be sorted by vram_addr
        assert sorted_addrs == [0x100, 0x200, 0x300]

    def test_prepare_empty_entries_returns_empty(self) -> None:
        """When no entries are provided, return empty list."""
        service = FrameInjectionService()

        capture = MockCaptureResult(entries=[], palettes={})
        canvas = Image.new("RGBA", (16, 16), (255, 0, 0, 255))

        batches = service.prepare_injection_batches(canvas, capture)

        assert batches == []

    def test_prepare_with_selected_entry_ids_filters(self) -> None:
        """Only selected entries should be processed."""
        service = FrameInjectionService()

        tile1 = MockTile(rom_offset=0x10000, vram_addr=0x100)
        tile2 = MockTile(rom_offset=0x20000, vram_addr=0x200)

        entry1 = MockEntry(id=1, tiles=[tile1])
        entry2 = MockEntry(id=2, tiles=[tile2])

        capture = MockCaptureResult(
            entries=[entry1, entry2],
            palettes={0: [0] * 16},
        )
        canvas = Image.new("RGBA", (16, 16), (255, 0, 0, 255))

        # Only process entry 1
        batches = service.prepare_injection_batches(
            canvas,
            capture,
            selected_entry_ids=[1],
        )

        # Should only have batch for entry1's rom_offset
        rom_offsets = [b.rom_offset for b in batches]
        assert 0x10000 in rom_offsets
        assert 0x20000 not in rom_offsets
