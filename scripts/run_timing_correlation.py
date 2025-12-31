#!/usr/bin/env python3
"""
Run timing correlation between sprite captures and DMA events.

Links OAM sprite tiles to the DMA transfers that populated their VRAM,
then traces back to staging buffer addresses.

Usage:
    python scripts/run_timing_correlation.py \\
        --capture mesen2_exchange/sprite_capture_*.json \\
        --dma-log mesen2_exchange/dma_probe_log.txt

    # With wider frame search window
    python scripts/run_timing_correlation.py \\
        --capture mesen2_exchange/sprite_capture_*.json \\
        --dma-log mesen2_exchange/sa1_hypothesis_run_*/dma_probe_log.txt \\
        --frame-window 500

    # Output as JSON
    python scripts/run_timing_correlation.py \\
        --capture mesen2_exchange/sprite_capture_*.json \\
        --dma-log mesen2_exchange/dma_probe_log.txt \\
        --json > correlation_results.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.mesen_integration.timing_correlator import (
    TimingCorrelator,
    format_correlation_report,
    generate_correlation_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Correlate sprite captures with DMA events for ROM tracing."
    )
    parser.add_argument(
        "--capture",
        type=Path,
        nargs="+",
        required=True,
        help="Sprite capture JSON file(s) or glob pattern",
    )
    parser.add_argument(
        "--dma-log",
        type=Path,
        required=True,
        help="DMA probe log file or directory containing dma_probe_log.txt",
    )
    parser.add_argument(
        "--frame-window",
        type=int,
        default=100,
        help="Max frames before capture to search for DMA (default: 100)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file (default: stdout)",
    )

    args = parser.parse_args()

    # Initialize correlator
    correlator = TimingCorrelator(frame_window=args.frame_window)

    # Find DMA log
    if args.dma_log.is_dir():
        dma_log_path = args.dma_log / "dma_probe_log.txt"
    else:
        dma_log_path = args.dma_log

    print(f"Loading DMA log from {dma_log_path}...", file=sys.stderr)
    dma_count = correlator.load_dma_log(dma_log_path)
    print(f"Loaded {dma_count} DMA events", file=sys.stderr)

    if dma_count == 0:
        print("Error: No DMA events found in log", file=sys.stderr)
        return 1

    # Load captures
    tile_count = 0
    for capture_path in args.capture:
        if capture_path.is_file():
            tile_count += correlator.load_capture(capture_path)
        elif "*" in str(capture_path) or "?" in str(capture_path):
            # Glob pattern
            tile_count += correlator.load_captures_glob(capture_path)
        else:
            print(f"Warning: {capture_path} not found", file=sys.stderr)

    print(
        f"Loaded {len(correlator.captures)} captures with {tile_count} tiles",
        file=sys.stderr,
    )

    if not correlator.captures:
        print("Error: No captures loaded", file=sys.stderr)
        return 1

    # Run correlation
    print("Running correlation...", file=sys.stderr)
    results = correlator.correlate()

    # Generate output
    if args.json:
        output = json.dumps(generate_correlation_json(results), indent=2)
    else:
        output = format_correlation_report(results)

    # Write output
    if args.output:
        args.output.write_text(output)
        print(f"Results written to {args.output}", file=sys.stderr)
    else:
        print(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
