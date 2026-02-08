#!/usr/bin/env python3
"""
Search systematically around successful sprite finds for larger character data
"""

import os
import sys
from pathlib import Path

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.rom_extractor import ROMExtractor


def test_offset_extraction(rom_path: str, offset: int, output_dir: str, test_name: str) -> dict:
    """Quick test extraction at offset"""
    try:
        extractor = ROMExtractor()
        output_base = Path(output_dir) / f"search_{test_name}_0x{offset:06X}"

        # Attempt extraction
        output_path, extraction_info = extractor.extract_sprite_from_rom(rom_path, offset, str(output_base), test_name)

        # Check results
        output_file = Path(output_path)
        if output_file.exists():
            file_size = output_file.stat().st_size
            tiles = extraction_info.get("tile_count", 0) if extraction_info else 0

            # Score based on size and tiles (larger = more likely to be character)
            score = tiles + (file_size / 100)  # Favor more tiles and larger files

            return {
                "success": True,
                "output_path": output_path,
                "file_size": file_size,
                "tiles": tiles,
                "score": score,
                "extraction_info": extraction_info,
            }
        return {"success": False, "error": "No output file"}

    except Exception as e:
        return {"success": False, "error": str(e)}


def search_region(
    rom_path: str, start_offset: int, end_offset: int, step: int, output_dir: str, region_name: str
) -> list:
    """Search a ROM region systematically"""
    print(f"\\n🔍 SEARCHING REGION: {region_name}")
    print(f"   Range: 0x{start_offset:06X} - 0x{end_offset:06X} (step: 0x{step:X})")

    results = []
    successful = 0

    for offset in range(start_offset, end_offset, step):
        test_name = f"{region_name}_{offset:06X}"
        result = test_offset_extraction(rom_path, offset, output_dir, test_name)
        result["offset"] = offset
        result["name"] = test_name

        if result["success"]:
            successful += 1
            tiles = result["tiles"]
            score = result["score"]

            # Only report interesting findings (larger sprites)
            if tiles >= 20:  # At least 20 tiles = substantial sprite
                print(f"   ✓ 0x{offset:06X}: {tiles:3d} tiles, score={score:6.1f}")

        results.append(result)

    print(f"   → Found {successful} extractable sprites in {region_name}")
    return results


def main():
    """Search around successful areas for larger character sprites"""
    rom_path = os.environ.get(
        "SPRITEPAL_ROM_PATH", str(Path(__file__).resolve().parents[2] / "roms" / "Kirby Super Star (USA).sfc")
    )
    output_dir = "systematic_sprite_search"

    Path(output_dir).mkdir(exist_ok=True)

    if not Path(rom_path).exists():
        print(f"Error: ROM file not found: {rom_path}")
        return 1

    print("=== SYSTEMATIC SPRITE SEARCH AROUND SUCCESSFUL AREAS ===")
    print(f"ROM: {rom_path}")
    print(f"Output: {output_dir}")
    print("Target: Find larger character sprites (50+ tiles)")

    # Define search regions around successful documented offsets
    search_regions = [
        # Around the successful enemy sprite (0x302238)
        (0x302000, 0x302800, 0x40, "green_greens_enemy_area"),
        # Around the successful main sprite areas (0x280000-0x2A0000)
        (0x280000, 0x285000, 0x100, "main_sprite_area_detailed"),
        (0x290000, 0x295000, 0x100, "main_sprite_area_2_detailed"),
        (0x2A0000, 0x2A5000, 0x100, "main_sprite_area_3_detailed"),
        # Expand search into adjacent areas
        (0x270000, 0x280000, 0x200, "pre_main_sprite_area"),
        (0x2A5000, 0x2B0000, 0x200, "post_main_sprite_area"),
        # Check if there's a pattern every 64KB (common in SNES ROMs)
        (0x1C0000, 0x1C5000, 0x200, "potential_sprite_bank_1"),
        (0x240000, 0x245000, 0x200, "potential_sprite_bank_2"),
    ]

    all_results = []

    for start, end, step, name in search_regions:
        region_results = search_region(rom_path, start, end, step, output_dir, name)
        all_results.extend(region_results)

    # Analyze all results
    successful_results = [r for r in all_results if r["success"]]

    print("\\n" + "=" * 60)
    print("SYSTEMATIC SEARCH SUMMARY")
    print(f"Total attempts: {len(all_results)}")
    print(f"Successful extractions: {len(successful_results)}")

    if successful_results:
        # Sort by score (tiles + size factor)
        successful_results.sort(key=lambda x: x["score"], reverse=True)

        # Show top candidates for character sprites
        large_sprites = [r for r in successful_results if r["tiles"] >= 50]  # 50+ tiles = character-sized
        medium_sprites = [r for r in successful_results if 20 <= r["tiles"] < 50]  # 20-49 tiles = enemy-sized

        print("\\n🎯 LARGE SPRITE CANDIDATES (50+ tiles, likely characters):")
        if large_sprites:
            for i, result in enumerate(large_sprites[:10], 1):  # Top 10
                print(
                    f"  {i:2d}. 0x{result['offset']:06X}: {result['tiles']:3d} tiles, "
                    f"score={result['score']:6.1f} ({result['name']})"
                )
        else:
            print("     None found - need to expand search or look in different regions")

        print("\\n⚔️  MEDIUM SPRITE CANDIDATES (20-49 tiles, likely enemies):")
        for i, result in enumerate(medium_sprites[:15], 1):  # Top 15
            print(
                f"  {i:2d}. 0x{result['offset']:06X}: {result['tiles']:3d} tiles, "
                f"score={result['score']:6.1f} ({result['name']})"
            )

        print("\\n📊 SIZE DISTRIBUTION:")
        tile_ranges = {
            "Tiny (1-9)": len([r for r in successful_results if r["tiles"] < 10]),
            "Small (10-19)": len([r for r in successful_results if 10 <= r["tiles"] < 20]),
            "Medium (20-49)": len([r for r in successful_results if 20 <= r["tiles"] < 50]),
            "Large (50+)": len([r for r in successful_results if r["tiles"] >= 50]),
        }

        for size_range, count in tile_ranges.items():
            print(f"   {size_range}: {count} sprites")

        # Recommendations
        print("\\n💡 NEXT STEPS:")
        if large_sprites:
            print(f"   ✅ Found {len(large_sprites)} large sprite candidates!")
            print("   → Visually inspect top candidates for Kirby character")
            print("   → Check if they contain recognizable character shapes")
        else:
            print("   🔍 No large sprites found in searched regions")
            print("   → Try different ROM regions (0x100000+, 0x180000+)")
            print("   → Search with smaller step sizes around medium sprites")
            print("   → Check if Kirby uses different compression or storage method")

        print("\\n🎨 VISUAL INSPECTION NEEDED:")
        print(f"   → Open PNG files in {output_dir}/ and look for:")
        print("   → Kirby's round pink shape")
        print("   → Enemy characters (King Dedede, Waddle Dee, etc.)")
        print("   → Animation frames (multiple similar sprites)")

    else:
        print("\\n❌ NO SUCCESSFUL EXTRACTIONS in searched regions")
        print("This suggests character sprites may be in different ROM areas or use different compression")

    return 0


if __name__ == "__main__":
    sys.exit(main())
