#!/usr/bin/env python3
"""
Correlate Mesen2 runtime sprite offsets with exhal-validated ROM offsets
"""
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SpriteOffset:
    """Represents a sprite offset with metadata"""
    offset: int
    source: str  # 'mesen2' or 'exhal'
    hits: int = 0
    confidence: float = 0.0
    size: int = 0
    tiles: int = 0

class SpriteOffsetCorrelator:
    """Correlates sprite offsets between Mesen2 runtime and exhal validation"""

    def __init__(self):
        self.mesen2_offsets: list[SpriteOffset] = []
        self.exhal_offsets: list[SpriteOffset] = []

    def load_mesen2_data(self, log_file: str) -> None:
        """Load Mesen2 runtime sprite offsets from log file"""
        log_path = Path(log_file)
        if not log_path.exists():
            print(f"Warning: Mesen2 log file not found: {log_file}")
            return

        print(f"Loading Mesen2 data from: {log_file}")

        with open(log_path) as f:
            content = f.read()

        # Parse ROM offsets section
        rom_section = False
        for line in content.split('\n'):
            line = line.strip()

            if '--- ROM Offsets ---' in line:
                rom_section = True
                continue
            if line.startswith('---') and rom_section:
                break

            if rom_section and line:
                # Parse format: $373E00: 47 hits
                match = re.match(r'\$([0-9A-Fa-f]+):\s*(\d+)\s*hits?', line)
                if match:
                    offset = int(match.group(1), 16)
                    hits = int(match.group(2))

                    sprite_offset = SpriteOffset(
                        offset=offset,
                        source='mesen2',
                        hits=hits
                    )
                    self.mesen2_offsets.append(sprite_offset)

        print(f"  Loaded {len(self.mesen2_offsets)} Mesen2 offsets")

    def load_exhal_data(self, offsets_file: str) -> None:
        """Load exhal-validated sprite offsets"""
        offsets_path = Path(offsets_file)
        if not offsets_path.exists():
            print(f"Warning: Exhal offsets file not found: {offsets_file}")
            return

        print(f"Loading exhal data from: {offsets_file}")

        with open(offsets_path) as f:
            content = f.read()

        for line in content.split('\n'):
            line = line.strip()

            if line.startswith('#') or not line:
                continue

            # Parse format: 0x0CC100  # 58624 bytes, 1832 tiles, score=1.000
            match = re.match(r'0x([0-9A-Fa-f]+)\s+#\s+(\d+)\s+bytes,\s+(\d+)\s+tiles,\s+score=([0-9.]+)', line)
            if match:
                offset = int(match.group(1), 16)
                size = int(match.group(2))
                tiles = int(match.group(3))
                confidence = float(match.group(4))

                sprite_offset = SpriteOffset(
                    offset=offset,
                    source='exhal',
                    size=size,
                    tiles=tiles,
                    confidence=confidence
                )
                self.exhal_offsets.append(sprite_offset)

        print(f"  Loaded {len(self.exhal_offsets)} exhal-validated offsets")

    def analyze_offset_ranges(self) -> None:
        """Analyze the range distributions of both datasets"""
        print("\n=== OFFSET RANGE ANALYSIS ===")

        if self.mesen2_offsets:
            mesen2_min = min(s.offset for s in self.mesen2_offsets)
            mesen2_max = max(s.offset for s in self.mesen2_offsets)
            print(f"Mesen2 offsets: 0x{mesen2_min:06X} - 0x{mesen2_max:06X}")

        if self.exhal_offsets:
            exhal_min = min(s.offset for s in self.exhal_offsets)
            exhal_max = max(s.offset for s in self.exhal_offsets)
            print(f"Exhal offsets:  0x{exhal_min:06X} - 0x{exhal_max:06X}")

    def find_direct_matches(self, tolerance: int = 0x100) -> list[tuple[SpriteOffset, SpriteOffset]]:
        """Find direct matches between datasets within tolerance"""
        matches = []

        for mesen2_sprite in self.mesen2_offsets:
            for exhal_sprite in self.exhal_offsets:
                diff = abs(mesen2_sprite.offset - exhal_sprite.offset)
                if diff <= tolerance:
                    matches.append((mesen2_sprite, exhal_sprite))

        return matches

    def analyze_address_translation(self) -> None:
        """Analyze possible address translation patterns"""
        print("\n=== ADDRESS TRANSLATION ANALYSIS ===")

        # Check for common SNES address mapping patterns
        for mesen2_sprite in self.mesen2_offsets[:10]:  # Check top 10
            original = mesen2_sprite.offset

            # Try different address translations
            translations = {
                "LoROM": original & 0x3FFFFF if original >= 0x800000 else original,
                "HiROM": (original - 0xC00000) if original >= 0xC00000 else original,
                "Bank strip": original & 0xFFFF,
                "Linear": original - 0x300000 if original >= 0x300000 else original,
            }

            print(f"\nMesen2 offset 0x{original:06X} ({mesen2_sprite.hits} hits):")

            best_match = None
            best_diff = float('inf')

            for translation_name, translated in translations.items():
                if translated < 0:
                    continue

                # Find closest exhal offset
                for exhal_sprite in self.exhal_offsets:
                    diff = abs(translated - exhal_sprite.offset)
                    if diff < best_diff:
                        best_diff = diff
                        best_match = (translation_name, translated, exhal_sprite)

                print(f"  {translation_name}: 0x{translated:06X}")

            if best_match and best_diff < 0x10000:  # Within 64KB
                name, translated, exhal = best_match
                print(f"  → Best match: {name} → 0x{translated:06X} ≈ 0x{exhal.offset:06X} (diff: 0x{best_diff:X})")

    def find_pattern_matches(self) -> None:
        """Look for patterns between high-activity Mesen2 offsets and high-confidence exhal offsets"""
        print("\n=== PATTERN MATCHING ===")

        # Get top Mesen2 offsets by hits
        top_mesen2 = sorted(self.mesen2_offsets, key=lambda s: s.hits, reverse=True)[:15]

        # Get top exhal offsets by confidence
        top_exhal = sorted(self.exhal_offsets, key=lambda s: s.confidence, reverse=True)[:15]

        print("Top Mesen2 offsets (by activity):")
        for i, sprite in enumerate(top_mesen2, 1):
            print(f"  {i:2d}. 0x{sprite.offset:06X} ({sprite.hits:2d} hits)")

        print("\nTop exhal offsets (by confidence):")
        for i, sprite in enumerate(top_exhal, 1):
            print(f"  {i:2d}. 0x{sprite.offset:06X} (score={sprite.confidence:.3f}, {sprite.size:5d} bytes, {sprite.tiles:4d} tiles)")

    def export_correlation_report(self, output_file: str) -> None:
        """Export comprehensive correlation report"""
        with open(output_file, 'w') as f:
            f.write("# Sprite Offset Correlation Report\\n")
            f.write(f"# Mesen2 runtime offsets: {len(self.mesen2_offsets)}\\n")
            f.write(f"# Exhal validated offsets: {len(self.exhal_offsets)}\\n\\n")

            # Direct matches
            direct_matches = self.find_direct_matches(tolerance=0x1000)
            f.write("## Direct Matches (within 4KB tolerance)\\n")
            f.write(f"Found {len(direct_matches)} potential matches:\\n\\n")

            for mesen2, exhal in direct_matches:
                diff = abs(mesen2.offset - exhal.offset)
                f.write(f"0x{mesen2.offset:06X} → 0x{exhal.offset:06X} "
                       f"(diff: 0x{diff:X}, hits: {mesen2.hits}, score: {exhal.confidence:.3f})\\n")

            # High-activity offsets for further investigation
            f.write("\\n## High-Activity Mesen2 Offsets\\n")
            top_mesen2 = sorted(self.mesen2_offsets, key=lambda s: s.hits, reverse=True)[:20]
            f.writelines(f"0x{sprite.offset:06X}  # {sprite.hits} runtime hits\\n" for sprite in top_mesen2)

            # High-confidence exhal offsets
            f.write("\\n## High-Confidence Exhal Offsets\\n")
            top_exhal = sorted(self.exhal_offsets, key=lambda s: s.confidence, reverse=True)[:20]
            f.writelines(f"0x{sprite.offset:06X}  # score={sprite.confidence:.3f}, {sprite.size} bytes\\n" for sprite in top_exhal)

        print(f"\\n✓ Correlation report exported to: {output_file}")

def main():
    """Main correlation analysis"""
    correlator = SpriteOffsetCorrelator()

    # Load data from both sources
    mesen2_log = "/mnt/c/Users/gabri/OneDrive/Dokumente/Mesen2/LuaScriptData/Example/sprite_capture_20250817_231000.txt"
    exhal_offsets = "discovered_sprite_offsets.txt"

    correlator.load_mesen2_data(mesen2_log)
    correlator.load_exhal_data(exhal_offsets)

    if not correlator.mesen2_offsets or not correlator.exhal_offsets:
        print("⚠️  Missing data - cannot perform correlation")
        return

    # Perform analysis
    correlator.analyze_offset_ranges()
    correlator.analyze_address_translation()
    correlator.find_pattern_matches()

    # Export results
    correlator.export_correlation_report("sprite_correlation_analysis.txt")

    print("\\n=== CORRELATION SUMMARY ===")
    print(f"Mesen2 runtime detections: {len(correlator.mesen2_offsets)}")
    print(f"Exhal validated offsets: {len(correlator.exhal_offsets)}")

    direct_matches = correlator.find_direct_matches(tolerance=0x1000)
    print(f"Direct matches found: {len(direct_matches)}")

    if direct_matches:
        print("\\n💡 INTEGRATION OPPORTUNITY:")
        print(f"   Found {len(direct_matches)} potential correlations between runtime and static analysis")
        print("   These offsets are both actively used during gameplay AND contain valid sprite data")
    else:
        print("\\n🤔 ADDRESS MAPPING INSIGHT:")
        print("   No direct matches found - this suggests address translation is needed")
        print("   Mesen2 uses runtime/banked addresses while exhal uses linear ROM addresses")

if __name__ == "__main__":
    main()
