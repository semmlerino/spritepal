#!/usr/bin/env python3
"""
Extract sprite from ROM at specified offset using HAL decompression.

Usage:
    uv run python scripts/extract_rom_sprite.py --rom <rom_path> --offset <hex_offset> --output <output_dir> --name <sprite_name>

Example:
    uv run python scripts/extract_rom_sprite.py \
        --rom "roms/Kirby Super Star (USA).sfc" \
        --offset 0x29B299 \
        --output extracted_sprites/poppy_bros_sr/ \
        --name poppy_bros_sr
"""

import argparse
import json
import sys
from pathlib import Path


def convert_4bpp_to_png(tile_data: bytes, output_path: Path, tiles_per_row: int = 16) -> int:
    """Convert 4bpp tile data to grayscale PNG."""
    import numpy as np
    from PIL import Image

    # Each tile is 32 bytes (8x8 pixels, 4bpp)
    tile_size = 32
    tile_count = len(tile_data) // tile_size

    if tile_count == 0:
        raise ValueError("No complete tiles in data")

    # Calculate image dimensions
    rows = (tile_count + tiles_per_row - 1) // tiles_per_row
    img_width = tiles_per_row * 8
    img_height = rows * 8

    # Create image array
    img_array = np.zeros((img_height, img_width), dtype=np.uint8)

    for tile_idx in range(tile_count):
        tile_offset = tile_idx * tile_size
        tile_bytes = tile_data[tile_offset : tile_offset + tile_size]

        if len(tile_bytes) < tile_size:
            break

        # Decode 4bpp tile
        tile_x = (tile_idx % tiles_per_row) * 8
        tile_y = (tile_idx // tiles_per_row) * 8

        for row in range(8):
            # 4bpp: bitplanes 0,1 in first 16 bytes, bitplanes 2,3 in next 16 bytes
            bp0 = tile_bytes[row * 2]
            bp1 = tile_bytes[row * 2 + 1]
            bp2 = tile_bytes[16 + row * 2]
            bp3 = tile_bytes[16 + row * 2 + 1]

            for col in range(8):
                bit = 7 - col
                pixel = (
                    ((bp0 >> bit) & 1)
                    | (((bp1 >> bit) & 1) << 1)
                    | (((bp2 >> bit) & 1) << 2)
                    | (((bp3 >> bit) & 1) << 3)
                )
                # Scale 0-15 to 0-255
                img_array[tile_y + row, tile_x + col] = pixel * 17

    # Create and save image
    img = Image.fromarray(img_array, mode="L")
    img.save(output_path)

    return tile_count


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract sprite from ROM at specified offset using HAL decompression")
    parser.add_argument("--rom", "-r", required=True, help="Path to ROM file")
    parser.add_argument(
        "--offset",
        "-o",
        required=True,
        help=(
            "ROM offset in hexadecimal (e.g., 0x29B299). "
            "By default, assumes this is a ROM address (adds 512 for .smc header). "
            "If using Mesen's 'FILE:' offset output, use --no-header-adjust."
        ),
    )
    parser.add_argument("--output", "-d", required=True, help="Output directory for extracted files")
    parser.add_argument("--name", "-n", default="sprite", help="Sprite name (default: sprite)")
    parser.add_argument(
        "--no-header-adjust",
        action="store_true",
        help=(
            "Don't adjust offset for SMC header (use raw file offset). "
            "Use this when providing Mesen 'FILE: 0xNNNNNN' offsets, which already include the header."
        ),
    )

    args = parser.parse_args()

    # Parse offset
    offset_str = args.offset
    if offset_str.startswith("0x") or offset_str.startswith("0X"):
        offset = int(offset_str, 16)
    else:
        try:
            offset = int(offset_str, 16)
        except ValueError:
            offset = int(offset_str)

    # Validate ROM exists
    rom_path = Path(args.rom)
    if not rom_path.exists():
        print(f"ERROR: ROM file not found: {rom_path}")
        return 1

    # Detect SMC header and adjust offset
    file_size = rom_path.stat().st_size
    smc_offset = 512 if file_size % 1024 == 512 else 0

    if smc_offset and not args.no_header_adjust:
        file_offset = offset + smc_offset
        print(f"Detected {smc_offset}-byte SMC header")
        print(f"Adjusting offset: 0x{offset:06X} (ROM) -> 0x{file_offset:06X} (file)")
        offset = file_offset
    elif smc_offset:
        print("SMC header detected but --no-header-adjust specified, using raw offset")

    # Create output directory
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"ROM: {rom_path}")
    print(f"Offset: 0x{offset:06X}")
    print(f"Output: {output_dir}")
    print()

    # Use HALCompressor directly
    try:
        from core.hal_compression import HALCompressor

        hal = HALCompressor()

        # Decompress from ROM
        print(f"Decompressing from offset 0x{offset:06X}...")
        decompressed_data = hal.decompress_from_rom(str(rom_path), offset)

        if not decompressed_data:
            print("ERROR: Decompression returned no data")
            return 1

        print(f"Decompressed: {len(decompressed_data)} bytes")

        # Save raw decompressed data
        raw_path = output_dir / f"{args.name}.bin"
        with open(raw_path, "wb") as f:
            f.write(decompressed_data)
        print(f"Raw data saved: {raw_path}")

        # Convert to PNG
        png_path = output_dir / f"{args.name}.png"
        tile_count = convert_4bpp_to_png(decompressed_data, png_path)
        print(f"PNG saved: {png_path} ({tile_count} tiles)")

        # Save metadata
        metadata = {
            "rom_path": str(rom_path),
            "rom_offset": f"0x{offset:06X}",
            "sprite_name": args.name,
            "decompressed_size": len(decompressed_data),
            "tile_count": tile_count,
        }
        metadata_path = output_dir / f"{args.name}_metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)
        print(f"Metadata saved: {metadata_path}")

        print()
        print("=" * 60)
        print("EXTRACTION SUCCESSFUL")
        print("=" * 60)

    except ImportError as e:
        print(f"ERROR: Failed to import core modules: {e}")
        print("Make sure you're running from the spritepal directory")
        return 1
    except Exception as e:
        print(f"ERROR: Extraction failed: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
