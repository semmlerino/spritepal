"""Headless rendering of WorkbenchCanvas alignment view.

Replicates the visual output of WorkbenchCanvas without Qt display.
Use this to verify alignment calculations match the actual app.

Usage:
    # From project file (recommended):
    uv run python scripts/render_workbench.py --project mapping.spritepal-mapping.json --mapping-index 0

    # Manual specification:
    uv run python scripts/render_workbench.py \
        --capture mesen2_exchange/capture.json \
        --ai-frame path/to/frame.png \
        --entry-ids "6,7,8,9,10,11,12,13" \
        --auto-align --match-scale
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.mesen_integration.capture_renderer import CaptureRenderer
from core.mesen_integration.click_extractor import CaptureResult, MesenCaptureParser
from core.services.content_bounds_analyzer import ContentBoundsAnalyzer
from core.services.tile_sampling_service import TileSamplingService


def load_capture(capture_path: Path, selected_entry_ids: list[int] | None = None) -> CaptureResult:
    """Load a Mesen capture from JSON, optionally filtering entries."""
    parser = MesenCaptureParser()
    capture = parser.parse_file(capture_path)

    if selected_entry_ids is not None:
        # Filter to only selected entries
        filtered_entries = [e for e in capture.entries if e.id in selected_entry_ids]
        # Create new CaptureResult with filtered entries
        capture = CaptureResult(
            frame=capture.frame,
            visible_count=len(filtered_entries),
            obsel=capture.obsel,
            entries=filtered_entries,
            palettes=capture.palettes,
            timestamp=capture.timestamp,
        )

    return capture


def load_project(project_path: Path) -> dict[str, Any]:
    """Load a .spritepal-mapping.json project file."""
    with open(project_path, encoding="utf-8") as f:
        return json.load(f)


def get_mapping_from_project(project: dict[str, Any], mapping_index: int, project_dir: Path) -> dict[str, Any]:
    """Extract mapping details from project by index.

    Returns dict with:
        - capture_path: Path to capture JSON
        - ai_frame_path: Path to AI frame image
        - selected_entry_ids: List of entry IDs
        - offset_x, offset_y: Alignment offsets
        - flip_h, flip_v: Flip states
        - scale: Scale factor
    """
    mappings = project.get("mappings", [])
    if mapping_index >= len(mappings):
        raise ValueError(f"Mapping index {mapping_index} out of range (0-{len(mappings) - 1})")

    mapping = mappings[mapping_index]
    ai_frame_id = mapping.get("ai_frame_id")  # This is a filename like "sprite_00_edited.png"
    game_frame_id = mapping.get("game_frame_id")

    # Find AI frame by matching filename in path
    # Normalize Windows backslashes before extracting filename
    ai_frames = project.get("ai_frames", [])
    ai_frame = next(
        (f for f in ai_frames if Path(f.get("path", "").replace("\\", "/")).name == ai_frame_id),
        None,
    )
    if ai_frame is None:
        raise ValueError(f"AI frame '{ai_frame_id}' not found in project")

    # Find game frame
    game_frames = project.get("game_frames", [])
    game_frame = next((f for f in game_frames if f.get("id") == game_frame_id), None)
    if game_frame is None:
        raise ValueError(f"Game frame with id {game_frame_id} not found")

    # Resolve paths (may be relative or absolute, may use Windows backslashes)
    ai_frame_path_str = ai_frame.get("path", "")
    capture_path_str = game_frame.get("capture_path", "")

    # Normalize Windows paths
    ai_frame_path = Path(ai_frame_path_str.replace("\\", "/"))
    capture_path = Path(capture_path_str.replace("\\", "/"))

    # Make relative if not absolute
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
        "game_frame_name": game_frame.get("display_name", game_frame_id),
        "ai_frame_name": Path(ai_frame_path_str).name,
    }


def compute_tile_rects(capture_result: CaptureResult) -> list[tuple[int, int, int, int]]:
    """Compute 8x8 tile rectangles from OAM entries in scene coordinates.

    These are the actual tile regions that will receive injected pixel data.

    Returns:
        List of (x, y, width, height) tuples in scene coordinates (relative to bbox origin).
    """
    tile_rects: list[tuple[int, int, int, int]] = []
    bbox = capture_result.bounding_box

    for entry in capture_result.entries:
        # Calculate relative position within the sprite bounds
        rel_x = entry.x - bbox.x
        rel_y = entry.y - bbox.y

        # Break into 8x8 tiles
        for ty in range(0, entry.height, 8):
            for tx in range(0, entry.width, 8):
                tile_rects.append((rel_x + tx, rel_y + ty, 8, 8))

    return tile_rects


def check_out_of_bounds(
    ai_image: Image.Image,
    tile_rects: list[tuple[int, int, int, int]],
    offset_x: int,
    offset_y: int,
    scale: float,
) -> tuple[bool, list[tuple[int, int, int, int]]]:
    """Check if AI frame content extends outside tile regions.

    Args:
        ai_image: AI frame image
        tile_rects: List of (x, y, w, h) tile rectangles in scene coordinates
        offset_x: AI frame X offset
        offset_y: AI frame Y offset
        scale: AI frame scale factor

    Returns:
        Tuple of (has_overflow, overflow_rects) where overflow_rects are
        (x, y, w, h) in scene coordinates.
    """
    service = TileSamplingService()
    content_bbox = ai_image.getbbox()  # Non-transparent content bounds

    return service.check_content_outside_tiles(
        content_bbox,
        tile_rects,
        offset_x,
        offset_y,
        scale,
    )


def draw_overflow_regions(
    draw: ImageDraw.ImageDraw,
    overflow_rects: list[tuple[int, int, int, int]],
    min_x: int,
    min_y: int,
    display_scale: int,
) -> None:
    """Draw overflow regions with red striped pattern.

    Args:
        draw: PIL ImageDraw object
        overflow_rects: List of (x, y, w, h) rectangles in scene coordinates
        min_x: Canvas origin X offset
        min_y: Canvas origin Y offset
        display_scale: Display magnification factor
    """
    for x, y, w, h in overflow_rects:
        # Convert to canvas coordinates
        x1 = (x - min_x) * display_scale
        y1 = (y - min_y) * display_scale
        x2 = x1 + w * display_scale
        y2 = y1 + h * display_scale

        # Draw red border
        draw.rectangle([x1, y1, x2, y2], outline=(255, 0, 0, 200), width=2)

        # Draw diagonal stripes (hatching pattern)
        stripe_spacing = 8
        for offset in range(-max(w, h) * display_scale, max(w, h) * display_scale, stripe_spacing):
            # Diagonal lines from top-left to bottom-right
            line_x1 = x1 + offset
            line_y1 = y1
            line_x2 = x1 + offset + h * display_scale
            line_y2 = y2

            # Clip to rectangle bounds
            if line_x1 < x1:
                line_y1 += x1 - line_x1
                line_x1 = x1
            if line_x2 > x2:
                line_y2 -= line_x2 - x2
                line_x2 = x2
            if line_y1 < y1 or line_y2 > y2 or line_x1 > x2 or line_x2 < x1:
                continue

            draw.line([(line_x1, line_y1), (line_x2, line_y2)], fill=(255, 0, 0, 150), width=1)


def compute_auto_align(
    ai_image: Image.Image,
    capture_result: CaptureResult,
    game_image: Image.Image,
    match_scale: bool = False,
    flip_h: bool = False,
    flip_v: bool = False,
) -> tuple[int, int, float]:
    """Compute auto-alignment offset and scale.

    Replicates WorkbenchCanvas._on_auto_align() logic.

    Returns:
        Tuple of (offset_x, offset_y, scale)
    """
    # Get AI content bounding box (non-transparent pixels)
    ai_bbox = ai_image.getbbox()
    if ai_bbox is None:
        ai_bbox = (0, 0, ai_image.width, ai_image.height)

    ai_x, ai_y, ai_x2, ai_y2 = ai_bbox
    ai_content_width = ai_x2 - ai_x
    ai_content_height = ai_y2 - ai_y

    # Game frame bounding box
    bbox = capture_result.bounding_box

    # Calculate scale if Match Scale is enabled
    if match_scale and ai_content_width > 0 and ai_content_height > 0:
        scale_x = bbox.width / ai_content_width
        scale_y = bbox.height / ai_content_height
        scale = min(scale_x, scale_y)
        scale = max(0.1, min(1.0, scale))
    else:
        scale = 1.0

    # Calculate AI content center in original image coordinates
    ai_center_x = ai_x + ai_content_width / 2
    ai_center_y = ai_y + ai_content_height / 2

    if flip_h:
        ai_center_x = ai_image.width - ai_center_x
    if flip_v:
        ai_center_y = ai_image.height - ai_center_y

    # Apply scale to get visual content center
    scaled_ai_center_x = ai_center_x * scale
    scaled_ai_center_y = ai_center_y * scale

    # Game frame center of mass (weighted by opaque pixels)
    game_center_x, game_center_y = ContentBoundsAnalyzer.compute_centroid(game_image)

    # Calculate offset to align centers
    offset_x = int(game_center_x - scaled_ai_center_x)
    offset_y = int(game_center_y - scaled_ai_center_y)

    return offset_x, offset_y, scale


def draw_tile_overlay(
    draw: ImageDraw.ImageDraw,
    capture_result: CaptureResult,
    game_pos_x: int,
    game_pos_y: int,
    display_scale: int,
) -> None:
    """Draw OAM tile boundaries like the app's tile overlay.

    Args:
        draw: PIL ImageDraw object
        capture_result: Capture with OAM entries
        game_pos_x: X position of game frame on canvas
        game_pos_y: Y position of game frame on canvas
        display_scale: Display magnification factor
    """
    bbox = capture_result.bounding_box
    tile_size = 8 * display_scale

    # Colors matching the app
    border_color = (150, 150, 150, 200)

    for entry in capture_result.entries:
        # Calculate relative position within the sprite bounds
        rel_x = (entry.x - bbox.x) * display_scale
        rel_y = (entry.y - bbox.y) * display_scale
        width = entry.width * display_scale
        height = entry.height * display_scale

        # Break into 8x8 tiles
        for ty in range(0, height, tile_size):
            for tx in range(0, width, tile_size):
                x1 = game_pos_x + rel_x + tx
                y1 = game_pos_y + rel_y + ty
                x2 = x1 + tile_size
                y2 = y1 + tile_size
                draw.rectangle([x1, y1, x2, y2], outline=border_color, width=1)


def render_workbench(
    capture_result: CaptureResult,
    ai_image: Image.Image,
    offset_x: int = 0,
    offset_y: int = 0,
    scale: float = 1.0,
    flip_h: bool = False,
    flip_v: bool = False,
    display_scale: int = 4,
    show_markers: bool = True,
    show_tile_overlay: bool = False,
    show_overflow: bool = False,
    opacity: float = 0.7,
) -> tuple[Image.Image, bool, list[tuple[int, int, int, int]]]:
    """Render workbench canvas view as an image.

    Args:
        capture_result: Parsed Mesen capture
        ai_image: AI frame PIL image
        offset_x: X offset for AI frame
        offset_y: Y offset for AI frame
        scale: Scale factor for AI frame
        flip_h: Horizontal flip
        flip_v: Vertical flip
        display_scale: Multiplier for display (default 4x like app)
        show_markers: Whether to draw center markers
        show_tile_overlay: Whether to draw OAM tile boundaries
        show_overflow: Whether to draw out-of-bounds regions
        opacity: AI frame opacity (0.0-1.0)

    Returns:
        Tuple of (rendered_image, has_overflow, overflow_rects)
    """
    # Render game frame
    renderer = CaptureRenderer(capture_result)
    game_image = renderer.render_selection()

    # Get dimensions
    game_w, game_h = game_image.size
    ai_w, ai_h = ai_image.size

    # Apply transforms to AI image
    transformed_ai = ai_image.copy()
    if flip_h:
        transformed_ai = transformed_ai.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if flip_v:
        transformed_ai = transformed_ai.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

    # Scale AI image
    scaled_ai_w = int(ai_w * scale)
    scaled_ai_h = int(ai_h * scale)
    if scale != 1.0:
        transformed_ai = transformed_ai.resize((scaled_ai_w, scaled_ai_h), Image.Resampling.NEAREST)

    # Calculate canvas size (need to fit both game frame and positioned AI frame)
    # Game frame is at origin (0, 0)
    # AI frame is at (offset_x, offset_y)
    min_x = min(0, offset_x)
    min_y = min(0, offset_y)
    max_x = max(game_w, offset_x + scaled_ai_w)
    max_y = max(game_h, offset_y + scaled_ai_h)

    canvas_w = max_x - min_x
    canvas_h = max_y - min_y

    # Create canvas at display scale
    canvas = Image.new(
        "RGBA",
        (canvas_w * display_scale, canvas_h * display_scale),
        (48, 48, 48, 255),  # Dark gray background like app
    )

    # Scale images for display
    game_scaled = game_image.resize((game_w * display_scale, game_h * display_scale), Image.Resampling.NEAREST)
    ai_scaled = transformed_ai.resize(
        (scaled_ai_w * display_scale, scaled_ai_h * display_scale),
        Image.Resampling.NEAREST,
    )

    # Apply opacity to AI frame
    if opacity < 1.0:
        ai_alpha = ai_scaled.getchannel("A")
        ai_alpha = Image.eval(ai_alpha, lambda a: int(a * opacity))
        ai_scaled.putalpha(ai_alpha)

    # Position game frame (offset from min_x, min_y)
    game_pos_x = (0 - min_x) * display_scale
    game_pos_y = (0 - min_y) * display_scale

    # Position AI frame
    ai_pos_x = (offset_x - min_x) * display_scale
    ai_pos_y = (offset_y - min_y) * display_scale

    # Paste game frame first
    canvas.paste(game_scaled, (game_pos_x, game_pos_y), game_scaled)

    # Paste AI frame on top
    canvas.paste(ai_scaled, (ai_pos_x, ai_pos_y), ai_scaled)

    # Create draw object for overlays
    draw = ImageDraw.Draw(canvas)

    # Draw tile overlay if requested
    if show_tile_overlay:
        draw_tile_overlay(draw, capture_result, game_pos_x, game_pos_y, display_scale)

    # Draw markers if requested
    if show_markers:
        # Game centroid (green)
        game_centroid_x, game_centroid_y = ContentBoundsAnalyzer.compute_centroid(game_image)
        cx = game_pos_x + int(game_centroid_x * display_scale)
        cy = game_pos_y + int(game_centroid_y * display_scale)
        marker_size = 6
        draw.ellipse(
            [cx - marker_size, cy - marker_size, cx + marker_size, cy + marker_size],
            outline=(0, 255, 0),
            width=2,
        )

        # AI content center (after transforms) - yellow
        ai_bbox = ai_image.getbbox()
        if ai_bbox:
            ai_x, ai_y, ai_x2, ai_y2 = ai_bbox
            ai_center_x = ai_x + (ai_x2 - ai_x) / 2
            ai_center_y = ai_y + (ai_y2 - ai_y) / 2
            if flip_h:
                ai_center_x = ai_image.width - ai_center_x
            if flip_v:
                ai_center_y = ai_image.height - ai_center_y
            # Scale and position
            ax = ai_pos_x + int(ai_center_x * scale * display_scale)
            ay = ai_pos_y + int(ai_center_y * scale * display_scale)
            draw.ellipse(
                [ax - marker_size, ay - marker_size, ax + marker_size, ay + marker_size],
                outline=(255, 255, 0),
                width=2,
            )

    # Check for out-of-bounds content
    tile_rects = compute_tile_rects(capture_result)
    has_overflow, overflow_rects = check_out_of_bounds(
        ai_image if not (flip_h or flip_v) else transformed_ai,
        tile_rects,
        offset_x,
        offset_y,
        scale,
    )

    # Draw overflow regions if requested
    if show_overflow and has_overflow:
        draw_overflow_regions(draw, overflow_rects, min_x, min_y, display_scale)

    return canvas, has_overflow, overflow_rects


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Headless rendering of WorkbenchCanvas alignment view",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Load from project file:
  %(prog)s --project mapping.spritepal-mapping.json --mapping-index 0

  # Manual with auto-align:
  %(prog)s -c capture.json -a frame.png --entry-ids "6,7,8,9" --auto-align --match-scale

  # Use saved alignment from project:
  %(prog)s --project mapping.spritepal-mapping.json -m 0 --use-saved
""",
    )

    # Project-based loading
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
    parser.add_argument(
        "--use-saved",
        action="store_true",
        help="Use saved alignment from project instead of auto-align",
    )
    parser.add_argument(
        "--list-mappings",
        action="store_true",
        help="List all mappings in project and exit",
    )

    # Manual specification
    parser.add_argument("--capture", "-c", type=Path, help="Path to Mesen capture JSON")
    parser.add_argument("--ai-frame", "-a", type=Path, help="Path to AI frame image")
    parser.add_argument(
        "--entry-ids",
        type=str,
        help="Comma-separated entry IDs (e.g., '6,7,8,9,10,11,12,13')",
    )

    # Alignment options
    parser.add_argument("--auto-align", action="store_true", help="Apply auto-alignment")
    parser.add_argument("--match-scale", action="store_true", help="Scale AI to match game frame")
    parser.add_argument("--flip-h", action="store_true", help="Flip horizontally")
    parser.add_argument("--flip-v", action="store_true", help="Flip vertically")
    parser.add_argument("--offset-x", type=int, default=0, help="Manual X offset")
    parser.add_argument("--offset-y", type=int, default=0, help="Manual Y offset")
    parser.add_argument("--scale", type=float, default=1.0, help="Manual scale")

    # Display options
    parser.add_argument("--output", "-o", type=Path, default=Path("workbench_render.png"), help="Output path")
    parser.add_argument("--display-scale", type=int, default=4, help="Display magnification (default: 4)")
    parser.add_argument("--opacity", type=float, default=0.7, help="AI opacity (default: 0.7)")
    parser.add_argument("--no-markers", action="store_true", help="Hide center markers")
    parser.add_argument("--tile-overlay", action="store_true", help="Show OAM tile boundaries")
    parser.add_argument("--show-overflow", action="store_true", help="Show out-of-bounds regions")

    args = parser.parse_args()

    # Handle project-based loading
    if args.project:
        project = load_project(args.project)
        project_dir = args.project.parent

        # List mappings mode
        if args.list_mappings:
            mappings = project.get("mappings", [])
            print(f"Project: {args.project}")
            print(f"Found {len(mappings)} mappings:\n")
            for i, m in enumerate(mappings):
                ai_id = m.get("ai_frame_id")
                game_id = m.get("game_frame_id")
                status = m.get("status", "pending")
                print(f"  [{i}] AI#{ai_id} -> {game_id} ({status})")
            return

        # Get mapping details
        mapping_info = get_mapping_from_project(project, args.mapping_index, project_dir)
        capture_path = mapping_info["capture_path"]
        ai_frame_path = mapping_info["ai_frame_path"]
        selected_entry_ids = mapping_info["selected_entry_ids"]

        print(f"Project: {args.project}")
        print(f"Mapping [{args.mapping_index}]: {mapping_info['ai_frame_name']} -> {mapping_info['game_frame_name']}")

        # Use saved alignment if requested
        if args.use_saved:
            args.offset_x = mapping_info["offset_x"]
            args.offset_y = mapping_info["offset_y"]
            args.flip_h = mapping_info["flip_h"]
            args.flip_v = mapping_info["flip_v"]
            args.scale = mapping_info["scale"]
            args.auto_align = False
            print(f"Using saved alignment: offset=({args.offset_x}, {args.offset_y}), scale={args.scale:.2f}")
    else:
        # Manual specification
        if not args.capture or not args.ai_frame:
            parser.error("Either --project or both --capture and --ai-frame required")
        capture_path = args.capture
        ai_frame_path = args.ai_frame
        selected_entry_ids = None
        if args.entry_ids:
            selected_entry_ids = [int(x.strip()) for x in args.entry_ids.split(",")]

    # Load data
    print(f"Loading capture: {capture_path}")
    capture_result = load_capture(capture_path, selected_entry_ids)
    if selected_entry_ids:
        print(f"  Filtered to entry IDs: {selected_entry_ids}")
    print(f"  {capture_result.visible_count} sprites, bbox: {capture_result.bounding_box}")

    print(f"Loading AI frame: {ai_frame_path}")
    ai_image = Image.open(ai_frame_path).convert("RGBA")
    print(f"  Size: {ai_image.size}")

    # Render game frame for alignment calculations
    renderer = CaptureRenderer(capture_result)
    game_image = renderer.render_selection()

    # Determine alignment
    if args.auto_align:
        offset_x, offset_y, scale = compute_auto_align(
            ai_image,
            capture_result,
            game_image,
            match_scale=args.match_scale,
            flip_h=args.flip_h,
            flip_v=args.flip_v,
        )
        print(f"Auto-align: offset=({offset_x}, {offset_y}), scale={scale:.2f}")
    else:
        offset_x = args.offset_x
        offset_y = args.offset_y
        scale = args.scale
        print(f"Manual: offset=({offset_x}, {offset_y}), scale={scale:.2f}")

    # Render
    print("Rendering...")
    result, has_overflow, overflow_rects = render_workbench(
        capture_result,
        ai_image,
        offset_x=offset_x,
        offset_y=offset_y,
        scale=scale,
        flip_h=args.flip_h,
        flip_v=args.flip_v,
        display_scale=args.display_scale,
        show_markers=not args.no_markers,
        show_tile_overlay=args.tile_overlay,
        show_overflow=args.show_overflow,
        opacity=args.opacity,
    )

    result.save(args.output)
    print(f"Saved to: {args.output}")

    # Report out-of-bounds status
    if has_overflow:
        print("\n⚠️  OUT OF BOUNDS: AI frame content extends past tile area!")
        print(f"   {len(overflow_rects)} overflow region(s) detected")
        print("   Content outside tile area will NOT be injected.")
    else:
        print("\n✓ AI frame fits within tile area")

    # Print debug info
    game_centroid = ContentBoundsAnalyzer.compute_centroid(game_image)
    ai_bbox = ai_image.getbbox()
    if ai_bbox:
        ai_center = (
            ai_bbox[0] + (ai_bbox[2] - ai_bbox[0]) / 2,
            ai_bbox[1] + (ai_bbox[3] - ai_bbox[1]) / 2,
        )
        print("\nDebug info:")
        print(f"  Game centroid: ({game_centroid[0]:.1f}, {game_centroid[1]:.1f})")
        print(f"  AI content center: ({ai_center[0]:.1f}, {ai_center[1]:.1f})")
        print(f"  AI content bbox: {ai_bbox}")


if __name__ == "__main__":
    main()
