"""
ROM Tile Matcher with SA-1 Character Conversion.

Matches VRAM-captured tiles back to ROM offsets by:
1. Decompressing ROM data with HAL
2. Converting decompressed bitmap to SNES 4bpp format (SA-1 character conversion)
3. Building hash database of converted tiles
4. Looking up captured VRAM tiles (already in SNES 4bpp format)

This bridges the format gap:
    ROM (HAL compressed) → HAL decompress → Bitmap format
    → SA-1 character conversion → SNES 4bpp format → VRAM

Without this conversion, VRAM tiles won't match ROM-decompressed bytes.

Usage:
    from core.mesen_integration.rom_tile_matcher import ROMTileMatcher

    matcher = ROMTileMatcher(rom_path)
    matcher.build_database()

    # Match VRAM tile data (32 bytes, SNES 4bpp format)
    matches = matcher.lookup_vram_tile(vram_tile_bytes)
    if matches:
        print(f"Found at ROM offset ${matches[0].rom_offset:06X}")
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from core.hal_compression import HALCompressor
from core.mesen_integration.sa1_character_conversion import (
    TWO_PLANE_COMBOS,
    bitmap_to_snes_4bpp,
    extract_two_planes,
    get_two_plane_candidates,
)
from utils.rom_utils import detect_smc_offset_from_size

BYTES_PER_PACKED_TILE = 16  # Packed 2bpp tile = 16 bytes

if TYPE_CHECKING:
    from collections.abc import Iterator

logger = logging.getLogger(__name__)

BYTES_PER_TILE = 32  # 4bpp tile = 32 bytes


@dataclass
class TileLocation:
    """Location of a tile in ROM."""

    rom_offset: int  # HAL-compressed block start in ROM
    tile_index: int  # Tile index within decompressed block
    description: str = ""
    flip_variant: str = ""  # "" = original, "H", "V", "HV"

    @property
    def tile_byte_offset(self) -> int:
        """Byte offset within decompressed data."""
        return self.tile_index * BYTES_PER_TILE


@dataclass
class ROMBlock:
    """A decompressed block from ROM."""

    rom_offset: int
    description: str
    decompressed_size: int = 0
    tile_count: int = 0
    # Tile hashes in SNES 4bpp format (after SA-1 conversion)
    tile_hashes: list[str] = field(default_factory=list)


class ROMTileMatcher:
    """
    Matches VRAM tiles to ROM offsets with SA-1 format conversion.

    Unlike TileHashDatabase which hashes raw decompressed data,
    this matcher applies SA-1 character conversion to convert
    ROM bitmap format → SNES 4bpp format before hashing.
    """

    # Known sprite data offsets in Kirby Super Star ROM
    KNOWN_SPRITE_OFFSETS: list[tuple[int, str]] = [
        # Main sprite banks
        (0x1B0000, "Kirby main sprites"),
        (0x1A0000, "Common enemies"),
        (0x180000, "Items and UI"),
        (0x190000, "Background tiles"),
        (0x1C0000, "Background gradients"),
        (0x280000, "Additional sprites"),
        (0x0E0000, "Title/fonts"),
        # Additional locations from game analysis
        (0x1D0000, "Boss sprites 1"),
        (0x1E0000, "Boss sprites 2"),
        (0x200000, "Milky Way sprites"),
        (0x210000, "Arena sprites"),
        (0x220000, "Meta Knight sprites"),
        (0x230000, "Dyna Blade sprites"),
        (0x240000, "Gourmet Race sprites"),
        (0x250000, "Great Cave sprites"),
        (0x260000, "Spring Breeze sprites"),
        (0x270000, "Revenge of MK sprites"),
    ]

    def __init__(
        self,
        rom_path: str | Path,
        apply_sa1_conversion: bool = True,
    ):
        """
        Initialize ROM tile matcher.

        Args:
            rom_path: Path to ROM file
            apply_sa1_conversion: If True, convert bitmap→SNES 4bpp when indexing
        """
        self.rom_path = Path(rom_path)
        self.apply_sa1_conversion = apply_sa1_conversion
        self._hal = HALCompressor()

        # Detect SMC header
        file_size = self.rom_path.stat().st_size
        self._header_offset = detect_smc_offset_from_size(file_size)

        # Database: hash → list of locations
        self._hash_to_locations: dict[str, list[TileLocation]] = {}
        self._blocks: list[ROMBlock] = []

        # Two-plane database: (planes_combo, hash) → ROM locations
        # Stores 16-byte hashes for each two-plane combination (6 combos total)
        # Used when VRAM tile has exactly 2 zero planes
        self._two_plane_db: dict[tuple[int, int], dict[str, list[TileLocation]]] = {
            combo: {} for combo in TWO_PLANE_COMBOS
        }
        self._two_plane_indexed = False

        # HAL two-plane database: planes 0+2 extracted from HAL-decompressed tiles
        # This is different from _two_plane_db which searches raw ROM bytes
        # Key: hash of planes 0+2, Value: list of TileLocations
        self._hal_two_plane_db: dict[str, list[TileLocation]] = {}
        self._hal_two_plane_indexed = False

        # Statistics
        self._total_tiles = 0
        self._unique_hashes = 0
        self._two_plane_tiles = 0
        self._hal_two_plane_matches = 0
        self._two_plane_matches_by_combo: dict[tuple[int, int], int] = {
            combo: 0 for combo in TWO_PLANE_COMBOS
        }

    def scan_rom_for_blocks(
        self,
        step: int = 0x400,
        min_tiles: int = 8,
        progress_callback: object | None = None,
    ) -> list[tuple[int, str]]:
        """
        Scan entire ROM for valid HAL-compressed blocks.

        Args:
            step: Scan step size in bytes (default: 1KB)
            min_tiles: Minimum tiles to consider valid (default: 8)
            progress_callback: Optional callback(current, total) for progress

        Returns:
            List of (rom_offset, description) tuples
        """
        rom_size = self.rom_path.stat().st_size - self._header_offset
        found: list[tuple[int, str]] = []
        total_steps = rom_size // step

        logger.info(f"Scanning ROM for HAL blocks (step={step}, min_tiles={min_tiles})")

        for i, offset in enumerate(range(0, rom_size, step)):
            if callable(progress_callback) and i % 100 == 0:
                progress_callback(i, total_steps)

            file_offset = offset + self._header_offset
            try:
                data = self._hal.decompress_from_rom(str(self.rom_path), file_offset)
                if len(data) >= BYTES_PER_TILE * min_tiles:
                    tiles = len(data) // BYTES_PER_TILE
                    bank = (offset >> 16) & 0xFF
                    addr = offset & 0xFFFF
                    desc = f"${bank:02X}:{addr:04X} ({tiles} tiles)"
                    found.append((offset, desc))
            except Exception:
                pass

        logger.info(f"Found {len(found)} HAL blocks in ROM")
        return found

    def build_two_plane_index(
        self,
        step: int = 16,
        start: int = 0,
        end: int | None = None,
        progress_callback: object | None = None,
    ) -> int:
        """
        Scan raw ROM for 16-byte patterns, indexing all two-plane combinations.

        This allows discovering which plane combination actually matches captured
        VRAM tiles, rather than hardcoding one combination.

        Args:
            step: Scan step size in bytes (default: 16 = no overlap)
            start: Starting offset in ROM
            end: Ending offset in ROM (default: ROM size)
            progress_callback: Optional callback(current, total)

        Returns:
            Number of patterns indexed.
        """
        rom_size = self.rom_path.stat().st_size - self._header_offset
        if end is None:
            end = rom_size

        total_steps = (end - start) // step
        indexed = 0

        logger.info(f"Building two-plane index (step={step}, range=${start:X}-${end:X})")

        with open(self.rom_path, "rb") as f:
            f.seek(self._header_offset + start)
            rom_data = f.read(end - start)

        for i in range(0, len(rom_data) - BYTES_PER_PACKED_TILE + 1, step):
            if callable(progress_callback) and i % 10000 == 0:
                progress_callback(i // step, total_steps)

            chunk = rom_data[i : i + BYTES_PER_PACKED_TILE]
            if len(chunk) != BYTES_PER_PACKED_TILE:
                continue

            # Skip empty chunks
            if all(b == 0 for b in chunk):
                continue

            # Hash this 16-byte chunk
            chunk_hash = hashlib.sha256(chunk).hexdigest()[:16]
            rom_offset = start + i

            # Store in all plane combo databases
            # When we look up, we'll extract the same 2 planes from VRAM tile
            for combo in TWO_PLANE_COMBOS:
                if chunk_hash not in self._two_plane_db[combo]:
                    self._two_plane_db[combo][chunk_hash] = []
                self._two_plane_db[combo][chunk_hash].append(
                    TileLocation(
                        rom_offset=rom_offset,
                        tile_index=0,  # Raw ROM, not from HAL block
                        description=f"raw@${rom_offset:06X} ({combo[0]}+{combo[1]})",
                        flip_variant="",
                    )
                )

            indexed += 1

        self._two_plane_indexed = True
        self._two_plane_tiles = indexed
        logger.info(f"Two-plane index built: {indexed} patterns indexed")

        return indexed

    def build_database(
        self,
        additional_offsets: list[tuple[int, str]] | None = None,
        scan_rom: bool = False,
        scan_step: int = 0x400,
        scan_min_tiles: int = 8,
        build_two_plane: bool = False,
        two_plane_step: int = 16,
        progress_callback: object | None = None,
    ) -> int:
        """
        Build tile hash database from ROM.

        Args:
            additional_offsets: Extra (offset, description) pairs to scan
            scan_rom: If True, scan entire ROM for valid HAL blocks (slow but comprehensive)
            scan_step: Step size for ROM scanning (default: 1KB)
            scan_min_tiles: Minimum tiles per block when scanning (default: 8)
            build_two_plane: If True, also build two-plane index from raw ROM
            two_plane_step: Step size for two-plane scanning (default: 16 bytes)
            progress_callback: Optional callback(current, total) for progress

        Returns:
            Number of tiles indexed
        """
        if scan_rom:
            # Comprehensive ROM scan
            offsets = self.scan_rom_for_blocks(
                step=scan_step,
                min_tiles=scan_min_tiles,
                progress_callback=progress_callback,
            )
            if additional_offsets:
                existing = {o[0] for o in offsets}
                for offset, desc in additional_offsets:
                    if offset not in existing:
                        offsets.append((offset, desc))
        else:
            # Use known offsets only
            offsets = list(self.KNOWN_SPRITE_OFFSETS)
            if additional_offsets:
                offsets.extend(additional_offsets)

        self._hash_to_locations.clear()
        self._blocks.clear()
        self._total_tiles = 0

        logger.info(f"Building tile database from {len(offsets)} ROM offsets")
        if self._header_offset:
            logger.info(f"SMC header offset: {self._header_offset} bytes")
        logger.info(f"SA-1 conversion: {'enabled' if self.apply_sa1_conversion else 'disabled'}")

        for i, (offset, description) in enumerate(offsets):
            if callable(progress_callback):
                progress_callback(i, len(offsets))

            try:
                tiles = self._index_offset(offset, description)
                self._total_tiles += tiles
            except Exception as e:
                logger.debug(f"Failed to index ${offset:06X}: {e}")

        self._unique_hashes = len(self._hash_to_locations)
        logger.info(
            f"Database built: {self._total_tiles} tiles, "
            f"{self._unique_hashes} unique hashes"
        )

        # Optionally build two-plane index for raw ROM pattern matching
        if build_two_plane:
            logger.info("Building two-plane index from raw ROM...")
            self.build_two_plane_index(step=two_plane_step)

        return self._total_tiles

    def _index_offset(self, rom_offset: int, description: str) -> int:
        """
        Index tiles from a single ROM offset.

        Decompresses data, optionally applies SA-1 conversion, then hashes.
        """
        file_offset = rom_offset + self._header_offset

        try:
            data = self._hal.decompress_from_rom(str(self.rom_path), file_offset)
        except Exception as e:
            logger.debug(f"Failed to decompress ${rom_offset:06X}: {e}")
            return 0

        if len(data) < BYTES_PER_TILE:
            return 0

        tile_count = len(data) // BYTES_PER_TILE
        block = ROMBlock(
            rom_offset=rom_offset,
            description=description,
            decompressed_size=len(data),
            tile_count=tile_count,
        )

        for tile_idx in range(tile_count):
            tile_start = tile_idx * BYTES_PER_TILE
            tile_data = data[tile_start : tile_start + BYTES_PER_TILE]

            # Apply SA-1 character conversion if enabled
            if self.apply_sa1_conversion:
                try:
                    # ROM has bitmap format, convert to SNES 4bpp
                    tile_data = bitmap_to_snes_4bpp(tile_data)
                except ValueError:
                    # Skip malformed tiles
                    continue

            tile_hash = self._hash_tile(tile_data)
            block.tile_hashes.append(tile_hash)

            # Index this tile
            location = TileLocation(
                rom_offset=rom_offset,
                tile_index=tile_idx,
                description=description,
            )
            self._hash_to_locations.setdefault(tile_hash, []).append(location)

            # Also index flipped variants for better matching
            self._index_flip_variants(tile_data, location)

        self._blocks.append(block)
        logger.debug(f"Indexed ${rom_offset:06X}: {tile_count} tiles ({description})")
        return tile_count

    def _index_flip_variants(
        self,
        tile_data: bytes,
        base_location: TileLocation,
    ) -> None:
        """Index horizontally and vertically flipped variants."""
        for flip_type, flipped in self._iter_flips(tile_data):
            if flipped == tile_data:
                continue  # Skip if flip produces same data

            flip_hash = self._hash_tile(flipped)
            location = TileLocation(
                rom_offset=base_location.rom_offset,
                tile_index=base_location.tile_index,
                description=base_location.description,
                flip_variant=flip_type,
            )
            self._hash_to_locations.setdefault(flip_hash, []).append(location)

    def _iter_flips(self, tile_data: bytes) -> Iterator[tuple[str, bytes]]:
        """Generate H, V, HV flip variants of a tile."""
        # Horizontal flip
        yield "H", self._flip_h(tile_data)
        # Vertical flip
        yield "V", self._flip_v(tile_data)
        # Both
        yield "HV", self._flip_h(self._flip_v(tile_data))

    @staticmethod
    def _flip_h(tile_data: bytes) -> bytes:
        """Flip tile horizontally (reverse bit order in each bitplane byte)."""
        result = bytearray(32)
        for i, byte in enumerate(tile_data):
            # Reverse bits in byte
            result[i] = int(f"{byte:08b}"[::-1], 2)
        return bytes(result)

    @staticmethod
    def _flip_v(tile_data: bytes) -> bytes:
        """Flip tile vertically (reverse row order)."""
        result = bytearray(32)
        # SNES 4bpp: rows 0-7 in bytes 0-15 (bitplanes 0,1), 16-31 (bitplanes 2,3)
        for row in range(8):
            src_row = 7 - row
            # Bitplanes 0,1
            result[row * 2] = tile_data[src_row * 2]
            result[row * 2 + 1] = tile_data[src_row * 2 + 1]
            # Bitplanes 2,3
            result[16 + row * 2] = tile_data[16 + src_row * 2]
            result[16 + row * 2 + 1] = tile_data[16 + src_row * 2 + 1]
        return bytes(result)

    @staticmethod
    def _hash_tile(tile_data: bytes) -> str:
        """Generate hash for tile data."""
        return hashlib.sha256(tile_data).hexdigest()[:16]

    def lookup_vram_tile(
        self,
        vram_tile: bytes,
        max_matches: int = 10,
        try_two_plane: bool = True,
    ) -> list[TileLocation]:
        """
        Look up a VRAM tile to find ROM locations.

        VRAM tiles are already in SNES 4bpp format, so no conversion needed.
        If no match found and tile has exactly 2 zero planes, tries two-plane
        lookup to find 16-byte pattern in raw ROM.

        Args:
            vram_tile: 32 bytes of VRAM tile data (SNES 4bpp format)
            max_matches: Maximum number of matches to return
            try_two_plane: If True, try two-plane lookup on no HAL match

        Returns:
            List of TileLocation matches, sorted by ROM offset
        """
        if len(vram_tile) != BYTES_PER_TILE:
            return []

        # First try standard HAL-decompressed database
        tile_hash = self._hash_tile(vram_tile)
        locations = self._hash_to_locations.get(tile_hash, [])

        if locations:
            sorted_locs = sorted(locations, key=lambda x: (x.rom_offset, x.tile_index))
            return sorted_locs[:max_matches]

        # No HAL match - try two-plane lookup if tile qualifies
        if try_two_plane and self._two_plane_indexed:
            candidates = get_two_plane_candidates(vram_tile)
            for combo in candidates:
                # Extract the two non-zero planes from VRAM tile
                extracted = extract_two_planes(vram_tile, combo)
                two_plane_hash = hashlib.sha256(extracted).hexdigest()[:16]

                # Look up in the corresponding combo database
                if combo in self._two_plane_db:
                    matches = self._two_plane_db[combo].get(two_plane_hash, [])
                    if matches:
                        # Track which combo matched for statistics
                        self._two_plane_matches_by_combo[combo] += 1
                        sorted_matches = sorted(matches, key=lambda x: x.rom_offset)
                        return sorted_matches[:max_matches]

        return []

    def lookup_vram_tiles(
        self,
        vram_tiles: list[bytes],
    ) -> dict[int, list[TileLocation]]:
        """
        Look up multiple VRAM tiles.

        Args:
            vram_tiles: List of 32-byte VRAM tiles

        Returns:
            Dict mapping tile index → list of matches
        """
        results: dict[int, list[TileLocation]] = {}
        for idx, tile in enumerate(vram_tiles):
            matches = self.lookup_vram_tile(tile)
            if matches:
                results[idx] = matches
        return results

    def get_statistics(self) -> dict[str, object]:
        """Get database statistics."""
        stats: dict[str, object] = {
            "rom_path": str(self.rom_path),
            "sa1_conversion": self.apply_sa1_conversion,
            "header_offset": self._header_offset,
            "blocks_indexed": len(self._blocks),
            "total_tiles": self._total_tiles,
            "unique_hashes": self._unique_hashes,
            "collision_rate": (
                1 - self._unique_hashes / self._total_tiles
                if self._total_tiles > 0
                else 0
            ),
            "two_plane_indexed": self._two_plane_indexed,
            "two_plane_tiles": self._two_plane_tiles,
        }

        # Add two-plane match statistics by combo
        if self._two_plane_indexed:
            combo_stats: dict[str, int] = {}
            for combo, count in self._two_plane_matches_by_combo.items():
                combo_str = f"planes_{combo[0]}_{combo[1]}"
                combo_stats[combo_str] = count
            stats["two_plane_matches_by_combo"] = combo_stats
            stats["total_two_plane_matches"] = sum(
                self._two_plane_matches_by_combo.values()
            )

        return stats

    def save_database(self, output_path: str | Path) -> None:
        """Save database to JSON file."""
        output_path = Path(output_path)

        data = {
            "version": "1.0",
            "rom_path": str(self.rom_path),
            "sa1_conversion": self.apply_sa1_conversion,
            "header_offset": self._header_offset,
            "statistics": self.get_statistics(),
            "blocks": [
                {
                    "rom_offset": block.rom_offset,
                    "description": block.description,
                    "decompressed_size": block.decompressed_size,
                    "tile_count": block.tile_count,
                }
                for block in self._blocks
            ],
            "hash_to_locations": {
                hash_: [
                    {
                        "rom_offset": loc.rom_offset,
                        "tile_index": loc.tile_index,
                        "description": loc.description,
                        "flip_variant": loc.flip_variant,
                    }
                    for loc in locs
                ]
                for hash_, locs in self._hash_to_locations.items()
            },
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Database saved to {output_path}")

    @classmethod
    def load_database(cls, db_path: str | Path, rom_path: str | Path) -> ROMTileMatcher:
        """
        Load database from JSON file.

        Args:
            db_path: Path to database JSON
            rom_path: Path to ROM file (for verification)

        Returns:
            Loaded ROMTileMatcher instance
        """
        db_path = Path(db_path)
        rom_path = Path(rom_path)

        with open(db_path, encoding="utf-8") as f:
            data = json.load(f)

        instance = cls(
            rom_path=rom_path,
            apply_sa1_conversion=data.get("sa1_conversion", True),
        )

        # Restore blocks
        for block_data in data.get("blocks", []):
            instance._blocks.append(
                ROMBlock(
                    rom_offset=block_data["rom_offset"],
                    description=block_data["description"],
                    decompressed_size=block_data["decompressed_size"],
                    tile_count=block_data["tile_count"],
                )
            )

        # Restore hash mappings
        for hash_, locs in data.get("hash_to_locations", {}).items():
            instance._hash_to_locations[hash_] = [
                TileLocation(
                    rom_offset=loc["rom_offset"],
                    tile_index=loc["tile_index"],
                    description=loc["description"],
                    flip_variant=loc.get("flip_variant", ""),
                )
                for loc in locs
            ]

        instance._total_tiles = sum(b.tile_count for b in instance._blocks)
        instance._unique_hashes = len(instance._hash_to_locations)

        logger.info(
            f"Database loaded: {instance._total_tiles} tiles, "
            f"{instance._unique_hashes} hashes"
        )

        return instance
