#!/usr/bin/env python3
"""
Analyze decompression quality and investigate alignment warnings
"""
import sys
import tempfile
from pathlib import Path

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.hal_compression import HALCompressor


def test_raw_decompression(rom_path: str, offset: int) -> dict:
    """Test raw decompression at offset and analyze the data"""
    try:
        compressor = HALCompressor()

        print(f"Testing raw decompression at 0x{offset:06X}...")

        # Create temporary file for ROM data
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            # Copy ROM to temp file for exhal
            with open(rom_path, 'rb') as rom:
                tmp_file.write(rom.read())
            tmp_rom_path = tmp_file.name

        # Decompress using HAL
        decompressed_data = compressor.decompress_from_rom(tmp_rom_path, offset)

        Path(tmp_rom_path).unlink()  # Clean up temp file

        if not decompressed_data:
            return {
                "success": False,
                "error": "No data decompressed",
                "size": 0
            }

        # Analyze the decompressed data
        size = len(decompressed_data)
        tiles = size // 32
        extra_bytes = size % 32

        # Data pattern analysis
        zero_count = decompressed_data.count(0)
        ff_count = decompressed_data.count(0xFF)
        unique_bytes = len(set(decompressed_data))

        # Check for repeating patterns (common in sprites)
        pattern_score = 0
        if len(decompressed_data) >= 4:
            for i in range(0, min(len(decompressed_data) - 3, 1000), 2):  # Sample first 1000 bytes
                if decompressed_data[i:i+2] == decompressed_data[i+2:i+4]:
                    pattern_score += 1

        # Header/padding analysis
        first_32_bytes = decompressed_data[:32]
        last_32_bytes = decompressed_data[-32:] if size >= 32 else decompressed_data

        return {
            "success": True,
            "size": size,
            "tiles": tiles,
            "extra_bytes": extra_bytes,
            "is_aligned": extra_bytes == 0,
            "zero_percentage": (zero_count / size) * 100,
            "ff_percentage": (ff_count / size) * 100,
            "unique_bytes": unique_bytes,
            "pattern_score": pattern_score,
            "first_32_hex": " ".join(f"{b:02X}" for b in first_32_bytes),
            "last_32_hex": " ".join(f"{b:02X}" for b in last_32_bytes),
            "data_preview": decompressed_data[:64]  # First 64 bytes for analysis
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "size": 0
        }

def analyze_alignment_issues(results: list) -> dict:
    """Analyze patterns in alignment issues"""
    aligned_count = sum(1 for r in results if r["success"] and r["is_aligned"])
    total_successful = sum(1 for r in results if r["success"])

    if total_successful == 0:
        return {"error": "No successful decompressions"}

    alignment_rate = (aligned_count / total_successful) * 100

    # Group by extra bytes
    extra_bytes_distribution = {}
    for r in results:
        if r["success"] and not r["is_aligned"]:
            extra = r["extra_bytes"]
            extra_bytes_distribution[extra] = extra_bytes_distribution.get(extra, 0) + 1

    return {
        "total_successful": total_successful,
        "aligned_count": aligned_count,
        "misaligned_count": total_successful - aligned_count,
        "alignment_rate": alignment_rate,
        "extra_bytes_distribution": extra_bytes_distribution
    }

def check_sprite_validity(data_preview: bytes) -> dict:
    """Check if decompressed data looks like valid sprite data"""
    if not data_preview:
        return {"is_sprite": False, "confidence": 0.0}

    # SNES 4bpp sprite data characteristics:
    # - Should have reasonable data density (not all 0x00 or 0xFF)
    # - Should have patterns typical of graphics data
    # - First few bytes often contain tile indices/metadata

    density = (len(data_preview) - data_preview.count(0)) / len(data_preview)
    ff_density = data_preview.count(0xFF) / len(data_preview)
    unique_ratio = len(set(data_preview)) / len(data_preview)

    # Look for typical sprite patterns
    sprite_score = 0

    # Good density (not too empty, not too full)
    if 0.1 < density < 0.9:
        sprite_score += 1

    # Not too many 0xFF bytes (which might indicate padding)
    if ff_density < 0.3:
        sprite_score += 1

    # Good variety of byte values
    if unique_ratio > 0.2:
        sprite_score += 1

    # Check for incrementing patterns (common in tile indices)
    increment_count = 0
    for i in range(len(data_preview) - 1):
        if data_preview[i+1] == data_preview[i] + 1:
            increment_count += 1

    if increment_count > 3:
        sprite_score += 1

    confidence = sprite_score / 4.0

    return {
        "is_sprite": confidence > 0.5,
        "confidence": confidence,
        "density": density,
        "ff_density": ff_density,
        "unique_ratio": unique_ratio,
        "increment_patterns": increment_count
    }

def main():
    """Main decompression analysis"""
    rom_path = "../Kirby Super Star (USA).sfc"

    if not Path(rom_path).exists():
        print(f"Error: ROM not found: {rom_path}")
        return 1

    # Test the same offsets we validated before
    test_offsets = [
        (0x073E00, "mesen2_top_hit_1"),        # Had 6 extra bytes
        (0x073F00, "mesen2_top_hit_2"),        # Had 29 extra bytes (significant misalignment)
        (0x074500, "mesen2_medium_hit_2"),     # Worked fine
        (0x0CC100, "exhal_perfect_score_1"),   # Perfect score
        (0x0E1300, "exhal_perfect_score_2"),   # Perfect score
        (0x07B500, "exhal_perfect_score_3"),   # Perfect score
    ]

    print("=== DECOMPRESSION QUALITY ANALYSIS ===")
    print(f"ROM: {rom_path}")
    print(f"Testing {len(test_offsets)} offsets for data alignment and quality...")
    print()

    results = []

    for offset, name in test_offsets:
        result = test_raw_decompression(rom_path, offset)
        result["offset"] = offset
        result["name"] = name
        results.append(result)

        if result["success"]:
            aligned = "✓" if result["is_aligned"] else f"✗ (+{result['extra_bytes']} bytes)"
            sprite_check = check_sprite_validity(result["data_preview"])
            sprite_status = "✓" if sprite_check["is_sprite"] else f"? (conf={sprite_check['confidence']:.2f})"

            print(f"0x{offset:06X} ({name}):")
            print(f"  Size: {result['size']:5d} bytes ({result['tiles']:3d} tiles)")
            print(f"  Aligned: {aligned}")
            print(f"  Sprite data: {sprite_status}")
            print(f"  Unique bytes: {result['unique_bytes']:3d}, Patterns: {result['pattern_score']}")
            print(f"  Zero%: {result['zero_percentage']:5.1f}%, FF%: {result['ff_percentage']:5.1f}%")
            print(f"  First 16: {result['first_32_hex'][:47]}...")
            print()
        else:
            print(f"0x{offset:06X} ({name}): ✗ FAILED - {result['error']}")
            print()

    # Overall alignment analysis
    alignment_analysis = analyze_alignment_issues(results)

    print("=== ALIGNMENT ANALYSIS ===")
    if "error" not in alignment_analysis:
        print(f"Successful decompressions: {alignment_analysis['total_successful']}/{len(test_offsets)}")
        print(f"Properly aligned: {alignment_analysis['aligned_count']}/{alignment_analysis['total_successful']}")
        print(f"Alignment rate: {alignment_analysis['alignment_rate']:.1f}%")

        if alignment_analysis['extra_bytes_distribution']:
            print("\\nExtra bytes distribution:")
            for extra_bytes, count in sorted(alignment_analysis['extra_bytes_distribution'].items()):
                print(f"  +{extra_bytes} bytes: {count} offsets")

    # Quality assessment
    successful_results = [r for r in results if r["success"]]
    sprite_validations = [check_sprite_validity(r["data_preview"]) for r in successful_results]

    valid_sprites = sum(1 for v in sprite_validations if v["is_sprite"])
    avg_confidence = sum(v["confidence"] for v in sprite_validations) / len(sprite_validations) if sprite_validations else 0

    print("\\n=== SPRITE DATA QUALITY ===")
    print(f"Valid sprite data: {valid_sprites}/{len(successful_results)} ({(valid_sprites/len(successful_results)*100):.1f}%)")
    print(f"Average confidence: {avg_confidence:.3f}")

    print("\\n=== CONCLUSIONS ===")

    if alignment_analysis.get('alignment_rate', 0) >= 50:
        print("✅ DECOMPRESSION APPEARS CORRECT")
        print("   • Majority of offsets produce properly aligned data")
        print("   • Misalignment is likely due to headers/padding, not decompression errors")
    else:
        print("⚠️  DECOMPRESSION MAY HAVE ISSUES")
        print("   • High rate of misaligned data suggests offset problems")
        print("   • Could indicate incorrect offsets or ROM version mismatch")

    if valid_sprites >= len(successful_results) * 0.8:
        print("✅ SPRITE DATA QUALITY GOOD")
        print("   • Decompressed data shows sprite characteristics")
        print("   • PNG extraction should produce valid graphics")
    else:
        print("⚠️  SPRITE DATA QUALITY QUESTIONABLE")
        print("   • Some decompressed data may not be valid sprites")
        print("   • Offsets might point to non-graphics data")

    # Specific recommendations
    print("\\n=== RECOMMENDATIONS ===")

    misaligned_offsets = [(r["offset"], r["extra_bytes"]) for r in results if r["success"] and not r["is_aligned"]]

    if misaligned_offsets:
        print("🔧 OFFSET ADJUSTMENT NEEDED:")
        for offset, extra in misaligned_offsets:
            if extra <= 8:
                print(f"   • 0x{offset:06X}: Try 0x{offset-extra:06X} (subtract {extra} bytes)")
            else:
                print(f"   • 0x{offset:06X}: Significant misalignment (+{extra}) - may be wrong offset")

    print("🧪 VALIDATION SUGGESTIONS:")
    print("   • Compare extracted PNGs visually with known Kirby sprites")
    print("   • Test offset adjustments for misaligned data")
    print("   • Use tile viewers to inspect raw decompressed data")

    return 0

if __name__ == "__main__":
    sys.exit(main())
