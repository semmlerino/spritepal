#!/usr/bin/env python3
"""
Visualize the extracted mushroom sprite candidates to identify the actual sprite
"""

from pathlib import Path

from PIL import Image


def snes_4bpp_to_image(data: bytes, width: int = 8, height: int = 8) -> Image.Image:
    """Convert SNES 4bpp tile data to an image"""

    # SNES 4bpp format: 2 bytes for 8 pixels (2 bitplanes), then 2 more bytes (2 more bitplanes)
    # Total of 32 bytes per 8x8 tile

    pixels = []

    for y in range(height):
        row = []
        for x in range(0, width, 8):  # Process 8 pixels at a time
            # Get the 4 bytes for this row of 8 pixels
            offset = (y * (width // 8) * 4) + ((x // 8) * 32)

            if offset + 3 < len(data):
                bp0 = data[offset + 0]  # Bitplane 0
                bp1 = data[offset + 1]  # Bitplane 1
                bp2 = data[offset + 16]  # Bitplane 2
                bp3 = data[offset + 17]  # Bitplane 3

                # Extract 8 pixels from the bitplanes
                for bit in range(8):
                    pixel = 0
                    if bp0 & (0x80 >> bit):
                        pixel |= 1
                    if bp1 & (0x80 >> bit):
                        pixel |= 2
                    if bp2 & (0x80 >> bit):
                        pixel |= 4
                    if bp3 & (0x80 >> bit):
                        pixel |= 8

                    # Convert 4-bit value to grayscale
                    gray = pixel * 17  # Scale 0-15 to 0-255
                    row.append(gray)
            else:
                row.extend([0] * 8)

        pixels.extend(row)

    # Create image
    img = Image.new("L", (width, height))
    img.putdata(pixels)
    return img


def visualize_16x16_sprite(data: bytes) -> Image.Image:
    """Convert 128 bytes of SNES sprite data to a 16x16 image"""

    # A 16x16 sprite consists of 4 8x8 tiles arranged in a 2x2 grid
    # Each tile is 32 bytes

    if len(data) < 128:
        print(f"Warning: Data too short ({len(data)} bytes), expected 128")
        data = data + b"\x00" * (128 - len(data))

    # Extract the 4 tiles
    tiles = []
    for i in range(4):
        tile_data = data[i * 32 : (i + 1) * 32]
        tile_img = snes_4bpp_to_image(tile_data)
        tiles.append(tile_img)

    # Combine into 16x16 image
    # Tile arrangement: 0 1
    #                   2 3
    combined = Image.new("L", (16, 16))
    combined.paste(tiles[0], (0, 0))
    combined.paste(tiles[1], (8, 0))
    combined.paste(tiles[2], (0, 8))
    combined.paste(tiles[3], (8, 8))

    return combined


def main():
    """Visualize all mushroom sprite candidates"""

    # Find all extracted candidates
    candidates = sorted(Path().glob("potential_mushroom_*.bin"))

    print(f"Found {len(candidates)} mushroom sprite candidates")
    print("Converting to images...\n")

    # Create a composite image showing all candidates
    if candidates:
        n_candidates = len(candidates)
        cols = 8  # Show 8 sprites per row
        rows = (n_candidates + cols - 1) // cols

        # Create large canvas for all sprites
        canvas_width = cols * (16 + 4) + 4  # 16px sprite + 4px padding
        canvas_height = rows * (16 + 4) + 4
        canvas = Image.new("RGB", (canvas_width, canvas_height), (64, 64, 64))

        for idx, candidate_file in enumerate(candidates):
            # Load sprite data
            with open(candidate_file, "rb") as f:
                sprite_data = f.read()

            # Convert to image
            sprite_img = visualize_16x16_sprite(sprite_data)

            # Scale up for better visibility
            sprite_img = sprite_img.resize((16, 16), Image.NEAREST)

            # Convert to RGB and apply a palette for better visibility
            sprite_rgb = Image.new("RGB", (16, 16))
            for y in range(16):
                for x in range(16):
                    val = sprite_img.getpixel((x, y))
                    if val == 0:
                        color = (0, 0, 0)  # Black for transparent
                    else:
                        # Use a brownish palette for mushroom
                        r = min(255, val + 50)
                        g = min(255, val)
                        b = min(255, val - 50) if val > 50 else 0
                        color = (r, g, b)
                    sprite_rgb.putpixel((x, y), color)

            # Place on canvas
            col = idx % cols
            row = idx // cols
            x = col * 20 + 4
            y = row * 20 + 4
            canvas.paste(sprite_rgb, (x, y))

            # Extract offset from filename
            offset = candidate_file.replace("potential_mushroom_", "").replace(".bin", "")
            print(f"  {idx:2d}. Offset 0x{offset} - Placed at ({x}, {y})")

            # Also save individual images
            individual_path = f"mushroom_candidate_{offset}.png"
            sprite_rgb_large = sprite_rgb.resize((64, 64), Image.NEAREST)
            sprite_rgb_large.save(individual_path)

        # Save composite image
        canvas_path = "mushroom_candidates_all.png"
        canvas.save(canvas_path)
        print(f"\nSaved composite image to {canvas_path}")
        print("Individual sprites saved as mushroom_candidate_*.png")

        # Analyze which candidates look most like sprites
        print("\n=== Analysis ===")
        for idx, candidate_file in enumerate(candidates[:5]):  # Check first 5
            with open(candidate_file, "rb") as f:
                data = f.read()

            # Check for sprite characteristics
            non_zero = sum(1 for b in data if b != 0)
            unique_values = len(set(data))

            print(f"Candidate {idx}: {non_zero}/128 non-zero bytes, {unique_values} unique values")

            # Show first 16 bytes
            print(f"  First 16 bytes: {' '.join(f'{b:02x}' for b in data[:16])}")


if __name__ == "__main__":
    main()
