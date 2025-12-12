"""
Sprite injection functionality for SpritePal
Handles reinsertion of edited sprites back into VRAM
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from PIL import Image

from utils.constants import (
    IMAGE_DIMENSION_MULTIPLE,
    PIXEL_MASK_4BIT,
    TILE_HEIGHT,
    TILE_WIDTH,
    VRAM_SPRITE_OFFSET,
)
from utils.file_validator import atomic_write
from utils.logging_config import get_logger

logger = get_logger(__name__)

def encode_4bpp_tile(tile_pixels: list[int]) -> bytes:
    """
    Encode an 8x8 tile to SNES 4bpp format.
    Adapted from sprite_editor/tile_utils.py
    """
    if len(tile_pixels) != 64:
        logger.error(f"Invalid tile size: expected 64 pixels, got {len(tile_pixels)}")
        raise ValueError(f"Expected 64 pixels, got {len(tile_pixels)}")

    logger.debug("Encoding 8x8 tile to 4bpp format")

    output = bytearray(32)

    for y in range(8):
        bp0 = 0
        bp1 = 0
        bp2 = 0
        bp3 = 0

        # Encode each pixel in the row
        for x in range(8):
            pixel = tile_pixels[y * 8 + x] & PIXEL_MASK_4BIT  # Ensure 4-bit value
            bp0 |= ((pixel & 1) >> 0) << (7 - x)
            bp1 |= ((pixel & 2) >> 1) << (7 - x)
            bp2 |= ((pixel & 4) >> 2) << (7 - x)
            bp3 |= ((pixel & 8) >> 3) << (7 - x)

        # Store bitplanes in SNES format
        output[y * 2] = bp0
        output[y * 2 + 1] = bp1
        output[16 + y * 2] = bp2
        output[16 + y * 2 + 1] = bp3

    return bytes(output)

class SpriteInjector:
    """Handles sprite injection back to VRAM"""

    def __init__(self) -> None:
        self.metadata: dict[str, Any] | None = None
        self.sprite_path: str | None = None
        self.vram_data: bytearray | None = None
        logger.debug("SpriteInjector initialized")

    def load_metadata(self, metadata_path: str) -> dict[str, Any]:
        """Load extraction metadata from JSON file"""
        logger.debug(f"Loading metadata from {metadata_path}")
        with Path(metadata_path).open() as f:
            self.metadata = json.load(f)
        if self.metadata:
            logger.info(f"Loaded metadata with {len(self.metadata)} entries")
        else:
            logger.warning("Loaded empty metadata")
            self.metadata = {}
        return self.metadata

    def validate_sprite(self, sprite_path: str) -> tuple[bool, str]:
        """Validate sprite file format and dimensions"""
        logger.debug(f"Validating sprite: {sprite_path}")
        try:
            with Image.open(sprite_path) as img:
                logger.debug(f"Sprite info: {img.size} pixels, mode={img.mode}")

                # Check if indexed or grayscale mode
                if img.mode not in ["P", "L"]:
                    logger.error(f"Invalid image mode: {img.mode}, expected P (indexed) or L (grayscale)")
                    return (
                        False,
                        f"Image must be in indexed (P) or grayscale (L) mode (found {img.mode})",
                    )

                # Check dimensions are multiples of 8
                width, height = img.size
                if width % IMAGE_DIMENSION_MULTIPLE != 0 or height % IMAGE_DIMENSION_MULTIPLE != 0:
                    logger.error(f"Invalid dimensions: {width}x{height} (not multiples of 8)")
                    return (
                        False,
                        f"Image dimensions must be multiples of {IMAGE_DIMENSION_MULTIPLE} (found {width}x{height})",
                    )

                # Check color count based on mode
                img_mode = img.mode  # Capture before context exits
                if img.mode == "P":
                    # Indexed mode - count actual unique colors used
                    # Cast needed: PIL's ImagingCore is iterable at runtime but not typed as such
                    unique_colors = len(set(cast(Any, img.getdata())))
                    logger.debug(f"Indexed mode with {unique_colors} unique colors")
                    if unique_colors > 16:
                        logger.error(f"Too many colors: {unique_colors} (max 16)")
                        return False, f"Image has too many colors ({unique_colors}, max 16)"
                    logger.debug(f"Palette validation passed: {unique_colors} colors <= 16")
                elif img.mode == "L":
                    # Grayscale mode - verify values are valid (0-255)
                    # Cast needed: PIL's ImagingCore is iterable at runtime but not typed as such
                    pixels = list(cast(Any, img.getdata()))
                    max_val = max(pixels) if pixels else 0
                    if max_val > 255:
                        logger.error(f"Invalid grayscale value: {max_val}")
                        return False, f"Invalid grayscale values (max: {max_val})"
                    logger.debug(f"Grayscale validation passed: max value {max_val} <= 255")

                self.sprite_path = sprite_path
                logger.info(f"Sprite validation successful: {width}x{height}, mode={img_mode}")
                return True, "Sprite validation successful"

        except Exception as e:
            logger.exception("Sprite validation failed")
            return False, f"Error validating sprite: {e!s}"

    def convert_png_to_4bpp(self, png_path: str) -> bytes:
        """Convert PNG to SNES 4bpp tile data"""
        logger.info(f"Converting PNG to 4bpp: {png_path}")

        # Extract all needed data from image within context manager
        with Image.open(png_path) as img:
            # Handle different image modes
            if img.mode == "L":
                # Grayscale mode - likely from ROM extraction
                # Convert grayscale values back to palette indices
                # Cast needed: PIL's ImagingCore is iterable at runtime but not typed as such
                pixels = list(cast(Any, img.getdata()))
                original_max = max(pixels) if pixels else 0
                # Divide by 17 to get original 4-bit indices (0-15)
                pixels = [min(15, p // 17) for p in pixels]
                logger.debug(f"Converting grayscale to palette indices: max grayscale={original_max}, max index={max(pixels) if pixels else 0}")
            elif img.mode == "P":
                # Already indexed - use as-is
                # Cast needed: PIL's ImagingCore is iterable at runtime but not typed as such
                pixels = list(cast(Any, img.getdata()))
                max_index = max(pixels) if pixels else 0
                logger.debug(f"Using indexed palette directly: max index={max_index}")

                # Validate palette indices for 4-bit compatibility (Issue 7 fix)
                if max_index > 15:
                    raise ValueError(
                        f"PNG palette has indices up to {max_index}, but SNES sprites "
                        f"only support 16 colors (indices 0-15). Please reduce the "
                        f"image palette to 16 colors or use grayscale mode."
                    )
            else:
                # Convert to indexed mode
                logger.warning(f"Converting {img.mode} to indexed mode - may lose color information")
                converted = img.convert("P", palette=Image.Palette.ADAPTIVE, colors=16)
                # Cast needed: PIL's ImagingCore is iterable at runtime but not typed as such
                pixels = list(cast(Any, converted.getdata()))

            width, height = img.size
        tiles_x = width // TILE_WIDTH
        tiles_y = height // TILE_HEIGHT
        total_tiles = tiles_x * tiles_y
        logger.debug(f"Processing {total_tiles} tiles ({tiles_x}x{tiles_y})")

        # Process tiles
        output_data = bytearray()
        processed_tiles = 0

        for tile_y in range(tiles_y):
            for tile_x in range(tiles_x):
                # Extract 8x8 tile
                tile_pixels = []
                for y in range(TILE_HEIGHT):
                    for x in range(TILE_WIDTH):
                        pixel_x = tile_x * TILE_WIDTH + x
                        pixel_y = tile_y * TILE_HEIGHT + y
                        pixel_index = pixel_y * width + pixel_x

                        if pixel_index < len(pixels):
                            tile_pixels.append(pixels[pixel_index] & PIXEL_MASK_4BIT)
                        else:
                            tile_pixels.append(0)

                # Encode tile
                tile_data = encode_4bpp_tile(tile_pixels)
                output_data.extend(tile_data)
                processed_tiles += 1

                if processed_tiles % 100 == 0:
                    logger.debug(f"Processed {processed_tiles}/{total_tiles} tiles")

        logger.info(f"Converted {total_tiles} tiles to {len(output_data)} bytes of 4bpp tile data")
        return bytes(output_data)

    def inject_sprite(
        self,
        sprite_path: str,
        vram_path: str,
        output_path: str,
        offset: int | None = None,
    ) -> tuple[bool, str]:
        """Inject sprite into VRAM at specified offset"""
        logger.info(f"Starting sprite injection: {sprite_path} -> {output_path}")
        try:
            # Use offset from metadata if not provided
            if offset is None and self.metadata and "extraction" in self.metadata:
                offset_str = self.metadata["extraction"].get("vram_offset", hex(VRAM_SPRITE_OFFSET))
                offset = int(offset_str, 16)
                logger.info(f"Using offset from metadata: 0x{offset:04X}")
            elif offset is None:
                offset = VRAM_SPRITE_OFFSET
                logger.info(f"Using default offset: 0x{offset:04X}")
            else:
                logger.info(f"Using provided offset: 0x{offset:04X}")

            # Convert PNG to 4bpp
            tile_data = self.convert_png_to_4bpp(sprite_path)

            # Read original VRAM
            logger.debug(f"Loading VRAM from {vram_path}")
            with Path(vram_path).open("rb") as f:
                self.vram_data = bytearray(f.read())
            logger.debug(f"Loaded {len(self.vram_data)} bytes of VRAM data")

            # Validate offset
            if offset + len(tile_data) > len(self.vram_data):
                logger.error(f"Tile data would exceed VRAM bounds: offset=0x{offset:04X}, size={len(tile_data)}, VRAM size={len(self.vram_data)}")
                return (
                    False,
                    f"Tile data ({len(tile_data)} bytes) would exceed VRAM size at offset 0x{offset:04X}",
                )

            # Inject tile data
            logger.info(f"Injecting {len(tile_data)} bytes at offset 0x{offset:04X}")
            original_data = self.vram_data[offset : offset + len(tile_data)]
            self.vram_data[offset : offset + len(tile_data)] = tile_data

            # Log details about the injection
            bytes_changed = sum(1 for i in range(len(tile_data)) if original_data[i] != tile_data[i])
            logger.debug(f"Modified {bytes_changed}/{len(tile_data)} bytes in VRAM")

            # Write modified VRAM atomically (prevents corruption on crash/power loss)
            atomic_write(output_path, bytes(self.vram_data))
            logger.info(f"Successfully wrote modified VRAM to {output_path}")

            return (
                True,
                f"Successfully injected {len(tile_data)} bytes at offset 0x{offset:04X}",
            )

        except Exception as e:
            logger.exception("Sprite injection failed")
            return False, f"Error injecting sprite: {e!s}"

    def get_extraction_info(self) -> dict[str, Any] | None:
        """Get extraction information from metadata"""
        if self.metadata and "extraction" in self.metadata:
            extraction_info = self.metadata["extraction"]
            return extraction_info if isinstance(extraction_info, dict) else None
        return None

