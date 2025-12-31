"""
Tile hash database for mapping VRAM tiles back to ROM offsets.

Instead of parsing complex game pointer tables, this module:
1. Extracts tiles from known ROM offsets (decompress with HAL)
2. Hashes each 8x8 tile (32 bytes for 4bpp SNES format)
3. Creates a database mapping tile_hash -> list of (rom_offset, tile_index) matches

When capturing sprites from Mesen 2:
1. Hash the captured VRAM tiles (optionally including H/V/HV flips at lookup time)
2. Look up each hash to find the source ROM offset
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from core.hal_compression import HALCompressor
from core.rom_validator import ROMHeaderError, ROMValidator
from utils.logging_config import get_logger
from utils.rom_utils import detect_smc_offset_from_size

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
        matches = db.lookup_tile_matches(vram_tile_bytes)
        if matches:
            print(f"Tile candidates: {[m.rom_offset for m in matches]}")
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
        self._hash_to_match: dict[str, list[TileMatch]] = {}
        self._blocks: list[ROMSpriteBlock] = []
        self._rom_header_offset = 0
        self._rom_checksum: int | None = None
        self._rom_title: str | None = None
        self._rom_size = self.rom_path.stat().st_size if self.rom_path.exists() else 0

        if self.rom_path.exists():
            try:
                header, smc_offset = ROMValidator.validate_rom_header(str(self.rom_path))
                self._rom_header_offset = smc_offset
                self._rom_checksum = header.checksum
                self._rom_title = header.title
            except ROMHeaderError as exc:
                self._rom_header_offset = detect_smc_offset_from_size(self._rom_size)
                logger.warning(
                    "ROM header validation failed for %s (%s). Using size-based SMC detection (%d bytes).",
                    self.rom_path,
                    exc,
                    self._rom_header_offset,
                )

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
        if self._rom_header_offset:
            logger.info(f"Adjusting ROM offsets by {self._rom_header_offset} bytes for SMC header")

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
        file_offset = rom_offset + self._rom_header_offset
        try:
            data = self._hal.decompress_from_rom(str(self.rom_path), file_offset)
        except Exception as e:
            logger.warning(f"Failed to decompress ${rom_offset:06X}: {e}")
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

            self._hash_to_match.setdefault(tile_hash, []).append(
                TileMatch(
                    rom_offset=rom_offset,
                    tile_index=tile_idx,
                    description=description,
                )
            )

        self._blocks.append(block)
        logger.debug(f"Indexed ${rom_offset:06X}: {tile_count} tiles, {description}")
        return tile_count

    def lookup_tile(self, tile_data: bytes, include_flips: bool = False) -> TileMatch | None:
        """
        Look up a tile by its data.

        Args:
            tile_data: 32 bytes of 4bpp tile data
            include_flips: Also try H/V/HV flipped variants

        Returns:
            TileMatch if found, None otherwise
        """
        matches = self.lookup_tile_matches(tile_data, include_flips=include_flips)
        return matches[0] if matches else None

    def lookup_tile_matches(self, tile_data: bytes, include_flips: bool = False) -> list[TileMatch]:
        """
        Look up all matches for a tile by its data.

        Args:
            tile_data: 32 bytes of 4bpp tile data
            include_flips: Also try H/V/HV flipped variants

        Returns:
            List of TileMatch candidates (may be empty)
        """
        if len(tile_data) != BYTES_PER_TILE:
            logger.warning(f"Invalid tile data size: {len(tile_data)}")
            return []

        hashes = {self._hash_tile(tile_data)}
        if include_flips:
            for variant in self._iter_flip_variants(tile_data):
                hashes.add(self._hash_tile(variant))

        matches: list[TileMatch] = []
        for tile_hash in hashes:
            matches.extend(self._hash_to_match.get(tile_hash, []))
        return self._dedupe_matches(matches)

    def lookup_tiles(
        self,
        tiles_data: list[bytes],
        include_flips: bool = False,
    ) -> list[TileMatch | None]:
        """Look up multiple tiles at once (first match only)."""
        return [self.lookup_tile(t, include_flips=include_flips) for t in tiles_data]

    def lookup_tiles_matches(
        self,
        tiles_data: list[bytes],
        include_flips: bool = False,
    ) -> list[list[TileMatch]]:
        """Look up multiple tiles at once (all candidates)."""
        return [self.lookup_tile_matches(t, include_flips=include_flips) for t in tiles_data]

    def find_rom_offset_for_vram_tiles(
        self,
        vram_tiles: list[bytes],
        include_flips: bool = False,
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
            matches = self.lookup_tile_matches(tile_data, include_flips=include_flips)
            if matches:
                for rom_offset in {m.rom_offset for m in matches}:
                    offset_counts[rom_offset] = offset_counts.get(rom_offset, 0) + 1

        return dict(sorted(offset_counts.items(), key=lambda x: -x[1]))

    def get_statistics(self) -> dict[str, object]:
        """Get database statistics."""
        return {
            "total_blocks": len(self._blocks),
            "total_unique_hashes": len(self._hash_to_match),
            "hashes_with_collisions": sum(1 for matches in self._hash_to_match.values() if len(matches) > 1),
            "total_matches": sum(len(matches) for matches in self._hash_to_match.values()),
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
            "metadata": {
                "rom_title": self._rom_title,
                "rom_checksum": self._rom_checksum,
                "rom_size": self._rom_size,
                "rom_header_offset": self._rom_header_offset,
            },
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
        metadata = data.get("metadata", {})
        if metadata and self.rom_path.exists():
            expected_checksum = metadata.get("rom_checksum")
            expected_header_offset = metadata.get("rom_header_offset")
            if expected_checksum is not None and self._rom_checksum is not None:
                if expected_checksum != self._rom_checksum:
                    logger.warning(
                        "Tile DB ROM checksum mismatch (db=0x%04X, rom=0x%04X).",
                        expected_checksum,
                        self._rom_checksum,
                    )
            if expected_header_offset is not None and expected_header_offset != self._rom_header_offset:
                logger.warning(
                    "Tile DB header offset mismatch (db=%s, rom=%s).",
                    expected_header_offset,
                    self._rom_header_offset,
                )

        for block_data in data["blocks"]:
            block = ROMSpriteBlock(
                rom_offset=block_data["rom_offset"],
                description=block_data["description"],
                tile_count=block_data["tile_count"],
                tile_hashes=block_data["hashes"],
            )

            for tile_idx, tile_hash in enumerate(block.tile_hashes):
                self._hash_to_match.setdefault(tile_hash, []).append(
                    TileMatch(
                        rom_offset=block.rom_offset,
                        tile_index=tile_idx,
                        description=block.description,
                    )
                )

            self._blocks.append(block)

        logger.info(f"Loaded database: {len(self._blocks)} blocks, {len(self._hash_to_match)} hashes")

    @staticmethod
    def _hash_tile(tile_data: bytes) -> str:
        """Generate hash for a tile."""
        return hashlib.md5(tile_data).hexdigest()

    @staticmethod
    def _reverse_byte(value: int) -> int:
        value = ((value & 0xF0) >> 4) | ((value & 0x0F) << 4)
        value = ((value & 0xCC) >> 2) | ((value & 0x33) << 2)
        value = ((value & 0xAA) >> 1) | ((value & 0x55) << 1)
        return value

    @classmethod
    def _flip_tile(cls, tile_data: bytes, flip_h: bool, flip_v: bool) -> bytes:
        if not flip_h and not flip_v:
            return tile_data
        if len(tile_data) != BYTES_PER_TILE:
            return tile_data
        out = bytearray(BYTES_PER_TILE)
        for row in range(8):
            src_row = 7 - row if flip_v else row
            for plane_offset in (0, 16):
                b0 = tile_data[plane_offset + (src_row * 2)]
                b1 = tile_data[plane_offset + (src_row * 2) + 1]
                if flip_h:
                    b0 = cls._reverse_byte(b0)
                    b1 = cls._reverse_byte(b1)
                out[plane_offset + (row * 2)] = b0
                out[plane_offset + (row * 2) + 1] = b1
        return bytes(out)

    @classmethod
    def _iter_flip_variants(cls, tile_data: bytes) -> list[bytes]:
        return [
            cls._flip_tile(tile_data, flip_h=True, flip_v=False),
            cls._flip_tile(tile_data, flip_h=False, flip_v=True),
            cls._flip_tile(tile_data, flip_h=True, flip_v=True),
        ]

    @staticmethod
    def _dedupe_matches(matches: list[TileMatch]) -> list[TileMatch]:
        seen: set[tuple[int, int]] = set()
        deduped: list[TileMatch] = []
        for match in matches:
            key = (match.rom_offset, match.tile_index)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(match)
        return deduped

    def iter_all_matches(self) -> Iterator[tuple[str, list[TileMatch]]]:
        """Iterate over all hash->matches pairs."""
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
