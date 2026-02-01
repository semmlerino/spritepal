#!/usr/bin/env python3
"""Verify ROM tile injection by extracting and visualizing tiles at specific offsets.

Usage:
    # Compare original vs injected ROM at specific offsets
    python scripts/verify_rom_tiles.py --original roms/original.sfc --injected roms/injected.sfc --offsets 0x282018 0x282058

    # Extract tiles from a single ROM
    python scripts/verify_rom_tiles.py --rom roms/game.sfc --offsets 0x282018 --tiles 4 -o /tmp/tiles.png

    # Use offsets from a game frame in the mapping file
    python scripts/verify_rom_tiles.py --original roms/original.sfc --injected roms/injected.sfc --frame capture_1769108991
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


def read_tile_from_rom(rom_data: bytes, offset: int, smc_header: int = 0) -> bytes:
    """Read 32 bytes of raw 4bpp tile data from ROM."""
    actual_offset = offset + smc_header
    if actual_offset + 32 > len(rom_data):
        return b"\x00" * 32
    return rom_data[actual_offset : actual_offset + 32]


def tile_to_image(tile_data: bytes, palette: list[tuple[int, int, int]] | None = None) -> Image.Image:
    """Convert 32 bytes of 4bpp SNES tile data to an 8x8 RGBA image."""
    if palette is None:
        # Default grayscale palette
        palette = [(i * 17, i * 17, i * 17) for i in range(16)]

    img = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    pixels = img.load()

    if len(tile_data) < 32:
        return img

    for y in range(8):
        # SNES 4bpp: 2 bytes per row for planes 0-1, then 2 bytes for planes 2-3
        bp0 = tile_data[y * 2]
        bp1 = tile_data[y * 2 + 1]
        bp2 = tile_data[16 + y * 2]
        bp3 = tile_data[16 + y * 2 + 1]

        for x in range(8):
            bit = 7 - x
            color_idx = (
                ((bp0 >> bit) & 1) | (((bp1 >> bit) & 1) << 1) | (((bp2 >> bit) & 1) << 2) | (((bp3 >> bit) & 1) << 3)
            )

            if color_idx == 0:
                pixels[x, y] = (0, 0, 0, 0)  # Transparent
            else:
                r, g, b = palette[color_idx]
                pixels[x, y] = (r, g, b, 255)

    return img


def create_comparison_image(
    offsets: list[int],
    original_rom: bytes | None,
    injected_rom: bytes | None,
    tiles_per_offset: int = 1,
    scale: int = 4,
    smc_header: int = 0,
) -> Image.Image:
    """Create a side-by-side comparison image of tiles at given offsets."""
    # Calculate layout
    cols = 2 if (original_rom and injected_rom) else 1
    rows = len(offsets)
    tile_w = 8 * tiles_per_offset
    tile_h = 8

    # Add space for labels
    label_height = 20
    margin = 10

    img_w = (tile_w * scale * cols) + (margin * (cols + 1))
    img_h = (tile_h * scale * rows) + (margin * (rows + 1)) + label_height

    result = Image.new("RGBA", (img_w, img_h), (40, 40, 40, 255))

    # Rainbow palette for better visibility
    palette = [
        (0, 0, 0),  # 0: Black (transparent)
        (255, 255, 255),  # 1: White
        (255, 0, 0),  # 2: Red
        (0, 255, 0),  # 3: Green
        (0, 0, 255),  # 4: Blue
        (255, 255, 0),  # 5: Yellow
        (255, 0, 255),  # 6: Magenta
        (0, 255, 255),  # 7: Cyan
        (128, 128, 128),  # 8: Gray
        (255, 128, 0),  # 9: Orange
        (128, 0, 255),  # 10: Purple
        (0, 128, 255),  # 11: Light blue
        (255, 128, 128),  # 12: Pink
        (128, 255, 128),  # 13: Light green
        (128, 128, 255),  # 14: Light purple
        (255, 255, 128),  # 15: Light yellow
    ]

    for row, offset in enumerate(offsets):
        y_pos = margin + (row * (tile_h * scale + margin))

        # Original ROM (left column)
        if original_rom:
            x_pos = margin
            for t in range(tiles_per_offset):
                tile_data = read_tile_from_rom(original_rom, offset + t * 32, smc_header)
                tile_img = tile_to_image(tile_data, palette)
                tile_img = tile_img.resize((8 * scale, 8 * scale), Image.Resampling.NEAREST)
                result.paste(tile_img, (x_pos + t * 8 * scale, y_pos))

        # Injected ROM (right column)
        if injected_rom:
            x_pos = margin + (tile_w * scale + margin) if original_rom else margin
            for t in range(tiles_per_offset):
                tile_data = read_tile_from_rom(injected_rom, offset + t * 32, smc_header)
                tile_img = tile_to_image(tile_data, palette)
                tile_img = tile_img.resize((8 * scale, 8 * scale), Image.Resampling.NEAREST)
                result.paste(tile_img, (x_pos + t * 8 * scale, y_pos))

    return result


def get_offsets_from_mapping(mapping_path: Path, frame_id: str) -> list[int]:
    """Extract ROM offsets for a game frame from the mapping file."""
    with open(mapping_path) as f:
        data = json.load(f)

    for frame in data.get("game_frames", []):
        if frame.get("id") == frame_id:
            return frame.get("rom_offsets", [])

    raise ValueError(f"Game frame '{frame_id}' not found in mapping file")


def detect_smc_header(rom_data: bytes) -> int:
    """Detect if ROM has SMC header (512 bytes if size % 0x8000 == 512)."""
    if len(rom_data) % 0x8000 == 512:
        return 512
    return 0


def main():
    parser = argparse.ArgumentParser(description="Verify ROM tile injection")
    parser.add_argument("--rom", type=Path, help="Single ROM to extract from")
    parser.add_argument("--original", type=Path, help="Original ROM for comparison")
    parser.add_argument("--injected", type=Path, help="Injected ROM for comparison")
    parser.add_argument("--offsets", type=str, nargs="+", help="ROM offsets (hex, e.g., 0x282018)")
    parser.add_argument("--frame", type=str, help="Game frame ID to get offsets from mapping")
    parser.add_argument(
        "--mapping", type=Path, default=Path("mapping.spritepal-mapping.json"), help="Mapping file path"
    )
    parser.add_argument("--tiles", type=int, default=1, help="Tiles per offset to display")
    parser.add_argument("--scale", type=int, default=8, help="Scale factor for display")
    parser.add_argument("-o", "--output", type=Path, default=Path("/tmp/tile_verify.png"), help="Output image path")

    args = parser.parse_args()

    # Get offsets
    if args.frame:
        offsets = get_offsets_from_mapping(args.mapping, args.frame)
        print(f"Offsets from frame '{args.frame}': {[f'0x{o:X}' for o in offsets]}")
    elif args.offsets:
        offsets = [int(o, 16) if o.startswith("0x") else int(o) for o in args.offsets]
    else:
        parser.error("Must specify --offsets or --frame")

    # Load ROM(s)
    original_rom = None
    injected_rom = None

    if args.rom:
        original_rom = args.rom.read_bytes()
        print(f"Loaded ROM: {args.rom} ({len(original_rom)} bytes)")
    else:
        if args.original:
            original_rom = args.original.read_bytes()
            print(f"Loaded original: {args.original} ({len(original_rom)} bytes)")
        if args.injected:
            injected_rom = args.injected.read_bytes()
            print(f"Loaded injected: {args.injected} ({len(injected_rom)} bytes)")

    if not original_rom and not injected_rom:
        parser.error("Must specify --rom or --original/--injected")

    # Detect SMC header
    smc_header = detect_smc_header(original_rom or injected_rom)
    if smc_header:
        print(f"Detected SMC header: {smc_header} bytes")

    # Create comparison image
    img = create_comparison_image(
        offsets=offsets,
        original_rom=original_rom,
        injected_rom=injected_rom,
        tiles_per_offset=args.tiles,
        scale=args.scale,
        smc_header=smc_header,
    )

    # Save
    img.save(args.output, "PNG")
    print(f"Saved: {args.output}")

    # Print offset info
    print("\nOffset details:")
    for offset in offsets:
        print(f"  0x{offset:06X} ({offset})")
        if original_rom:
            tile = read_tile_from_rom(original_rom, offset, smc_header)
            print(f"    Original: {tile[:16].hex()}...")
        if injected_rom:
            tile = read_tile_from_rom(injected_rom, offset, smc_header)
            print(f"    Injected: {tile[:16].hex()}...")


if __name__ == "__main__":
    main()
