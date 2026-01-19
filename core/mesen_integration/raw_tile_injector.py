"""Raw Tile Injector - Writes individual 4bpp tiles to scattered ROM addresses.

Unlike HAL-compressed sprites which are stored contiguously, boss sprites like
King Dedede are stored as raw 4bpp tiles at various ROM addresses. This module
handles injection of such scattered tiles.
"""

from __future__ import annotations

import logging
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class TileInjectionMapping:
    """Mapping of a tile to its ROM address."""

    vram_word: int  # VRAM word address (for reference)
    rom_offset: int  # Absolute ROM file offset
    tile_data: bytes | None = None  # 32-byte 4bpp tile data (set during injection)


@dataclass
class RawTileInjectionResult:
    """Result of raw tile injection operation."""

    success: bool
    output_path: str
    tiles_written: int
    message: str


def image_to_4bpp_tile(tile_img: Image.Image) -> bytes:
    """Convert 8x8 PIL Image to 32-byte SNES 4bpp format.

    Args:
        tile_img: 8x8 indexed or RGB image (will be converted to indices 0-15)

    Returns:
        32-byte SNES 4bpp tile data
    """
    # Ensure 8x8
    if tile_img.size != (8, 8):
        tile_img = tile_img.resize((8, 8), Image.Resampling.NEAREST)

    # Convert to indexed if not already
    pixels: list[int]
    if tile_img.mode == "P":
        pixels = [int(p) for p in tile_img.getdata()]
    elif tile_img.mode == "L":
        # Grayscale - check if already palette indices (0-15) or full grayscale (0-255)
        raw_pixels = [int(p) for p in tile_img.getdata()]
        max_val = max(raw_pixels) if raw_pixels else 0
        if max_val <= 15:
            # Already palette indices, use directly
            pixels = raw_pixels
        else:
            # Full grayscale 0-255, convert to 0-15
            pixels = [min(15, p // 16) for p in raw_pixels]
    elif tile_img.mode in ("RGB", "RGBA"):
        # For RGB, use luminance as index (simplified)
        # In practice, you'd want proper palette matching
        tile_img = tile_img.convert("L")
        pixels = [min(15, int(p) // 16) for p in tile_img.getdata()]
    else:
        tile_img = tile_img.convert("L")
        pixels = [min(15, int(p) // 16) for p in tile_img.getdata()]

    # Clamp to 4bpp range
    pixels = [min(15, max(0, int(p))) for p in pixels]

    # Convert to SNES 4bpp format
    # 8 rows, each row has 4 bitplanes interleaved
    # Bytes 0-15: bitplanes 0-1 (2 bytes per row)
    # Bytes 16-31: bitplanes 2-3 (2 bytes per row)
    tile_bytes = bytearray(32)

    for row in range(8):
        bp0 = 0
        bp1 = 0
        bp2 = 0
        bp3 = 0

        for col in range(8):
            pixel = pixels[row * 8 + col]
            bit = 7 - col

            if pixel & 0x01:
                bp0 |= 1 << bit
            if pixel & 0x02:
                bp1 |= 1 << bit
            if pixel & 0x04:
                bp2 |= 1 << bit
            if pixel & 0x08:
                bp3 |= 1 << bit

        # Bitplanes 0-1 at row * 2
        tile_bytes[row * 2] = bp0
        tile_bytes[row * 2 + 1] = bp1
        # Bitplanes 2-3 at 16 + row * 2
        tile_bytes[16 + row * 2] = bp2
        tile_bytes[16 + row * 2 + 1] = bp3

    return bytes(tile_bytes)


class RawTileInjector:
    """Injects raw 4bpp tiles to scattered ROM addresses."""

    def __init__(self) -> None:
        self._backup_created = False

    def inject_tiles(
        self,
        rom_path: str | Path,
        output_path: str | Path,
        tile_mappings: list[TileInjectionMapping],
        create_backup: bool = True,
    ) -> RawTileInjectionResult:
        """Inject multiple tiles to their mapped ROM addresses.

        Args:
            rom_path: Path to source ROM file
            output_path: Path for modified ROM output
            tile_mappings: List of TileInjectionMapping with rom_offset and tile_data
            create_backup: Whether to create backup of original

        Returns:
            RawTileInjectionResult with success status and details
        """
        rom_path = Path(rom_path)
        output_path = Path(output_path)

        if not rom_path.exists():
            return RawTileInjectionResult(
                success=False,
                output_path=str(output_path),
                tiles_written=0,
                message=f"ROM file not found: {rom_path}",
            )

        # Validate all mappings have tile data
        missing_data = [m for m in tile_mappings if m.tile_data is None]
        if missing_data:
            return RawTileInjectionResult(
                success=False,
                output_path=str(output_path),
                tiles_written=0,
                message=f"{len(missing_data)} tiles missing data",
            )

        # Create backup if requested
        if create_backup:
            backup_path = rom_path.with_suffix(rom_path.suffix + ".bak")
            if not backup_path.exists():
                shutil.copy2(rom_path, backup_path)
                logger.info(f"Created backup: {backup_path}")

        # Copy ROM to output path
        shutil.copy2(rom_path, output_path)

        # Inject tiles
        tiles_written = 0
        try:
            with open(output_path, "r+b") as f:
                rom_size = f.seek(0, 2)  # Get file size

                for mapping in tile_mappings:
                    if mapping.tile_data is None:
                        continue

                    # Validate offset
                    if mapping.rom_offset < 0 or mapping.rom_offset + 32 > rom_size:
                        logger.warning(
                            f"Skipping tile at invalid offset 0x{mapping.rom_offset:06X} (ROM size: 0x{rom_size:06X})"
                        )
                        continue

                    # Write tile
                    f.seek(mapping.rom_offset)
                    f.write(mapping.tile_data)
                    tiles_written += 1
                    logger.debug(f"Wrote tile to ROM offset 0x{mapping.rom_offset:06X}")

        except OSError as e:
            return RawTileInjectionResult(
                success=False,
                output_path=str(output_path),
                tiles_written=tiles_written,
                message=f"Write error: {e}",
            )

        return RawTileInjectionResult(
            success=True,
            output_path=str(output_path),
            tiles_written=tiles_written,
            message=f"Successfully wrote {tiles_written} tiles to {output_path.name}",
        )

    def inject_from_rom_map(
        self,
        rom_path: str | Path,
        output_path: str | Path,
        rom_map: Mapping[str, object],
        modified_tiles: dict[int, Image.Image],  # vram_word -> tile image
        create_backup: bool = True,
    ) -> RawTileInjectionResult:
        """Inject tiles using a ROM map JSON and modified tile images.

        Args:
            rom_path: Path to source ROM file
            output_path: Path for modified ROM output
            rom_map: ROM map dict (from sprite_rom_mapper.py JSON output)
            modified_tiles: Dict of vram_word -> modified PIL Image
            create_backup: Whether to create backup

        Returns:
            RawTileInjectionResult
        """
        # Build mappings from ROM map
        mappings: list[TileInjectionMapping] = []

        raw_mappings = rom_map.get("mappings", [])
        if not isinstance(raw_mappings, list):
            raw_mappings = []

        for entry in raw_mappings:
            if not isinstance(entry, dict):
                continue
            vram_word = entry.get("vram_word")
            rom_offset = entry.get("rom_offset")

            if vram_word is None or rom_offset is None:
                continue

            # Check if this tile was modified
            if vram_word in modified_tiles:
                tile_img = modified_tiles[vram_word]
                tile_data = image_to_4bpp_tile(tile_img)

                mappings.append(
                    TileInjectionMapping(
                        vram_word=vram_word,
                        rom_offset=rom_offset,
                        tile_data=tile_data,
                    )
                )

        if not mappings:
            return RawTileInjectionResult(
                success=False,
                output_path=str(output_path),
                tiles_written=0,
                message="No modified tiles to inject",
            )

        return self.inject_tiles(rom_path, output_path, mappings, create_backup)


def load_rom_map(rom_map_path: str | Path) -> Mapping[str, object] | None:
    """Load ROM map JSON file.

    Args:
        rom_map_path: Path to ROM map JSON (from sprite_rom_mapper.py)

    Returns:
        Dict with mappings, or None if load failed
    """
    import json

    path = Path(rom_map_path)
    if not path.exists():
        logger.warning(f"ROM map not found: {path}")
        return None

    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to load ROM map: {e}")
        return None
