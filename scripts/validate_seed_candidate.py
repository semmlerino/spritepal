#!/usr/bin/env python3
"""
Validate ROM trace seed candidates by trying address conversions + HAL decompression.

Example:
  python3 scripts/validate_seed_candidate.py roms/game.sfc --seed 0xFCC455 --auto-map --tiles 256 --png out.png
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.hal_compression import HALCompressionError, HALCompressor
from core.tile_renderer import TileRenderer
from utils.constants import BYTES_PER_TILE, RomMappingType, normalize_address, parse_address_string
from utils.logging_config import setup_logging

LOW_INFO_UNIQUE_BYTES = 2


@dataclass(frozen=True)
class CandidateResult:
    name: str
    offset: int
    ok: bool
    error: str | None
    data_len: int
    remainder: int
    tile_count: int
    high_info_tiles: int
    high_info_pct: float
    avg_unique: float
    flat_tiles: int
    flat_pct: float
    hist_cv: float
    plausible: bool


def _unique_count(tile_data: bytes) -> int:
    return len(set(tile_data))


def _analyze_tiles(data: bytes) -> tuple[int, int, float, float, int, float]:
    tile_count = len(data) // BYTES_PER_TILE
    if tile_count <= 0:
        return 0, 0, 0.0, 0.0, 0, 0.0
    unique_counts = []
    high_info = 0
    flat_tiles = 0
    for i in range(tile_count):
        tile = data[i * BYTES_PER_TILE : (i + 1) * BYTES_PER_TILE]
        unique = _unique_count(tile)
        unique_counts.append(unique)
        if unique > LOW_INFO_UNIQUE_BYTES:
            high_info += 1
        if all(b == 0x00 for b in tile) or all(b == 0xFF for b in tile):
            flat_tiles += 1
    high_info_pct = high_info / tile_count if tile_count else 0.0
    avg_unique = sum(unique_counts) / tile_count if tile_count else 0.0
    flat_pct = flat_tiles / tile_count if tile_count else 0.0
    return tile_count, high_info, high_info_pct, avg_unique, flat_tiles, flat_pct


def _histogram_cv(data: bytes) -> float:
    if not data:
        return 0.0
    counts = [0] * 256
    for b in data:
        counts[b] += 1
    mean = sum(counts) / len(counts)
    if mean == 0:
        return 0.0
    variance = sum((count - mean) ** 2 for count in counts) / len(counts)
    return math.sqrt(variance) / mean


def _build_candidates(
    seed: int,
    rom_size: int,
    *,
    has_header: bool,
    mapping_types: list[RomMappingType],
    include_raw: bool,
    prg_size: int | None,
) -> list[tuple[str, int]]:
    candidates: dict[int, list[str]] = {}

    def add(name: str, offset: int) -> None:
        if offset < 0 or offset >= rom_size:
            return
        candidates.setdefault(offset, []).append(name)

    raw_allowed = True
    if prg_size is not None and seed >= prg_size:
        raw_allowed = False

    if include_raw and raw_allowed:
        add("file_offset_raw", seed)
        if has_header:
            add("file_offset_header", seed + 0x200)

    for mapping in mapping_types:
        offset = normalize_address(seed, rom_size, mapping_type=mapping)
        base_name = mapping.name.lower()
        add(base_name, offset)
        if has_header:
            add(f"{base_name}+header", offset + 0x200)

    ordered: list[tuple[str, int]] = []
    for offset, names in sorted(candidates.items()):
        ordered.append(("+".join(names), offset))
    return ordered


def _render_tiles(data: bytes, out_path: Path, tiles: int, tiles_per_row: int) -> None:
    tile_count = len(data) // BYTES_PER_TILE
    if tile_count <= 0:
        return
    tiles = min(tiles, tile_count)
    width_tiles = max(1, tiles_per_row)
    height_tiles = math.ceil(tiles / width_tiles)
    render_data = data[: tiles * BYTES_PER_TILE]
    renderer = TileRenderer()
    img = renderer.render_tiles(render_data, width_tiles, height_tiles, palette_index=None)
    if img is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate ROM trace seeds with HAL decompression.")
    parser.add_argument("rom", type=Path, help="Path to the ROM file")
    parser.add_argument("--seed", required=True, help="Seed address (hex, decimal, or SNES bank:offset)")
    parser.add_argument("--auto-map", action="store_true", help="Try common SNES mappings + raw offset")
    parser.add_argument(
        "--mapping",
        action="append",
        choices=["lorom", "hirom", "sa1"],
        help="Mapping types to try (repeatable)",
    )
    parser.add_argument(
        "--force-raw", action="store_true", help="Include raw file-offset candidate even for banked seeds"
    )
    parser.add_argument("--prg-size", help="PRG size from rom trace (hex ok)")
    parser.add_argument("--min-tiles", type=int, default=32, help="Minimum tiles for plausibility")
    parser.add_argument(
        "--min-high-info-pct",
        type=float,
        default=0.2,
        help="Minimum high-info tile percentage (0-1)",
    )
    parser.add_argument("--max-flat-pct", type=float, default=0.5, help="Reject if flat tiles exceed this ratio")
    parser.add_argument(
        "--min-hist-cv",
        type=float,
        default=0.0,
        help="Reject if byte histogram CV is below this threshold (0 disables)",
    )
    parser.add_argument("--max-bytes", default="0x10000", help="Reject outputs larger than this (hex ok)")
    parser.add_argument("--max-tiles", type=int, default=0, help="Reject outputs larger than this (0 disables)")
    parser.add_argument("--tiles", type=int, default=256, help="Tiles to render when --png is set")
    parser.add_argument("--tiles-per-row", type=int, default=16, help="Tiles per row for PNG output")
    parser.add_argument("--png", type=Path, help="Optional PNG output path")
    args = parser.parse_args()

    setup_logging(log_level="WARNING")

    if not args.rom.exists():
        print(f"ROM not found: {args.rom}")
        return 1

    try:
        seed_value, seed_format = parse_address_string(args.seed)
    except ValueError:
        seed_value = int(str(args.seed), 0)
        seed_format = "numeric"

    prg_size = int(str(args.prg_size), 0) if args.prg_size else None
    max_bytes = int(str(args.max_bytes), 0) if args.max_bytes else 0

    rom_size = args.rom.stat().st_size
    has_header = rom_size % 1024 == 512

    mappings: list[RomMappingType] = []
    if args.mapping:
        for entry in args.mapping:
            mappings.append(RomMappingType[entry.upper()])
    elif args.auto_map:
        mappings = [RomMappingType.SA1, RomMappingType.HIROM, RomMappingType.LOROM]

    print(f"Seed: {args.seed} (parsed=0x{seed_value:06X}, format={seed_format})")
    if prg_size is not None:
        print(f"PRG size: 0x{prg_size:X} ({prg_size} bytes)")
    print(f"ROM size: 0x{rom_size:X} ({rom_size} bytes), header={'yes' if has_header else 'no'}")
    if has_header:
        print("Header detection is heuristic (rom_size % 1024 == 512). Verify if results look off.")
    include_raw = True
    if seed_format in ("snes_banked", "snes") and not args.force_raw:
        include_raw = False
        print("Seed looks like a bus address; raw file-offset candidate disabled (use --force-raw to override).")
    if prg_size is not None and seed_value >= prg_size:
        print("Seed >= PRG size; skipping raw file-offset candidate.")

    candidates = _build_candidates(
        seed_value,
        rom_size,
        has_header=has_header,
        mapping_types=mappings,
        include_raw=include_raw,
        prg_size=prg_size,
    )

    if not candidates:
        print("No candidate offsets to test.")
        return 1

    hal = HALCompressor()
    results: list[CandidateResult] = []
    any_plausible = False

    for name, offset in candidates:
        try:
            data = hal.decompress_from_rom(str(args.rom), offset)
            if max_bytes and len(data) > max_bytes:
                raise HALCompressionError(f"Output exceeds max bytes ({len(data)} > {max_bytes})")
            remainder = len(data) % BYTES_PER_TILE
            tile_count, high_info_tiles, high_info_pct, avg_unique, flat_tiles, flat_pct = _analyze_tiles(data)
            if args.max_tiles and tile_count > args.max_tiles:
                raise HALCompressionError(f"Output exceeds max tiles ({tile_count} > {args.max_tiles})")
            hist_cv = _histogram_cv(data)
            plausible = (
                len(data) >= args.min_tiles * BYTES_PER_TILE
                and remainder == 0
                and high_info_pct >= args.min_high_info_pct
                and flat_pct <= args.max_flat_pct
                and (args.min_hist_cv <= 0 or hist_cv >= args.min_hist_cv)
            )
            result = CandidateResult(
                name=name,
                offset=offset,
                ok=True,
                error=None,
                data_len=len(data),
                remainder=remainder,
                tile_count=tile_count,
                high_info_tiles=high_info_tiles,
                high_info_pct=high_info_pct,
                avg_unique=avg_unique,
                flat_tiles=flat_tiles,
                flat_pct=flat_pct,
                hist_cv=hist_cv,
                plausible=plausible,
            )
            results.append(result)
            if plausible:
                any_plausible = True
            if args.png:
                if len(candidates) > 1:
                    out_path = args.png.with_name(f"{args.png.stem}_{name}.png")
                else:
                    out_path = args.png
                _render_tiles(data, out_path, args.tiles, args.tiles_per_row)
        except HALCompressionError as exc:
            results.append(
                CandidateResult(
                    name=name,
                    offset=offset,
                    ok=False,
                    error=str(exc),
                    data_len=0,
                    remainder=0,
                    tile_count=0,
                    high_info_tiles=0,
                    high_info_pct=0.0,
                    avg_unique=0.0,
                    flat_tiles=0,
                    flat_pct=0.0,
                    hist_cv=0.0,
                    plausible=False,
                )
            )

    print("\nCandidate results:")
    for result in results:
        status = "ok" if result.ok else "error"
        print(
            f"- {result.name}: offset=0x{result.offset:06X} status={status} "
            f"len={result.data_len} remainder={result.remainder} tiles={result.tile_count} "
            f"high_info={result.high_info_tiles} ({result.high_info_pct:.1%}) avg_unique={result.avg_unique:.1f} "
            f"flat={result.flat_tiles} ({result.flat_pct:.1%}) hist_cv={result.hist_cv:.3f} "
            f"plausible={result.plausible}"
        )
        if result.error:
            print(f"  error: {result.error}")

    return 0 if any_plausible else 2


if __name__ == "__main__":
    raise SystemExit(main())
