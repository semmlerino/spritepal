#!/usr/bin/env python3
"""
Comprehensive verification of address translation hypotheses
"""

import re
import sys
from pathlib import Path


def load_mesen2_offsets() -> set[int]:
    """Load all unique Mesen2 runtime offsets"""
    capture_dir = Path("/mnt/c/Users/gabri/OneDrive/Dokumente/Mesen2/LuaScriptData/Example")
    capture_files = list(capture_dir.glob("sprite_capture_*.txt"))

    all_offsets = set()

    for file_path in capture_files:
        try:
            with open(file_path) as f:
                content = f.read()

            rom_section = False
            for line in content.split("\n"):
                line = line.strip()
                if "--- ROM Offsets ---" in line:
                    rom_section = True
                    continue
                if line.startswith("---") and rom_section:
                    break

                if rom_section and line:
                    match = re.match(r"\$([0-9A-Fa-f]+):\s*(\d+)\s*hits?", line)
                    if match:
                        offset = int(match.group(1), 16)
                        all_offsets.add(offset)
        except Exception as e:
            print(f"Error processing {file_path}: {e}")

    return all_offsets


def load_exhal_offsets() -> set[int]:
    """Load all exhal static offsets"""
    offsets_file = "discovered_sprite_offsets.txt"

    if not Path(offsets_file).exists():
        return set()

    offsets = set()
    with open(offsets_file) as f:
        for line in f:
            line = line.strip()
            if line.startswith("#") or not line:
                continue

            match = re.match(r"0x([0-9A-Fa-f]+)", line)
            if match:
                offset = int(match.group(1), 16)
                offsets.add(offset)

    return offsets


def test_address_translations(mesen2_offsets: set[int], exhal_offsets: set[int]) -> dict:
    """Test various address translation hypotheses"""

    translations = {
        "direct": lambda x: x,  # No translation
        "subtract_300000": lambda x: x - 0x300000,  # Our current hypothesis
        "subtract_200000": lambda x: x - 0x200000,  # Alternative
        "subtract_400000": lambda x: x - 0x400000,  # Alternative
        "lorom_mapping": lambda x: (x & 0x3FFFFF) if x >= 0x800000 else x,  # LoROM
        "hirom_mapping": lambda x: (x - 0xC00000) if x >= 0xC00000 else x,  # HiROM
        "bank_stripping": lambda x: x & 0xFFFF,  # Strip bank bits
        "snes_to_pc": lambda x: ((x & 0x7F0000) >> 1) + (x & 0x7FFF),  # SNES -> PC addr
    }

    results = {}

    for name, translation_func in translations.items():
        try:
            # Translate Mesen2 offsets
            translated_offsets = set()
            for offset in mesen2_offsets:
                try:
                    translated = translation_func(offset)
                    if translated >= 0:  # Ignore negative results
                        translated_offsets.add(translated)
                except Exception:
                    continue

            # Find matches with exhal offsets
            matches = translated_offsets.intersection(exhal_offsets)

            # Calculate statistics
            results[name] = {
                "translated_count": len(translated_offsets),
                "matches": len(matches),
                "match_percentage": (len(matches) / len(translated_offsets)) * 100 if translated_offsets else 0,
                "coverage_percentage": (len(matches) / len(exhal_offsets)) * 100 if exhal_offsets else 0,
                "matching_offsets": sorted(matches)[:10],  # First 10 matches for inspection
            }

        except Exception as e:
            results[name] = {"error": str(e)}

    return results


def analyze_offset_patterns(mesen2_offsets: set[int], exhal_offsets: set[int]) -> dict:
    """Analyze patterns in offset distributions"""

    def get_region_stats(offsets: set[int]) -> dict:
        regions = {}

        for offset in offsets:
            # Bank analysis (upper 8 bits)
            (offset >> 16) & 0xFF

            # Region classification
            if offset < 0x100000:
                region = "0x00-0x0F"
            elif offset < 0x200000:
                region = "0x10-0x1F"
            elif offset < 0x300000:
                region = "0x20-0x2F"
            elif offset < 0x400000:
                region = "0x30-0x3F"
            else:
                region = "0x40+"

            regions[region] = regions.get(region, 0) + 1

        return regions

    mesen2_regions = get_region_stats(mesen2_offsets)
    exhal_regions = get_region_stats(exhal_offsets)

    # Look for mathematical relationships
    relationships = []

    for m_offset in sorted(mesen2_offsets)[:10]:  # Check first 10
        closest_matches = []
        for e_offset in exhal_offsets:
            diff = abs(m_offset - e_offset)
            if diff < 0x100000:  # Within 1MB
                closest_matches.append((e_offset, diff, m_offset - e_offset))

        # Sort by closest match
        closest_matches.sort(key=lambda x: x[1])

        if closest_matches:
            relationships.append(
                {
                    "mesen2_offset": f"0x{m_offset:06X}",
                    "closest_exhal": f"0x{closest_matches[0][0]:06X}",
                    "difference": closest_matches[0][2],
                    "diff_hex": f"0x{abs(closest_matches[0][2]):06X}",
                }
            )

    return {"mesen2_regions": mesen2_regions, "exhal_regions": exhal_regions, "closest_relationships": relationships}


def find_validation_candidates(translation_results: dict, mesen2_offsets: set[int]) -> list[tuple[str, int, int]]:
    """Find the best translation candidates for validation"""

    candidates = []

    # Find translation method with most matches
    best_method = max(
        [k for k in translation_results if "error" not in translation_results[k]],
        key=lambda k: translation_results[k]["matches"],
        default=None,
    )

    if best_method and translation_results[best_method]["matches"] > 0:
        matching_offsets = translation_results[best_method]["matching_offsets"]

        # Find original Mesen2 offsets that led to these matches
        for match_offset in matching_offsets[:5]:  # Top 5
            for original_offset in mesen2_offsets:
                if (best_method == "subtract_300000" and original_offset - 0x300000 == match_offset) or (
                    best_method == "direct" and original_offset == match_offset
                ):
                    candidates.append((best_method, original_offset, match_offset))
                # Add other translation methods as needed

    return candidates


def main():
    """Main address translation verification"""
    print("=== ADDRESS TRANSLATION VERIFICATION ===")

    # Load data
    mesen2_offsets = load_mesen2_offsets()
    exhal_offsets = load_exhal_offsets()

    print(f"Mesen2 runtime offsets: {len(mesen2_offsets)}")
    print(f"Exhal static offsets: {len(exhal_offsets)}")

    if not mesen2_offsets or not exhal_offsets:
        print("Error: Missing offset data")
        return 1

    # Test translation methods
    print("\\nTesting address translation methods...")
    translation_results = test_address_translations(mesen2_offsets, exhal_offsets)

    print("\\nTRANSLATION RESULTS:")
    print(f"{'Method':<20} {'Matches':<8} {'Match%':<8} {'Coverage%':<10} {'Sample Matches'}")
    print("-" * 80)

    for method, result in translation_results.items():
        if "error" in result:
            print(f"{method:<20} ERROR: {result['error']}")
            continue

        matches = result["matches"]
        match_pct = result["match_percentage"]
        coverage_pct = result["coverage_percentage"]
        samples = ", ".join(f"0x{x:06X}" for x in result["matching_offsets"][:3])

        print(f"{method:<20} {matches:<8} {match_pct:<8.1f} {coverage_pct:<10.2f} {samples}")

    # Pattern analysis
    print("\\n=== PATTERN ANALYSIS ===")
    patterns = analyze_offset_patterns(mesen2_offsets, exhal_offsets)

    print("Mesen2 offset distribution:")
    for region, count in sorted(patterns["mesen2_regions"].items()):
        print(f"  {region}: {count}")

    print("\\nExhal offset distribution:")
    for region, count in sorted(patterns["exhal_regions"].items()):
        print(f"  {region}: {count}")

    print("\\nClosest relationships (first 5):")
    for rel in patterns["closest_relationships"][:5]:
        print(f"  {rel['mesen2_offset']} → {rel['closest_exhal']} (diff: {rel['diff_hex']})")

    # Find best translation method
    best_results = [
        (method, result["matches"])
        for method, result in translation_results.items()
        if "matches" in result and result["matches"] > 0
    ]

    if best_results:
        best_method, best_matches = max(best_results, key=lambda x: x[1])
        print(f"\\n🏆 BEST TRANSLATION METHOD: {best_method}")
        print(f"   Matches: {best_matches}")
        print(f"   Success rate: {translation_results[best_method]['match_percentage']:.1f}%")

        # Validation candidates
        candidates = find_validation_candidates(translation_results, mesen2_offsets)
        if candidates:
            print("\\n✅ VALIDATION CANDIDATES:")
            for method, original, translated in candidates:
                print(f"   0x{original:06X} → 0x{translated:06X} (via {method})")
    else:
        print("\\n❌ NO SUCCESSFUL TRANSLATIONS FOUND")
        print("   This suggests the address mapping is more complex than simple arithmetic")
        print("   Possible issues:")
        print("   • Different ROM regions use different mapping")
        print("   • Banking/segmentation complexities")
        print("   • Mesen2 and exhal use different address spaces")

    return 0


if __name__ == "__main__":
    sys.exit(main())
