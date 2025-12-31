#!/usr/bin/env python3
"""
Analyze SA-1 hypothesis data from mesen2_dma_probe.lua output.

Parses dma_probe_log.txt to extract SA-1 DMA entries and determine
if character conversion is being used during gameplay.

Usage:
    python scripts/analyze_sa1_hypothesis.py mesen2_exchange/sa1_hypothesis_run_*/
    python scripts/analyze_sa1_hypothesis.py mesen2_exchange/movie_probe_run/dma_probe_log.txt

"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

# Pattern to match SA1 DMA log lines
# Example: "12:34:56 SA1 DMA (ctrl_write): ctrl=0x80 enabled=Y char_conv=N auto=N src=0x123456 dest=0x654321 size=0x0100"
SA1_DMA_PATTERN = re.compile(
    r"SA1 DMA \((\w+)\): "
    r"ctrl=0x([0-9A-Fa-f]+) "
    r"enabled=([YN]) "
    r"char_conv=([YN]) "
    r"auto=([YN])"
)


def analyze_log(log_path: Path) -> dict[str, object]:
    """Analyze a single dma_probe_log.txt file for SA-1 hypothesis data."""
    results: dict[str, object] = {
        "log_file": str(log_path),
        "total_sa1_entries": 0,
        "char_conv_enabled": 0,
        "char_conv_disabled": 0,
        "dma_enabled": 0,
        "dma_disabled": 0,
        "auto_enabled": 0,
        "reasons": Counter(),
        "ctrl_values": Counter(),
        "sample_entries": [],
    }

    if not log_path.exists():
        results["error"] = f"File not found: {log_path}"
        return results

    with open(log_path, encoding="utf-8", errors="replace") as f:
        for line_no, line in enumerate(f, 1):
            match = SA1_DMA_PATTERN.search(line)
            if not match:
                continue

            reason = match.group(1)
            ctrl_hex = match.group(2)
            enabled = match.group(3) == "Y"
            char_conv = match.group(4) == "Y"
            auto = match.group(5) == "Y"

            results["total_sa1_entries"] += 1

            if char_conv:
                results["char_conv_enabled"] += 1
            else:
                results["char_conv_disabled"] += 1

            if enabled:
                results["dma_enabled"] += 1
            else:
                results["dma_disabled"] += 1

            if auto:
                results["auto_enabled"] += 1

            results["reasons"][reason] += 1
            results["ctrl_values"][ctrl_hex] += 1

            # Collect sample entries (first 5 char_conv=Y, first 5 char_conv=N)
            sample_entries = results["sample_entries"]
            if isinstance(sample_entries, list):
                if char_conv and sum(1 for e in sample_entries if e.get("char_conv")) < 5:
                    sample_entries.append({
                        "line": line_no,
                        "reason": reason,
                        "ctrl": ctrl_hex,
                        "char_conv": char_conv,
                        "enabled": enabled,
                        "raw": line.strip()[:120],
                    })
                elif not char_conv and sum(1 for e in sample_entries if not e.get("char_conv")) < 5:
                    sample_entries.append({
                        "line": line_no,
                        "reason": reason,
                        "ctrl": ctrl_hex,
                        "char_conv": char_conv,
                        "enabled": enabled,
                        "raw": line.strip()[:120],
                    })

    return results


def determine_hypothesis_outcome(results: dict[str, object]) -> str:
    """Determine the SA-1 hypothesis outcome based on analysis results."""
    total = results.get("total_sa1_entries", 0)
    char_conv_enabled = results.get("char_conv_enabled", 0)
    char_conv_disabled = results.get("char_conv_disabled", 0)

    if total == 0:
        return "INCONCLUSIVE - No SA-1 DMA entries found"

    ratio = char_conv_enabled / total if total > 0 else 0

    if ratio > 0.5:
        return f"CONFIRMED - {ratio:.1%} of SA-1 DMA operations use character conversion"
    elif ratio > 0.1:
        return f"PARTIAL - {ratio:.1%} of SA-1 DMA operations use character conversion"
    elif char_conv_enabled > 0:
        return f"WEAK - Only {char_conv_enabled}/{total} SA-1 DMA operations use character conversion"
    else:
        return "FALSIFIED - No character conversion observed in any SA-1 DMA operation"


def print_report(results: dict[str, object]) -> None:
    """Print the analysis report."""
    print("=" * 80)
    print("SA-1 CHARACTER CONVERSION HYPOTHESIS ANALYSIS")
    print("=" * 80)
    print()

    if "error" in results:
        print(f"ERROR: {results['error']}")
        return

    print(f"Log file: {results['log_file']}")
    print()

    total = results["total_sa1_entries"]
    print(f"Total SA-1 DMA entries: {total}")
    print()

    if total == 0:
        print("No SA-1 DMA entries found in log.")
        print("This could mean:")
        print("  - The game doesn't use SA-1 DMA during the captured period")
        print("  - The log was from a non-SA-1 game")
        print("  - The capture period was too short or early")
        return

    print("CHARACTER CONVERSION STATUS:")
    char_conv_enabled = results["char_conv_enabled"]
    char_conv_disabled = results["char_conv_disabled"]
    ratio = char_conv_enabled / total if total > 0 else 0
    print(f"  char_conv=Y (enabled):  {char_conv_enabled:5d} ({ratio:.1%})")
    print(f"  char_conv=N (disabled): {char_conv_disabled:5d} ({1-ratio:.1%})")
    print()

    print("DMA STATUS:")
    dma_enabled = results["dma_enabled"]
    dma_disabled = results["dma_disabled"]
    print(f"  enabled=Y:  {dma_enabled:5d}")
    print(f"  enabled=N:  {dma_disabled:5d}")
    print()

    print("TRIGGER REASONS:")
    reasons = results.get("reasons", {})
    if isinstance(reasons, Counter):
        for reason, count in reasons.most_common():
            print(f"  {reason}: {count}")
    print()

    print("CTRL REGISTER VALUES:")
    ctrl_values = results.get("ctrl_values", {})
    if isinstance(ctrl_values, Counter):
        for ctrl, count in ctrl_values.most_common(10):
            # Decode the ctrl bits
            ctrl_int = int(ctrl, 16)
            enabled = "enabled" if (ctrl_int & 0x80) else "disabled"
            char_conv = "CC" if (ctrl_int & 0x20) else "normal"
            auto = "auto" if (ctrl_int & 0x10) else "manual"
            print(f"  0x{ctrl}: {count:5d}  ({enabled}, {char_conv}, {auto})")
    print()

    print("SAMPLE ENTRIES:")
    sample_entries = results.get("sample_entries", [])
    if isinstance(sample_entries, list):
        for entry in sample_entries[:10]:
            if isinstance(entry, dict):
                cc_status = "char_conv=Y" if entry.get("char_conv") else "char_conv=N"
                print(f"  Line {entry.get('line', '?')}: {cc_status} ctrl=0x{entry.get('ctrl', '??')}")
    print()

    print("=" * 80)
    outcome = determine_hypothesis_outcome(results)
    print(f"HYPOTHESIS OUTCOME: {outcome}")
    print("=" * 80)
    print()

    if "CONFIRMED" in outcome or "PARTIAL" in outcome:
        print("NEXT STEPS:")
        print("  1. Character conversion IS being used")
        print("  2. VRAM tiles will NOT match ROM-decompressed bytes")
        print("  3. Use Strategy A (timing correlation) instead of direct hash matching")
        print("  4. Update SA1_HYPOTHESIS_FINDINGS.md with this outcome")
    elif "FALSIFIED" in outcome:
        print("NEXT STEPS:")
        print("  1. Character conversion is NOT the cause of low hash match rate")
        print("  2. Investigate other causes:")
        print("     - Palette remapping")
        print("     - Runtime composition")
        print("     - Compression variant")
        print("     - Interlaced planes")
        print("  3. Update SA1_HYPOTHESIS_FINDINGS.md with this outcome")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze SA-1 hypothesis data from mesen2_dma_probe.lua output."
    )
    parser.add_argument(
        "target",
        type=Path,
        help="Log file or directory containing dma_probe_log.txt",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )

    args = parser.parse_args()

    # Find the log file
    if args.target.is_dir():
        log_path = args.target / "dma_probe_log.txt"
    else:
        log_path = args.target

    results = analyze_log(log_path)

    if args.json:
        import json
        # Convert Counter objects to dicts for JSON serialization
        output = dict(results)
        if isinstance(output.get("reasons"), Counter):
            output["reasons"] = dict(output["reasons"])
        if isinstance(output.get("ctrl_values"), Counter):
            output["ctrl_values"] = dict(output["ctrl_values"])
        output["hypothesis_outcome"] = determine_hypothesis_outcome(results)
        print(json.dumps(output, indent=2))
    else:
        print_report(results)

    # Exit code based on outcome
    if "error" in results:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
