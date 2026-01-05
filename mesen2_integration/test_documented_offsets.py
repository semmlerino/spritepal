#!/usr/bin/env python3
"""
Test documented Kirby Super Star sprite offsets from ROM hacking community
"""

import sys
from pathlib import Path

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.rom_extractor import ROMExtractor


def test_documented_offset(rom_path: str, offset: int, output_dir: str, test_name: str) -> dict:
    """Test sprite extraction at a documented offset"""
    try:
        extractor = ROMExtractor()
        output_base = Path(output_dir) / f"documented_{test_name}_0x{offset:06X}"

        print(f"Testing documented offset 0x{offset:06X} ({test_name})...")

        # Attempt extraction
        output_path, extraction_info = extractor.extract_sprite_from_rom(rom_path, offset, str(output_base), test_name)

        # Check results
        output_file = Path(output_path)
        if output_file.exists():
            file_size = output_file.stat().st_size
            print(f"  ✓ Success: {output_path} ({file_size} bytes)")
            return {
                "success": True,
                "output_path": output_path,
                "file_size": file_size,
                "extraction_info": extraction_info,
            }
        else:
            print("  ✗ Failed: No output file created")
            return {"success": False, "error": "No output file"}

    except Exception as e:
        print(f"  ✗ Error: {e}")
        return {"success": False, "error": str(e)}


def main():
    """Test documented ROM offsets for actual character sprites"""
    rom_path = "../Kirby Super Star (USA).sfc"
    output_dir = "documented_sprite_test"

    Path(output_dir).mkdir(exist_ok=True)

    if not Path(rom_path).exists():
        print(f"Error: ROM file not found: {rom_path}")
        return 1

    print("=== TESTING DOCUMENTED KIRBY SUPER STAR SPRITE OFFSETS ===")
    print(f"ROM: {rom_path}")
    print(f"Output: {output_dir}")
    print()

    # Documented offsets from ROM hacking community research
    documented_offsets = [
        # From TCRF/Data Crystal documentation
        (0x302238, "flying_bird_enemy"),  # Enemy sprite from Green Greens first room
        (0x3020EF, "green_greens_music"),  # Music header - might be near sprite data
        (0x302125, "green_greens_door"),  # Door exit data - level data often has sprites
        # Try areas around documented addresses (sprite data often clustered)
        (0x302000, "green_greens_area_start"),  # Start of Green Greens area
        (0x302300, "green_greens_area_mid"),  # Middle of area
        (0x302500, "green_greens_area_end"),  # End of area
        # Try different compression boundaries (HAL uses specific patterns)
        (0x300000, "hal_boundary_300k"),  # Common HAL boundary
        (0x301000, "hal_boundary_301k"),  # 4KB after
        (0x304000, "hal_boundary_304k"),  # 16KB after
        # Try areas that might contain Kirby's main sprite data
        (0x280000, "main_sprite_area_1"),  # ROM region often used for main sprites
        (0x290000, "main_sprite_area_2"),  # Adjacent area
        (0x2A0000, "main_sprite_area_3"),  # Next area
    ]

    print(f"Testing {len(documented_offsets)} documented/inferred offsets:")

    results = []
    successful = 0

    for offset, name in documented_offsets:
        result = test_documented_offset(rom_path, offset, output_dir, name)
        result["offset"] = offset
        result["name"] = name
        results.append(result)

        if result["success"]:
            successful += 1

        print()  # Blank line between tests

    print("=" * 60)
    print("DOCUMENTED OFFSET TEST SUMMARY")
    print(f"Successful extractions: {successful}/{len(documented_offsets)}")

    if successful > 0:
        print(f"\\n✅ SUCCESS! Found {successful} extractable sprites at documented locations:")
        for result in results:
            if result["success"]:
                info = result["extraction_info"]
                print(f"  • 0x{result['offset']:06X} ({result['name']}):")
                print(f"    → File: {Path(result['output_path']).name}")
                print(f"    → Size: {result['file_size']} bytes")
                if info:
                    print(f"    → Tiles: {info.get('tile_count', 'N/A')}")

        print("\\n📋 NEXT STEPS:")
        print("1. Visually inspect the extracted PNGs")
        print("2. Look for recognizable Kirby characters or enemies")
        print("3. If found, use these as reference to find similar data")
    else:
        print("\\n❌ NO SUCCESS at documented offsets")
        print("\\nThis suggests:")
        print("• ROM version mismatch (USA vs Japan vs Europe)")
        print("• Compression format differences")
        print("• Need to search different ROM regions")
        print("• Documented offsets may be for level data, not sprites")

        print("\\n🔄 ALTERNATIVE STRATEGIES:")
        print("1. Test PRG-ROM mode vs LoROM/HiROM addressing")
        print("2. Search for Kirby's distinctive round shape in raw ROM data")
        print("3. Use tile viewers to scan for character-like patterns")
        print("4. Try different ROM dumps or versions")

    return 0 if successful > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
