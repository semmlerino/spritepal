#!/usr/bin/env python3
"""Sprite ROM Mapper - Finds ROM addresses for sprite tiles from VRAM/OAM dumps.

This tool automates the process of tracing SNES sprite tiles back to their
ROM addresses by:
1. Parsing OAM dumps to identify sprite tile indices
2. Extracting raw 4bpp tile data from VRAM dumps
3. Searching for exact byte matches in the ROM file
4. Building a complete address map

Usage:
    python sprite_rom_mapper.py <rom_path> <dump_dir> [options]

Examples:
    # Map Dedede F71 sprites (palette 7)
    python sprite_rom_mapper.py roms/Kirby.sfc DededeDMP --palette 7

    # Map all sprites from a dump
    python sprite_rom_mapper.py roms/Kirby.sfc DededeDMP/archive --all-palettes

    # Export results to JSON
    python sprite_rom_mapper.py roms/Kirby.sfc DededeDMP -o dedede_map.json
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class OAMSprite:
    """Parsed OAM sprite entry."""

    index: int
    x: int
    y: int
    tile: int
    palette: int
    priority: int
    h_flip: bool
    v_flip: bool
    size_large: bool  # From high table

    @property
    def is_visible(self) -> bool:
        """Check if sprite is likely visible (not offscreen)."""
        # Sprites at y=224+ or x=256+ are typically offscreen
        return self.y < 224 and self.x < 256


@dataclass
class TileMatch:
    """A tile found in ROM."""

    vram_addr: int  # Word address in VRAM
    rom_offset: int  # Byte offset in ROM file
    tile_data: bytes  # 32-byte 4bpp tile


@dataclass
class SpriteROMMap:
    """Complete mapping of sprite tiles to ROM addresses."""

    frame_name: str
    palette: int
    oam_tiles: list[int]  # OAM tile indices used
    matches: dict[int, TileMatch]  # vram_addr -> match
    vram_base: int  # OBSEL-derived VRAM base
    not_found: list[int] = field(default_factory=list)  # VRAM addrs not in ROM


def parse_oam(oam_data: bytes) -> list[OAMSprite]:
    """Parse OAM dump into sprite entries.

    OAM structure:
    - Low table: 512 bytes (128 sprites × 4 bytes)
    - High table: 32 bytes (128 sprites × 2 bits each)
    """
    sprites = []
    low_table = oam_data[:512]
    high_table = oam_data[512:544]

    for i in range(128):
        offset = i * 4
        x_low = low_table[offset]
        y = low_table[offset + 1]
        tile = low_table[offset + 2]
        attr = low_table[offset + 3]

        # High table: 2 bits per sprite
        high_byte = high_table[i // 4]
        high_bits = (high_byte >> ((i % 4) * 2)) & 0x03
        x_high = high_bits & 0x01
        size_large = bool(high_bits & 0x02)

        # Combine X coordinate (9 bits)
        x = x_low | (x_high << 8)
        if x >= 256:
            x -= 512  # Sign extend

        # Parse attributes
        palette = (attr >> 1) & 0x07
        priority = (attr >> 4) & 0x03
        h_flip = bool(attr & 0x40)
        v_flip = bool(attr & 0x80)

        sprites.append(
            OAMSprite(
                index=i,
                x=x,
                y=y,
                tile=tile,
                palette=palette,
                priority=priority,
                h_flip=h_flip,
                v_flip=v_flip,
                size_large=size_large,
            )
        )

    return sprites


def get_16x16_tile_indices(base_tile: int) -> list[int]:
    """Get the 4 tile indices for a 16×16 sprite.

    SNES 16×16 layout:
    [t+0 ] [t+1 ]
    [t+16] [t+17]
    """
    return [base_tile, base_tile + 1, base_tile + 16, base_tile + 17]


def extract_vram_tile(vram_data: bytes, vram_word: int, tile_base: int = 0) -> bytes:
    """Extract a 32-byte 4bpp tile from VRAM.

    Args:
        vram_data: Raw VRAM dump (64KB)
        vram_word: VRAM word address
        tile_base: OBSEL tile base in words (0x0000, 0x2000, 0x4000, 0x6000)
    """
    # Each tile is 32 bytes (8×8 pixels × 4bpp)
    byte_addr = vram_word * 2
    return vram_data[byte_addr : byte_addr + 32]


def search_rom_for_tile(rom_data: bytes, tile: bytes) -> int | None:
    """Search ROM for exact tile match.

    Returns:
        ROM file offset if found, None otherwise.
    """
    if len(tile) != 32:
        return None
    if tile == b"\x00" * 32:
        return None  # Skip empty tiles

    pos = rom_data.find(tile)
    return pos if pos >= 0 else None


def get_obsel_base(obsel: int) -> tuple[int, int]:
    """Parse OBSEL register for tile base addresses.

    OBSEL ($2101):
    - Bits 0-2: Object size
    - Bits 3-4: Name select (gap between name tables)
    - Bits 5-7: Name base address

    Returns:
        (name_base_words, name_select_gap)
    """
    name_base = (obsel >> 5) & 0x07
    name_select = (obsel >> 3) & 0x03

    # Name base is in 16KB units (0x4000 bytes = 0x2000 words)
    base_words = name_base * 0x2000

    # Name select adds gap for second name table
    gap = name_select * 0x1000

    return base_words, gap


def calculate_vram_address(tile_idx: int, obsel: int = 0x63) -> int:
    """Calculate VRAM word address for a tile index.

    Args:
        tile_idx: OAM tile index (0-255)
        obsel: OBSEL register value (default 0x63 for Kirby gameplay)

    Returns:
        VRAM word address
    """
    name_base, name_gap = get_obsel_base(obsel)

    # Tile index to VRAM offset (each tile = 16 words)
    tile_offset = tile_idx * 16

    # Apply name base
    vram_word = name_base + tile_offset

    return vram_word


def map_sprites_to_rom(
    rom_path: Path,
    vram_path: Path,
    oam_path: Path,
    palette_filter: int | None = None,
    obsel: int = 0x63,
) -> SpriteROMMap:
    """Map sprite tiles from dumps to ROM addresses.

    Args:
        rom_path: Path to ROM file
        vram_path: Path to VRAM dump
        oam_path: Path to OAM dump
        palette_filter: Only include sprites with this palette (None = all)
        obsel: OBSEL register value for VRAM addressing

    Returns:
        SpriteROMMap with all found tiles
    """
    # Load files
    rom_data = rom_path.read_bytes()
    vram_data = vram_path.read_bytes()
    oam_data = oam_path.read_bytes()

    # Parse OAM
    sprites = parse_oam(oam_data)

    # Filter by palette if specified
    if palette_filter is not None:
        sprites = [s for s in sprites if s.palette == palette_filter]

    # Filter visible sprites only
    sprites = [s for s in sprites if s.is_visible]

    # Collect unique tile indices
    oam_tiles = set()
    for sprite in sprites:
        if sprite.size_large:
            oam_tiles.update(get_16x16_tile_indices(sprite.tile))
        else:
            oam_tiles.add(sprite.tile)

    oam_tiles = sorted(oam_tiles)

    # Map tiles to VRAM addresses and search ROM
    matches: dict[int, TileMatch] = {}
    not_found: list[int] = []
    name_base, _ = get_obsel_base(obsel)

    for tile_idx in oam_tiles:
        vram_word = calculate_vram_address(tile_idx, obsel)
        tile_data = extract_vram_tile(vram_data, vram_word)

        rom_offset = search_rom_for_tile(rom_data, tile_data)

        if rom_offset is not None:
            matches[vram_word] = TileMatch(
                vram_addr=vram_word,
                rom_offset=rom_offset,
                tile_data=tile_data,
            )
        # Skip empty tiles from not_found
        elif tile_data != b"\x00" * 32:
            not_found.append(vram_word)

    # Build result
    frame_name = vram_path.stem.replace("_VRAM", "")

    return SpriteROMMap(
        frame_name=frame_name,
        palette=palette_filter if palette_filter is not None else -1,
        oam_tiles=oam_tiles,
        matches=matches,
        vram_base=name_base,
        not_found=not_found,
    )


def format_address_map(sprite_map: SpriteROMMap) -> str:
    """Format sprite map as human-readable text."""
    lines = [
        f"=== Sprite ROM Map: {sprite_map.frame_name} ===",
        f"Palette: {sprite_map.palette}",
        f"VRAM Base: 0x{sprite_map.vram_base:04X}",
        f"OAM Tiles: {sprite_map.oam_tiles}",
        f"Found: {len(sprite_map.matches)}/{len(sprite_map.oam_tiles) + len(sprite_map.not_found)} tiles",
        "",
    ]

    if sprite_map.matches:
        # Sort by ROM offset
        sorted_matches = sorted(sprite_map.matches.values(), key=lambda m: m.rom_offset)

        lines.append("ROM Addresses:")
        min_rom = min(m.rom_offset for m in sorted_matches)
        max_rom = max(m.rom_offset for m in sorted_matches)
        lines.append(f"  Range: 0x{min_rom:06X} - 0x{max_rom:06X}")
        lines.append("")

        for match in sorted_matches:
            lines.append(f"  VRAM 0x{match.vram_addr:04X} -> ROM 0x{match.rom_offset:06X}")

    if sprite_map.not_found:
        lines.append("")
        lines.append(f"Not found in ROM: {len(sprite_map.not_found)} tiles")
        for addr in sprite_map.not_found:
            lines.append(f"  VRAM 0x{addr:04X}")

    return "\n".join(lines)


def export_to_json(sprite_map: SpriteROMMap) -> dict:
    """Export sprite map to JSON-serializable dict."""
    return {
        "frame_name": sprite_map.frame_name,
        "palette": sprite_map.palette,
        "vram_base": sprite_map.vram_base,
        "oam_tiles": sprite_map.oam_tiles,
        "found_count": len(sprite_map.matches),
        "total_tiles": len(sprite_map.oam_tiles),
        "rom_range": {
            "min": min((m.rom_offset for m in sprite_map.matches.values()), default=0),
            "max": max((m.rom_offset for m in sprite_map.matches.values()), default=0),
        },
        "mappings": [
            {
                "vram_word": m.vram_addr,
                "vram_byte": m.vram_addr * 2,
                "rom_offset": m.rom_offset,
                "rom_hex": f"0x{m.rom_offset:06X}",
            }
            for m in sorted(sprite_map.matches.values(), key=lambda m: m.rom_offset)
        ],
        "not_found": [f"0x{addr:04X}" for addr in sprite_map.not_found],
    }


def find_dump_files(dump_dir: Path) -> dict[str, Path]:
    """Find VRAM, OAM, CGRAM dumps in directory."""
    files = {}

    for f in dump_dir.iterdir():
        name_lower = f.name.lower()
        if "vram" in name_lower and f.suffix == ".dmp":
            files["vram"] = f
        elif "oam" in name_lower and f.suffix == ".dmp":
            files["oam"] = f
        elif "cgram" in name_lower and f.suffix == ".dmp":
            files["cgram"] = f

    return files


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Map sprite tiles from VRAM/OAM dumps to ROM addresses",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Map palette 7 sprites (Dedede)
    python sprite_rom_mapper.py roms/Kirby.sfc DededeDMP --palette 7

    # Map all visible sprites
    python sprite_rom_mapper.py roms/Kirby.sfc DededeDMP --all-palettes

    # Export to JSON
    python sprite_rom_mapper.py roms/Kirby.sfc DededeDMP -p 7 -o map.json
        """,
    )

    parser.add_argument("rom", type=Path, help="Path to ROM file")
    parser.add_argument("dump_dir", type=Path, help="Directory containing *_VRAM.dmp, *_OAM.dmp files")
    parser.add_argument("-p", "--palette", type=int, help="Filter by palette index (0-7)")
    parser.add_argument("--all-palettes", action="store_true", help="Include all palettes")
    parser.add_argument("--obsel", type=lambda x: int(x, 0), default=0x63, help="OBSEL register value (default: 0x63)")
    parser.add_argument("-o", "--output", type=Path, help="Output JSON file")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show tile data")

    args = parser.parse_args()

    # Validate paths
    if not args.rom.exists():
        print(f"Error: ROM file not found: {args.rom}")
        return 1

    if not args.dump_dir.exists():
        print(f"Error: Dump directory not found: {args.dump_dir}")
        return 1

    # Find dump files
    dump_files = find_dump_files(args.dump_dir)
    if "vram" not in dump_files:
        print(f"Error: No *_VRAM.dmp file found in {args.dump_dir}")
        return 1
    if "oam" not in dump_files:
        print(f"Error: No *_OAM.dmp file found in {args.dump_dir}")
        return 1

    print(f"ROM: {args.rom}")
    print(f"VRAM: {dump_files['vram']}")
    print(f"OAM: {dump_files['oam']}")
    print(f"OBSEL: 0x{args.obsel:02X}")
    print()

    # Determine palette filter
    palette_filter = None
    if args.palette is not None:
        palette_filter = args.palette
    elif not args.all_palettes:
        # Default to palette 7 if not specified
        palette_filter = 7
        print("(Defaulting to palette 7 - use --all-palettes for all)")

    # Map sprites
    sprite_map = map_sprites_to_rom(
        rom_path=args.rom,
        vram_path=dump_files["vram"],
        oam_path=dump_files["oam"],
        palette_filter=palette_filter,
        obsel=args.obsel,
    )

    # Output results
    print(format_address_map(sprite_map))

    # Export JSON if requested
    if args.output:
        json_data = export_to_json(sprite_map)
        args.output.write_text(json.dumps(json_data, indent=2))
        print(f"\nExported to: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
