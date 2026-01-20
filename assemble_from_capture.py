#!/usr/bin/env python3
"""
Assemble a full sprite from Mesen2 capture JSON.

This script reads a capture file containing all OAM entries and their positions,
then assembles them into a single composite image exactly as they appear in-game.
"""

import argparse
import json
from pathlib import Path

from PIL import Image

from core.tile_renderer import TileRenderer


def bytes_from_hex(hex_str: str) -> bytes:
    """Convert hex string to bytes."""
    return bytes.fromhex(hex_str)


def render_entry(entry: dict, renderer: TileRenderer, palette: list[int] | None = None) -> Image.Image | None:
    """Render a single OAM entry from its tile data."""
    if "tiles" not in entry and "tile_data" not in entry:
        return None

    tiles = entry.get("tiles") or entry.get("tile_data", [])
    if not tiles:
        return None

    width = entry.get("width", 8)
    height = entry.get("height", 8)

    # Create canvas for this sprite
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    for tile_info in tiles:
        hex_data = tile_info.get("data_hex", "")
        if not hex_data or len(hex_data) < 64:  # 32 bytes = 64 hex chars
            continue

        tile_bytes = bytes_from_hex(hex_data)
        tile_img = renderer.render_tiles(tile_bytes, 1, 1, palette_index=None)

        if tile_img:
            pos_x = tile_info.get("pos_x", 0) * 8
            pos_y = tile_info.get("pos_y", 0) * 8
            canvas.paste(tile_img, (pos_x, pos_y), tile_img)

    # Apply flips
    if entry.get("flip_h"):
        canvas = canvas.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if entry.get("flip_v"):
        canvas = canvas.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

    return canvas


def assemble_sprite(capture_data: dict, renderer: TileRenderer, filter_func=None) -> tuple[Image.Image, dict]:
    """
    Assemble all OAM entries into a single composite image.

    Args:
        capture_data: Parsed JSON capture data
        renderer: TileRenderer instance
        filter_func: Optional function to filter entries (return True to include)

    Returns:
        Tuple of (composite image, metadata dict)
    """
    entries = capture_data.get("entries", [])
    if not entries:
        return None, {}

    # Filter entries if needed
    if filter_func:
        entries = [e for e in entries if filter_func(e)]

    if not entries:
        return None, {}

    # Find bounding box of all sprites
    min_x = min(e["x"] for e in entries)
    min_y = min(e["y"] for e in entries)
    max_x = max(e["x"] + e.get("width", 8) for e in entries)
    max_y = max(e["y"] + e.get("height", 8) for e in entries)

    # Create canvas
    canvas_width = max_x - min_x
    canvas_height = max_y - min_y

    if canvas_width <= 0 or canvas_height <= 0:
        return None, {}

    canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))

    # Sort by OAM priority (higher OAM index = drawn later = on top)
    # Actually, lower priority value = drawn first (behind), but OAM index matters too
    # For simplicity, just use OAM index order (reverse to draw lower indices first)
    sorted_entries = sorted(entries, key=lambda e: e.get("id", 0))

    placed_count = 0
    for entry in sorted_entries:
        entry_img = render_entry(entry, renderer)
        if entry_img:
            paste_x = entry["x"] - min_x
            paste_y = entry["y"] - min_y
            canvas.paste(entry_img, (paste_x, paste_y), entry_img)
            placed_count += 1

    metadata = {
        "total_entries": len(entries),
        "placed_entries": placed_count,
        "bounds": {"min_x": min_x, "min_y": min_y, "max_x": max_x, "max_y": max_y},
        "size": {"width": canvas_width, "height": canvas_height},
        "frame": capture_data.get("frame", 0),
    }

    return canvas, metadata


def main():
    parser = argparse.ArgumentParser(description="Assemble sprites from Mesen2 capture JSON")
    parser.add_argument("capture_file", help="Path to capture JSON file")
    parser.add_argument("--output", "-o", default="assembled_sprite.png", help="Output filename")
    parser.add_argument("--min-x", type=int, help="Filter: minimum X position")
    parser.add_argument("--max-x", type=int, help="Filter: maximum X position")
    parser.add_argument("--min-y", type=int, help="Filter: minimum Y position")
    parser.add_argument("--max-y", type=int, help="Filter: maximum Y position")
    parser.add_argument("--exclude-hud", action="store_true", help="Exclude HUD sprites (y < 32)")
    parser.add_argument("--large-only", action="store_true", help="Only include large sprites (16x16+)")
    parser.add_argument("--list", action="store_true", help="List all entries without assembling")
    args = parser.parse_args()

    # Load capture
    capture_path = Path(args.capture_file)
    if not capture_path.exists():
        print(f"Error: File not found: {capture_path}")
        return

    with open(capture_path) as f:
        capture_data = json.load(f)

    print(f"Loaded capture: {capture_path.name}")
    print(f"  Frame: {capture_data.get('frame', 'unknown')}")
    print(f"  Entries: {len(capture_data.get('entries', []))}")

    entries = capture_data.get("entries", [])

    if args.list:
        print("\nOAM Entries:")
        print("-" * 80)
        for entry in entries:
            w = entry.get("width", 8)
            h = entry.get("height", 8)
            flip_h = "H" if entry.get("flip_h") else "-"
            flip_v = "V" if entry.get("flip_v") else "-"
            print(
                f"  [{entry['id']:3d}] pos=({entry['x']:4d},{entry['y']:3d}) size={w:2d}x{h:2d} "
                f"tile={entry['tile']:3d} pal={entry.get('palette', 0)} flip={flip_h}{flip_v}"
            )
        return

    # Build filter function
    def entry_filter(e):
        if args.exclude_hud and e["y"] < 32:
            return False
        if args.large_only and e.get("width", 8) < 16:
            return False
        if args.min_x is not None and e["x"] < args.min_x:
            return False
        if args.max_x is not None and e["x"] > args.max_x:
            return False
        if args.min_y is not None and e["y"] < args.min_y:
            return False
        if args.max_y is not None and e["y"] > args.max_y:
            return False
        return True

    renderer = TileRenderer()
    result, metadata = assemble_sprite(capture_data, renderer, entry_filter)

    if result:
        result.save(args.output)
        print(f"\nAssembled sprite saved to: {args.output}")
        print(f"  Size: {metadata['size']['width']}x{metadata['size']['height']} pixels")
        print(f"  Entries used: {metadata['placed_entries']}/{metadata['total_entries']}")
        print(
            f"  Bounds: ({metadata['bounds']['min_x']}, {metadata['bounds']['min_y']}) to "
            f"({metadata['bounds']['max_x']}, {metadata['bounds']['max_y']})"
        )
    else:
        print("Error: Could not assemble sprite (no valid entries)")


if __name__ == "__main__":
    main()
