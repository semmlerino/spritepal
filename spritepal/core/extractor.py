"""
Core sprite extraction functionality
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

if TYPE_CHECKING:
    import logging

from core.tile_utils import decode_4bpp_tile
from utils.constants import (
    BYTES_PER_TILE,
    DEFAULT_TILES_PER_ROW,
    PREVIEW_TILES_PER_ROW,
    TILE_HEIGHT,
    TILE_WIDTH,
    VRAM_SPRITE_OFFSET,
    VRAM_SPRITE_SIZE,
)
from utils.file_validator import FileValidator
from utils.logging_config import get_logger

logger: logging.Logger = get_logger(__name__)

class SpriteExtractor:
    """Handles sprite extraction from VRAM dumps"""

    def __init__(self) -> None:
        self.vram_data: bytes | None = None
        self.offset: int = VRAM_SPRITE_OFFSET
        self.size: int = VRAM_SPRITE_SIZE
        self.tiles_per_row: int = DEFAULT_TILES_PER_ROW
        logger.debug(f"SpriteExtractor initialized: offset=0x{self.offset:04X}, size={self.size}, tiles_per_row={self.tiles_per_row}")

    def load_vram(self, vram_path: str) -> None:
        """Load VRAM dump file with validation"""
        logger.info(f"Loading VRAM file: {vram_path}")

        # Validate file before loading
        result = FileValidator.validate_vram_file(vram_path)
        if not result.is_valid:
            logger.error(f"VRAM validation failed: {result.error_message}")
            raise ValueError(f"Invalid VRAM file: {result.error_message}")
        logger.debug("VRAM file validation passed")

        with Path(vram_path).open("rb") as f:
            self.vram_data = f.read()

        expected_size = 65536  # 64KB
        if len(self.vram_data) == expected_size:
            logger.info(f"Loaded standard 64KB VRAM dump from {vram_path}")
        else:
            logger.warning(f"Loaded non-standard VRAM dump: {len(self.vram_data)} bytes (expected {expected_size} bytes)")

    def extract_tiles(
        self, offset: int | None = None, size: int | None = None
    ) -> tuple[list[list[list[int]]], int]:
        """Extract tiles from VRAM data"""
        if self.vram_data is None:
            logger.error("Attempted to extract tiles without loading VRAM data")
            raise ValueError("VRAM data not loaded. Call load_vram() first.")

        if offset is None:
            offset = self.offset
            logger.debug(f"Using default offset: 0x{offset:04X}")
        if size is None:
            size = self.size
            logger.debug(f"Using default size: {size} bytes")

        logger.info(f"Extracting tiles from offset 0x{offset:04X}, size: {size} bytes")

        # Validate offset
        result = FileValidator.validate_offset(offset, len(self.vram_data))
        if not result.is_valid:
            logger.error(f"Invalid extraction offset: {result.error_message}")
            raise ValueError(f"Invalid offset: {result.error_message}")

        # Read sprite data from offset
        if offset + size > len(self.vram_data):
            old_size = size
            size = len(self.vram_data) - offset
            logger.warning(f"Adjusted extraction size from {old_size} to {size} bytes to fit VRAM bounds")

        sprite_data = self.vram_data[offset : offset + size]

        # Calculate number of tiles
        num_tiles = len(sprite_data) // BYTES_PER_TILE
        logger.info(f"Extracting {num_tiles} tiles from {len(sprite_data)} bytes of sprite data")

        # Extract each tile
        tiles: list[list[list[int]]] = []
        log_interval = 100  # Log progress every 100 tiles

        for tile_idx in range(num_tiles):
            tile_offset = tile_idx * BYTES_PER_TILE
            tile_data = sprite_data[tile_offset : tile_offset + BYTES_PER_TILE]

            # Decode 4bpp tile
            pixels = decode_4bpp_tile(tile_data)
            tiles.append(pixels)

            # Log progress at intervals
            if (tile_idx + 1) % log_interval == 0:
                logger.debug(f"Extracted {tile_idx + 1}/{num_tiles} tiles")

        logger.info(f"Successfully extracted {num_tiles} tiles")
        return tiles, num_tiles

    def create_grayscale_image(
        self, tiles: list[list[list[int]]], tiles_per_row: int | None = None
    ) -> Image.Image:
        """Create a grayscale image from tiles"""
        if tiles_per_row is None:
            tiles_per_row = self.tiles_per_row

        num_tiles = len(tiles)
        rows = (num_tiles + tiles_per_row - 1) // tiles_per_row

        # Create image
        img_width = tiles_per_row * TILE_WIDTH
        img_height = rows * TILE_HEIGHT

        logger.info(f"Creating grayscale image: {img_width}x{img_height} pixels ({num_tiles} tiles in {rows} rows, {tiles_per_row} tiles/row)")

        # Create image data as bytes for efficient processing
        img_data = bytearray(img_width * img_height)

        # Place tiles directly into byte array
        log_interval = 500  # Log progress every 500 tiles for performance

        for tile_idx, pixels in enumerate(tiles):
            tile_x = (tile_idx % tiles_per_row) * TILE_WIDTH
            tile_y = (tile_idx // tiles_per_row) * TILE_HEIGHT

            for y, row in enumerate(pixels):
                row_offset = (tile_y + y) * img_width + tile_x
                # Copy entire row at once
                img_data[row_offset : row_offset + TILE_WIDTH] = row

            if (tile_idx + 1) % log_interval == 0:
                logger.debug(f"Placed {tile_idx + 1}/{num_tiles} tiles into image")

        # Create image from bytes
        img = Image.frombytes("P", (img_width, img_height), bytes(img_data))

        # Set grayscale palette
        grayscale_palette = []
        for i in range(256):
            gray = (i * 255) // 15 if i < 16 else 0
            grayscale_palette.extend([gray, gray, gray])
        img.putpalette(grayscale_palette)
        logger.debug("Applied grayscale palette (16 shades mapped to 0-255)")

        logger.info(f"Grayscale image created successfully: {img_width}x{img_height} pixels, mode={img.mode}")
        return img

    def extract_sprites_grayscale(
        self,
        vram_path: str,
        output_path: str,
        offset: int | None = None,
        size: int | None = None,
        tiles_per_row: int | None = None,
    ) -> tuple[Image.Image, int]:
        """Extract sprites as grayscale image"""
        logger.info("=" * 60)
        logger.info(f"Starting sprite extraction: {vram_path} -> {output_path}")
        logger.debug(f"Parameters: offset={offset}, size={size}, tiles_per_row={tiles_per_row}")

        # Load VRAM
        self.load_vram(vram_path)

        # Extract tiles
        tiles, num_tiles = self.extract_tiles(offset, size)

        # Create image
        img = self.create_grayscale_image(tiles, tiles_per_row)

        # Save
        img.save(output_path)
        logger.info(f"Saved grayscale sprite image to {output_path} ({img.size[0]}x{img.size[1]} pixels, {num_tiles} tiles)")
        logger.info("=" * 60)

        return img, num_tiles
