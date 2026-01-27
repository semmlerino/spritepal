"""Render quantized preview to verify symmetry preservation.

Shows the result of quantizing an AI frame to a SNES palette, which is what
appears in the app's Preview pane. Use this to verify that symmetric features
(like eyes) are preserved after quantization.

Usage:
    # From project file:
    uv run python scripts/render_quantized_preview.py \
        --project mapping.spritepal-mapping.json --mapping-index 0

    # Manual specification:
    uv run python scripts/render_quantized_preview.py \
        --ai-frame path/to/frame.png \
        --capture mesen2_exchange/capture.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.mesen_integration.capture_renderer import CaptureRenderer
from core.mesen_integration.click_extractor import MesenCaptureParser
from core.palette_utils import quantize_to_palette
from core.services.sprite_compositor import SpriteCompositor, TransformParams


def load_project(project_path: Path) -> dict:
    """Load a .spritepal-mapping.json project file."""
    with open(project_path, encoding="utf-8") as f:
        return json.load(f)


def get_mapping_from_project(project: dict, mapping_index: int, project_dir: Path) -> dict:
    """Extract mapping details from project by index."""
    mappings = project.get("mappings", [])
    if mapping_index >= len(mappings):
        raise ValueError(f"Mapping index {mapping_index} out of range")

    mapping = mappings[mapping_index]
    ai_frame_id = mapping.get("ai_frame_id")
    game_frame_id = mapping.get("game_frame_id")

    # Find AI frame
    ai_frames = project.get("ai_frames", [])
    ai_frame = next(
        (f for f in ai_frames if Path(f.get("path", "").replace("\\", "/")).name == ai_frame_id),
        None,
    )
    if ai_frame is None:
        raise ValueError(f"AI frame '{ai_frame_id}' not found")

    # Find game frame
    game_frames = project.get("game_frames", [])
    game_frame = next((f for f in game_frames if f.get("id") == game_frame_id), None)
    if game_frame is None:
        raise ValueError(f"Game frame '{game_frame_id}' not found")

    # Resolve paths
    ai_frame_path = Path(ai_frame.get("path", "").replace("\\", "/"))
    capture_path = Path(game_frame.get("capture_path", "").replace("\\", "/"))

    if not ai_frame_path.is_absolute():
        ai_frame_path = project_dir / ai_frame_path
    if not capture_path.is_absolute():
        capture_path = project_dir / capture_path

    return {
        "capture_path": capture_path,
        "ai_frame_path": ai_frame_path,
        "selected_entry_ids": game_frame.get("selected_entry_ids", []),
        "offset_x": mapping.get("offset_x", 0),
        "offset_y": mapping.get("offset_y", 0),
        "flip_h": mapping.get("flip_h", False),
        "flip_v": mapping.get("flip_v", False),
        "scale": mapping.get("scale", 1.0),
    }


def render_quantized_preview(
    ai_image: Image.Image,
    palette: list[tuple[int, int, int]],
    scale: float = 1.0,
    flip_h: bool = False,
    flip_v: bool = False,
) -> Image.Image:
    """Render the quantized AI frame using the compositor.

    This replicates what the Preview pane shows in the app.
    """
    # Apply transforms
    transformed = ai_image.copy()
    if flip_h:
        transformed = transformed.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if flip_v:
        transformed = transformed.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

    if scale != 1.0:
        new_w = int(transformed.width * scale)
        new_h = int(transformed.height * scale)
        transformed = transformed.resize((new_w, new_h), Image.Resampling.NEAREST)

    # Quantize to palette (function takes PIL Image, returns PIL Image in mode "P")
    indexed_img = quantize_to_palette(transformed, palette)
    # Convert back to RGBA for display (preserves transparency)
    return indexed_img.convert("RGBA")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render quantized preview to verify symmetry preservation",
    )

    parser.add_argument(
        "--project",
        "-p",
        type=Path,
        help="Path to .spritepal-mapping.json project file",
    )
    parser.add_argument(
        "--mapping-index",
        "-m",
        type=int,
        default=0,
        help="Index of mapping in project (default: 0)",
    )
    parser.add_argument("--ai-frame", "-a", type=Path, help="Path to AI frame image")
    parser.add_argument("--capture", "-c", type=Path, help="Path to Mesen capture JSON")
    parser.add_argument("--scale", type=float, default=1.0, help="Scale factor")
    parser.add_argument("--flip-h", action="store_true", help="Flip horizontally")
    parser.add_argument("--flip-v", action="store_true", help="Flip vertically")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("quantized_preview.png"),
        help="Output path",
    )
    parser.add_argument(
        "--display-scale",
        type=int,
        default=4,
        help="Display magnification (default: 4)",
    )
    parser.add_argument(
        "--side-by-side",
        action="store_true",
        help="Show original and quantized side by side",
    )

    args = parser.parse_args()

    # Load from project or manual
    if args.project:
        project = load_project(args.project)
        project_dir = args.project.parent
        mapping_info = get_mapping_from_project(project, args.mapping_index, project_dir)

        ai_frame_path = mapping_info["ai_frame_path"]
        capture_path = mapping_info["capture_path"]
        selected_entry_ids = mapping_info["selected_entry_ids"]
        scale = mapping_info["scale"]
        flip_h = mapping_info["flip_h"]
        flip_v = mapping_info["flip_v"]

        print(f"Project: {args.project}")
        print(f"Mapping index: {args.mapping_index}")
    else:
        if not args.ai_frame:
            parser.error("Either --project or --ai-frame required")
        ai_frame_path = args.ai_frame
        capture_path = args.capture
        selected_entry_ids = None
        scale = args.scale
        flip_h = args.flip_h
        flip_v = args.flip_v

    # Load AI frame
    print(f"Loading AI frame: {ai_frame_path}")
    ai_image = Image.open(ai_frame_path).convert("RGBA")
    print(f"  Size: {ai_image.size}")

    # Get palette from capture or use default
    if capture_path and capture_path.exists():
        print(f"Loading capture: {capture_path}")
        parser_obj = MesenCaptureParser()
        capture = parser_obj.parse_file(capture_path)

        if selected_entry_ids:
            entries = [e for e in capture.entries if e.id in selected_entry_ids]
        else:
            entries = capture.entries

        # Get palette from first entry
        if entries and capture.palettes:
            palette_idx = entries[0].palette
            palette = capture.palettes[palette_idx]
            print(f"  Using palette {palette_idx}: {len(palette)} colors")
        else:
            # Default SNES grayscale palette
            palette = [(i * 17, i * 17, i * 17) for i in range(16)]
            print("  Using default grayscale palette")
    else:
        # Default SNES grayscale palette
        palette = [(i * 17, i * 17, i * 17) for i in range(16)]
        print("Using default grayscale palette")

    # Render quantized preview
    print(f"Quantizing with scale={scale:.2f}, flip_h={flip_h}, flip_v={flip_v}...")
    quantized = render_quantized_preview(ai_image, palette, scale=scale, flip_h=flip_h, flip_v=flip_v)

    # Scale up for display
    display_scale = args.display_scale
    if args.side_by_side:
        # Apply flip transforms to original (but NOT scale - we want full detail)
        original = ai_image.copy()
        if flip_h:
            original = original.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        if flip_v:
            original = original.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

        # Scale quantized up for display (NEAREST to show blocky pixels)
        quant_scaled = quantized.resize(
            (quantized.width * display_scale, quantized.height * display_scale),
            Image.Resampling.NEAREST,
        )

        # Scale original to match quantized display size (LANCZOS to preserve detail)
        orig_scaled = original.resize(
            (quant_scaled.width, quant_scaled.height),
            Image.Resampling.LANCZOS,
        )

        # Create side-by-side canvas
        gap = 20
        canvas = Image.new(
            "RGBA",
            (orig_scaled.width + gap + quant_scaled.width, max(orig_scaled.height, quant_scaled.height)),
            (48, 48, 48, 255),
        )
        canvas.paste(orig_scaled, (0, 0), orig_scaled)
        canvas.paste(quant_scaled, (orig_scaled.width + gap, 0), quant_scaled)
        result = canvas
        print("Created side-by-side comparison (original full-detail | quantized SNES)")
    else:
        result = quantized.resize(
            (quantized.width * display_scale, quantized.height * display_scale),
            Image.Resampling.NEAREST,
        )

    result.save(args.output)
    print(f"Saved to: {args.output}")
    print(f"\nTo view: open {args.output}")


if __name__ == "__main__":
    main()
