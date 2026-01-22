#!/usr/bin/env python3
"""
Extract the largest sprite candidates found in systematic search
"""

import sys
from pathlib import Path

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.rom_extractor import ROMExtractor


def extract_candidate(rom_path: str, offset: int, output_dir: str, expected_tiles: int) -> dict:
    """Extract a high-priority sprite candidate"""
    try:
        extractor = ROMExtractor()
        test_name = f"large_candidate_{expected_tiles}tiles"
        output_base = Path(output_dir) / f"{test_name}_0x{offset:06X}"

        print(f"🎯 EXTRACTING: 0x{offset:06X} (expected {expected_tiles} tiles)")

        # Attempt extraction
        output_path, extraction_info = extractor.extract_sprite_from_rom(rom_path, offset, str(output_base), test_name)

        # Check results
        output_file = Path(output_path)
        if output_file.exists():
            file_size = output_file.stat().st_size
            actual_tiles = extraction_info.get("tile_count", 0) if extraction_info else 0

            print(f"   ✅ SUCCESS: {Path(output_path).name}")
            print(f"   📊 Size: {file_size} bytes, Actual tiles: {actual_tiles}")

            return {
                "success": True,
                "output_path": output_path,
                "file_size": file_size,
                "actual_tiles": actual_tiles,
                "expected_tiles": expected_tiles,
            }
        print("   ❌ FAILED: No output file created")
        return {"success": False, "error": "No output file"}

    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        return {"success": False, "error": str(e)}


def main():
    """Extract the highest-priority large sprite candidates"""
    rom_path = "../Kirby Super Star (USA).sfc"
    output_dir = "large_sprite_candidates"

    Path(output_dir).mkdir(exist_ok=True)

    if not Path(rom_path).exists():
        print(f"Error: ROM file not found: {rom_path}")
        return 1

    print("🔥 EXTRACTING LARGEST SPRITE CANDIDATES")
    print("=" * 50)

    # Top candidates from systematic search (ordered by size)
    large_candidates = [
        (0x2A3100, 303),  # MASSIVE - likely main character
        (0x2A4400, 212),  # Very large
        (0x2A4300, 207),  # Very large
        (0x294100, 120),  # Large
        (0x293500, 126),  # Large
        (0x271600, 131),  # Large
        (0x2A3C00, 130),  # Large
        (0x293700, 109),  # Medium-large
        (0x2A2E00, 112),  # Medium-large
        (0x2A0E00, 88),  # Medium (for comparison)
    ]

    print(f"Extracting {len(large_candidates)} high-priority candidates...")
    print("Target: Find Kirby main character sprite (should be 100+ tiles)")
    print()

    results = []
    successful = 0

    for offset, expected_tiles in large_candidates:
        result = extract_candidate(rom_path, offset, output_dir, expected_tiles)
        result["offset"] = offset
        results.append(result)

        if result["success"]:
            successful += 1

        print()  # Blank line between candidates

    print("=" * 50)
    print("LARGE CANDIDATE EXTRACTION SUMMARY")
    print(f"Successful extractions: {successful}/{len(large_candidates)}")

    if successful > 0:
        print(f"\\n🎉 EXTRACTED {successful} LARGE SPRITE CANDIDATES!")

        # Analyze results
        character_candidates = []
        for result in results:
            if result["success"] and result["actual_tiles"] >= 100:
                character_candidates.append(result)

        print("\\n👑 POTENTIAL CHARACTER SPRITES (100+ tiles):")
        for i, result in enumerate(character_candidates, 1):
            print(f"  {i}. 0x{result['offset']:06X}: {result['actual_tiles']} tiles ({result['file_size']} bytes)")
            print(f"     → {Path(result['output_path']).name}")

        if character_candidates:
            print("\\n🎯 PRIORITY INSPECTION:")
            print(f"   1. Open the largest candidate: 0x{character_candidates[0]['offset']:06X}")
            print("   2. Look for Kirby's distinctive round pink shape")
            print("   3. Check for animation frames (idle, walking, jumping)")
            print("   4. Verify character proportions and details")

            print("\\n📂 FILES TO CHECK:")
            for result in character_candidates[:3]:  # Top 3
                print(f"   • {Path(result['output_path']).name}")
        else:
            print("\\n⚠️  No 100+ tile sprites found")
            print("   → Check medium-large sprites (50-99 tiles)")
            print("   → Kirby might be stored differently than expected")

        print("\\n💡 WHAT TO LOOK FOR:")
        print("   ✅ Kirby's round body shape")
        print("   ✅ Multiple similar sprites (animation frames)")
        print("   ✅ Character facial features (eyes, mouth)")
        print("   ✅ Power-up variations (Fire, Ice, Stone, etc.)")
        print("   ❌ Repetitive background patterns")
        print("   ❌ UI elements or text")

    else:
        print("\\n❌ NO SUCCESSFUL EXTRACTIONS")
        print("This suggests the large sprites detected may have been false positives")
        print("or the extraction process failed for these specific offsets")

    return 0 if successful > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
