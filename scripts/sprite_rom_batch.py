#!/usr/bin/env python3
"""Batch Sprite ROM Mapper - Process multiple dump directories and merge results.

Scans directories recursively for VRAM/OAM dump pairs and builds a complete
ROM address map across all animation frames.

Usage:
    python sprite_rom_batch.py <rom_path> <base_dir> [options]

Examples:
    # Scan all subdirectories for Dedede dumps
    python sprite_rom_batch.py roms/Kirby.sfc DededeDMP --palette 7

    # Export merged map
    python sprite_rom_batch.py roms/Kirby.sfc DededeDMP -p 7 -o dedede_all_frames.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from sprite_rom_mapper import (
    SpriteROMMap,
    export_to_json,
    find_dump_files,
    format_address_map,
    map_sprites_to_rom,
)


@dataclass
class ROMRegion:
    """A contiguous region in ROM used by sprite tiles."""

    start: int
    end: int
    frames: list[str]  # Frame names that use this region


@dataclass
class MergedSpriteMap:
    """Combined sprite map across multiple animation frames."""

    palette: int
    frames: list[SpriteROMMap]
    all_rom_offsets: set[int]
    regions: list[ROMRegion]


def find_all_dump_dirs(base_dir: Path) -> list[Path]:
    """Recursively find directories containing dump files."""
    dump_dirs = []

    # Check base dir itself
    files = find_dump_files(base_dir)
    if "vram" in files and "oam" in files:
        dump_dirs.append(base_dir)

    # Check subdirectories
    for subdir in base_dir.iterdir():
        if subdir.is_dir():
            dump_dirs.extend(find_all_dump_dirs(subdir))

    return dump_dirs


def identify_rom_regions(sprite_maps: list[SpriteROMMap], gap_threshold: int = 0x100) -> list[ROMRegion]:
    """Identify contiguous ROM regions from sprite maps.

    Args:
        sprite_maps: List of sprite maps to analyze
        gap_threshold: Max gap between offsets to consider same region
    """
    # Collect all offsets with frame info
    offset_frames: dict[int, list[str]] = {}
    for sm in sprite_maps:
        for match in sm.matches.values():
            if match.rom_offset not in offset_frames:
                offset_frames[match.rom_offset] = []
            if sm.frame_name not in offset_frames[match.rom_offset]:
                offset_frames[match.rom_offset].append(sm.frame_name)

    if not offset_frames:
        return []

    # Sort offsets
    sorted_offsets = sorted(offset_frames.keys())

    # Group into regions
    regions: list[ROMRegion] = []
    region_start = sorted_offsets[0]
    region_end = sorted_offsets[0]
    region_frames: set[str] = set(offset_frames[sorted_offsets[0]])

    for offset in sorted_offsets[1:]:
        if offset - region_end <= gap_threshold:
            # Extend current region
            region_end = offset
            region_frames.update(offset_frames[offset])
        else:
            # Start new region
            regions.append(
                ROMRegion(
                    start=region_start,
                    end=region_end,
                    frames=sorted(region_frames),
                )
            )
            region_start = offset
            region_end = offset
            region_frames = set(offset_frames[offset])

    # Don't forget last region
    regions.append(
        ROMRegion(
            start=region_start,
            end=region_end,
            frames=sorted(region_frames),
        )
    )

    return regions


def merge_sprite_maps(sprite_maps: list[SpriteROMMap], palette: int) -> MergedSpriteMap:
    """Merge multiple sprite maps into a combined view."""
    all_offsets: set[int] = set()
    for sm in sprite_maps:
        for match in sm.matches.values():
            all_offsets.add(match.rom_offset)

    regions = identify_rom_regions(sprite_maps)

    return MergedSpriteMap(
        palette=palette,
        frames=sprite_maps,
        all_rom_offsets=all_offsets,
        regions=regions,
    )


def format_merged_map(merged: MergedSpriteMap) -> str:
    """Format merged map as human-readable text."""
    lines = [
        "=" * 60,
        f"MERGED SPRITE ROM MAP - Palette {merged.palette}",
        "=" * 60,
        f"Total frames: {len(merged.frames)}",
        f"Total unique ROM offsets: {len(merged.all_rom_offsets)}",
        f"Distinct ROM regions: {len(merged.regions)}",
        "",
    ]

    # Show regions
    lines.append("ROM REGIONS:")
    for i, region in enumerate(merged.regions, 1):
        size = region.end - region.start + 32  # +32 for last tile
        lines.append(f"  Region {i}: 0x{region.start:06X} - 0x{region.end + 31:06X} ({size} bytes)")
        lines.append(f"    Frames: {', '.join(region.frames)}")
    lines.append("")

    # Show per-frame summary
    lines.append("PER-FRAME SUMMARY:")
    for sm in merged.frames:
        if sm.matches:
            min_off = min(m.rom_offset for m in sm.matches.values())
            max_off = max(m.rom_offset for m in sm.matches.values())
            lines.append(f"  {sm.frame_name}: {len(sm.matches)} tiles @ 0x{min_off:06X}-0x{max_off:06X}")
        else:
            lines.append(f"  {sm.frame_name}: 0 tiles found")

    return "\n".join(lines)


def export_merged_to_json(merged: MergedSpriteMap) -> dict:
    """Export merged map to JSON-serializable dict."""
    return {
        "palette": merged.palette,
        "total_frames": len(merged.frames),
        "total_unique_offsets": len(merged.all_rom_offsets),
        "regions": [
            {
                "start": f"0x{r.start:06X}",
                "end": f"0x{r.end + 31:06X}",
                "size_bytes": r.end - r.start + 32,
                "frames": r.frames,
            }
            for r in merged.regions
        ],
        "frames": [export_to_json(sm) for sm in merged.frames],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batch process sprite dumps and merge ROM maps",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("rom", type=Path, help="Path to ROM file")
    parser.add_argument("base_dir", type=Path, help="Base directory to scan for dumps")
    parser.add_argument("-p", "--palette", type=int, default=7, help="Palette index (default: 7)")
    parser.add_argument("--obsel", type=lambda x: int(x, 0), default=0x63, help="OBSEL register value")
    parser.add_argument("-o", "--output", type=Path, help="Output JSON file")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show per-frame details")

    args = parser.parse_args()

    # Validate paths
    if not args.rom.exists():
        print(f"Error: ROM file not found: {args.rom}")
        return 1

    if not args.base_dir.exists():
        print(f"Error: Base directory not found: {args.base_dir}")
        return 1

    # Find all dump directories
    dump_dirs = find_all_dump_dirs(args.base_dir)
    if not dump_dirs:
        print(f"Error: No dump directories found in {args.base_dir}")
        return 1

    print(f"ROM: {args.rom}")
    print(f"Found {len(dump_dirs)} dump directories")
    print(f"Palette: {args.palette}")
    print()

    # Process each dump directory
    sprite_maps: list[SpriteROMMap] = []
    for dump_dir in dump_dirs:
        dump_files = find_dump_files(dump_dir)
        if "vram" not in dump_files or "oam" not in dump_files:
            continue

        print(f"Processing: {dump_dir.name}...", end=" ")
        sprite_map = map_sprites_to_rom(
            rom_path=args.rom,
            vram_path=dump_files["vram"],
            oam_path=dump_files["oam"],
            palette_filter=args.palette,
            obsel=args.obsel,
        )
        sprite_maps.append(sprite_map)
        print(f"{len(sprite_map.matches)} tiles")

        if args.verbose:
            print(format_address_map(sprite_map))
            print()

    # Merge results
    merged = merge_sprite_maps(sprite_maps, args.palette)

    # Output
    print()
    print(format_merged_map(merged))

    # Export JSON if requested
    if args.output:
        json_data = export_merged_to_json(merged)
        args.output.write_text(json.dumps(json_data, indent=2))
        print(f"\nExported to: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
