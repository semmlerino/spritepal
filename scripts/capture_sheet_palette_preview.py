#!/usr/bin/env python
"""Capture the quantized preview from Sheet Palette Editor.

This script renders the quantized preview as it appears in the Sheet Palette
Editor's Live Preview panel (right side - "Quantized" view).

Usage:
    uv run python scripts/capture_sheet_palette_preview.py [OPTIONS]

Examples:
    # Default: use mapping.spritepal-mapping.json, first mapping
    uv run python scripts/capture_sheet_palette_preview.py

    # Specify output and display scale
    uv run python scripts/capture_sheet_palette_preview.py -o preview.png --display-scale 4
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path, PureWindowsPath

import numpy as np
from PIL import Image

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.palette_utils import quantize_with_mappings, snap_to_snes_color


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Capture quantized preview from Sheet Palette Editor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "-p", "--project",
        type=Path,
        default=Path("mapping.spritepal-mapping.json"),
        help="Path to .spritepal-mapping.json project file",
    )
    parser.add_argument(
        "-m", "--mapping-index",
        type=int,
        default=0,
        help="Index of mapping to use for AI frame (default: 0)",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=Path("/tmp/sheet_palette_quantized.png"),
        help="Output path for preview image",
    )
    parser.add_argument(
        "--display-scale",
        type=int,
        default=4,
        help="Display magnification (default: 4)",
    )

    args = parser.parse_args()

    # Load project
    if not args.project.exists():
        print(f"Error: Project file not found: {args.project}")
        sys.exit(1)

    with open(args.project) as f:
        project = json.load(f)

    # Get AI frame from mapping
    if args.mapping_index >= len(project.get("mappings", [])):
        print(f"Error: Mapping index {args.mapping_index} out of range")
        sys.exit(1)

    mapping = project["mappings"][args.mapping_index]
    ai_frame_id = mapping["ai_frame_id"]

    # Find AI frame path
    ai_frame = next(
        (f for f in project["ai_frames"] if PureWindowsPath(f["path"]).name == ai_frame_id),
        None,
    )
    if ai_frame is None:
        print(f"Error: AI frame not found: {ai_frame_id}")
        sys.exit(1)

    ai_frame_path = Path(PureWindowsPath(ai_frame["path"]).as_posix())
    if not ai_frame_path.exists():
        print(f"Error: AI frame file not found: {ai_frame_path}")
        sys.exit(1)

    # Load sample image
    sample_image = Image.open(ai_frame_path).convert("RGBA")
    print(f"AI frame: {ai_frame_path.name} ({sample_image.width}x{sample_image.height})")

    # Get sheet palette
    sp = project.get("sheet_palette")
    if not sp or not sp.get("colors"):
        print("Error: No sheet_palette in project")
        sys.exit(1)

    palette_colors = [tuple(c) for c in sp["colors"]]
    color_mappings = {
        tuple(eval(k) if isinstance(k, str) else k): v
        for k, v in sp.get("color_mappings", {}).items()
    }
    background_color = tuple(sp["background_color"]) if sp.get("background_color") else None
    background_tolerance = sp.get("background_tolerance", 30)
    alpha_threshold = sp.get("alpha_threshold", 128)
    dither_mode = sp.get("dither_mode", "none")
    dither_strength = float(sp.get("dither_strength", 0.0))

    print(f"Palette: {len(palette_colors)} colors, {len(color_mappings)} mappings")

    # Apply background removal if configured
    image_to_quantize = sample_image
    if background_color is not None:
        from core.services.content_bounds_analyzer import remove_background
        image_to_quantize = remove_background(
            sample_image,
            background_color,
            background_tolerance,
        )
        print(f"Background removed: {background_color} (tolerance {background_tolerance})")

    # Snap palette to SNES precision
    palette_rgb = [snap_to_snes_color(c) for c in palette_colors]

    # Quantize with mappings (matches Sheet Palette Editor preview)
    quantized_indexed = quantize_with_mappings(
        image_to_quantize,
        palette_rgb,
        color_mappings,
        transparency_threshold=alpha_threshold,
        dither_mode=dither_mode,
        dither_strength=dither_strength,
    )

    # Convert to RGBA with binary alpha (matches SNES hardware)
    quantized_rgba = quantized_indexed.convert("RGBA")
    idx_array = np.array(quantized_indexed)
    binary_alpha = np.where(idx_array == 0, 0, 255).astype(np.uint8)
    quantized_rgba.putalpha(Image.fromarray(binary_alpha, mode="L"))

    # Scale for display
    if args.display_scale != 1:
        scaled = quantized_rgba.resize(
            (quantized_rgba.width * args.display_scale, quantized_rgba.height * args.display_scale),
            Image.Resampling.NEAREST,
        )
    else:
        scaled = quantized_rgba

    scaled.save(args.output)
    print(f"Saved: {args.output} ({scaled.width}x{scaled.height})")


if __name__ == "__main__":
    main()
