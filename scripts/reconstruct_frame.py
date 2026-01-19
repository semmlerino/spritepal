#!/usr/bin/env python3
"""
Pixel-Perfect SNES Frame Reconstruction from Mesen 2 Capture.

This script reconstructs exactly what the SNES PPU draws using:
- OAM positions (no guessing)
- VRAM tile data (from capture)
- CGRAM palettes (from capture)
- Proper flip handling

Usage:
    python reconstruct_frame.py capture.json [--output frame.png]
    python reconstruct_frame.py capture.json --cluster --output sprites/

High-Level Rule: Do NOT try to "rearrange tiles manually."
Instead, reconstruct exactly what the PPU draws.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

# SNES constants
SNES_WIDTH = 256
SNES_HEIGHT = 224
BYTES_PER_TILE = 32


@dataclass
class Palette:
    """SNES palette with RGB colors."""

    colors: list[tuple[int, int, int]]  # 16 RGB tuples

    @classmethod
    def from_bgr555_list(cls, bgr555_values: list[int]) -> Palette:
        """Convert list of BGR555 integers to RGB palette."""
        colors = []
        for bgr in bgr555_values:
            r = (bgr & 0x1F) << 3
            g = ((bgr >> 5) & 0x1F) << 3
            b = ((bgr >> 10) & 0x1F) << 3
            # Full 8-bit expansion
            r = r | (r >> 5)
            g = g | (g >> 5)
            b = b | (b >> 5)
            colors.append((r, g, b))
        return cls(colors)

    @classmethod
    def from_rgb_list(cls, rgb_values: list[list[int]]) -> Palette:
        """Convert list of [R, G, B] lists to palette."""
        colors = [(c[0], c[1], c[2]) for c in rgb_values]
        return cls(colors)


def decode_4bpp_tile(data: bytes) -> list[list[int]]:
    """
    Decode a single SNES 4bpp 8x8 tile.

    SNES 4bpp format:
    - 32 bytes per tile
    - Bytes 0-15: bitplanes 0-1 interleaved
    - Bytes 16-31: bitplanes 2-3 interleaved

    Returns 8x8 grid of color indices (0-15).
    """
    if len(data) < 32:
        data = data + b"\x00" * (32 - len(data))

    pixels = [[0] * 8 for _ in range(8)]

    for y in range(8):
        # Bitplanes 0-1 (low bytes)
        bp0 = data[y * 2]
        bp1 = data[y * 2 + 1]
        # Bitplanes 2-3 (high bytes)
        bp2 = data[16 + y * 2]
        bp3 = data[16 + y * 2 + 1]

        for x in range(8):
            bit = 7 - x
            idx = ((bp0 >> bit) & 1) | (((bp1 >> bit) & 1) << 1) | (((bp2 >> bit) & 1) << 2) | (((bp3 >> bit) & 1) << 3)
            pixels[y][x] = idx

    return pixels


def render_tile_to_image(
    tile_data: bytes,
    palette: Palette,
) -> Image.Image:
    """Render a single 8x8 tile to an RGBA image."""
    pixels = decode_4bpp_tile(tile_data)
    img = Image.new("RGBA", (8, 8), (0, 0, 0, 0))

    for y in range(8):
        for x in range(8):
            idx = pixels[y][x]
            if idx == 0:
                # Color 0 is transparent
                continue
            r, g, b = palette.colors[idx]
            img.putpixel((x, y), (r, g, b, 255))

    return img


@dataclass
class OAMSprite:
    """Parsed OAM sprite entry."""

    id: int
    x: int
    y: int
    tile: int
    width: int
    height: int
    flip_h: bool
    flip_v: bool
    palette: int
    priority: int
    tiles: list[dict]  # [{tile_index, vram_addr, pos_x, pos_y, data_hex}]


def parse_capture(json_path: Path) -> tuple[list[OAMSprite], dict[int, Palette]]:
    """Parse capture JSON and return sprites and palettes."""
    data = json.loads(json_path.read_text(encoding="utf-8"))

    # Parse palettes (handle both BGR555 int and RGB list formats)
    palettes: dict[int, Palette] = {}
    for key, values in data.get("palettes", {}).items():
        pal_idx = int(key)
        if values and isinstance(values[0], list):
            # RGB format: [[r, g, b], ...]
            palettes[pal_idx] = Palette.from_rgb_list(values)
        else:
            # BGR555 format: [int, int, ...]
            palettes[pal_idx] = Palette.from_bgr555_list(values)

    # Parse OAM entries
    sprites: list[OAMSprite] = []
    for entry in data.get("entries", []):
        sprite = OAMSprite(
            id=entry.get("id", 0),
            x=entry.get("x", 0),
            y=entry.get("y", 0),
            tile=entry.get("tile", 0),
            width=entry.get("width", 8),
            height=entry.get("height", 8),
            flip_h=entry.get("flip_h", False),
            flip_v=entry.get("flip_v", False),
            palette=entry.get("palette", 0),
            priority=entry.get("priority", 0),
            tiles=entry.get("tiles", []),
        )
        sprites.append(sprite)

    return sprites, palettes


def render_sprite(sprite: OAMSprite, palettes: dict[int, Palette]) -> Image.Image:
    """Render a sprite from its tile data."""
    width = sprite.width
    height = sprite.height

    # Get the palette for this sprite
    palette = palettes.get(sprite.palette)
    if palette is None:
        # Fallback grayscale
        palette = Palette([(i * 17, i * 17, i * 17) for i in range(16)])

    # Create sprite canvas
    sprite_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    # Render each tile at its position within the sprite
    for tile in sprite.tiles:
        data_hex = tile.get("data_hex", "")
        if not data_hex or len(data_hex) != 64:  # 32 bytes = 64 hex chars
            continue

        tile_data = bytes.fromhex(data_hex)
        tile_img = render_tile_to_image(tile_data, palette)

        # Position within sprite (before flips)
        pos_x = tile.get("pos_x", 0) * 8
        pos_y = tile.get("pos_y", 0) * 8

        sprite_img.paste(tile_img, (pos_x, pos_y), tile_img)

    # Apply flips AFTER all tiles are composed
    if sprite.flip_h:
        sprite_img = sprite_img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if sprite.flip_v:
        sprite_img = sprite_img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

    return sprite_img


def reconstruct_frame(
    sprites: list[OAMSprite],
    palettes: dict[int, Palette],
    show_bounds: bool = False,
) -> Image.Image:
    """
    Reconstruct a full SNES frame from OAM data.

    IMPORTANT SNES rules:
    - Within OBJ layer, lower OAM index is always on top (priority bits are for OBJ vs BG).
    - Y is 8-bit and wraps at 256. If y+height > 256, the sprite also appears at y-256.
    """
    canvas = Image.new("RGBA", (SNES_WIDTH, SNES_HEIGHT), (48, 48, 48, 255))

    # SNES: lower OAM index is on top => draw high IDs first, low IDs last.
    sorted_sprites = sorted(sprites, key=lambda s: s.id, reverse=True)

    for sprite in sorted_sprites:
        sprite_img = render_sprite(sprite, palettes)

        x = sprite.x
        y = sprite.y & 0xFF  # OAM Y is 8-bit

        # If the sprite is entirely in the non-visible bottom border and does NOT wrap, skip it.
        # (If it wraps, we must render the wrapped part at y-256.)
        if y >= SNES_HEIGHT and (y + sprite.height) <= 256:
            continue

        # Render at normal Y (will clip if below the visible 224 lines)
        positions = [(x, y)]

        # If it wraps past 255, render the wrapped part at y-256 (negative y shows top portion)
        if (y + sprite.height) > 256:
            positions.append((x, y - 256))

        for px, py in positions:
            canvas.paste(sprite_img, (px, py), sprite_img)

            if show_bounds:
                from PIL import ImageDraw
                draw = ImageDraw.Draw(canvas)
                draw.rectangle(
                    [px, py, px + sprite.width - 1, py + sprite.height - 1],
                    outline=(255, 0, 255, 128),
                )

    return canvas


def cluster_sprites(
    sprites: list[OAMSprite],
    distance_threshold: int = 32,
) -> list[list[OAMSprite]]:
    """
    Cluster nearby sprites (likely same game object).

    Uses simple distance-based clustering.
    For better results, cluster by:
    - Proximity
    - Same palette
    - Same priority
    """
    if not sprites:
        return []

    # Filter visible sprites (using proper Y wrapping logic)
    def is_visible(s: OAMSprite) -> bool:
        y = s.y & 0xFF
        # Entirely off-screen and doesn't wrap: skip
        if y >= SNES_HEIGHT and (y + s.height) <= 256:
            return False
        return True

    visible = [s for s in sprites if is_visible(s)]
    if not visible:
        return []

    groups: list[list[OAMSprite]] = []
    used: set[int] = set()

    # Sort by position for more consistent clustering
    visible = sorted(visible, key=lambda s: (s.y, s.x))

    for sprite in visible:
        if sprite.id in used:
            continue

        # Start new group
        group = [sprite]
        used.add(sprite.id)

        # Find nearby sprites with same palette
        center_x = sprite.x + sprite.width // 2
        center_y = sprite.y + sprite.height // 2

        for other in visible:
            if other.id in used:
                continue

            # Check distance
            other_cx = other.x + other.width // 2
            other_cy = other.y + other.height // 2
            dx = abs(center_x - other_cx)
            dy = abs(center_y - other_cy)

            if dx < distance_threshold and dy < distance_threshold:
                # Same palette and priority increases likelihood of same object
                if other.palette == sprite.palette:
                    group.append(other)
                    used.add(other.id)

        groups.append(group)

    return groups


def extract_cluster(
    group: list[OAMSprite],
    palettes: dict[int, Palette],
) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """
    Extract a sprite cluster to a tight-fit image.

    Returns (image, bounding_box).
    """
    if not group:
        return Image.new("RGBA", (8, 8), (0, 0, 0, 0)), (0, 0, 8, 8)

    # Calculate bounding box
    min_x = min(s.x for s in group)
    min_y = min(s.y for s in group)
    max_x = max(s.x + s.width for s in group)
    max_y = max(s.y + s.height for s in group)

    width = max_x - min_x
    height = max_y - min_y

    # Create canvas
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    # Sort by priority then ID
    sorted_group = sorted(group, key=lambda s: (s.priority, s.id))

    for sprite in sorted_group:
        sprite_img = render_sprite(sprite, palettes)
        paste_x = sprite.x - min_x
        paste_y = sprite.y - min_y
        canvas.paste(sprite_img, (paste_x, paste_y), sprite_img)

    return canvas, (min_x, min_y, max_x, max_y)


def main():
    parser = argparse.ArgumentParser(description="Pixel-perfect SNES frame reconstruction from Mesen 2 capture")
    parser.add_argument("capture", help="Path to capture JSON file")
    parser.add_argument(
        "--output", "-o", default="reconstructed_frame.png", help="Output path (file or directory if --cluster)"
    )
    parser.add_argument("--cluster", "-c", action="store_true", help="Also extract clustered sprite groups")
    parser.add_argument("--cluster-distance", type=int, default=32, help="Distance threshold for clustering (pixels)")
    parser.add_argument("--bounds", "-b", action="store_true", help="Show sprite bounding boxes")
    parser.add_argument("--individual", "-i", action="store_true", help="Also save individual OAM entries")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    capture_path = Path(args.capture)
    if not capture_path.exists():
        print(f"Error: Capture file not found: {capture_path}")
        return 1

    print("=" * 60)
    print("PIXEL-PERFECT SNES FRAME RECONSTRUCTION")
    print("=" * 60)
    print(f"Capture: {capture_path}")

    # Parse capture
    print("\n[1] Parsing capture...")
    sprites, palettes = parse_capture(capture_path)
    print(f"    Sprites: {len(sprites)}")
    print(f"    Palettes: {len(palettes)}")

    # Check palette format
    if palettes:
        sample_pal = next(iter(palettes.values()))
        print(f"    Sample color: RGB{sample_pal.colors[1]}")

    # Reconstruct full frame
    print("\n[2] Reconstructing frame...")
    frame = reconstruct_frame(sprites, palettes, show_bounds=args.bounds)

    # Determine output path
    output_path = Path(args.output)
    if args.cluster:
        output_path.mkdir(parents=True, exist_ok=True)
        frame_path = output_path / "full_frame.png"
    else:
        frame_path = output_path

    frame.save(frame_path)
    print(f"    Saved: {frame_path}")

    # Cluster sprites if requested
    if args.cluster:
        print(f"\n[3] Clustering sprites (threshold={args.cluster_distance}px)...")
        groups = cluster_sprites(sprites, args.cluster_distance)
        print(f"    Found {len(groups)} sprite groups")

        saved = 0
        for i, group in enumerate(groups):
            if len(group) == 0:
                continue

            img, bbox = extract_cluster(group, palettes)

            # Skip empty images
            if img.getextrema()[3][1] == 0:  # Alpha max is 0
                continue

            x, y = bbox[0], bbox[1]
            filename = f"group_{i:03d}_at_{x}_{y}_{img.width}x{img.height}.png"
            img.save(output_path / filename)
            saved += 1

            if args.verbose:
                print(f"    {filename}: {len(group)} sprites")

        print(f"    Saved {saved} sprite groups")

    # Save individual sprites if requested
    if args.individual:
        print("\n[4] Saving individual sprites...")
        if args.cluster:
            ind_dir = output_path / "individual"
        else:
            ind_dir = output_path.parent / "individual"
        ind_dir.mkdir(parents=True, exist_ok=True)

        for sprite in sprites:
            if 224 <= sprite.y < 240:
                continue

            img = render_sprite(sprite, palettes)
            filename = f"oam_{sprite.id:03d}_pal{sprite.palette}_at_{sprite.x}_{sprite.y}.png"
            img.save(ind_dir / filename)

        print(f"    Saved to {ind_dir}")

    print("\n" + "=" * 60)
    print("RECONSTRUCTION COMPLETE")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
