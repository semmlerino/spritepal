"""
Core sprite extraction functionality
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image

if TYPE_CHECKING:
    import logging
else:
    pass

from utils.constants import (
    BYTES_PER_TILE,
    DEFAULT_TILES_PER_ROW,
    PREVIEW_TILES_PER_ROW,
    TILE_HEIGHT,
    TILE_WIDTH,
    VRAM_SPRITE_OFFSET,
    VRAM_SPRITE_SIZE,
)
from utils.logging_config import get_logger
from utils.validation import validate_offset, validate_vram_file

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
        is_valid, error_msg = validate_vram_file(vram_path)
        if not is_valid:
            logger.error(f"VRAM validation failed: {error_msg}")
            raise ValueError(f"Invalid VRAM file: {error_msg}")
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
        is_valid, error_msg = validate_offset(offset, len(self.vram_data))
        if not is_valid:
            logger.error(f"Invalid extraction offset: {error_msg}")
            raise ValueError(f"Invalid offset: {error_msg}")

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
            pixels = self._decode_4bpp_tile(tile_data)
            tiles.append(pixels)

            # Log progress at intervals
            if (tile_idx + 1) % log_interval == 0:
                logger.debug(f"Extracted {tile_idx + 1}/{num_tiles} tiles")

        logger.info(f"Successfully extracted {num_tiles} tiles")
        return tiles, num_tiles

    def _decode_4bpp_tile(self, tile_data: bytes) -> list[list[int]]:
        """Decode a 4bpp SNES tile to pixel indices"""
        if len(tile_data) < BYTES_PER_TILE:
            logger.warning(f"Tile data is incomplete: {len(tile_data)} bytes (expected {BYTES_PER_TILE})")

        pixels: list[list[int]] = []

        # 4bpp SNES format: 32 bytes per 8x8 tile
        for y in range(8):
            row: list[int] = []
            # Get the 4 bytes for this row
            b0 = tile_data[y * 2] if y * 2 < len(tile_data) else 0
            b1 = tile_data[y * 2 + 1] if y * 2 + 1 < len(tile_data) else 0
            b2 = tile_data[y * 2 + 16] if y * 2 + 16 < len(tile_data) else 0
            b3 = tile_data[y * 2 + 17] if y * 2 + 17 < len(tile_data) else 0

            # Decode each pixel in the row
            for x in range(8):
                bit = 7 - x
                pixel = 0
                if b0 & (1 << bit):
                    pixel |= 1
                if b1 & (1 << bit):
                    pixel |= 2
                if b2 & (1 << bit):
                    pixel |= 4
                if b3 & (1 << bit):
                    pixel |= 8
                row.append(pixel)
            pixels.append(row)

        return pixels

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

    def get_preview_image(
        self,
        vram_path: str,
        offset: int | None = None,
        size: int | None = None,
        max_tiles: int = 64,
    ) -> tuple[Image.Image, int]:
        """Get a preview image of the sprites"""
        logger.debug(f"Generating preview image with max {max_tiles} tiles")

        # Load VRAM
        self.load_vram(vram_path)

        # Extract limited tiles for preview
        tiles, num_tiles = self.extract_tiles(offset, size)

        # Limit tiles for preview
        if len(tiles) > max_tiles:
            logger.debug(f"Limiting preview to {max_tiles} tiles (from {len(tiles)})")
            tiles = tiles[:max_tiles]

        # Use smaller grid for preview
        preview_tiles_per_row = min(PREVIEW_TILES_PER_ROW, self.tiles_per_row)
        logger.debug(f"Using {preview_tiles_per_row} tiles per row for preview")

        # Create preview image
        img = self.create_grayscale_image(tiles, preview_tiles_per_row)
        logger.debug(f"Preview image created: {img.size[0]}x{img.size[1]} pixels")

        return img, num_tiles

    def extract_sprite(
        self,
        vram_path: str,
        output_base: str,
        cgram_path: str | None = None,
        oam_path: str | None = None,
        vram_offset: int | None = None,
        create_grayscale: bool = True,
        create_metadata: bool = True,
        create_palette_files: bool = True,
    ) -> dict[str, Any]:
        """Extract sprite from VRAM with full metadata.

        Wrapper providing the interface expected by CoreOperationsManager.
        Delegates to extract_sprites_grayscale for core functionality.

        Args:
            vram_path: Path to VRAM dump file
            output_base: Base path for output files (without extension)
            cgram_path: Path to CGRAM dump file (for palette data)
            oam_path: Path to OAM dump file (for sprite attributes)
            vram_offset: Offset in VRAM to start extraction
            create_grayscale: Whether to create grayscale output
            create_metadata: Whether to create metadata file
            create_palette_files: Whether to create palette files

        Returns:
            Dict with extraction results including image, tile_count, output_path
        """
        logger.info(f"extract_sprite called: vram={vram_path}, output_base={output_base}")
        logger.debug(
            f"Options: cgram={cgram_path}, oam={oam_path}, "
            f"offset={vram_offset}, grayscale={create_grayscale}, "
            f"metadata={create_metadata}, palette_files={create_palette_files}"
        )

        output_path = f"{output_base}.png"
        image, tile_count = self.extract_sprites_grayscale(
            vram_path, output_path, offset=vram_offset
        )

        result: dict[str, Any] = {
            "success": True,
            "image": image,
            "tile_count": tile_count,
            "output_path": output_path,
        }

        # Store optional paths for future use when palette/metadata
        # features are implemented
        if cgram_path:
            result["cgram_path"] = cgram_path
            logger.debug(f"CGRAM path stored: {cgram_path}")
        if oam_path:
            result["oam_path"] = oam_path
            logger.debug(f"OAM path stored: {oam_path}")

        logger.info(f"extract_sprite completed: {tile_count} tiles extracted")
        return result
