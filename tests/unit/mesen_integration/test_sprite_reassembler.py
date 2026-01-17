"""Tests for SpriteReassembler SNES tile arrangement.

Verifies that the reassembler correctly handles SNES 16-tile row stride
when extracting tiles from decompressed data.

SNES sprite tile layout:
- 16x16 (2x2 tiles): [0][1] / [16][17]
- 32x32 (4x4 tiles): [0][1][2][3] / [16][17][18][19] / [32][33][34][35] / [48][49][50][51]
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from core.mesen_integration.click_extractor import OAMEntry
from core.mesen_integration.sprite_reassembler import SpriteReassembler
from utils.constants import BYTES_PER_TILE


@pytest.fixture
def mock_hal_compressor() -> MagicMock:
    """Mock HAL compressor that returns predetermined decompressed data."""
    compressor = MagicMock()
    return compressor


@pytest.fixture
def mock_tile_renderer() -> MagicMock:
    """Mock tile renderer that records what tiles it receives."""
    renderer = MagicMock()
    # Return a dummy image
    renderer.render_tiles.return_value = Image.new("RGBA", (8, 8))
    return renderer


def create_oam_entry(
    *,
    width: int = 8,
    height: int = 8,
    tile: int = 0,
    rom_offset: int = 0x100000,
    flip_h: bool = False,
    flip_v: bool = False,
) -> OAMEntry:
    """Create OAM entry for testing."""
    return OAMEntry(
        id=0,
        x=100,
        y=100,
        tile=tile,
        width=width,
        height=height,
        flip_h=flip_h,
        flip_v=flip_v,
        palette=0,
        rom_offset=rom_offset,
    )


def create_tile_data(num_tiles: int, pattern: str = "numbered") -> bytes:
    """Create tile data where each tile has a unique identifier.

    Args:
        num_tiles: Total number of tiles to create
        pattern: 'numbered' puts tile index in first byte, 'unique' makes each tile unique

    Returns:
        Byte data representing num_tiles worth of tile data
    """
    data = bytearray()
    for i in range(num_tiles):
        if pattern == "numbered":
            # First byte is the tile index, rest are zeros
            tile_data = bytes([i]) + b"\x00" * (BYTES_PER_TILE - 1)
        else:
            # Fill entire tile with tile index
            tile_data = bytes([i] * BYTES_PER_TILE)
        data.extend(tile_data)
    return bytes(data)


class TestSNESTileArrangement:
    """Test SNES 16-tile row stride arrangement."""

    def test_8x8_sprite_single_tile(self, mock_hal_compressor: MagicMock, mock_tile_renderer: MagicMock):
        """8x8 sprite only needs one tile, no stride involved."""
        # Create data with 64 tiles (enough for any test)
        tiles_data = create_tile_data(64)
        mock_hal_compressor.decompress_file.return_value = tiles_data

        entry = create_oam_entry(width=8, height=8, tile=5)

        with patch.object(SpriteReassembler, "_get_decompressed_data", return_value=tiles_data):
            reassembler = SpriteReassembler(
                rom_path=Path("/fake/rom.sfc"),
                hal_compressor=mock_hal_compressor,
                tile_renderer=mock_tile_renderer,
            )
            reassembler._render_oam_entry(entry, palette_index=0)

        # Verify render_tiles was called
        mock_tile_renderer.render_tiles.assert_called_once()
        call_args = mock_tile_renderer.render_tiles.call_args

        # For 8x8, should get exactly one tile's worth of data
        tile_bytes = call_args[0][0]
        assert len(tile_bytes) == BYTES_PER_TILE

        # Should be tile 5's data (first byte is 5)
        assert tile_bytes[0] == 5

    def test_16x16_sprite_uses_stride(self, mock_hal_compressor: MagicMock, mock_tile_renderer: MagicMock):
        """16x16 sprite should read tiles 0, 1, 16, 17 not 0, 1, 2, 3."""
        # Create data with 64 tiles
        tiles_data = create_tile_data(64)
        mock_hal_compressor.decompress_file.return_value = tiles_data

        # 16x16 sprite starting at tile 0
        entry = create_oam_entry(width=16, height=16, tile=0)

        with patch.object(SpriteReassembler, "_get_decompressed_data", return_value=tiles_data):
            reassembler = SpriteReassembler(
                rom_path=Path("/fake/rom.sfc"),
                hal_compressor=mock_hal_compressor,
                tile_renderer=mock_tile_renderer,
            )
            reassembler._render_oam_entry(entry, palette_index=0)

        mock_tile_renderer.render_tiles.assert_called_once()
        call_args = mock_tile_renderer.render_tiles.call_args

        # For 16x16, should get 4 tiles' worth of data
        tile_bytes = call_args[0][0]
        assert len(tile_bytes) == 4 * BYTES_PER_TILE

        # Extract the first byte of each tile (the tile index)
        tile_indices = [tile_bytes[i * BYTES_PER_TILE] for i in range(4)]

        # SNES 16x16 arrangement: tiles 0, 1, 16, 17
        expected_indices = [0, 1, 16, 17]
        assert tile_indices == expected_indices, f"Expected tiles {expected_indices}, got {tile_indices}"

    def test_16x16_sprite_with_nonzero_base_tile(self, mock_hal_compressor: MagicMock, mock_tile_renderer: MagicMock):
        """16x16 sprite starting at tile 4 should read tiles 4, 5, 20, 21."""
        tiles_data = create_tile_data(64)

        entry = create_oam_entry(width=16, height=16, tile=4)

        with patch.object(SpriteReassembler, "_get_decompressed_data", return_value=tiles_data):
            reassembler = SpriteReassembler(
                rom_path=Path("/fake/rom.sfc"),
                hal_compressor=mock_hal_compressor,
                tile_renderer=mock_tile_renderer,
            )
            reassembler._render_oam_entry(entry, palette_index=0)

        call_args = mock_tile_renderer.render_tiles.call_args
        tile_bytes = call_args[0][0]

        tile_indices = [tile_bytes[i * BYTES_PER_TILE] for i in range(4)]

        # Base tile 4: should read tiles 4, 5, 20, 21
        expected_indices = [4, 5, 20, 21]
        assert tile_indices == expected_indices

    def test_32x32_sprite_uses_stride(self, mock_hal_compressor: MagicMock, mock_tile_renderer: MagicMock):
        """32x32 sprite should use 16-tile row stride for all 4 rows."""
        tiles_data = create_tile_data(128)

        entry = create_oam_entry(width=32, height=32, tile=0)

        with patch.object(SpriteReassembler, "_get_decompressed_data", return_value=tiles_data):
            reassembler = SpriteReassembler(
                rom_path=Path("/fake/rom.sfc"),
                hal_compressor=mock_hal_compressor,
                tile_renderer=mock_tile_renderer,
            )
            reassembler._render_oam_entry(entry, palette_index=0)

        call_args = mock_tile_renderer.render_tiles.call_args
        tile_bytes = call_args[0][0]

        # 32x32 = 4x4 = 16 tiles
        assert len(tile_bytes) == 16 * BYTES_PER_TILE

        tile_indices = [tile_bytes[i * BYTES_PER_TILE] for i in range(16)]

        # 32x32 SNES arrangement with 16-tile stride:
        # Row 0: tiles 0, 1, 2, 3
        # Row 1: tiles 16, 17, 18, 19
        # Row 2: tiles 32, 33, 34, 35
        # Row 3: tiles 48, 49, 50, 51
        expected_indices = [
            0,
            1,
            2,
            3,  # Row 0
            16,
            17,
            18,
            19,  # Row 1
            32,
            33,
            34,
            35,  # Row 2
            48,
            49,
            50,
            51,  # Row 3
        ]
        assert tile_indices == expected_indices

    def test_out_of_bounds_tile_zero_padded(self, mock_hal_compressor: MagicMock, mock_tile_renderer: MagicMock):
        """Tiles that exceed data bounds should be zero-padded."""
        # Create only 16 tiles (0-15) - tiles 16 and 17 don't exist
        tiles_data = create_tile_data(16)

        # 16x16 sprite starting at tile 0
        # Needs tiles 0, 1, 16, 17 - tile 16 and 17 are out of bounds
        entry = create_oam_entry(width=16, height=16, tile=0)

        with patch.object(SpriteReassembler, "_get_decompressed_data", return_value=tiles_data):
            reassembler = SpriteReassembler(
                rom_path=Path("/fake/rom.sfc"),
                hal_compressor=mock_hal_compressor,
                tile_renderer=mock_tile_renderer,
            )
            # Should not raise, should pad with zeros
            reassembler._render_oam_entry(entry, palette_index=0)

        call_args = mock_tile_renderer.render_tiles.call_args
        tile_bytes = call_args[0][0]

        # Should still get 4 tiles' worth
        assert len(tile_bytes) == 4 * BYTES_PER_TILE

        # First two tiles should be valid
        assert tile_bytes[0] == 0  # Tile 0
        assert tile_bytes[BYTES_PER_TILE] == 1  # Tile 1

        # Tiles 16 and 17 should be zero-padded
        assert tile_bytes[2 * BYTES_PER_TILE] == 0  # Zero-padded
        assert tile_bytes[3 * BYTES_PER_TILE] == 0  # Zero-padded


class TestTileRenderingIntegration:
    """Test that stride-extracted tiles are passed correctly to renderer."""

    def test_tiles_wide_and_high_passed_correctly(self, mock_hal_compressor: MagicMock, mock_tile_renderer: MagicMock):
        """Verify tiles_wide and tiles_high are passed to render_tiles."""
        tiles_data = create_tile_data(64)

        entry = create_oam_entry(width=32, height=16, tile=0)  # 4x2 tiles

        with patch.object(SpriteReassembler, "_get_decompressed_data", return_value=tiles_data):
            reassembler = SpriteReassembler(
                rom_path=Path("/fake/rom.sfc"),
                hal_compressor=mock_hal_compressor,
                tile_renderer=mock_tile_renderer,
            )
            reassembler._render_oam_entry(entry, palette_index=0)

        call_args = mock_tile_renderer.render_tiles.call_args
        _, tiles_wide, tiles_high, palette_index = call_args[0]

        assert tiles_wide == 4
        assert tiles_high == 2
        assert palette_index == 0

    def test_32x16_sprite_arrangement(self, mock_hal_compressor: MagicMock, mock_tile_renderer: MagicMock):
        """32x16 (4x2 tiles) should read tiles 0-3, 16-19."""
        tiles_data = create_tile_data(64)

        entry = create_oam_entry(width=32, height=16, tile=0)

        with patch.object(SpriteReassembler, "_get_decompressed_data", return_value=tiles_data):
            reassembler = SpriteReassembler(
                rom_path=Path("/fake/rom.sfc"),
                hal_compressor=mock_hal_compressor,
                tile_renderer=mock_tile_renderer,
            )
            reassembler._render_oam_entry(entry, palette_index=0)

        call_args = mock_tile_renderer.render_tiles.call_args
        tile_bytes = call_args[0][0]

        tile_indices = [tile_bytes[i * BYTES_PER_TILE] for i in range(8)]

        # 32x16 = 4 wide x 2 high
        # Row 0: tiles 0, 1, 2, 3
        # Row 1: tiles 16, 17, 18, 19
        expected_indices = [0, 1, 2, 3, 16, 17, 18, 19]
        assert tile_indices == expected_indices
