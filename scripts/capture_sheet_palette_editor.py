#!/usr/bin/env python
"""Capture Sheet Palette Editor screenshot with Live Preview.

This script opens the Sheet Palette Editor dialog with a sample AI frame
to show the Live Preview panel with Original and Quantized views.

Usage:
    uv run python scripts/capture_sheet_palette_editor.py [OPTIONS]

Examples:
    # Default: use mapping.spritepal-mapping.json, save to /tmp/sheet_palette_editor.png
    uv run python scripts/capture_sheet_palette_editor.py

    # Specify project and output
    uv run python scripts/capture_sheet_palette_editor.py -p my_project.json -o preview.png
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path, PureWindowsPath

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PIL import Image
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from core.frame_mapping_project import SheetPalette
from ui.frame_mapping.dialogs.sheet_palette_mapping_dialog import (
    SheetPaletteMappingDialog,
)
from ui.frame_mapping.services.palette_service import GamePaletteInfo


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Capture Sheet Palette Editor with Live Preview",
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
        help="Index of mapping to use for sample AI frame (default: 0)",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=Path("/tmp/sheet_palette_editor.png"),
        help="Output path for screenshot",
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=500,
        help="Delay in ms before capturing (default: 500)",
    )

    args = parser.parse_args()

    # Load project
    if not args.project.exists():
        print(f"Error: Project file not found: {args.project}")
        sys.exit(1)

    with open(args.project) as f:
        project = json.load(f)

    # Get AI frame from mapping for sample image
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

    print(f"Using AI frame: {ai_frame_path.name}")

    # Collect sheet colors from all AI frames
    sheet_colors: dict[tuple[int, int, int], int] = {}
    for frame_data in project["ai_frames"]:
        frame_path = Path(PureWindowsPath(frame_data["path"]).as_posix())
        if frame_path.exists():
            try:
                img = Image.open(frame_path).convert("RGBA")
                for pixel in img.getdata():
                    if pixel[3] > 128:  # Non-transparent
                        rgb = (pixel[0], pixel[1], pixel[2])
                        sheet_colors[rgb] = sheet_colors.get(rgb, 0) + 1
            except Exception as e:
                print(f"Warning: Could not process {frame_path}: {e}")

    print(f"Collected {len(sheet_colors)} unique colors from AI frames")

    # Get current palette
    current_palette: SheetPalette | None = None
    if project.get("sheet_palette") and project["sheet_palette"].get("colors"):
        sp = project["sheet_palette"]
        current_palette = SheetPalette(
            colors=[tuple(c) for c in sp["colors"]],
            color_mappings={tuple(k) if isinstance(k, list) else eval(k): v
                           for k, v in sp.get("color_mappings", {}).items()},
            background_color=tuple(sp["background_color"]) if sp.get("background_color") else None,
            background_tolerance=sp.get("background_tolerance", 30),
        )
        print(f"Loaded sheet_palette with {len(current_palette.colors)} colors")

    # Build game palettes dict (simplified - just need structure)
    game_palettes: dict[str, GamePaletteInfo] = {}
    for gf in project.get("game_frames", []):
        gf_id = gf.get("id", "")
        if gf_id:
            # Would normally load from capture, but we just need basic structure
            game_palettes[gf_id] = GamePaletteInfo(
                colors=[(0, 0, 0)] * 16,  # Placeholder
                display_name=gf_id,
            )

    # Create Qt app
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    # Create and show dialog
    dialog = SheetPaletteMappingDialog(
        sheet_colors=sheet_colors,
        current_palette=current_palette,
        game_palettes=game_palettes,
        parent=None,
        sample_ai_frame_path=ai_frame_path,
    )

    def capture_and_close() -> None:
        # Grab screenshot
        pixmap = dialog.grab()
        pixmap.save(str(args.output))
        print(f"Saved screenshot to: {args.output}")
        dialog.close()
        app.quit()

    # Schedule capture after dialog renders
    QTimer.singleShot(args.delay, capture_and_close)

    dialog.show()
    app.exec()


if __name__ == "__main__":
    main()
