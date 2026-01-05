#!/usr/bin/env python3
"""
Run the full sprite correlation pipeline: VRAM → Staging → ROM.

Traces sprite captures back to their ROM offsets by:
1. Correlating VRAM tiles with DMA events (timing correlation)
2. Matching tile data to ROM (with SA-1 character conversion)

Usage:
    python scripts/run_full_correlation.py \\
        --rom "roms/Kirby Super Star (USA).sfc" \\
        --dma-log mesen2_exchange/dma_probe_log.txt \\
        --capture "mesen2_exchange/sprite_capture_*.json"

    # Output as JSON
    python scripts/run_full_correlation.py \\
        --rom "roms/Kirby Super Star (USA).sfc" \\
        --dma-log mesen2_exchange/dma_probe_log.txt \\
        --capture "mesen2_exchange/sprite_capture_*.json" \\
        --json > results.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.mesen_integration.full_correlation_pipeline import (
    CorrelationPipeline,
    format_pipeline_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Full sprite correlation: VRAM → Staging → ROM")
    parser.add_argument(
        "--rom",
        type=Path,
        required=True,
        help="Path to ROM file",
    )
    parser.add_argument(
        "--dma-log",
        type=Path,
        required=True,
        help="Path to DMA probe log file or directory",
    )
    parser.add_argument(
        "--capture",
        type=Path,
        nargs="+",
        required=True,
        help="Sprite capture JSON file(s) or glob pattern",
    )
    parser.add_argument(
        "--frame-window",
        type=int,
        default=100,
        help="Max frames to search for DMA events (default: 100)",
    )
    parser.add_argument(
        "--no-sa1-conversion",
        action="store_true",
        help="Disable SA-1 bitmap→SNES conversion (for testing)",
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
    parser.add_argument(
        "--save-database",
        type=Path,
        help="Save tile database to JSON file",
    )
    parser.add_argument(
        "--scan-rom",
        action="store_true",
        help="Scan entire ROM for HAL blocks (comprehensive but slow)",
    )
    parser.add_argument(
        "--scan-step",
        type=lambda x: int(x, 16) if x.startswith("0x") else int(x),
        default=0x400,
        help="Scan step size in bytes (default: 0x400 = 1KB)",
    )
    parser.add_argument(
        "--scan-min-tiles",
        type=int,
        default=8,
        help="Minimum tiles per block when scanning (default: 8)",
    )
    parser.add_argument(
        "--build-two-plane",
        action="store_true",
        help="Build two-plane index from raw ROM for tiles with 2 zero planes",
    )
    parser.add_argument(
        "--two-plane-step",
        type=int,
        default=16,
        help="Step size for two-plane scanning (default: 16 bytes)",
    )
    parser.add_argument(
        "--json-max-matches",
        type=int,
        default=200,
        help="Max rom_matches in JSON output (default: 200). Use 0 for unlimited.",
    )
    parser.add_argument(
        "--json-max-mapping",
        type=int,
        default=50,
        help="Max staging_to_rom mappings in JSON output (default: 50). Use 0 for unlimited.",
    )

    args = parser.parse_args()

    # Validate ROM exists
    if not args.rom.exists():
        print(f"Error: ROM file not found: {args.rom}", file=sys.stderr)
        return 1

    # Initialize pipeline
    print(f"Initializing pipeline with ROM: {args.rom}", file=sys.stderr)
    pipeline = CorrelationPipeline(
        rom_path=args.rom,
        dma_log_path=args.dma_log,
        frame_window=args.frame_window,
        apply_sa1_conversion=not args.no_sa1_conversion,
    )

    # Load captures
    tile_count = 0
    for capture_path in args.capture:
        if capture_path.is_file():
            tile_count += pipeline.load_capture(capture_path)
        elif "*" in str(capture_path) or "?" in str(capture_path):
            tile_count += pipeline.load_captures(capture_path)
        else:
            print(f"Warning: {capture_path} not found", file=sys.stderr)

    print(f"Loaded {tile_count} tiles from captures", file=sys.stderr)

    if tile_count == 0:
        print("Error: No tiles loaded from captures", file=sys.stderr)
        return 1

    # Build database
    if args.scan_rom:
        print(f"Scanning ROM for HAL blocks (step=0x{args.scan_step:X})...", file=sys.stderr)
    else:
        print("Building ROM tile database from known offsets...", file=sys.stderr)

    if args.build_two_plane:
        print(f"Will also build two-plane index (step={args.two_plane_step})...", file=sys.stderr)

    db_tiles = pipeline.build_database(
        scan_rom=args.scan_rom,
        scan_step=args.scan_step,
        scan_min_tiles=args.scan_min_tiles,
        build_two_plane=args.build_two_plane,
        two_plane_step=args.two_plane_step,
    )
    print(f"Database built: {db_tiles} tiles indexed", file=sys.stderr)

    # Save database if requested
    if args.save_database:
        pipeline._matcher.save_database(args.save_database)
        print(f"Database saved to {args.save_database}", file=sys.stderr)

    # Run pipeline
    print("Running correlation pipeline...", file=sys.stderr)
    results = pipeline.run()

    # Generate output
    if args.json:
        # Apply configurable limits (0 = unlimited)
        rom_matches = (
            results.rom_matches if args.json_max_matches == 0 else results.rom_matches[: args.json_max_matches]
        )
        staging_items = list(results.staging_to_rom_mapping.items())
        if args.json_max_mapping != 0:
            staging_items = staging_items[: args.json_max_mapping]

        output_data = {
            "summary": results.get_summary(),
            "database_stats": pipeline.get_database_stats(),
            "rom_matches": [
                {
                    "sprite_id": m.sprite_id,
                    "tile_index": m.tile_index,
                    "vram_addr": f"0x{m.vram_addr:04X}",
                    "staging_addr": f"0x{m.staging_addr:06X}",
                    "dma_frame": m.dma_frame,
                    "rom_offset": f"0x{m.rom_offset:06X}",
                    "rom_tile_index": m.rom_tile_index,
                    "rom_description": m.rom_description,
                    "flip_variant": m.flip_variant,
                }
                for m in rom_matches
            ],
            "staging_to_rom": {
                f"0x{staging:06X}": [f"0x{rom:06X}" for rom in rom_offsets] for staging, rom_offsets in staging_items
            },
        }
        output = json.dumps(output_data, indent=2)
    else:
        output = format_pipeline_report(results)

    # Write output
    if args.output:
        args.output.write_text(output)
        print(f"Results written to {args.output}", file=sys.stderr)
    else:
        print(output)

    # Print summary to stderr
    summary = results.get_summary()
    print("\n--- Summary ---", file=sys.stderr)
    print(f"ROM match rate: {summary['rom_match_rate']}", file=sys.stderr)
    print(f"Unique ROM offsets: {summary['unique_rom_offsets']}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
