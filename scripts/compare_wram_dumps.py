#!/usr/bin/env python3
"""
Compare baseline and ablated WRAM dumps to analyze what 0xE9E667 controls.

Usage:
    python compare_wram_dumps.py <baseline.bin> <ablated.bin>

Example:
    python compare_wram_dumps.py mesen2_exchange/wram_dump_frame_1795_baseline.bin mesen2_exchange/wram_dump_frame_1795_ablated.bin
"""

import argparse
import sys
from pathlib import Path


def load_dump(filepath: Path) -> bytes:
    """Load binary dump file."""
    with open(filepath, 'rb') as f:
        return f.read()


def find_diff_ranges(baseline: bytes, ablated: bytes) -> list[dict]:
    """Find contiguous ranges of differing bytes."""
    if len(baseline) != len(ablated):
        print(f"WARNING: Size mismatch: baseline={len(baseline)}, ablated={len(ablated)}")

    min_len = min(len(baseline), len(ablated))
    ranges = []
    in_diff = False
    start = 0

    for i in range(min_len):
        if baseline[i] != ablated[i]:
            if not in_diff:
                in_diff = True
                start = i
        else:
            if in_diff:
                ranges.append({
                    'start': start,
                    'end': i - 1,
                    'size': i - start,
                    'baseline': baseline[start:i],
                    'ablated': ablated[start:i]
                })
                in_diff = False

    # Handle trailing diff
    if in_diff:
        ranges.append({
            'start': start,
            'end': min_len - 1,
            'size': min_len - start,
            'baseline': baseline[start:min_len],
            'ablated': ablated[start:min_len]
        })

    return ranges


def analyze_diff_pattern(ranges: list[dict]) -> dict:
    """Analyze the diff pattern to infer what changed."""
    if not ranges:
        return {'type': 'IDENTICAL', 'description': 'No differences found'}

    total_diff_bytes = sum(r['size'] for r in ranges)
    total_size = 2048  # WRAM dump size

    analysis = {
        'type': 'UNKNOWN',
        'total_diff_bytes': total_diff_bytes,
        'num_ranges': len(ranges),
        'diff_percentage': total_diff_bytes / total_size * 100,
        'ranges': []
    }

    for r in ranges:
        analysis['ranges'].append({
            'offset': f"0x{r['start']:04X}",
            'wram_addr': f"0x{0x2000 + r['start']:04X}",
            'size': r['size'],
            'baseline_hex': r['baseline'].hex()[:64] + ('...' if len(r['baseline']) > 32 else ''),
            'ablated_hex': r['ablated'].hex()[:64] + ('...' if len(r['ablated']) > 32 else '')
        })

    # Classify the diff pattern
    if total_diff_bytes <= 16:
        analysis['type'] = 'LOCALIZED_SMALL'
        analysis['description'] = 'Small localized change - likely a pointer or index byte'
    elif total_diff_bytes <= 64 and len(ranges) == 1:
        analysis['type'] = 'LOCALIZED_BLOCK'
        analysis['description'] = 'Single contiguous block changed - likely a single sprite tile or metadata struct'
    elif total_diff_bytes <= 128 and len(ranges) <= 4:
        analysis['type'] = 'SPARSE_LOCALIZED'
        analysis['description'] = 'Few scattered changes - likely indices/pointers at known offsets'
    elif total_diff_bytes > 512:
        analysis['type'] = 'WIDESPREAD'
        analysis['description'] = 'Large portion changed - different decode mode or entirely different sprite batch'
    else:
        analysis['type'] = 'MODERATE'
        analysis['description'] = 'Moderate changes - partial sprite data replacement'

    return analysis


def main():
    parser = argparse.ArgumentParser(description='Compare WRAM dumps for diff analysis')
    parser.add_argument('baseline', help='Baseline WRAM dump file')
    parser.add_argument('ablated', help='Ablated WRAM dump file')

    args = parser.parse_args()

    baseline_path = Path(args.baseline)
    ablated_path = Path(args.ablated)

    if not baseline_path.exists():
        print(f"ERROR: Baseline file not found: {baseline_path}")
        sys.exit(1)
    if not ablated_path.exists():
        print(f"ERROR: Ablated file not found: {ablated_path}")
        sys.exit(1)

    baseline = load_dump(baseline_path)
    ablated = load_dump(ablated_path)

    print(f"Baseline: {baseline_path} ({len(baseline)} bytes)")
    print(f"Ablated:  {ablated_path} ({len(ablated)} bytes)")
    print("=" * 60)

    ranges = find_diff_ranges(baseline, ablated)
    analysis = analyze_diff_pattern(ranges)

    print(f"\nDiff Type: {analysis['type']}")
    print(f"Description: {analysis.get('description', 'N/A')}")
    print(f"\nTotal diff bytes: {analysis.get('total_diff_bytes', 0)}")
    print(f"Diff percentage: {analysis.get('diff_percentage', 0):.2f}%")
    print(f"Number of ranges: {analysis.get('num_ranges', 0)}")

    if 'ranges' in analysis and analysis['ranges']:
        print("\nDiff ranges:")
        for i, r in enumerate(analysis['ranges'][:10]):  # Limit to first 10
            print(f"\n  Range {i+1}:")
            print(f"    WRAM addr: {r['wram_addr']} (offset {r['offset']})")
            print(f"    Size: {r['size']} bytes")
            print(f"    Baseline: {r['baseline_hex']}")
            print(f"    Ablated:  {r['ablated_hex']}")

        if len(analysis['ranges']) > 10:
            print(f"\n  ... and {len(analysis['ranges']) - 10} more ranges")

    print("\n" + "=" * 60)
    print("INTERPRETATION:")
    if analysis['type'] == 'IDENTICAL':
        print("  The WRAM staging buffer is identical - ablation may affect later frames or VRAM directly")
    elif analysis['type'] == 'LOCALIZED_SMALL':
        print("  0xE9E667 likely controls a POINTER or INDEX that selects different data")
        print("  The actual sprite tile data is the same, but accessed via different offset")
    elif analysis['type'] == 'LOCALIZED_BLOCK':
        print("  0xE9E667 likely selects a DIFFERENT SPRITE VARIANT (animation frame, palette)")
        print("  A single tile's worth of data is different")
    elif analysis['type'] == 'WIDESPREAD':
        print("  0xE9E667 likely controls a MAJOR BRANCH in sprite loading")
        print("  Could be: different character, entirely different sprite batch, or decode mode")
    else:
        print("  Intermediate pattern - may need deeper analysis of the specific ranges")


if __name__ == '__main__':
    main()
