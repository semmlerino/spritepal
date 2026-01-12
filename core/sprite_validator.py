"""
Enhanced sprite validation for SpritePal
Provides comprehensive validation for sprites before injection
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import cast

from PIL import Image

from utils.constants import BYTES_PER_TILE
from utils.logging_config import get_logger

logger = get_logger(__name__)


class SpriteValidator:
    """Enhanced sprite validation with detailed error reporting"""

    @staticmethod
    def validate_sprite_comprehensive(
        sprite_path: str, metadata_path: str | None = None
    ) -> tuple[bool, list[str], list[str]]:
        """
        Perform comprehensive sprite validation.

        Args:
            sprite_path: Path to sprite PNG file
            metadata_path: path to metadata JSON

        Returns:
            Tuple of (is_valid, errors, warnings)
        """
        errors: list[str] = []
        warnings: list[str] = []

        if not Path(sprite_path).exists():
            errors.append(f"Sprite file not found: {sprite_path}")
            return False, errors, warnings

        try:
            with Image.open(sprite_path) as img:
                format_errors, format_warnings = SpriteValidator._validate_format(img)
                errors.extend(format_errors)
                warnings.extend(format_warnings)

                dim_errors, dim_warnings = SpriteValidator._validate_dimensions(img)
                errors.extend(dim_errors)
                warnings.extend(dim_warnings)

                color_errors, color_warnings = SpriteValidator._validate_colors(img)
                errors.extend(color_errors)
                warnings.extend(color_warnings)

                if metadata_path and Path(metadata_path).exists():
                    meta_errors, meta_warnings = SpriteValidator._validate_against_metadata(img, metadata_path)
                    errors.extend(meta_errors)
                    warnings.extend(meta_warnings)

        except Exception as e:
            errors.append(f"Failed to load sprite: {e}")

        return len(errors) == 0, errors, warnings

    @staticmethod
    def _validate_format(img: Image.Image) -> tuple[list[str], list[str]]:
        """Validate image format"""
        errors: list[str] = []
        warnings: list[str] = []

        if img.mode not in ["P", "L"]:
            errors.append(f"Image must be in indexed (P) or grayscale (L) mode, found: {img.mode}")

        if img.mode == "P" and "transparency" in img.info:
            warnings.append("Image has transparency which will be ignored")

        return errors, warnings

    @staticmethod
    def _validate_dimensions(img: Image.Image) -> tuple[list[str], list[str]]:
        """Validate image dimensions"""
        errors: list[str] = []
        warnings: list[str] = []

        width, height = img.size

        # SNES tiles are 8x8 pixels
        if width % 8 != 0:
            errors.append(f"Width must be a multiple of 8 (found: {width})")
        if height % 8 != 0:
            errors.append(f"Height must be a multiple of 8 (found: {height})")

        max_tiles = 1024
        total_tiles = (width // 8) * (height // 8)

        if total_tiles > max_tiles:
            warnings.append(
                f"Sprite sheet has {total_tiles} tiles, which is quite large (max recommended: {max_tiles})"
            )

        if width > 256 or height > 256:
            warnings.append(f"Sprite dimensions ({width}x{height}) are larger than typical (256x256)")

        return errors, warnings

    @staticmethod
    def _validate_colors(img: Image.Image) -> tuple[list[str], list[str]]:
        """Validate color usage"""
        errors: list[str] = []
        warnings: list[str] = []

        if img.mode == "P":
            # Cast needed: PIL's ImagingCore is iterable at runtime but not typed as such
            pixels = list(cast(Iterable[int], img.getdata()))
            unique_colors = set(pixels)

            # SNES 4bpp sprites support max 16 colors (indices 0-15)
            if len(unique_colors) > 16:
                errors.append(f"Image uses {len(unique_colors)} colors, maximum is 16")

            max_index = max(unique_colors) if unique_colors else 0
            if max_index > 15:
                errors.append(f"Image uses color index {max_index}, maximum allowed is 15")

            # Index 0 is typically transparent in SNES sprites
            if 0 in unique_colors:
                # Count how many pixels use index 0
                transparent_pixels = pixels.count(0)
                total_pixels = len(pixels)
                transparency_percent = (transparent_pixels / total_pixels) * 100

                if transparency_percent > 50:
                    warnings.append(f"Image has {transparency_percent:.1f}% transparent pixels (index 0)")

        elif img.mode == "L":
            # Grayscale values should map to 16 discrete levels (0, 17, 34, ..., 255)
            # to match SNES 4bpp color depth
            # Cast needed: PIL's ImagingCore is iterable at runtime but not typed as such
            pixels = list(cast(Iterable[int], img.getdata()))
            unique_values = set(pixels)

            non_standard_values = []
            for val in unique_values:
                expected_index = round(val / 17)
                expected_value = expected_index * 17
                if abs(val - expected_value) > 1:
                    non_standard_values.append(val)

            if non_standard_values:
                warnings.append(f"Image contains non-standard grayscale values: {sorted(non_standard_values)[:5]}...")

        return errors, warnings

    @staticmethod
    def _validate_against_metadata(img: Image.Image, metadata_path: str) -> tuple[list[str], list[str]]:
        """Validate sprite against its metadata"""
        errors: list[str] = []
        warnings: list[str] = []

        try:
            with Path(metadata_path).open() as f:
                metadata = json.load(f)

            if "extraction" in metadata:
                extraction_info = metadata["extraction"]

                if "tile_count" in extraction_info:
                    expected_tiles = extraction_info["tile_count"]
                    width, height = img.size
                    actual_tiles = (width // 8) * (height // 8)

                    if actual_tiles != expected_tiles:
                        warnings.append(f"Tile count mismatch: expected {expected_tiles}, found {actual_tiles}")

        except Exception as e:
            warnings.append(f"Failed to validate against metadata: {e}")

        return errors, warnings

    @staticmethod
    def estimate_compressed_size(sprite_path: str) -> tuple[int, int]:
        """
        Estimate the uncompressed and potential compressed size of a sprite.

        Returns:
            Tuple of (uncompressed_size, estimated_compressed_size)
        """
        try:
            with Image.open(sprite_path) as img:
                width, height = img.size

                # Calculate uncompressed size
                num_tiles = (width // 8) * (height // 8)
                uncompressed_size = num_tiles * BYTES_PER_TILE

                # Estimate compressed size (very rough estimate)
                # HAL compression typically achieves 40-60% compression
                # But it varies greatly based on sprite complexity
                # Cast needed: PIL's ImagingCore is iterable at runtime but not typed as such
                pixels = list(cast(Iterable[int], img.getdata()))
                unique_colors = len(set(pixels))

                # More colors = less compression typically
                if unique_colors <= 4:
                    compression_ratio = 0.3  # 70% compression
                elif unique_colors <= 8:
                    compression_ratio = 0.5  # 50% compression
                else:
                    compression_ratio = 0.7  # 30% compression

                estimated_compressed = int(uncompressed_size * compression_ratio)

            return uncompressed_size, estimated_compressed

        except Exception:
            logger.exception("Failed to estimate size")
            return 0, 0

    @staticmethod
    def check_sprite_compatibility(sprite1_path: str, sprite2_path: str) -> tuple[bool, list[str]]:
        """
        Check if two sprites are compatible (e.g., for swapping).

        Returns:
            Tuple of (compatible, reasons)
        """
        reasons = []

        try:
            with Image.open(sprite1_path) as img1, Image.open(sprite2_path) as img2:
                # Check dimensions
                if img1.size != img2.size:
                    reasons.append(f"Different dimensions: {img1.size} vs {img2.size}")

                # Check mode
                if img1.mode != img2.mode:
                    reasons.append(f"Different modes: {img1.mode} vs {img2.mode}")

                # Check tile count
                tiles1 = (img1.width // 8) * (img1.height // 8)
                tiles2 = (img2.width // 8) * (img2.height // 8)

                if tiles1 != tiles2:
                    reasons.append(f"Different tile counts: {tiles1} vs {tiles2}")

        except Exception as e:
            reasons.append(f"Failed to compare sprites: {e}")

        return len(reasons) == 0, reasons
