#!/usr/bin/env python3
"""
SNES tile encoding/decoding utilities
Consolidated from various sprite editor modules
"""

from ..constants import (
    BYTES_PER_TILE_4BPP,
    PIXELS_PER_TILE,
    TILE_BITPLANE_OFFSET,
    TILE_HEIGHT,
    TILE_WIDTH,
)


def decode_4bpp_tile(data: bytes, offset: int) -> list[int]:
    """
    Decode a single 8x8 4bpp SNES tile.

    Args:
        data: Raw tile data bytes
        offset: Starting offset in the data

    Returns:
        List of 64 pixel values (0-15)

    Raises:
        IndexError: If offset + BYTES_PER_TILE_4BPP exceeds data length
    """
    if offset + BYTES_PER_TILE_4BPP > len(data):
        raise IndexError(f"Tile data out of bounds at offset {offset}")

    tile = []
    for y in range(TILE_HEIGHT):
        row = []
        # Read bitplanes for this row
        bp0 = data[offset + y * 2]
        bp1 = data[offset + y * 2 + 1]
        bp2 = data[offset + TILE_BITPLANE_OFFSET + y * 2]
        bp3 = data[offset + TILE_BITPLANE_OFFSET + y * 2 + 1]

        # Decode each pixel in the row
        for x in range(TILE_WIDTH):
            bit = 7 - x
            pixel = (
                ((bp0 >> bit) & 1) | (((bp1 >> bit) & 1) << 1) | (((bp2 >> bit) & 1) << 2) | (((bp3 >> bit) & 1) << 3)
            )
            row.append(pixel)
        tile.extend(row)

    return tile


def encode_4bpp_tile(tile_pixels: list[int]) -> bytes:
    """
    Encode an 8x8 tile to SNES 4bpp format.

    Args:
        tile_pixels: List of 64 pixel values (0-15)

    Returns:
        32 bytes of encoded tile data

    Raises:
        ValueError: If tile_pixels doesn't contain exactly 64 values
    """
    if len(tile_pixels) != PIXELS_PER_TILE:
        raise ValueError(f"Expected {PIXELS_PER_TILE} pixels, got {len(tile_pixels)}")

    output = bytearray(BYTES_PER_TILE_4BPP)

    for y in range(TILE_HEIGHT):
        bp0 = 0
        bp1 = 0
        bp2 = 0
        bp3 = 0

        # Encode each pixel in the row
        for x in range(TILE_WIDTH):
            pixel = tile_pixels[y * TILE_WIDTH + x] & 0x0F  # Ensure 4-bit value
            bp0 |= ((pixel & 1) >> 0) << (7 - x)
            bp1 |= ((pixel & 2) >> 1) << (7 - x)
            bp2 |= ((pixel & 4) >> 2) << (7 - x)
            bp3 |= ((pixel & 8) >> 3) << (7 - x)

        # Store bitplanes in SNES format
        output[y * 2] = bp0
        output[y * 2 + 1] = bp1
        output[TILE_BITPLANE_OFFSET + y * 2] = bp2
        output[TILE_BITPLANE_OFFSET + y * 2 + 1] = bp3

    return bytes(output)


def decode_tiles(data: bytes, num_tiles: int, start_offset: int = 0) -> list[list[int]]:
    """
    Decode multiple 4bpp tiles from data.

    Args:
        data: Raw tile data bytes
        num_tiles: Number of tiles to decode
        start_offset: Starting offset in the data

    Returns:
        List of decoded tiles (each tile is a list of 64 pixels)
    """
    tiles = []
    for i in range(num_tiles):
        offset = start_offset + (i * BYTES_PER_TILE_4BPP)
        if offset + BYTES_PER_TILE_4BPP <= len(data):
            tile = decode_4bpp_tile(data, offset)
            tiles.append(tile)
        else:
            break

    return tiles


def encode_tiles(tiles: list[list[int]]) -> bytes:
    """
    Encode multiple tiles to SNES 4bpp format.

    Args:
        tiles: List of tiles (each tile is a list of 64 pixels)

    Returns:
        Encoded tile data
    """
    output = bytearray()
    for tile in tiles:
        encoded = encode_4bpp_tile(tile)
        output.extend(encoded)

    return bytes(output)


def calculate_tile_grid_exact(width: int, height: int) -> tuple[int, int, int]:
    """
    Calculate tile grid dimensions using exact division (truncate).

    Use this for encoding: only count complete tiles that fit within dimensions.
    Partial tiles at edges are excluded.

    Args:
        width: Image width in pixels
        height: Image height in pixels

    Returns:
        Tuple of (tiles_x, tiles_y, total_tiles)
    """
    tiles_x = width // TILE_WIDTH
    tiles_y = height // TILE_HEIGHT
    return tiles_x, tiles_y, tiles_x * tiles_y


def calculate_tile_grid_padded(width: int, height: int) -> tuple[int, int, int]:
    """
    Calculate tile grid dimensions using ceiling division (round up).

    Use this for extraction: includes partial tiles at edges.
    Ensures all pixels are covered even if image isn't tile-aligned.

    Args:
        width: Image width in pixels
        height: Image height in pixels

    Returns:
        Tuple of (tiles_x, tiles_y, total_tiles)
    """
    tiles_x = (width + TILE_WIDTH - 1) // TILE_WIDTH
    tiles_y = (height + TILE_HEIGHT - 1) // TILE_HEIGHT
    return tiles_x, tiles_y, tiles_x * tiles_y


def calculate_dimensions_from_tile_data(data_size: int, tiles_per_row: int) -> tuple[int, int, int, int, int]:
    """
    Calculate sprite layout dimensions from tile data size.

    Args:
        data_size: Size of tile data in bytes
        tiles_per_row: Number of tiles per row in output image

    Returns:
        Tuple of (total_tiles, tiles_x, tiles_y, width_pixels, height_pixels)

    Raises:
        ValueError: If tiles_per_row is less than or equal to 0
    """
    if tiles_per_row <= 0:
        raise ValueError(f"tiles_per_row must be positive, got {tiles_per_row}")

    total_tiles = data_size // BYTES_PER_TILE_4BPP
    tiles_x = tiles_per_row
    tiles_y = (total_tiles + tiles_x - 1) // tiles_x  # Round up
    width = tiles_x * TILE_WIDTH
    height = tiles_y * TILE_HEIGHT
    return total_tiles, tiles_x, tiles_y, width, height
