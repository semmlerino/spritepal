#!/usr/bin/env python3
"""
Analyze the discrepancy between runtime offsets (24) and static offsets (1085)
"""

import re
from pathlib import Path


def analyze_mesen2_capture_sessions() -> dict:
    """Analyze all Mesen2 capture sessions"""
    capture_dir = Path("/mnt/c/Users/gabri/OneDrive/Dokumente/Mesen2/LuaScriptData/Example")
    capture_files = list(capture_dir.glob("sprite_capture_*.txt"))

    all_runtime_offsets = set()
    session_data = []

    print(f"Analyzing {len(capture_files)} Mesen2 capture sessions...")

    for file_path in sorted(capture_files):
        try:
            with open(file_path) as f:
                content = f.read()

            # Extract session metadata
            capture_time = re.search(r"Capture Time: ([0-9.]+) seconds", content)
            sprites_captured = re.search(r"Sprites Captured: (\d+)/(\d+)", content)
            rom_offsets_found = re.search(r"ROM Offsets Found: (\d+)", content)

            # Extract ROM offsets
            rom_section = False
            session_offsets = set()

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
                        int(match.group(2))
                        session_offsets.add(offset)
                        all_runtime_offsets.add(offset)

            session_info = {
                "file": file_path.name,
                "capture_time": float(capture_time.group(1)) if capture_time else 0,
                "sprites_captured": int(sprites_captured.group(1)) if sprites_captured else 0,
                "total_sprites": int(sprites_captured.group(2)) if sprites_captured else 0,
                "rom_offsets_found": int(rom_offsets_found.group(1)) if rom_offsets_found else 0,
                "unique_offsets": len(session_offsets),
                "offsets": session_offsets,
            }
            session_data.append(session_info)

        except Exception as e:
            print(f"Error processing {file_path}: {e}")

    return {
        "sessions": session_data,
        "all_runtime_offsets": all_runtime_offsets,
        "total_unique_runtime": len(all_runtime_offsets),
    }


def analyze_exhal_static_data() -> dict:
    """Analyze exhal static discovery data"""
    offsets_file = "discovered_sprite_offsets.txt"

    if not Path(offsets_file).exists():
        print(f"Warning: {offsets_file} not found")
        return {"offsets": set(), "total_static": 0}

    static_offsets = set()
    confidence_distribution = {"perfect": 0, "high": 0, "medium": 0, "low": 0}

    with open(offsets_file) as f:
        for line in f:
            line = line.strip()
            if line.startswith("#") or not line:
                continue

            # Parse: 0x0CC100  # 58624 bytes, 1832 tiles, score=1.000
            match = re.match(r"0x([0-9A-Fa-f]+)\s+#.*score=([0-9.]+)", line)
            if match:
                offset = int(match.group(1), 16)
                confidence = float(match.group(2))
                static_offsets.add(offset)

                if confidence == 1.0:
                    confidence_distribution["perfect"] += 1
                elif confidence >= 0.9:
                    confidence_distribution["high"] += 1
                elif confidence >= 0.7:
                    confidence_distribution["medium"] += 1
                else:
                    confidence_distribution["low"] += 1

    return {
        "offsets": static_offsets,
        "total_static": len(static_offsets),
        "confidence_distribution": confidence_distribution,
    }


def find_overlapping_patterns(runtime_data: dict, static_data: dict) -> dict:
    """Find patterns in overlapping vs non-overlapping offsets"""

    runtime_offsets = runtime_data["all_runtime_offsets"]
    static_offsets = static_data["offsets"]

    # Convert runtime offsets using address translation
    translated_runtime = {offset - 0x300000 for offset in runtime_offsets if offset >= 0x300000}

    # Find overlaps
    direct_overlaps = runtime_offsets.intersection(static_offsets)
    translated_overlaps = translated_runtime.intersection(static_offsets)

    # Analyze ROM regions
    def analyze_region_distribution(offsets: set[int]) -> dict:
        regions = {
            "0x00000-0x7FFFF": 0,  # First 512KB
            "0x80000-0xBFFFF": 0,  # Second 256KB
            "0xC0000-0xEFFFF": 0,  # Main sprite areas (our focus)
            "0xF0000+": 0,  # Upper areas
        }

        for offset in offsets:
            if offset < 0x80000:
                regions["0x00000-0x7FFFF"] += 1
            elif offset < 0xC0000:
                regions["0x80000-0xBFFFF"] += 1
            elif offset < 0xF0000:
                regions["0xC0000-0xEFFFF"] += 1
            else:
                regions["0xF0000+"] += 1

        return regions

    return {
        "runtime_original": len(runtime_offsets),
        "runtime_translated": len(translated_runtime),
        "static_total": len(static_offsets),
        "direct_overlaps": len(direct_overlaps),
        "translated_overlaps": len(translated_overlaps),
        "translated_overlap_offsets": sorted(translated_overlaps),
        "runtime_regions": analyze_region_distribution(translated_runtime),
        "static_regions": analyze_region_distribution(static_offsets),
        "coverage_percentage": (len(translated_overlaps) / len(static_offsets)) * 100 if static_offsets else 0,
    }


def main():
    """Main analysis"""
    print("=== RUNTIME VS STATIC OFFSET ANALYSIS ===")

    # Analyze Mesen2 runtime data
    runtime_data = analyze_mesen2_capture_sessions()

    print("\\nRUNTIME ANALYSIS:")
    print(f"Total capture sessions: {len(runtime_data['sessions'])}")
    print(f"Total unique runtime offsets: {runtime_data['total_unique_runtime']}")

    successful_sessions = [s for s in runtime_data["sessions"] if s["rom_offsets_found"] > 0]
    print(f"Successful sessions: {len(successful_sessions)}/{len(runtime_data['sessions'])}")

    if successful_sessions:
        avg_capture_time = sum(s["capture_time"] for s in successful_sessions) / len(successful_sessions)
        avg_offsets_per_session = sum(s["rom_offsets_found"] for s in successful_sessions) / len(successful_sessions)
        print(f"Average successful capture time: {avg_capture_time:.1f} seconds")
        print(f"Average offsets per successful session: {avg_offsets_per_session:.1f}")

    # Analyze exhal static data
    static_data = analyze_exhal_static_data()

    print("\\nSTATIC ANALYSIS:")
    print(f"Total static offsets: {static_data['total_static']}")
    if static_data["confidence_distribution"]:
        conf_dist = static_data["confidence_distribution"]
        print("Confidence distribution:")
        print(f"  Perfect (1.0):     {conf_dist['perfect']}")
        print(f"  High (0.9-0.99):   {conf_dist['high']}")
        print(f"  Medium (0.7-0.89): {conf_dist['medium']}")
        print(f"  Low (<0.7):        {conf_dist['low']}")

    # Find overlapping patterns
    overlap_data = find_overlapping_patterns(runtime_data, static_data)

    print("\\nOVERLAP ANALYSIS:")
    print(f"Runtime offsets (original): {overlap_data['runtime_original']}")
    print(f"Runtime offsets (translated): {overlap_data['runtime_translated']}")
    print(f"Static offsets: {overlap_data['static_total']}")
    print(f"Direct overlaps: {overlap_data['direct_overlaps']}")
    print(f"Translated overlaps: {overlap_data['translated_overlaps']}")
    print(f"Coverage: {overlap_data['coverage_percentage']:.2f}% of static offsets seen at runtime")

    print("\\nREGION DISTRIBUTION:")
    print("Runtime (translated):")
    for region, count in overlap_data["runtime_regions"].items():
        print(f"  {region}: {count}")
    print("Static (exhal):")
    for region, count in overlap_data["static_regions"].items():
        print(f"  {region}: {count}")

    # Analysis conclusions
    print("\\n=== DISCREPANCY ANALYSIS ===")

    ratio = (
        overlap_data["static_total"] / overlap_data["runtime_translated"]
        if overlap_data["runtime_translated"] > 0
        else 0
    )
    print(f"Static/Runtime ratio: {ratio:.1f}x more static offsets")

    print(f"\\nPossible explanations for 24 runtime vs {static_data['total_static']} static:")
    print("1. LIMITED GAMEPLAY COVERAGE:")
    print(f"   • Average capture: {avg_capture_time:.1f} seconds")
    print("   • Only captures sprites actively used during that time")
    print("   • Many sprites are context-specific (enemies, power-ups, bosses)")

    print("\\n2. SPRITE USAGE PATTERNS:")
    print(f"   • {overlap_data['translated_overlaps']} runtime offsets matched static analysis")
    print("   • This validates our address translation approach")
    print(
        f"   • But most sprites ({static_data['total_static'] - overlap_data['translated_overlaps']}) were not used in captured gameplay"
    )

    print("\\n3. STATIC ANALYSIS COMPREHENSIVENESS:")
    print("   • Exhal finds ALL decompressible data in ROM")
    print("   • Includes unused sprites, alternate versions, debug graphics")
    print(f"   • {conf_dist['perfect'] + conf_dist['high']} high-confidence candidates likely real sprites")

    print("\\n💡 INTEGRATION STRATEGY:")
    print("• Use runtime detection to identify ACTIVE sprites")
    print("• Use static analysis to find ALL POSSIBLE sprites")
    print("• Combine both for complete sprite discovery")
    print("• Runtime detection validates which sprites are actually used in-game")


if __name__ == "__main__":
    main()
