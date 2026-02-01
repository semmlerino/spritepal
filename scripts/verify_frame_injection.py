"""
Visualize which ROM tiles changed for a specific capture/frame mapping.

This produces a single PNG with four panels:
  - Original ROM render (from tile offsets)
  - Injected ROM render
  - Changed tiles mask
  - ROM offset groups (color-coded)

Usage:
    # From a mapping project + game frame id
    uv run python scripts/verify_frame_injection.py \
        --project mapping.spritepal-mapping.json \
        --frame-id capture_1769108991 \
        --original roms/kss.sfc \
        --injected /tmp/kss_injected.sfc \
        -o /tmp/dedede_verify.png

    # From a capture directly
    uv run python scripts/verify_frame_injection.py \
        --capture mesen2_exchange/capture_1769108991.json \
        --entry-ids "6,7,8,9,10,11" \
        --original roms/kss.sfc \
        --injected /tmp/kss_injected.sfc \
        -o /tmp/dedede_verify.png
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.mesen_integration.click_extractor import (  # noqa: E402
    CaptureResult,
    MesenCaptureParser,
    OAMEntry,
    TileData,
)
from core.palette_utils import snes_palette_to_rgb  # noqa: E402
from core.repositories.frame_mapping_repository import FrameMappingRepository  # noqa: E402
from core.services.rom_verification_service import ROMVerificationService  # noqa: E402
from core.tile_utils import decode_4bpp_tile  # noqa: E402

BYTES_PER_TILE = 32


@dataclass(frozen=True)
class TilePlacement:
    entry: OAMEntry
    tile: TileData
    canvas_x: int
    canvas_y: int


def detect_smc_header(rom_data: bytes) -> int:
    """Detect if ROM has SMC header (512 bytes if size % 0x8000 == 512)."""
    return 512 if len(rom_data) % 0x8000 == 512 else 0


def read_tile_from_rom(rom_data: bytes, offset: int, smc_header: int) -> bytes:
    """Read 32 bytes of raw 4bpp tile data from ROM."""
    actual_offset = offset + smc_header
    if actual_offset < 0 or actual_offset + BYTES_PER_TILE > len(rom_data):
        return b"\x00" * BYTES_PER_TILE
    return rom_data[actual_offset : actual_offset + BYTES_PER_TILE]


def iter_tile_placements(entries: Iterable[OAMEntry], bbox: object) -> list[TilePlacement]:
    """Yield tile placements in capture bbox coordinates."""
    placements: list[TilePlacement] = []
    for entry in entries:
        for tile in entry.tiles:
            local_x = tile.pos_x * 8
            local_y = tile.pos_y * 8
            if entry.flip_h:
                local_x = entry.width - local_x - 8
            if entry.flip_v:
                local_y = entry.height - local_y - 8

            screen_x = entry.x + local_x
            screen_y = entry.y + local_y

            canvas_x = screen_x - bbox.x  # type: ignore[attr-defined]
            canvas_y = screen_y - bbox.y  # type: ignore[attr-defined]
            placements.append(TilePlacement(entry=entry, tile=tile, canvas_x=canvas_x, canvas_y=canvas_y))
    return placements


def get_palette_rgb(capture: CaptureResult) -> dict[int, list[tuple[int, int, int]]]:
    """Convert capture palettes to RGB tuples."""
    palette_rgb: dict[int, list[tuple[int, int, int]]] = {}
    for palette_idx, values in capture.palettes.items():
        palette_rgb[palette_idx] = snes_palette_to_rgb(values)
    return palette_rgb


def render_frame_from_rom(
    rom_data: bytes,
    placements: list[TilePlacement],
    palette_rgb: dict[int, list[tuple[int, int, int]]],
    bbox: object,
    smc_header: int,
) -> Image.Image:
    """Render a frame using ROM tile data for each placement."""
    width = bbox.width  # type: ignore[attr-defined]
    height = bbox.height  # type: ignore[attr-defined]
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    for placement in placements:
        tile = placement.tile
        if tile.rom_offset is None:
            continue

        palette = palette_rgb.get(placement.entry.palette)
        if palette is None:
            palette = [(i * 17, i * 17, i * 17) for i in range(16)]

        tile_bytes = read_tile_from_rom(rom_data, tile.rom_offset, smc_header)
        pixels = decode_4bpp_tile(tile_bytes)

        for py in range(8):
            for px in range(8):
                src_x = (7 - px) if placement.entry.flip_h else px
                src_y = (7 - py) if placement.entry.flip_v else py
                color_idx = pixels[src_y][src_x]
                if color_idx == 0:
                    continue
                color = palette[color_idx]
                dest_x = placement.canvas_x + px
                dest_y = placement.canvas_y + py
                if 0 <= dest_x < width and 0 <= dest_y < height:
                    img.putpixel((dest_x, dest_y), (*color, 255))

    return img


def render_changed_mask(
    original_rom: bytes,
    injected_rom: bytes,
    placements: list[TilePlacement],
    bbox: object,
    smc_header: int,
) -> Image.Image:
    """Render a mask highlighting tiles whose ROM data changed."""
    width = bbox.width  # type: ignore[attr-defined]
    height = bbox.height  # type: ignore[attr-defined]
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    for placement in placements:
        offset = placement.tile.rom_offset
        if offset is None:
            continue
        orig_tile = read_tile_from_rom(original_rom, offset, smc_header)
        new_tile = read_tile_from_rom(injected_rom, offset, smc_header)
        if orig_tile == new_tile:
            continue
        x1 = placement.canvas_x
        y1 = placement.canvas_y
        x2 = x1 + 7
        y2 = y1 + 7
        draw.rectangle([x1, y1, x2, y2], fill=(255, 0, 0, 120), outline=(255, 0, 0, 220))

    return img


def render_offset_groups(
    placements: list[TilePlacement],
    bbox: object,
) -> tuple[Image.Image, dict[int, tuple[int, int, int]]]:
    """Render a color-coded overlay for ROM offset groups."""
    width = bbox.width  # type: ignore[attr-defined]
    height = bbox.height  # type: ignore[attr-defined]
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    unique_offsets = sorted({p.tile.rom_offset for p in placements if p.tile.rom_offset is not None})
    colors: dict[int, tuple[int, int, int]] = {}
    for idx, offset in enumerate(unique_offsets):
        hue = (idx * 0.61803398875) % 1.0  # golden ratio for distribution
        r, g, b = hsv_to_rgb(hue, 0.65, 1.0)
        colors[offset] = (r, g, b)

    for placement in placements:
        offset = placement.tile.rom_offset
        if offset is None:
            continue
        color = colors[offset]
        x1 = placement.canvas_x
        y1 = placement.canvas_y
        x2 = x1 + 7
        y2 = y1 + 7
        draw.rectangle([x1, y1, x2, y2], fill=(*color, 120), outline=(*color, 220))

    return img, colors


def hsv_to_rgb(h: float, s: float, v: float) -> tuple[int, int, int]:
    """Convert HSV to RGB (0-1 floats to 0-255 ints)."""
    i = int(h * 6)
    f = (h * 6) - i
    p = v * (1 - s)
    q = v * (1 - f * s)
    t = v * (1 - (1 - f) * s)
    i = i % 6
    if i == 0:
        r, g, b = v, t, p
    elif i == 1:
        r, g, b = q, v, p
    elif i == 2:
        r, g, b = p, v, t
    elif i == 3:
        r, g, b = p, q, v
    elif i == 4:
        r, g, b = t, p, v
    else:
        r, g, b = v, p, q
    return int(r * 255), int(g * 255), int(b * 255)


def make_panel(image: Image.Image, label: str, scale: int = 4) -> Image.Image:
    """Create a labeled panel with optional scaling."""
    label_height = 18
    bg_color = (30, 30, 30, 255)
    scaled = image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST)
    panel = Image.new("RGBA", (scaled.width, scaled.height + label_height), bg_color)
    panel.paste(scaled, (0, label_height))
    draw = ImageDraw.Draw(panel)
    font = ImageFont.load_default()
    draw.text((6, 2), label, fill=(220, 220, 220, 255), font=font)
    return panel


def compose_grid(panels: list[Image.Image], cols: int = 2, margin: int = 12) -> Image.Image:
    """Compose panels into a grid."""
    rows = (len(panels) + cols - 1) // cols
    cell_w = max(p.width for p in panels)
    cell_h = max(p.height for p in panels)
    width = cols * cell_w + (cols + 1) * margin
    height = rows * cell_h + (rows + 1) * margin
    canvas = Image.new("RGBA", (width, height), (20, 20, 20, 255))

    for idx, panel in enumerate(panels):
        row = idx // cols
        col = idx % cols
        x = margin + col * (cell_w + margin)
        y = margin + row * (cell_h + margin)
        canvas.paste(panel, (x, y))

    return canvas


def parse_entry_ids(raw: str) -> list[int]:
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def get_relevant_entries(
    capture: CaptureResult,
    selected_entry_ids: list[int] | None,
    rom_offsets: list[int] | None,
) -> list[OAMEntry]:
    if selected_entry_ids:
        selected_set = set(selected_entry_ids)
        return [e for e in capture.entries if e.id in selected_set]
    if rom_offsets:
        offset_set = set(rom_offsets)
        return [e for e in capture.entries if e.rom_offset in offset_set]
    return capture.entries


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify frame injection with visual tile confirmation.")
    parser.add_argument("--project", type=Path, help="Path to .spritepal-mapping.json")
    parser.add_argument("--frame-id", type=str, help="Game frame id (from project)")
    parser.add_argument("--mapping-index", type=int, help="Mapping index (from project)")
    parser.add_argument("--capture", type=Path, help="Path to capture JSON (manual mode)")
    parser.add_argument(
        "--compare-capture",
        type=Path,
        help="Optional second capture JSON to render injected ROM with a different OAM layout",
    )
    parser.add_argument("--entry-ids", type=str, help="Comma-separated entry IDs (manual mode)")
    parser.add_argument("--original", type=Path, help="Original ROM path")
    parser.add_argument("--injected", type=Path, help="Injected ROM path")
    parser.add_argument("--skip-verify", action="store_true", help="Skip ROM verification corrections")
    parser.add_argument("--scale", type=int, default=4, help="Display scale for panels")
    parser.add_argument("-o", "--output", type=Path, default=Path("/tmp/frame_injection_verify.png"))

    args = parser.parse_args()

    if not args.project and not args.capture:
        parser.error("Must provide --project or --capture")

    if args.project:
        project = FrameMappingRepository.load(args.project)
        game_frame = None
        if args.mapping_index is not None:
            if args.mapping_index < 0 or args.mapping_index >= len(project.mappings):
                raise ValueError("Mapping index out of range")
            mapping = project.mappings[args.mapping_index]
            game_frame = project.get_game_frame_by_id(mapping.game_frame_id)
        elif args.frame_id:
            game_frame = project.get_game_frame_by_id(args.frame_id)
        else:
            parser.error("When using --project, provide --frame-id or --mapping-index")

        if game_frame is None:
            raise ValueError("Game frame not found in project")
        if game_frame.capture_path is None:
            raise ValueError("Game frame has no capture_path")

        # Normalize Windows-style backslashes if present
        capture_path = Path(str(game_frame.capture_path).replace("\\", "/")) if game_frame.capture_path else None
        compare_capture_path = Path(str(args.compare_capture).replace("\\", "/")) if args.compare_capture else None
        selected_entry_ids = game_frame.selected_entry_ids
        rom_offsets = game_frame.rom_offsets
    else:
        capture_path = Path(str(args.capture).replace("\\", "/")) if args.capture else None
        compare_capture_path = Path(str(args.compare_capture).replace("\\", "/")) if args.compare_capture else None
        selected_entry_ids = parse_entry_ids(args.entry_ids) if args.entry_ids else None
        rom_offsets = None

    if capture_path is None:
        raise ValueError("Capture path is required")

    # Load capture
    parser_obj = MesenCaptureParser()
    capture = parser_obj.parse_file(capture_path)

    relevant_entries = get_relevant_entries(capture, selected_entry_ids, rom_offsets)
    if not relevant_entries:
        raise ValueError("No entries matched selection")

    filtered_capture = CaptureResult(
        frame=capture.frame,
        visible_count=len(relevant_entries),
        obsel=capture.obsel,
        entries=relevant_entries,
        palettes=capture.palettes,
        timestamp=capture.timestamp,
    )

    # Optional ROM verification (mirrors injection)
    verification = None
    if not args.skip_verify:
        rom_for_verify = args.original or args.injected
        if rom_for_verify is not None:
            verifier = ROMVerificationService(rom_for_verify)
            verification = verifier.verify_offsets(
                filtered_capture,
                selected_entry_ids,
                include_missing=True,
            )
            verifier.apply_corrections(relevant_entries, verification.corrections)

    bbox = filtered_capture.bounding_box
    placements = iter_tile_placements(relevant_entries, bbox)
    palette_rgb = get_palette_rgb(filtered_capture)

    if args.original:
        original_rom = args.original.read_bytes()
    else:
        original_rom = None
    if args.injected:
        injected_rom = args.injected.read_bytes()
    else:
        injected_rom = None

    if original_rom is None and injected_rom is None:
        raise ValueError("Provide --original and/or --injected ROM")

    smc_header = detect_smc_header(original_rom or injected_rom or b"")

    panels: list[Image.Image] = []
    if original_rom is not None:
        original_img = render_frame_from_rom(original_rom, placements, palette_rgb, bbox, smc_header)
        panels.append(make_panel(original_img, "Original ROM", scale=args.scale))
    if injected_rom is not None:
        injected_img = render_frame_from_rom(injected_rom, placements, palette_rgb, bbox, smc_header)
        panels.append(make_panel(injected_img, "Injected ROM", scale=args.scale))
        if compare_capture_path:
            compare_capture = parser_obj.parse_file(compare_capture_path)
            compare_entries = get_relevant_entries(compare_capture, selected_entry_ids, rom_offsets)
            if not compare_entries:
                raise ValueError("No entries matched selection for compare capture")
            compare_filtered = CaptureResult(
                frame=compare_capture.frame,
                visible_count=len(compare_entries),
                obsel=compare_capture.obsel,
                entries=compare_entries,
                palettes=compare_capture.palettes,
                timestamp=compare_capture.timestamp,
            )
            compare_bbox = compare_filtered.bounding_box
            compare_placements = iter_tile_placements(compare_entries, compare_bbox)
            compare_palette_rgb = get_palette_rgb(compare_filtered)
            compare_img = render_frame_from_rom(
                injected_rom,
                compare_placements,
                compare_palette_rgb,
                compare_bbox,
                smc_header,
            )
            panels.append(make_panel(compare_img, "Injected ROM (Compare OAM)", scale=args.scale))
    if original_rom is not None and injected_rom is not None:
        changed_mask = render_changed_mask(original_rom, injected_rom, placements, bbox, smc_header)
        panels.append(make_panel(changed_mask, "Changed Tiles", scale=args.scale))

    offset_overlay, offset_colors = render_offset_groups(placements, bbox)
    panels.append(make_panel(offset_overlay, "ROM Offset Groups", scale=args.scale))

    output_img = compose_grid(panels, cols=2)
    output_img.save(args.output, "PNG")

    print(f"Saved: {args.output}")
    print(f"Capture: {capture_path}")
    print(f"Entries: {len(relevant_entries)}")
    print(f"Tiles: {len(placements)}")
    if smc_header:
        print(f"SMC header: {smc_header} bytes")

    if verification is not None:
        print(
            "ROM verification: "
            f"{verification.matched_hal} HAL, {verification.matched_raw} raw, {verification.not_found} not found"
        )
        if verification.has_corrections:
            corrected = [o for o, n in verification.corrections.items() if n is not None and n != o]
            print(f"Corrections applied: {len(corrected)}")

    offset_counts: dict[int, int] = {}
    for placement in placements:
        offset = placement.tile.rom_offset
        if offset is None:
            continue
        offset_counts[offset] = offset_counts.get(offset, 0) + 1

    if offset_counts:
        print("Offsets:")
        for offset in sorted(offset_counts):
            color = offset_colors.get(offset, (0, 0, 0))
            print(f"  0x{offset:X}: {offset_counts[offset]} tiles (color #{color[0]:02X}{color[1]:02X}{color[2]:02X})")


if __name__ == "__main__":
    main()
