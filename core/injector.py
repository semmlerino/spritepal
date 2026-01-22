"""
Sprite injection functionality for SpritePal
Handles reinsertion of edited sprites back into VRAM
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import cast

from PIL import Image

from core.types import ExtractionMetadata
from utils.constants import (
    IMAGE_DIMENSION_MULTIPLE,
    VRAM_SPRITE_OFFSET,
)
from utils.file_validator import atomic_write
from utils.logging_config import get_logger

logger = get_logger(__name__)


class SpriteInjector:
    """Handles sprite injection back to VRAM"""

    def __init__(self) -> None:
        self.metadata: ExtractionMetadata | None = None
        self.sprite_path: str | None = None
        self.vram_data: bytearray | None = None
        logger.debug("SpriteInjector initialized")

    def load_metadata(self, metadata_path: str) -> ExtractionMetadata:
        """Load extraction metadata from JSON file"""
        logger.debug(f"Loading metadata from {metadata_path}")
        with Path(metadata_path).open() as f:
            data = json.load(f)
            self.metadata = cast(ExtractionMetadata, data)

        if self.metadata:
            logger.info(f"Loaded metadata with {len(self.metadata)} entries")
        else:
            logger.warning("Loaded empty metadata")
            self.metadata = cast(
                ExtractionMetadata,
                {
                    "source_type": "vram",
                    "tile_count": 0,
                    "extraction_size": 0,
                    "palette_count": 0,
                },
            )
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
                    pixels = list(cast(Iterable[int], img.getdata()))
                    unique_colors = len(set(pixels))
                    logger.debug(f"Indexed mode with {unique_colors} unique colors")
                    if unique_colors > 16:
                        logger.error(f"Too many colors: {unique_colors} (max 16)")
                        return False, f"Image has too many colors ({unique_colors}, max 16)"

                    # Validate palette indices for 4bpp compatibility (must be 0-15)
                    max_index = max(pixels) if pixels else 0
                    if max_index > 15:
                        logger.error(f"PNG palette indices exceed 4bpp limit: max index {max_index} (must be 0-15)")
                        return (
                            False,
                            f"PNG has palette indices up to {max_index}, which exceeds SNES 4bpp limit (0-15). "
                            "Please re-save the PNG with a palette of 16 colors or fewer.",
                        )

                    logger.debug(f"Palette validation passed: {unique_colors} colors, max index {max_index}")
                elif img.mode == "L":
                    # Grayscale mode - verify values are valid (0-255)
                    # Cast needed: PIL's ImagingCore is iterable at runtime but not typed as such
                    pixels = list(cast(Iterable[int], img.getdata()))
                    max_val = max(pixels) if pixels else 0
                    if max_val > 255:
                        logger.error(f"Invalid grayscale value: {max_val}")
                        return False, f"Invalid grayscale values (max: {max_val})"

                    # Warn about precision loss for grayscale with values > 15
                    if max_val > 15:
                        logger.warning(
                            f"Grayscale PNG will be quantized (max {max_val} → index {max_val // 17}). "
                            "For lossless import, use indexed PNG with 16-color palette."
                        )

                    logger.debug(f"Grayscale validation passed: max value {max_val} <= 255")

                self.sprite_path = sprite_path
                logger.info(f"Sprite validation successful: {width}x{height}, mode={img_mode}")
                return True, "Sprite validation successful"

        except Exception as e:
            logger.exception("Sprite validation failed")
            return False, f"Error validating sprite: {e!s}"

    def convert_png_to_4bpp(self, png_path: str) -> bytes:
        """Convert PNG to SNES 4bpp tile data.

        Delegates to the centralized png_conversion service with permissive mode
        to support grayscale and RGB/RGBA images (which are converted to grayscale).
        """
        from core.services.png_conversion import convert_png_to_4bpp

        tile_data, _ = convert_png_to_4bpp(png_path, mode_policy="permissive")
        return tile_data

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
                logger.error(
                    f"Tile data would exceed VRAM bounds: offset=0x{offset:04X}, size={len(tile_data)}, VRAM size={len(self.vram_data)}"
                )
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
            # FIX #5: Clear VRAM buffer on error to free memory
            self.vram_data = bytearray()
            logger.exception("Sprite injection failed")
            return False, f"Error injecting sprite: {e!s}"
