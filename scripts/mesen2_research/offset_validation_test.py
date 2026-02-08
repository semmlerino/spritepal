#!/usr/bin/env python3
"""
Test discovered sprite offsets using the existing ROMExtractor
"""

import os
import sys
from pathlib import Path

# Add parent directory to path so we can import spritepal modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.hal_compression import HALCompressionError
from core.rom_extractor import ROMExtractor


def test_offset_extraction(rom_path: str, offset: int, output_dir: str, test_name: str) -> dict:
    """Test sprite extraction at a specific offset"""
    try:
        extractor = ROMExtractor()

        output_base = Path(output_dir) / f"{test_name}_0x{offset:06X}"

        print(f"Testing offset 0x{offset:06X}...")

        # Attempt extraction
        output_path, extraction_info = extractor.extract_sprite_from_rom(rom_path, offset, str(output_base), test_name)

        # Check if output file exists
        output_file = Path(output_path)
        if output_file.exists():
            file_size = output_file.stat().st_size
            print(f"  ✓ Extracted to: {output_path} ({file_size} bytes)")

            return {
                "success": True,
                "output_path": output_path,
                "file_size": file_size,
                "extraction_info": extraction_info,
                "error": None,
            }
        else:
            print("  ✗ No output file created")
            return {
                "success": False,
                "output_path": None,
                "file_size": 0,
                "extraction_info": extraction_info,
                "error": "No output file created",
            }

    except HALCompressionError as e:
        print(f"  ✗ HAL Compression Error: {e}")
        return {
            "success": False,
            "output_path": None,
            "file_size": 0,
            "extraction_info": None,
            "error": f"HAL Compression: {e}",
        }
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return {"success": False, "output_path": None, "file_size": 0, "extraction_info": None, "error": str(e)}


def main():
    """Test high-priority offsets from our correlation analysis"""
    rom_path = os.environ.get(
        "SPRITEPAL_ROM_PATH", str(Path(__file__).resolve().parents[2] / "roms" / "Kirby Super Star (USA).sfc")
    )
    output_dir = "validation_test_output"

    # Create output directory
    Path(output_dir).mkdir(exist_ok=True)

    if not Path(rom_path).exists():
        print(f"Error: ROM file not found: {rom_path}")
        return 1

    # Test offsets from correlation analysis
    # These are the translated offsets (Mesen2 - 0x300000)
    test_offsets = [
        # Direct address translations from Mesen2
        (0x073E00, "mesen2_top_hit_1"),  # 47 runtime hits
        (0x073F00, "mesen2_top_hit_2"),  # 45 runtime hits
        (0x074700, "mesen2_medium_hit_1"),  # 35 runtime hits
        (0x074500, "mesen2_medium_hit_2"),  # 34 runtime hits
        # Top exhal candidates for comparison
        (0x0CC100, "exhal_perfect_score_1"),  # score=1.000, 58624 bytes
        (0x0E1300, "exhal_perfect_score_2"),  # score=1.000, 56096 bytes
        (0x07B500, "exhal_perfect_score_3"),  # score=1.000, 49056 bytes
        (0x087200, "exhal_perfect_score_4"),  # score=1.000, 36160 bytes
        # High confidence exhal candidates
        (0x0C0000, "exhal_high_conf_1"),  # score=0.950, 42472 bytes
        (0x0C0100, "exhal_high_conf_2"),  # score=0.950, 41893 bytes
    ]

    print(f"Testing {len(test_offsets)} sprite offsets with ROMExtractor...")
    print(f"ROM: {rom_path}")
    print(f"Output: {output_dir}")
    print("=" * 60)

    results = []
    successful_extractions = 0

    for offset, test_name in test_offsets:
        result = test_offset_extraction(rom_path, offset, output_dir, test_name)
        result["offset"] = offset
        result["test_name"] = test_name
        results.append(result)

        if result["success"]:
            successful_extractions += 1

    print("=" * 60)
    print("VALIDATION SUMMARY")
    print(f"Successful extractions: {successful_extractions}/{len(test_offsets)}")

    if successful_extractions > 0:
        print(f"\\n✓ SUCCESS! Found {successful_extractions} valid sprite offsets:")
        for result in results:
            if result["success"]:
                info = result["extraction_info"]
                print(f"  • 0x{result['offset']:06X} ({result['test_name']}):")
                print(f"    → File: {Path(result['output_path']).name}")
                print(f"    → Size: {result['file_size']} bytes")
                if info:
                    print(f"    → Tiles: {info.get('tile_count', 'N/A')}")
                    print(f"    → Compressed size: {info.get('compressed_size', 'N/A')} bytes")

    if successful_extractions < len(test_offsets):
        print(f"\\n⚠️  FAILURES ({len(test_offsets) - successful_extractions}):")
        for result in results:
            if not result["success"]:
                print(f"  • 0x{result['offset']:06X} ({result['test_name']}): {result['error']}")

    # Analysis
    print("\\n=== ANALYSIS ===")

    mesen2_successes = sum(1 for r in results if r["success"] and "mesen2" in r["test_name"])
    exhal_successes = sum(1 for r in results if r["success"] and "exhal" in r["test_name"])

    print(f"Mesen2-derived offsets successful: {mesen2_successes}/4")
    print(f"Exhal-discovered offsets successful: {exhal_successes}/6")

    if mesen2_successes > 0 and exhal_successes > 0:
        print("\\n💡 CORRELATION CONFIRMED!")
        print("Both runtime detection AND static analysis found valid sprites")
        print("This validates our address translation approach")
    elif mesen2_successes > 0:
        print("\\n✓ Runtime detection validated")
        print("Mesen2 addresses can be successfully extracted with translation")
    elif exhal_successes > 0:
        print("\\n✓ Static analysis validated")
        print("Exhal-discovered offsets produce extractable sprites")
    else:
        print("\\n❌ Validation failed")
        print("Need to investigate extraction process or offset calculation")

    return 0 if successful_extractions > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
