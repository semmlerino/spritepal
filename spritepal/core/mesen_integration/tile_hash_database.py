"""
Tile hash database for mapping VRAM tiles back to ROM offsets.

Instead of parsing complex game pointer tables, this module:
1. Extracts tiles from known ROM offsets (decompress with HAL)
2. Hashes each 8x8 tile (32 bytes for 4bpp SNES format)
3. Creates a database mapping tile_hash -> (rom_offset, tile_index)

When capturing sprites from Mesen 2:
1. Hash the captured VRAM tiles
2. Look up each hash to find the source ROM offset
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from core.hal_compression import HALCompressor
from utils.logging_config import get_logger

logger = get_logger(__name__)

BYTES_PER_TILE = 32  # 4bpp SNES tile = 32 bytes


@dataclass
class TileMatch:
    """Result of a tile hash lookup."""

    rom_offset: int  # Where the sprite data starts in ROM
    tile_index: int  # Which tile within that block
    confidence: float = 1.0  # Match confidence (1.0 for exact match)
    description: str = ""  # Human-readable description

    @property
    def tile_byte_offset(self) -> int:
        """Byte offset within decompressed data."""
        return self.tile_index * BYTES_PER_TILE


@dataclass
class ROMSpriteBlock:
    """A block of sprite data at a ROM offset."""

    rom_offset: int
    description: str
    decompressed_size: int = 0
    tile_count: int = 0
    tile_hashes: list[str] = field(default_factory=list)


class TileHashDatabase:
    """
    Database mapping tile hashes to ROM offsets.

    Usage:
        db = TileHashDatabase(rom_path)
        db.build_database()  # Scan known offsets

        # Later, when matching VRAM tiles:
        match = db.lookup_tile(vram_tile_bytes)
        if match:
            print(f"Tile from ROM offset {match.rom_offset:X}")
    """

    # Known sprite data locations in Kirby Super Star
    KNOWN_SPRITE_OFFSETS = [
        (0x1B0000, "Kirby sprites"),
        (0x1A0000, "Enemy sprites"),
        (0x180000, "Items/UI graphics"),
        (0x190000, "Background tiles"),
        (0x1C0000, "Background gradients"),
        (0x280000, "Additional sprites"),
        (0x0E0000, "Title screen/fonts"),
        # More offsets can be added as discovered
    ]

    def __init__(self, rom_path: str | Path):
        """
        Initialize database with ROM path.

        Args:
            rom_path: Path to ROM file
        """
        self.rom_path = Path(rom_path)
        self._hal = HALCompressor()
        self._hash_to_match: dict[str, TileMatch] = {}
        self._blocks: list[ROMSpriteBlock] = []

    def build_database(
        self,
        additional_offsets: list[tuple[int, str]] | None = None,
        progress_callback: object | None = None,
    ) -> int:
        """
        Build the tile hash database from known ROM offsets.

        Args:
            additional_offsets: Extra (offset, description) pairs to scan
            progress_callback: Optional callback(current, total) for progress

        Returns:
            Total number of tiles indexed
        """
        offsets = list(self.KNOWN_SPRITE_OFFSETS)
        if additional_offsets:
            offsets.extend(additional_offsets)

        total_tiles = 0
        self._hash_to_match.clear()
        self._blocks.clear()

        logger.info(f"Building tile database from {len(offsets)} ROM offsets")

        for i, (offset, description) in enumerate(offsets):
            if callable(progress_callback):
                progress_callback(i, len(offsets))

            try:
                tiles = self._index_offset(offset, description)
                total_tiles += tiles
            except Exception as e:
                logger.warning(f"Failed to index offset ${offset:06X}: {e}")

        logger.info(f"Database built: {total_tiles} tiles, {len(self._hash_to_match)} unique hashes")
        return total_tiles

    def _index_offset(self, rom_offset: int, description: str) -> int:
        """Index tiles from a single ROM offset."""
        try:
            data = self._hal.decompress_from_rom(str(self.rom_path), rom_offset)
        except Exception as e:
            logger.debug(f"Failed to decompress ${rom_offset:06X}: {e}")
            return 0

        if len(data) < BYTES_PER_TILE:
            return 0

        tile_count = len(data) // BYTES_PER_TILE
        block = ROMSpriteBlock(
            rom_offset=rom_offset,
            description=description,
            decompressed_size=len(data),
            tile_count=tile_count,
        )

        for tile_idx in range(tile_count):
            tile_start = tile_idx * BYTES_PER_TILE
            tile_data = data[tile_start : tile_start + BYTES_PER_TILE]
            tile_hash = self._hash_tile(tile_data)

            block.tile_hashes.append(tile_hash)

            # Only store first occurrence (tiles may repeat)
            if tile_hash not in self._hash_to_match:
                self._hash_to_match[tile_hash] = TileMatch(
                    rom_offset=rom_offset,
                    tile_index=tile_idx,
                    description=description,
                )

        self._blocks.append(block)
        logger.debug(f"Indexed ${rom_offset:06X}: {tile_count} tiles, {description}")
        return tile_count

    def lookup_tile(self, tile_data: bytes) -> TileMatch | None:
        """
        Look up a tile by its data.

        Args:
            tile_data: 32 bytes of 4bpp tile data

        Returns:
            TileMatch if found, None otherwise
        """
        if len(tile_data) != BYTES_PER_TILE:
            logger.warning(f"Invalid tile data size: {len(tile_data)}")
            return None

        tile_hash = self._hash_tile(tile_data)
        return self._hash_to_match.get(tile_hash)

    def lookup_tiles(self, tiles_data: list[bytes]) -> list[TileMatch | None]:
        """Look up multiple tiles at once."""
        return [self.lookup_tile(t) for t in tiles_data]

    def find_rom_offset_for_vram_tiles(
        self,
        vram_tiles: list[bytes],
    ) -> dict[int, int]:
        """
        Find most likely ROM offset(s) for a set of VRAM tiles.

        Args:
            vram_tiles: List of 32-byte tile data from VRAM

        Returns:
            Dict mapping rom_offset -> count of matched tiles
        """
        offset_counts: dict[int, int] = {}

        for tile_data in vram_tiles:
            match = self.lookup_tile(tile_data)
            if match:
                offset_counts[match.rom_offset] = offset_counts.get(match.rom_offset, 0) + 1

        return dict(sorted(offset_counts.items(), key=lambda x: -x[1]))

    def get_statistics(self) -> dict[str, object]:
        """Get database statistics."""
        return {
            "total_blocks": len(self._blocks),
            "total_unique_hashes": len(self._hash_to_match),
            "total_tiles": sum(b.tile_count for b in self._blocks),
            "blocks": [
                {
                    "offset": f"${b.rom_offset:06X}",
                    "description": b.description,
                    "tiles": b.tile_count,
                    "bytes": b.decompressed_size,
                }
                for b in self._blocks
            ],
        }

    def save_database(self, path: str | Path) -> None:
        """
        Save database to JSON file for later loading.

        Args:
            path: Output file path
        """
        data = {
            "rom_path": str(self.rom_path),
            "blocks": [
                {
                    "rom_offset": b.rom_offset,
                    "description": b.description,
                    "tile_count": b.tile_count,
                    "hashes": b.tile_hashes,
                }
                for b in self._blocks
            ],
        }

        Path(path).write_text(json.dumps(data, indent=2))
        logger.info(f"Saved database to {path}")

    def load_database(self, path: str | Path) -> None:
        """
        Load database from JSON file.

        Args:
            path: Input file path
        """
        data = json.loads(Path(path).read_text())

        self._hash_to_match.clear()
        self._blocks.clear()

        for block_data in data["blocks"]:
            block = ROMSpriteBlock(
                rom_offset=block_data["rom_offset"],
                description=block_data["description"],
                tile_count=block_data["tile_count"],
                tile_hashes=block_data["hashes"],
            )

            for tile_idx, tile_hash in enumerate(block.tile_hashes):
                if tile_hash not in self._hash_to_match:
                    self._hash_to_match[tile_hash] = TileMatch(
                        rom_offset=block.rom_offset,
                        tile_index=tile_idx,
                        description=block.description,
                    )

            self._blocks.append(block)

        logger.info(f"Loaded database: {len(self._blocks)} blocks, {len(self._hash_to_match)} hashes")

    @staticmethod
    def _hash_tile(tile_data: bytes) -> str:
        """Generate hash for a tile."""
        return hashlib.md5(tile_data).hexdigest()

    def iter_all_matches(self) -> Iterator[tuple[str, TileMatch]]:
        """Iterate over all hash->match pairs."""
        yield from self._hash_to_match.items()


def build_and_save_database(
    rom_path: str | Path,
    output_path: str | Path | None = None,
) -> TileHashDatabase:
    """
    Convenience function to build and save a tile database.

    Args:
        rom_path: Path to ROM file
        output_path: Path to save JSON database (optional)

    Returns:
        Built TileHashDatabase instance
    """
    db = TileHashDatabase(rom_path)
    db.build_database()

    if output_path:
        db.save_database(output_path)

    return db
