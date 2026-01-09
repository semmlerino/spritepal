"""
ROM palette extraction functionality for SpritePal
Extracts sprite palettes directly from ROM files
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from utils.logging_config import get_logger
from utils.rom_utils import detect_smc_offset_from_size

logger = get_logger(__name__)


class ROMPaletteExtractor:
    """Extracts palettes directly from ROM files"""

    def __init__(self) -> None:
        """Initialize ROM palette extractor"""

    def extract_palettes_from_rom(
        self,
        rom_path: str,
        palette_offset: int,
        palette_indices: list[int],
        output_base: str,
    ) -> list[str]:
        """
        Extract specific palettes from ROM.

        Args:
            rom_path: Path to ROM file
            palette_offset: Offset in ROM where palette data starts
            palette_indices: List of palette indices to extract (0-15)
            output_base: Base name for output palette files

        Returns:
            List of created palette file paths
        """
        created_files = []

        try:
            with Path(rom_path).open("rb") as f:
                # Detect SMC header and adjust offset
                file_size = f.seek(0, 2)
                smc_offset = detect_smc_offset_from_size(file_size)
                file_offset = palette_offset + smc_offset
                if smc_offset > 0:
                    logger.debug(
                        f"Adjusting for {smc_offset}-byte SMC header: 0x{palette_offset:X} -> 0x{file_offset:X}"
                    )

                # Seek to palette offset (adjusted for SMC header)
                f.seek(file_offset)

                # Read all palette data (256 colors * 2 bytes each = 512 bytes)
                palette_data = f.read(512)

            if len(palette_data) < 512:
                logger.warning(f"Insufficient palette data at offset 0x{palette_offset:X}")
                return created_files

            # Process each requested palette
            for palette_idx in palette_indices:
                if palette_idx < 0 or palette_idx > 15:
                    logger.warning(f"Invalid palette index: {palette_idx}")
                    continue

                # Extract 16 colors for this palette
                palette_colors = self._extract_palette_colors(palette_data, palette_idx)

                # Create palette file
                palette_path = f"{output_base}_pal{palette_idx}.pal.json"
                palette_json = {
                    "name": f"Palette {palette_idx}",
                    "colors": palette_colors,
                }

                with Path(palette_path).open("w") as f:
                    json.dump(palette_json, f, indent=2)

                created_files.append(palette_path)
                logger.info(f"Extracted palette {palette_idx} to {Path(palette_path).name}")

        except OSError as e:
            logger.warning(f"Failed to extract palettes from ROM: {e}")

        return created_files

    def _extract_palette_colors(self, palette_data: bytes, palette_idx: int) -> list[list[int]]:
        """
        Extract 16 colors for a specific palette.

        Args:
            palette_data: Raw palette data (512 bytes)
            palette_idx: Palette index (0-15)

        Returns:
            List of 16 RGB color tuples
        """
        colors = []

        # Each palette has 16 colors, each color is 2 bytes (BGR555 format)
        palette_start = palette_idx * 16 * 2

        for color_idx in range(16):
            offset = palette_start + (color_idx * 2)

            # Read 2 bytes as little-endian BGR555
            if offset + 1 < len(palette_data):
                low_byte = palette_data[offset]
                high_byte = palette_data[offset + 1]
                bgr555 = (high_byte << 8) | low_byte

                # Convert BGR555 to RGB888
                b = (bgr555 & 0x7C00) >> 10
                g = (bgr555 & 0x03E0) >> 5
                r = bgr555 & 0x001F

                # Scale from 5-bit to 8-bit using standard SNES formula
                # This gives 248 for max value (31), not 255, but is the standard
                r = (r << 3) | (r >> 2)
                g = (g << 3) | (g >> 2)
                b = (b << 3) | (b >> 2)

                colors.append([r, g, b])
            else:
                # Default to black if data is missing
                colors.append([0, 0, 0])

        return colors

    def get_palette_config_from_sprite_config(
        self,
        game_config: Mapping[str, Any],  # pyright: ignore[reportExplicitAny] - JSON config needs nested .get() calls
        sprite_name: str,
    ) -> tuple[int | None, list[int] | None]:
        """
        Get palette offset and indices for a specific sprite.

        Falls back to global palette offset with default sprite palette indices (8-15)
        for manual offset extractions (sprite names like "manual_0x...").

        Args:
            game_config: Game configuration from sprite_locations.json
            sprite_name: Name of the sprite

        Returns:
            Tuple of (palette_offset, palette_indices) or (None, None) if not found
        """
        # Get global palette offset for the game
        palette_info = game_config.get("palettes", {})
        palette_offset_raw = palette_info.get("offset", None)
        palette_offset: int | None = None

        if palette_offset_raw and isinstance(palette_offset_raw, str):
            palette_offset = (
                int(palette_offset_raw, 16)
                if palette_offset_raw.startswith("0x")
                else int(palette_offset_raw)
            )
        elif isinstance(palette_offset_raw, int):
            palette_offset = palette_offset_raw

        # Get sprite-specific palette indices
        sprites = game_config.get("sprites", {})
        sprite_info = sprites.get(sprite_name, {})
        palette_indices = sprite_info.get("palette_indices", [])

        # Return sprite-specific config if available
        if palette_offset and palette_indices:
            return palette_offset, palette_indices

        # Fall back to default sprite palette indices (8-15) for manual extractions
        # These are the standard SNES sprite palettes
        if palette_offset:
            default_indices = list(range(8, 16))  # Palettes 8-15 for sprites
            return palette_offset, default_indices

        return None, None

    def extract_palette_range(
        self, rom_path: str, palette_offset: int, start_idx: int, end_idx: int
    ) -> dict[int, list[tuple[int, int, int]]]:
        """
        Extract a range of palettes from ROM.

        Args:
            rom_path: Path to ROM file
            palette_offset: Offset in ROM where palette data starts
            start_idx: Starting palette index (inclusive)
            end_idx: Ending palette index (inclusive)

        Returns:
            Dictionary mapping palette index to list of 16 RGB tuples
        """
        palettes: dict[int, list[tuple[int, int, int]]] = {}

        try:
            with Path(rom_path).open("rb") as f:
                # Detect SMC header and adjust offset
                file_size = f.seek(0, 2)
                smc_offset = detect_smc_offset_from_size(file_size)
                file_offset = palette_offset + smc_offset
                if smc_offset > 0:
                    logger.debug(
                        f"Adjusting for {smc_offset}-byte SMC header: 0x{palette_offset:X} -> 0x{file_offset:X}"
                    )

                f.seek(file_offset)
                palette_data = f.read(512)

            for idx in range(start_idx, end_idx + 1):
                if 0 <= idx <= 15:
                    colors_list = self._extract_palette_colors(palette_data, idx)
                    # Convert list of lists to list of tuples for consistency
                    palettes[idx] = [tuple(c) for c in colors_list]

        except OSError as e:
            logger.warning(f"Failed to extract palette range: {e}")

        return palettes

    def extract_palette_colors_from_rom(
        self, rom_path: str, palette_offset: int, palette_index: int
    ) -> list[tuple[int, int, int]] | None:
        """
        Extract a specific palette from ROM as a list of RGB tuples.

        Args:
            rom_path: Path to ROM file
            palette_offset: Offset in ROM where palette data starts
            palette_index: Index of the palette to extract (0-15)

        Returns:
            List of 16 RGB tuples, or None if extraction fails
        """
        try:
            with Path(rom_path).open("rb") as f:
                # Detect SMC header and adjust offset
                file_size = f.seek(0, 2)
                smc_offset = detect_smc_offset_from_size(file_size)
                file_offset = palette_offset + smc_offset

                f.seek(file_offset)
                palette_data = f.read(512)

            if 0 <= palette_index <= 15:
                colors_list = self._extract_palette_colors(palette_data, palette_index)
                # Convert list of lists to list of tuples for consistency
                return [tuple(c) for c in colors_list]

        except OSError as e:
            logger.warning(f"Failed to extract palette colors: {e}")

        return None
