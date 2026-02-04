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
import json
import sys
from pathlib import Path, PureWindowsPath

from PIL import Image


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

    # Get palette from sheet_palette (user's edited palette)
    if project.get("sheet_palette") and project["sheet_palette"].get("colors"):
        palette = [tuple(c) for c in project["sheet_palette"]["colors"]]
        print(f"Using sheet_palette: {len(palette)} colors")
    else:
        # Fallback: load from capture
        game_frame = next(
            (f for f in project["game_frames"] if f.get("id") == mapping["game_frame_id"]),
            None,
        )
        if game_frame is None:
            print("Error: No sheet_palette and game frame not found")
            sys.exit(1)

        capture_path = Path(PureWindowsPath(game_frame["capture_path"]).as_posix())
        palette_idx = game_frame.get("palette_index", 0)

        from core.mesen_integration.click_extractor import MesenCaptureParser

        parser_obj = MesenCaptureParser()
        capture = parser_obj.parse_file(capture_path)
        palette = [tuple(c) if isinstance(c, list) else c for c in capture.palettes[palette_idx]]
        print(f"Using capture palette {palette_idx}: {len(palette)} colors")

    # Load AI frame
    ai_image = Image.open(ai_frame_path).convert("RGBA")
    print(f"AI frame: {ai_frame_path.name} ({ai_image.size[0]}x{ai_image.size[1]})")

    # Get transform params
    scale = mapping.get("scale", 1.0)
    flip_h = mapping.get("flip_h", False)
    flip_v = mapping.get("flip_v", False)
    resampling = mapping.get("resampling", "lanczos")
    print(f"Transform: scale={scale:.3f}, flip_h={flip_h}, flip_v={flip_v}")

    # Apply transforms
    transformed = ai_image.copy()
    if flip_h:
        transformed = transformed.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if flip_v:
        transformed = transformed.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

    resample_mode = Image.Resampling.LANCZOS if resampling == "lanczos" else Image.Resampling.NEAREST
    if scale != 1.0:
        new_w = int(transformed.width * scale)
        new_h = int(transformed.height * scale)
        transformed = transformed.resize((new_w, new_h), resample_mode)

    print(f"Transformed size: {transformed.size}")

    # Quantize
    from core.palette_utils import quantize_to_palette

    indexed_img = quantize_to_palette(transformed, palette)
    quantized = indexed_img.convert("RGBA")

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
