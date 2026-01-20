#!/usr/bin/env python3
"""
Split a sprite sheet into individual frames by detecting sprites against background.

Usage:
    python split_spritesheet.py spritesheet.png output_dir/ [--bg-color R,G,B] [--min-size 16] [--padding 2]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


def find_sprite_bounds(
    img: Image.Image,
    bg_color: tuple[int, int, int],
    min_size: int = 16,
    tolerance: int = 30,
) -> list[tuple[int, int, int, int]]:
    """
    Find bounding boxes of sprites in an image by detecting non-background regions.

    Args:
        img: PIL Image (RGB or RGBA)
        bg_color: Background color to treat as transparent
        min_size: Minimum sprite dimension (filters noise)
        tolerance: Color matching tolerance

    Returns:
        List of (x, y, width, height) tuples for each sprite found
    """
    if img.mode == "RGBA":
        rgb_img = Image.new("RGB", img.size, bg_color)
        rgb_img.paste(img, mask=img.split()[3])
        img = rgb_img
    elif img.mode != "RGB":
        img = img.convert("RGB")

    width, height = img.size
    pixels = img.load()

    # Create mask of non-background pixels
    visited = [[False] * width for _ in range(height)]
    sprites: list[tuple[int, int, int, int]] = []

    def is_background(px: tuple[int, ...]) -> bool:
        return all(abs(px[i] - bg_color[i]) <= tolerance for i in range(3))

    def flood_fill(start_x: int, start_y: int) -> tuple[int, int, int, int] | None:
        """Flood fill to find sprite bounds."""
        if visited[start_y][start_x]:
            return None
        if is_background(pixels[start_x, start_y]):
            visited[start_y][start_x] = True
            return None

        min_x, max_x = start_x, start_x
        min_y, max_y = start_y, start_y
        stack = [(start_x, start_y)]

        while stack:
            x, y = stack.pop()
            if x < 0 or x >= width or y < 0 or y >= height:
                continue
            if visited[y][x]:
                continue
            if is_background(pixels[x, y]):
                visited[y][x] = True
                continue

            visited[y][x] = True
            min_x = min(min_x, x)
            max_x = max(max_x, x)
            min_y = min(min_y, y)
            max_y = max(max_y, y)

            # 4-connected neighbors
            stack.extend([(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)])

        w = max_x - min_x + 1
        h = max_y - min_y + 1
        if w >= min_size and h >= min_size:
            return (min_x, min_y, w, h)
        return None

    # Scan image for sprites
    for y in range(height):
        for x in range(width):
            bounds = flood_fill(x, y)
            if bounds:
                sprites.append(bounds)

    # Sort by position (top-to-bottom, left-to-right)
    sprites.sort(key=lambda b: (b[1], b[0]))

    return sprites


def detect_background_color(img: Image.Image) -> tuple[int, int, int]:
    """Detect background color by sampling corners."""
    if img.mode == "RGBA":
        img = img.convert("RGB")
    elif img.mode != "RGB":
        img = img.convert("RGB")

    pixels = img.load()
    w, h = img.size

    # Sample corners
    corners = [
        pixels[0, 0],
        pixels[w - 1, 0],
        pixels[0, h - 1],
        pixels[w - 1, h - 1],
    ]

    # Find most common corner color
    from collections import Counter

    color_counts = Counter(corners)
    most_common = color_counts.most_common(1)[0][0]
    return most_common[:3]  # type: ignore[return-value]


def split_spritesheet(
    input_path: str,
    output_dir: str,
    bg_color: tuple[int, int, int] | None = None,
    min_size: int = 16,
    padding: int = 2,
) -> dict[str, object]:
    """
    Split spritesheet into individual frame images.

    Args:
        input_path: Path to spritesheet image
        output_dir: Directory to save individual frames
        bg_color: Background color (auto-detected if None)
        min_size: Minimum sprite size
        padding: Padding to add around each sprite

    Returns:
        Project data dict with frame information
    """
    img = Image.open(input_path)
    if img.mode != "RGB":
        img = img.convert("RGB")

    if bg_color is None:
        bg_color = detect_background_color(img)
        print(f"Auto-detected background color: RGB{bg_color}")

    # Find sprites
    sprites = find_sprite_bounds(img, bg_color, min_size)
    print(f"Found {len(sprites)} sprites")

    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    frames_dir = output_path / "frames"
    frames_dir.mkdir(exist_ok=True)

    frames: list[dict[str, object]] = []

    for i, (x, y, w, h) in enumerate(sprites):
        # Extract with padding
        x1 = max(0, x - padding)
        y1 = max(0, y - padding)
        x2 = min(img.width, x + w + padding)
        y2 = min(img.height, y + h + padding)

        frame_img = img.crop((x1, y1, x2, y2))

        # Create RGBA with transparent background
        rgba = Image.new("RGBA", frame_img.size, (0, 0, 0, 0))
        for py in range(frame_img.height):
            for px in range(frame_img.width):
                pixel = frame_img.getpixel((px, py))
                if not all(abs(pixel[c] - bg_color[c]) <= 30 for c in range(3)):
                    rgba.putpixel((px, py), (*pixel, 255))

        # Save frame
        frame_id = f"frame_{i:02d}"
        frame_path = frames_dir / f"{frame_id}.png"
        rgba.save(frame_path)

        frames.append(
            {
                "id": frame_id,
                "index": i,
                "bounds": [x, y, w, h],
                "extracted_path": f"frames/{frame_id}.png",
                "size": [rgba.width, rgba.height],
            }
        )
        print(f"  {frame_id}: {w}x{h} at ({x}, {y})")

    # Create project data
    project_data = {
        "name": Path(input_path).stem,
        "spritesheet": {
            "path": str(Path(input_path).resolve()),
            "background_color": list(bg_color),
            "dimensions": [img.width, img.height],
            "frames": frames,
        },
        "mappings": [],
        "palette": None,
        "metadata": {
            "created_at": __import__("datetime").datetime.now().isoformat(),
            "frame_count": len(frames),
        },
    }

    # Save project file
    project_file = output_path / "project.json"
    with open(project_file, "w") as f:
        json.dump(project_data, f, indent=2)
    print(f"\nProject saved to: {project_file}")

    return project_data


def main() -> None:
    parser = argparse.ArgumentParser(description="Split spritesheet into individual frames")
    parser.add_argument("input", help="Input spritesheet image")
    parser.add_argument("output", help="Output directory for frames")
    parser.add_argument(
        "--bg-color",
        help="Background color as R,G,B (auto-detected if not specified)",
    )
    parser.add_argument(
        "--min-size",
        type=int,
        default=16,
        help="Minimum sprite dimension (default: 16)",
    )
    parser.add_argument(
        "--padding",
        type=int,
        default=2,
        help="Padding around each sprite (default: 2)",
    )

    args = parser.parse_args()

    bg_color = None
    if args.bg_color:
        bg_color = tuple(map(int, args.bg_color.split(",")))  # type: ignore[assignment]

    split_spritesheet(args.input, args.output, bg_color, args.min_size, args.padding)


if __name__ == "__main__":
    main()
