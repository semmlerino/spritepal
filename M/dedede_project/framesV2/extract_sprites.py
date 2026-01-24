#!/usr/bin/env python3
"""Extract sprites from spritesheet, removing green background and limiting to 15 colors."""

from pathlib import Path
from PIL import Image
import numpy as np
from collections import Counter


def get_background_color(img: Image.Image) -> tuple[int, int, int]:
    """Detect the background color (most common color at edges)."""
    width, height = img.size

    # Sample edges
    edge_pixels = []
    for x in range(width):
        edge_pixels.append(img.getpixel((x, 0)))
        edge_pixels.append(img.getpixel((x, height - 1)))
    for y in range(height):
        edge_pixels.append(img.getpixel((0, y)))
        edge_pixels.append(img.getpixel((width - 1, y)))

    # Get most common (the green background)
    counter = Counter(edge_pixels)
    bg_color = counter.most_common(1)[0][0]
    return bg_color[:3] if len(bg_color) > 3 else bg_color


def is_greenish(r: int, g: int, b: int, threshold: int = 60) -> bool:
    """Check if a color is greenish (G channel dominant)."""
    # A pixel is greenish if green is dominant and above threshold
    return g > r and g > b and g > threshold


def remove_green_background(img: Image.Image) -> Image.Image:
    """Remove green background and any greenish anti-aliased pixels."""
    img = img.convert("RGBA")
    data = np.array(img)

    # Detect background color from corners
    bg_color = get_background_color(img)
    print(f"Detected background color: RGB{bg_color}")

    # Create mask for background pixels (exact match with tolerance)
    tolerance = 20
    r_match = np.abs(data[:, :, 0].astype(int) - bg_color[0]) < tolerance
    g_match = np.abs(data[:, :, 1].astype(int) - bg_color[1]) < tolerance
    b_match = np.abs(data[:, :, 2].astype(int) - bg_color[2]) < tolerance
    bg_mask = r_match & g_match & b_match

    # Also remove any pixel that is "greenish" (G > R and G > B)
    # This catches anti-aliased edge pixels
    r = data[:, :, 0].astype(int)
    g = data[:, :, 1].astype(int)
    b = data[:, :, 2].astype(int)

    # Greenish: G is dominant and above a threshold
    greenish_mask = (g > r) & (g > b) & (g > 60)

    # Combine masks
    remove_mask = bg_mask | greenish_mask

    # Set to transparent
    data[remove_mask, 3] = 0

    return Image.fromarray(data)


def find_sprite_bounds(img: Image.Image) -> list[tuple[int, int, int, int]]:
    """Find bounding boxes of individual sprites."""
    data = np.array(img)
    alpha = data[:, :, 3]

    sprites = []

    # Find horizontal runs of sprites (rows)
    non_empty_rows = np.any(alpha > 0, axis=1)
    row_groups = []
    in_group = False
    group_start = 0

    for y, has_content in enumerate(non_empty_rows):
        if has_content and not in_group:
            in_group = True
            group_start = y
        elif not has_content and in_group:
            in_group = False
            row_groups.append((group_start, y))
    if in_group:
        row_groups.append((group_start, len(non_empty_rows)))

    # For each row group, find individual sprites
    for row_start, row_end in row_groups:
        row_alpha = alpha[row_start:row_end, :]
        cols_with_content = np.any(row_alpha > 0, axis=0)

        in_sprite = False
        sprite_start = 0
        min_gap = 3
        gap_count = 0

        for x, has_content in enumerate(cols_with_content):
            if has_content:
                if not in_sprite:
                    in_sprite = True
                    sprite_start = x
                gap_count = 0
            else:
                if in_sprite:
                    gap_count += 1
                    if gap_count >= min_gap:
                        sprites.append((sprite_start, row_start, x - gap_count + 1, row_end))
                        in_sprite = False

        if in_sprite:
            sprites.append((sprite_start, row_start, len(cols_with_content), row_end))

    return sprites


def reduce_colors(img: Image.Image, max_colors: int = 15) -> Image.Image:
    """Reduce image to max_colors (plus transparent)."""
    img = img.convert("RGBA")
    data = np.array(img)

    alpha = data[:, :, 3]
    non_transparent = alpha > 0

    if not np.any(non_transparent):
        return img

    pixels = data[non_transparent][:, :3]
    unique_colors = np.unique(pixels.reshape(-1, 3), axis=0)

    print(f"  Original unique colors: {len(unique_colors)}")

    if len(unique_colors) <= max_colors:
        return img

    # Need to quantize
    rgb_img = Image.new("RGB", img.size, (0, 0, 0))
    rgb_img.paste(img, mask=img.split()[3])

    quantized = rgb_img.quantize(colors=max_colors, method=Image.Quantize.MEDIANCUT)
    quantized_rgb = quantized.convert("RGB")

    result = Image.new("RGBA", img.size)
    result_data = np.array(result)
    quantized_data = np.array(quantized_rgb)

    result_data[:, :, :3] = quantized_data
    result_data[:, :, 3] = alpha

    return Image.fromarray(result_data)


def remove_remaining_green_from_palette(img: Image.Image) -> Image.Image:
    """After quantization, replace any remaining greenish colors with nearest non-green."""
    img = img.convert("RGBA")
    data = np.array(img)

    alpha = data[:, :, 3]
    non_transparent = alpha > 0

    if not np.any(non_transparent):
        return img

    # Find unique colors
    pixels = data[non_transparent][:, :3]
    unique_colors = np.unique(pixels.reshape(-1, 3), axis=0)

    # Separate green and non-green colors
    green_colors = []
    non_green_colors = []

    for color in unique_colors:
        r, g, b = color
        if g > r and g > b and g > 60:
            green_colors.append(tuple(color))
        else:
            non_green_colors.append(tuple(color))

    if not green_colors:
        return img  # No green to remove

    if not non_green_colors:
        # All colors are green - make them transparent
        data[non_transparent, 3] = 0
        return Image.fromarray(data)

    print(f"  Removing {len(green_colors)} greenish colors")

    # For each green color, find nearest non-green color
    non_green_array = np.array(non_green_colors)

    for green_color in green_colors:
        # Find nearest non-green by Euclidean distance
        distances = np.sqrt(np.sum((non_green_array - np.array(green_color)) ** 2, axis=1))
        nearest_idx = np.argmin(distances)
        nearest_color = non_green_colors[nearest_idx]

        # Replace in image
        mask = (
            (data[:, :, 0] == green_color[0]) &
            (data[:, :, 1] == green_color[1]) &
            (data[:, :, 2] == green_color[2]) &
            (alpha > 0)
        )
        data[mask, 0] = nearest_color[0]
        data[mask, 1] = nearest_color[1]
        data[mask, 2] = nearest_color[2]

    return Image.fromarray(data)


def extract_sprites(input_path: Path, output_dir: Path, max_colors: int = 15):
    """Main extraction function."""
    print(f"Loading {input_path}")
    img = Image.open(input_path)
    print(f"Image size: {img.size}, mode: {img.mode}")

    # Remove green background
    print("Removing green background...")
    img_no_bg = remove_green_background(img)

    # Find sprite bounds
    print("Finding sprite bounds...")
    bounds = find_sprite_bounds(img_no_bg)
    print(f"Found {len(bounds)} sprites")

    output_dir.mkdir(parents=True, exist_ok=True)

    for i, (x1, y1, x2, y2) in enumerate(bounds):
        sprite = img_no_bg.crop((x1, y1, x2, y2))

        print(f"Processing sprite {i:02d} ({x2-x1}x{y2-y1})...")

        # Reduce colors
        sprite_reduced = reduce_colors(sprite, max_colors)

        # Remove any remaining greenish colors from the palette
        sprite_clean = remove_remaining_green_from_palette(sprite_reduced)

        # Verify color count
        sprite_data = np.array(sprite_clean)
        alpha = sprite_data[:, :, 3]
        non_transparent = alpha > 0
        if np.any(non_transparent):
            pixels = sprite_data[non_transparent][:, :3]
            unique = np.unique(pixels.reshape(-1, 3), axis=0)
            print(f"  Final colors: {len(unique)}")

        output_path = output_dir / f"sprite_{i:02d}.png"
        sprite_clean.save(output_path)
        print(f"  Saved: {output_path.name}")

    full_no_bg = output_dir / "full_no_background.png"
    img_no_bg.save(full_no_bg)
    print(f"\nSaved full sheet without background: {full_no_bg.name}")


if __name__ == "__main__":
    script_dir = Path(__file__).parent
    input_file = script_dir / "spritesheet.png"
    output_dir = script_dir / "extracted"

    extract_sprites(input_file, output_dir, max_colors=15)
    print("\nDone!")
