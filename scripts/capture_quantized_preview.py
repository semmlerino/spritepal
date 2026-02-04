#!/usr/bin/env python
"""Capture quantized preview screenshot from a mapping project.

This script renders the quantized preview of an AI frame as it would appear
after palette quantization, using the sheet_palette from the project file.

Usage:
    uv run python scripts/capture_quantized_preview.py [OPTIONS]

Examples:
    # Default: use mapping.spritepal-mapping.json, first mapping, save to /tmp/quantized_preview.png
    uv run python scripts/capture_quantized_preview.py

    # Specify project and output
    uv run python scripts/capture_quantized_preview.py -p my_project.spritepal-mapping.json -o preview.png

    # Different mapping index
    uv run python scripts/capture_quantized_preview.py -m 2
"""

from __future__ import annotations

import argparse
import ast
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
        description="Capture quantized preview from a mapping project",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "-p", "--project",
        type=Path,
        default=Path("mapping.spritepal-mapping.json"),
        help="Path to .spritepal-mapping.json project file (default: mapping.spritepal-mapping.json)",
    )
    parser.add_argument(
        "-m", "--mapping-index",
        type=int,
        default=0,
        help="Index of mapping in project (default: 0)",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=Path("/tmp/quantized_preview.png"),
        help="Output path for screenshot (default: /tmp/quantized_preview.png)",
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

    # Get mapping
    if args.mapping_index >= len(project.get("mappings", [])):
        print(f"Error: Mapping index {args.mapping_index} out of range")
        sys.exit(1)

    mapping = project["mappings"][args.mapping_index]
    ai_frame_id = mapping["ai_frame_id"]

    # Find AI frame - use PureWindowsPath for cross-platform path handling
    ai_frame = next(
        (f for f in project["ai_frames"] if PureWindowsPath(f["path"]).name == ai_frame_id),
        None,
    )
    if ai_frame is None:
        print(f"Error: AI frame not found: {ai_frame_id}")
        sys.exit(1)

    # Use the path directly (convert Windows path to posix)
    ai_frame_path = Path(PureWindowsPath(ai_frame["path"]).as_posix())
    if not ai_frame_path.exists():
        print(f"Error: AI frame file not found: {ai_frame_path}")
        sys.exit(1)

    # Get sheet palette with all settings
    sp = project.get("sheet_palette")
    if not sp or not sp.get("colors"):
        print("Error: No sheet_palette in project")
        sys.exit(1)

    palette_colors = [tuple(c) for c in sp["colors"]]
    color_mappings = {
        tuple(ast.literal_eval(k) if isinstance(k, str) else k): v
        for k, v in sp.get("color_mappings", {}).items()
    }
    background_color = tuple(sp["background_color"]) if sp.get("background_color") else None
    background_tolerance = sp.get("background_tolerance", 30)
    alpha_threshold = sp.get("alpha_threshold", 128)
    dither_mode = sp.get("dither_mode", "none")
    dither_strength = float(sp.get("dither_strength", 0.0))

    print(f"Using sheet_palette: {len(palette_colors)} colors, {len(color_mappings)} mappings")

    # Load AI frame
    ai_image = Image.open(ai_frame_path).convert("RGBA")
    print(f"AI frame: {ai_frame_path.name} ({ai_image.size[0]}x{ai_image.size[1]})")

    # Get transform params
    scale = mapping.get("scale", 1.0)
    flip_h = mapping.get("flip_h", False)
    flip_v = mapping.get("flip_v", False)
    resampling = mapping.get("resampling", "lanczos")
    print(f"Transform: scale={scale:.3f}, flip_h={flip_h}, flip_v={flip_v}")

    # Apply flips (no interpolation, preserves exact colors)
    transformed = ai_image.copy()
    if flip_h:
        transformed = transformed.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if flip_v:
        transformed = transformed.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

    # Apply background removal if configured (before quantization)
    image_to_quantize = transformed
    if background_color is not None:
        from core.services.content_bounds_analyzer import remove_background
        image_to_quantize = remove_background(
            transformed,
            background_color,
            background_tolerance,
        )
        print(f"Background removed: {background_color} (tolerance {background_tolerance})")

    # Snap palette to SNES precision (matches injection pipeline)
    palette_rgb = [snap_to_snes_color(c) for c in palette_colors]

    # Quantize at FULL RESOLUTION first (respects explicit color mappings)
    # This matches the Sheet Palette Editor's Live Preview
    quantized_indexed = quantize_with_mappings(
        image_to_quantize,
        palette_rgb,
        color_mappings,
        transparency_threshold=alpha_threshold,
        dither_mode=dither_mode,
        dither_strength=dither_strength,
    )

    # Convert to RGBA with binary alpha (matches SNES hardware)
    quantized = quantized_indexed.convert("RGBA")
    idx_array = np.array(quantized_indexed)
    binary_alpha = np.where(idx_array == 0, 0, 255).astype(np.uint8)
    quantized.putalpha(Image.fromarray(binary_alpha, mode="L"))

    # NOW apply scale to the quantized result (NEAREST preserves palette indices)
    if scale != 1.0:
        new_w = int(quantized.width * scale)
        new_h = int(quantized.height * scale)
        quantized = quantized.resize((new_w, new_h), Image.Resampling.NEAREST)
        print(f"Scaled to: {quantized.size}")

    # Scale up for display
    display_scale = args.display_scale
    quant_scaled = quantized.resize(
        (quantized.width * display_scale, quantized.height * display_scale),
        Image.Resampling.NEAREST,
    )
    quant_scaled.save(args.output)
    print(f"Saved to: {args.output} ({quant_scaled.size[0]}x{quant_scaled.size[1]})")


if __name__ == "__main__":
    main()
