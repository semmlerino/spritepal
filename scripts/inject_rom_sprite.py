#!/usr/bin/env python3
"""
Inject edited sprite PNG into ROM using HAL compression.

Usage:
    uv run python scripts/inject_rom_sprite.py --sprite <png_path> --rom <rom_path> --offset <hex_offset> --output <output_rom>

Example:
    uv run python scripts/inject_rom_sprite.py \
        --sprite extracted_sprites/poppy_bros_sr/poppy_bros_sr_edited.png \
        --rom "roms/Kirby Super Star (USA).sfc" \
        --offset 0x29E667 \
        --output "roms/Kirby Super Star (USA) - Modified.sfc"
"""

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Inject edited sprite PNG into ROM using HAL compression")
    parser.add_argument("--sprite", "-s", required=True, help="Path to edited sprite PNG")
    parser.add_argument("--rom", "-r", required=True, help="Path to input ROM file")
    parser.add_argument(
        "--offset",
        "-o",
        required=True,
        help="ROM offset (hex, e.g., 0x29E667 or 29E667)",
    )
    parser.add_argument("--output", "-d", required=True, help="Path for output ROM file")
    parser.add_argument(
        "--fast",
        "-f",
        action="store_true",
        help="Use fast compression (larger output, faster)",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip creating backup of original ROM",
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

    # Validate files exist
    sprite_path = Path(args.sprite)
    if not sprite_path.exists():
        print(f"ERROR: Sprite file not found: {sprite_path}")
        return 1

    rom_path = Path(args.rom)
    if not rom_path.exists():
        print(f"ERROR: ROM file not found: {rom_path}")
        return 1

    output_path = Path(args.output)

    print(f"Sprite: {sprite_path}")
    print(f"ROM: {rom_path}")
    print(f"Offset: 0x{offset:06X}")
    print(f"Output: {output_path}")
    print(f"Fast compression: {args.fast}")
    print(f"Create backup: {not args.no_backup}")
    print()

    # Import and use ROMInjector
    try:
        from core.rom_injector import ROMInjector

        injector = ROMInjector()
        success, message = injector.inject_sprite_to_rom(
            sprite_path=str(sprite_path),
            rom_path=str(rom_path),
            output_path=str(output_path),
            sprite_offset=offset,
            fast_compression=args.fast,
            create_backup=not args.no_backup,
        )

        print()
        if success:
            print("=" * 60)
            print("INJECTION SUCCESSFUL")
            print("=" * 60)
            print(message)
            print("=" * 60)
            print()
            print(f"Modified ROM saved to: {output_path}")
            return 0
        else:
            print("=" * 60)
            print("INJECTION FAILED")
            print("=" * 60)
            print(message)
            print("=" * 60)
            return 1

    except ImportError as e:
        print(f"ERROR: Failed to import core modules: {e}")
        print("Make sure you're running from the spritepal directory")
        return 1
    except Exception as e:
        print(f"ERROR: Injection failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
