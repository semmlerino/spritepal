#!/usr/bin/env python3
"""
OAM (Object Attribute Memory) parser for SNES sprite palette mapping.
Extracts sprite-to-palette assignments from OAM dumps.
"""

import logging
from typing import TypedDict

from ..constants import (
    BYTES_PER_OAM_ENTRY,
    BYTES_PER_TILE_4BPP,
    KIRBY_TILE_END,
    KIRBY_TILE_START,
    KIRBY_VRAM_BASE,
    OAM_ENTRIES,
    OAM_HIGH_TABLE_OFFSET,
    OAM_SIZE,
)

logger = logging.getLogger(__name__)


class SpriteEntry(TypedDict):
    """OAM sprite entry structure."""

    index: int
    x: int
    y: int
    tile: int
    palette: int
    priority: int
    h_flip: int
    v_flip: int
    size: str


class OAMPaletteMapper:
    """Parse OAM data to map sprites to their assigned palettes."""

    def __init__(self) -> None:
        self.oam_entries: list[SpriteEntry] = []
        self.tile_palette_map: dict[int, int] = {}  # tile_number -> palette_number
        self.vram_palette_map: dict[int, int] = {}  # vram_offset -> palette_number
        # Sorted list for efficient range queries: (start_offset, end_offset, palette)
        self.vram_palette_ranges: list[tuple[int, int, int]] = []

    def parse_oam_dump(self, oam_file: str) -> None:
        """Parse OAM dump file and extract sprite entries."""
        with open(oam_file, "rb") as f:
            oam_data = f.read()

        if len(oam_data) < BYTES_PER_OAM_ENTRY:
            raise ValueError(f"OAM dump too small: {len(oam_data)} bytes (need at least {BYTES_PER_OAM_ENTRY})")

        if len(oam_data) < OAM_SIZE:
            logger.warning(f"Partial OAM data: {len(oam_data)} bytes (full size is {OAM_SIZE})")

        # Parse main OAM table
        for i in range(OAM_ENTRIES):
            offset = i * BYTES_PER_OAM_ENTRY

            if offset + BYTES_PER_OAM_ENTRY > len(oam_data):
                break

            # Read 4-byte sprite entry
            x_pos = oam_data[offset]
            y_pos = oam_data[offset + 1]
            tile_num = oam_data[offset + 2]
            attributes = oam_data[offset + 3]

            # Extract attributes
            palette = attributes & 0x07  # Lower 3 bits
            priority = (attributes >> 3) & 0x03
            h_flip = (attributes >> 5) & 0x01
            v_flip = (attributes >> 6) & 0x01
            tile_table = (attributes >> 7) & 0x01

            # Get size and MSB of position from high table
            high_table_offset = OAM_HIGH_TABLE_OFFSET + (i // 4)
            if high_table_offset < len(oam_data):
                high_table_byte = oam_data[high_table_offset]
                high_table_shift = (i % 4) * 2
                high_bits = (high_table_byte >> high_table_shift) & 0x03
            else:
                high_bits = 0

            size_bit = high_bits & 0x01
            x_msb = (high_bits >> 1) & 0x01

            actual_tile = tile_num | (tile_table << 8)

            sprite_entry = {
                "index": i,
                "x": x_pos | (x_msb << 8),
                "y": y_pos,
                "tile": actual_tile,
                "palette": palette,
                "priority": priority,
                "h_flip": h_flip,
                "v_flip": v_flip,
                "size": "large" if size_bit else "small",
            }

            from typing import cast

            self.oam_entries.append(cast(SpriteEntry, sprite_entry))
            self.tile_palette_map[actual_tile] = palette

            # For large sprites, map multiple tiles
            if size_bit:  # 16x16 sprite uses 4 tiles
                self.tile_palette_map[actual_tile + 1] = palette
                self.tile_palette_map[actual_tile + 16] = palette
                self.tile_palette_map[actual_tile + 17] = palette

    def build_vram_palette_map(self, base_vram_offset: int = 0x6000) -> None:
        """Build a map of VRAM offsets to palette numbers."""
        if base_vram_offset < 0 or base_vram_offset > 0x10000:
            raise ValueError(f"Invalid base VRAM offset: {hex(base_vram_offset)}")

        for tile_num, palette in self.tile_palette_map.items():
            if tile_num >= KIRBY_TILE_START and tile_num < KIRBY_TILE_END:
                tile_offset = tile_num - KIRBY_TILE_START
                if tile_offset < 0 or tile_offset > 0x7F:
                    continue

                try:
                    vram_word_addr = base_vram_offset + (tile_offset * 16)
                    if vram_word_addr > 0xFFFF:
                        continue

                    vram_byte_offset = vram_word_addr * 2
                    if vram_byte_offset < 0x20000:
                        self.vram_palette_map[vram_byte_offset] = palette
                        self.vram_palette_ranges.append(
                            (vram_byte_offset, vram_byte_offset + BYTES_PER_TILE_4BPP, palette)
                        )
                except (OverflowError, ValueError):
                    continue

        self.vram_palette_ranges.sort(key=lambda x: x[0])

    def get_palette_for_tile(self, tile_number: int) -> int | None:
        """Get palette number for a specific tile."""
        return self.tile_palette_map.get(tile_number)

    def get_palette_for_vram_offset(self, vram_offset: int) -> int | None:
        """Get palette number for a specific VRAM offset using binary search."""
        if not self.vram_palette_ranges:
            return None

        left, right = 0, len(self.vram_palette_ranges) - 1
        result_idx = -1

        while left <= right:
            mid = (left + right) // 2
            if self.vram_palette_ranges[mid][0] <= vram_offset:
                result_idx = mid
                left = mid + 1
            else:
                right = mid - 1

        if result_idx >= 0:
            start, end, palette = self.vram_palette_ranges[result_idx]
            if start <= vram_offset < end:
                return palette

        return None

    def get_active_palettes(self) -> list[int]:
        """Get list of palette numbers actually used by sprites."""
        return sorted(set(self.tile_palette_map.values()))

    def get_palette_usage_stats(self) -> dict[str, dict[int, int] | list[int] | int]:
        """Get statistics about palette usage."""
        palette_counts: dict[int, int] = {}
        for palette in self.tile_palette_map.values():
            palette_counts[palette] = palette_counts.get(palette, 0) + 1

        return {
            "palette_counts": palette_counts,
            "active_palettes": self.get_active_palettes(),
            "total_sprites": len(self.oam_entries),
            "visible_sprites": len([s for s in self.oam_entries if s["y"] < 224]),
        }

    def find_sprites_using_palette(self, palette_num: int) -> list[SpriteEntry]:
        """Find all sprite entries using a specific palette."""
        return [s for s in self.oam_entries if s["palette"] == palette_num]

    def find_sprites_in_region(self, x_start: int, y_start: int, x_end: int, y_end: int) -> list[SpriteEntry]:
        """Find sprites within a screen region."""
        return [s for s in self.oam_entries if x_start <= s["x"] <= x_end and y_start <= s["y"] <= y_end]


def create_tile_palette_map(oam_file: str, vram_base: int = KIRBY_VRAM_BASE) -> OAMPaletteMapper:
    """Convenience function to create palette mapping from OAM file.

    Args:
        oam_file: Path to OAM dump file
        vram_base: VRAM base word address (default: KIRBY_VRAM_BASE = 0x6000).
                  Do NOT divide by 2 - build_vram_palette_map handles conversion.

    Returns:
        Configured OAMPaletteMapper with tile→palette mappings
    """
    mapper = OAMPaletteMapper()
    mapper.parse_oam_dump(oam_file)
    mapper.build_vram_palette_map(vram_base)  # Pass word address directly
    return mapper
