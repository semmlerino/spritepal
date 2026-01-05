#!/usr/bin/env python3
"""
Compare two ablation test runs to identify which output bytes changed.

Reports byte offsets and tile indices for changed bytes.
SNES tiles are 32 bytes (4bpp 8x8).

Usage:
    python compare_ablation_runs.py <baseline_log> <ablation_log>

Example:
    python compare_ablation_runs.py baseline.txt ablation.txt
"""

import re
import sys
from pathlib import Path


def parse_output_bytes(log_path: Path) -> tuple[int, str, list[int]] | None:
    """Extract POPULATE_OUTPUT_BYTES from log file.

    Returns: (hash, hex_string, list_of_bytes) or None if not found.
    """
    with open(log_path) as f:
        for line in f:
            match = re.search(r"POPULATE_OUTPUT_BYTES:.*hash=0x([0-9A-Fa-f]+)\s+hex=([0-9A-Fa-f]+)", line)
            if match:
                hash_val = int(match.group(1), 16)
                hex_str = match.group(2)
                # Parse hex string to bytes
                byte_list = []
                for i in range(0, len(hex_str), 2):
                    byte_list.append(int(hex_str[i : i + 2], 16))
                return (hash_val, hex_str, byte_list)
    return None


def parse_ablation_result(log_path: Path) -> dict | None:
    """Extract ABLATION_RESULT from log file."""
    with open(log_path) as f:
        for line in f:
            match = re.search(r"ABLATION_RESULT:.*range=0x([0-9A-Fa-f]+)-0x([0-9A-Fa-f]+).*corrupted_reads=(\d+)", line)
            if match:
                return {
                    "range_start": int(match.group(1), 16),
                    "range_end": int(match.group(2), 16),
                    "corrupted_reads": int(match.group(3)),
                }
    return None


def compare_bytes(baseline: list[int], ablation: list[int]) -> list[dict]:
    """Compare byte lists, return list of changed byte info."""
    if len(baseline) != len(ablation):
        print(f"WARNING: Length mismatch - baseline={len(baseline)}, ablation={len(ablation)}")

    changes = []
    min_len = min(len(baseline), len(ablation))

    for i in range(min_len):
        if baseline[i] != ablation[i]:
            tile_idx = i // 32
            byte_in_tile = i % 32
            changes.append(
                {
                    "offset": i,
                    "baseline": baseline[i],
                    "ablation": ablation[i],
                    "tile_index": tile_idx,
                    "byte_in_tile": byte_in_tile,
                }
            )

    return changes


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    baseline_path = Path(sys.argv[1])
    ablation_path = Path(sys.argv[2])

    for p in [baseline_path, ablation_path]:
        if not p.exists():
            print(f"Error: File not found: {p}")
            sys.exit(1)

    print("=" * 70)
    print("ABLATION COMPARISON")
    print("=" * 70)
    print(f"Baseline: {baseline_path}")
    print(f"Ablation: {ablation_path}")
    print()

    # Parse baseline
    baseline_data = parse_output_bytes(baseline_path)
    if not baseline_data:
        print("Error: No POPULATE_OUTPUT_BYTES found in baseline log")
        sys.exit(1)
    baseline_hash, _, baseline_bytes = baseline_data
    print(f"Baseline hash: 0x{baseline_hash:08X}")
    print(f"Baseline bytes: {len(baseline_bytes)}")

    # Parse ablation
    ablation_data = parse_output_bytes(ablation_path)
    if not ablation_data:
        print("Error: No POPULATE_OUTPUT_BYTES found in ablation log")
        sys.exit(1)
    ablation_hash, _, ablation_bytes = ablation_data
    print(f"Ablation hash: 0x{ablation_hash:08X}")
    print(f"Ablation bytes: {len(ablation_bytes)}")

    # Parse ablation result
    ablation_result = parse_ablation_result(ablation_path)
    if ablation_result:
        print()
        print(f"Ablation range: 0x{ablation_result['range_start']:06X}-0x{ablation_result['range_end']:06X}")
        print(f"Corrupted reads: {ablation_result['corrupted_reads']}")

    print()
    print("-" * 70)

    # Compare
    if baseline_hash == ablation_hash:
        print("RESULT: Hashes MATCH - ablation had NO EFFECT")
        print("This ROM range is NOT a causal input to the output buffer.")
        return

    print("RESULT: Hashes DIFFER - ablation CHANGED output")
    print()

    changes = compare_bytes(baseline_bytes, ablation_bytes)

    # Group by tile
    tiles_affected = {}
    for c in changes:
        tile_idx = c["tile_index"]
        if tile_idx not in tiles_affected:
            tiles_affected[tile_idx] = []
        tiles_affected[tile_idx].append(c)

    print(f"Changed bytes: {len(changes)}")
    print(f"Tiles affected: {len(tiles_affected)}")
    print()

    # Detail by tile
    print("TILE-LEVEL CHANGES:")
    print("-" * 70)
    for tile_idx in sorted(tiles_affected.keys()):
        tile_changes = tiles_affected[tile_idx]
        print(f"  Tile {tile_idx} ({len(tile_changes)} bytes changed):")
        for c in tile_changes:
            print(
                f"    offset=0x{c['offset']:02X} byte_in_tile={c['byte_in_tile']:2d}: "
                f"0x{c['baseline']:02X} -> 0x{c['ablation']:02X}"
            )

    print()
    print("-" * 70)
    print("SUMMARY")
    print("-" * 70)

    if ablation_result:
        range_size = ablation_result["range_end"] - ablation_result["range_start"] + 1
        print(f"Targeted ROM range: {range_size} bytes")
        print(f"Corrupted reads: {ablation_result['corrupted_reads']}")

    print(f"Output bytes changed: {len(changes)} of {len(baseline_bytes)}")
    print(f"Tiles affected: {sorted(tiles_affected.keys())}")

    # Coverage
    coverage_pct = (len(changes) / len(baseline_bytes)) * 100
    print(f"Sensitivity: {coverage_pct:.1f}% of output bytes affected by this ROM range")


if __name__ == "__main__":
    main()
