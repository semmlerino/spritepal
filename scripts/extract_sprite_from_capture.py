#!/usr/bin/env python3
"""
CLI tool to extract sprites from Mesen 2 capture files.

Usage:
    python extract_sprite_from_capture.py [capture.json] [--output-dir OUTPUT]

This tool:
1. Reads a Mesen 2 capture JSON file
2. Maps OAM entries to ROM offsets using tile hash database
3. Renders and saves the sprites as PNG files
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from PIL import Image

from core.hal_compression import HALCompressor
from core.mesen_integration import (
    CaptureResult,
    MesenCaptureParser,
    TileHashDatabase,
)
from core.mesen_integration.capture_to_rom_mapper import CaptureToROMMapper
from core.tile_renderer import TileRenderer


def detect_vram_bug(capture: CaptureResult) -> bool:
    """Check if capture has the VRAM word-addressing bug."""
    if not capture.entries:
        return False

    for entry in capture.entries[:5]:  # Check first few
        if not entry.tiles:
            continue
        tile_hex = entry.tiles[0].data_hex
        # Bug pattern: even bytes are 00, 01, 02, 03... (loop index)
        is_buggy = all(tile_hex[i * 2 : i * 2 + 2] == f"{i:02X}" for i in range(min(8, len(tile_hex) // 2)))
        if is_buggy:
            return True

    return False


def render_oam_entry_directly(entry, tile_renderer: TileRenderer) -> Image.Image | None:
    """Render OAM entry directly from its captured VRAM tile data."""
    if not entry.tiles:
        return None

    # Get dimensions
    width = entry.width
    height = entry.height
    tiles_wide = width // 8
    height // 8

    # Render each tile and compose
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    for i, tile in enumerate(entry.tiles):
        tile_bytes = tile.data_bytes
        if len(tile_bytes) != 32:
            continue

        # Render single 8x8 tile
        tile_img = tile_renderer.render_tiles(tile_bytes, 1, 1, palette_index=None)
        if tile_img is None:
            continue

        # Position in the sprite
        tile_x = (i % tiles_wide) * 8
        tile_y = (i // tiles_wide) * 8

        canvas.paste(tile_img, (tile_x, tile_y))

    # Apply flips
    if entry.flip_h:
        canvas = canvas.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if entry.flip_v:
        canvas = canvas.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

    return canvas


def compose_sprite_group(
    entries: list,
    tile_renderer: TileRenderer,
) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """Compose multiple OAM entries into a single sprite image."""
    if not entries:
        return Image.new("RGBA", (8, 8), (0, 0, 0, 0)), (0, 0, 8, 8)

    # Calculate bounding box
    min_x = min(e.x for e in entries)
    min_y = min(e.y for e in entries)
    max_x = max(e.x + e.width for e in entries)
    max_y = max(e.y + e.height for e in entries)

    # Create canvas
    canvas_width = max_x - min_x
    canvas_height = max_y - min_y
    canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))

    # Render and place each entry
    for entry in entries:
        tile_img = render_oam_entry_directly(entry, tile_renderer)
        if tile_img is None:
            continue

        paste_x = entry.x - min_x
        paste_y = entry.y - min_y
        canvas.paste(tile_img, (paste_x, paste_y), tile_img)

    return canvas, (min_x, min_y, max_x, max_y)


def group_nearby_sprites(entries: list, distance_threshold: int = 32) -> list[list]:
    """Group OAM entries that are close together (likely same game object)."""
    if not entries:
        return []

    # Filter to visible sprites (not at y=224 which is off-screen)
    visible = [e for e in entries if e.y != 224 and e.y < 200]
    if not visible:
        visible = entries

    # Simple clustering by proximity
    groups: list[list] = []
    used = set()

    for entry in visible:
        if id(entry) in used:
            continue

        # Start new group
        group = [entry]
        used.add(id(entry))

        # Find nearby entries
        for other in visible:
            if id(other) in used:
                continue

            # Check distance
            dx = abs((entry.x + entry.width // 2) - (other.x + other.width // 2))
            dy = abs((entry.y + entry.height // 2) - (other.y + other.height // 2))

            if dx < distance_threshold and dy < distance_threshold:
                group.append(other)
                used.add(id(other))

        if len(group) > 0:
            groups.append(group)

    return groups


def main():
    parser = argparse.ArgumentParser(description="Extract sprites from Mesen 2 capture files")
    parser.add_argument("capture_file", nargs="?", help="Path to capture JSON file")
    parser.add_argument("--output-dir", "-o", default="extracted_sprites", help="Output directory for sprites")
    parser.add_argument("--rom", "-r", help="Path to ROM file (for hash database)")
    parser.add_argument("--database", "-d", help="Path to pre-built tile hash database")
    parser.add_argument("--group-threshold", "-g", type=int, default=32, help="Distance threshold for grouping sprites")
    parser.add_argument("--individual", "-i", action="store_true", help="Also save individual OAM entries")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    # Find capture file
    base_dir = Path(__file__).parent.parent
    if args.capture_file:
        capture_path = Path(args.capture_file)
    else:
        capture_path = base_dir / "mesen2_exchange" / "test_capture.json"

    if not capture_path.exists():
        print(f"ERROR: Capture file not found: {capture_path}")
        return 1

    # Find ROM
    rom_path = Path(args.rom) if args.rom else base_dir / "roms" / "Kirby Super Star (USA).sfc"

    # Output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("SPRITE EXTRACTION FROM MESEN 2 CAPTURE")
    print("=" * 60)
    print(f"Capture: {capture_path}")
    print(f"Output:  {output_dir}")

    # Parse capture
    print("\n[1] Parsing capture...")
    parser_obj = MesenCaptureParser()
    capture = parser_obj.parse_file(capture_path)
    print(f"    Found {len(capture.entries)} OAM entries")
    print(f"    Frame: {capture.frame}")

    # Check for bug
    if detect_vram_bug(capture):
        print("\n    ⚠️  WARNING: Capture has VRAM word-addressing bug!")
        print("       The tile data is corrupted (even bytes are loop indices).")
        print("       Regenerate capture with the fixed Lua script.")
        print("       Extraction will continue but sprites may look wrong.\n")

    # Initialize renderer
    tile_renderer = TileRenderer()

    # Try to map to ROM offsets if ROM available
    rom_offsets_found: dict[int, int] = {}
    if rom_path.exists():
        print("\n[2] Mapping to ROM offsets...")
        db_path = Path(args.database) if args.database else base_dir / "mesen2_exchange" / "tile_hash_database.json"

        mapper = CaptureToROMMapper(rom_path, db_path)
        if db_path.exists():
            print(f"    Loading database from {db_path}")
            mapper.build_database()
        else:
            print("    Building tile hash database (this may take a moment)...")
            mapper.build_database()

        result = mapper.map_capture(capture)
        rom_offsets_found = result.rom_offset_scores or result.rom_offset_summary

        if rom_offsets_found:
            print(f"    Matched {len(result.mapped_entries) - result.unmapped_count} entries to ROM offsets:")
            if result.rom_offset_scores:
                for offset, score in list(result.rom_offset_scores.items())[:5]:
                    print(f"      0x{offset:06X}: {score:.2f} score")
                if result.ambiguous:
                    print(f"      Ambiguous: {result.ambiguity_note}")
            else:
                for offset, count in list(result.rom_offset_summary.items())[:5]:
                    print(f"      0x{offset:06X}: {count} tiles")
        else:
            print("    No ROM matches found (verify capture integrity, ROM header, and DB coverage)")
    else:
        print("\n[2] ROM not found - skipping ROM offset mapping")

    # Group sprites
    print("\n[3] Grouping sprites by proximity...")
    groups = group_nearby_sprites(capture.entries, args.group_threshold)
    print(f"    Found {len(groups)} sprite groups")

    # Render groups
    print("\n[4] Rendering sprite groups...")
    saved_count = 0

    for i, group in enumerate(groups):
        if not group:
            continue

        sprite_img, bbox = compose_sprite_group(group, tile_renderer)

        # Skip tiny or empty sprites
        if sprite_img.width < 8 or sprite_img.height < 8:
            continue

        # Check if sprite has any non-transparent content
        if sprite_img.getextrema()[3][1] == 0:  # Alpha max is 0
            continue

        # Generate filename
        x, y = bbox[0], bbox[1]
        filename = f"sprite_group_{i:03d}_at_{x}_{y}_{sprite_img.width}x{sprite_img.height}.png"
        filepath = output_dir / filename

        sprite_img.save(filepath)
        saved_count += 1

        if args.verbose:
            print(f"    Saved: {filename} ({len(group)} OAM entries)")

    print(f"    Saved {saved_count} sprite groups")

    # Optionally save individual entries
    if args.individual:
        print("\n[5] Saving individual OAM entries...")
        individual_dir = output_dir / "individual"
        individual_dir.mkdir(exist_ok=True)

        for entry in capture.entries:
            if entry.y == 224:  # Skip off-screen
                continue

            tile_img = render_oam_entry_directly(entry, tile_renderer)
            if tile_img is None:
                continue

            filename = f"oam_{entry.id:03d}_at_{entry.x}_{entry.y}_{entry.width}x{entry.height}.png"
            filepath = individual_dir / filename
            tile_img.save(filepath)

        print(f"    Saved to {individual_dir}")

    # Summary
    print("\n" + "=" * 60)
    print("EXTRACTION COMPLETE")
    print("=" * 60)
    print(f"Output directory: {output_dir}")
    print(f"Sprite groups saved: {saved_count}")

    if rom_offsets_found:
        print("\nDetected ROM sources:")
        for offset, count in list(rom_offsets_found.items())[:10]:
            print(f"  0x{offset:06X}: {count} tiles")

    return 0


if __name__ == "__main__":
    sys.exit(main())
