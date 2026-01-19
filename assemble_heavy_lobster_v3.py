#!/usr/bin/env python3
"""
Better Heavy Lobster assembly based on visual analysis of the blocks.
"""

from pathlib import Path
from PIL import Image
from core.hal_compression import HALCompressor
from core.tile_renderer import TileRenderer

BYTES_PER_TILE = 32
SNES_STRIDE = 16

def extract_sprite_block(tiles_data: bytes, base_tile: int, width_tiles: int, height_tiles: int, renderer: TileRenderer) -> Image.Image:
    """Extract a sprite block using SNES 16-tile row stride."""
    tile_bytes = bytearray()
    for row in range(height_tiles):
        for col in range(width_tiles):
            tile_index = base_tile + col + (row * SNES_STRIDE)
            tile_start = tile_index * BYTES_PER_TILE
            tile_end = tile_start + BYTES_PER_TILE
            if tile_end <= len(tiles_data):
                tile_bytes.extend(tiles_data[tile_start:tile_end])
            else:
                tile_bytes.extend(b'\x00' * BYTES_PER_TILE)
    return renderer.render_tiles(bytes(tile_bytes), width_tiles, height_tiles, palette_index=None)


def main():
    rom_path = Path("roms/Kirby Super Star (USA).sfc")
    offset = 0x1EB260

    hal = HALCompressor()
    tiles_data = hal.decompress_from_rom(str(rom_path), offset)
    renderer = TileRenderer()

    # Extract all 32x32 blocks (4x4 tiles each)
    blocks = []
    for start_tile in range(0, 128, 4):  # First 8 columns of 32x32 blocks
        if start_tile + 3 + (3 * SNES_STRIDE) < len(tiles_data) // BYTES_PER_TILE:
            block = extract_sprite_block(tiles_data, start_tile, 4, 4, renderer)
            if block:
                blocks.append(block)

    print(f"Extracted {len(blocks)} blocks")

    # Also extract 16x16 blocks for finer control
    blocks_16 = []
    num_tiles = len(tiles_data) // BYTES_PER_TILE
    for start_tile in range(0, num_tiles, 2):
        if start_tile + 1 + SNES_STRIDE < num_tiles:
            block = extract_sprite_block(tiles_data, start_tile, 2, 2, renderer)
            if block:
                blocks_16.append((start_tile, block))

    print(f"Extracted {len(blocks_16)} 16x16 blocks")

    # Save all 16x16 blocks in a grid for reference
    cols = 8
    rows = (len(blocks_16) + cols - 1) // cols
    sheet16 = Image.new("RGBA", (cols * 16, rows * 16), (0, 0, 0, 0))
    for idx, (_, block) in enumerate(blocks_16):
        x = (idx % cols) * 16
        y = (idx // cols) * 16
        sheet16.paste(block, (x, y), block)
    sheet16.save("heavy_lobster_16x16_blocks.png")
    print("Saved: heavy_lobster_16x16_blocks.png")

    # Heavy Lobster visual arrangement attempt
    # Based on looking at the blocks, Heavy Lobster appears to be:
    # - Wide horizontally (about 6-7 blocks = 192-224 pixels)
    # - Medium height (about 3-4 blocks = 96-128 pixels)
    # - Has symmetrical claws on left and right

    # Create a large canvas
    canvas = Image.new("RGBA", (256, 160), (0, 0, 0, 0))

    # Looking at block patterns from the all_blocks image:
    # Blocks seem to show: claw parts, body center, eyes, legs
    # Let me try arranging based on visual patterns

    # Row 0 (y=0): Upper body / head area
    # Row 1 (y=32): Main body / eyes
    # Row 2 (y=64): Lower body / claws base
    # Row 3 (y=96): Legs / feet

    # Arrangement based on visual inspection of the 32x32 blocks
    # (block_index, x, y, flip_h)
    layout = [
        # Top row - claws and head
        (0, 16, 0, False),    # Left claw top
        (1, 48, 0, False),    # Left body
        (2, 80, 0, False),    # Center top
        (3, 112, 0, False),   # Right body
        (3, 144, 0, True),    # Right claw top (mirrored)

        # Second row - main body
        (4, 0, 32, False),    # Far left
        (5, 32, 32, False),   # Left mid
        (6, 64, 32, False),   # Center
        (7, 96, 32, False),   # Right mid
        (7, 128, 32, True),   # Far right (mirrored)

        # Third row - lower body
        (8, 16, 64, False),
        (9, 48, 64, False),
        (10, 80, 64, False),
        (11, 112, 64, False),

        # Fourth row - legs
        (12, 32, 96, False),
        (13, 64, 96, False),
        (14, 96, 96, False),
        (15, 128, 96, False),
    ]

    for block_idx, x, y, flip_h in layout:
        if block_idx < len(blocks):
            block = blocks[block_idx]
            if flip_h:
                block = block.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            canvas.paste(block, (x, y), block)

    canvas.save("heavy_lobster_v3.png")
    print("Saved: heavy_lobster_v3.png")

    # Also create a version with ALL blocks arranged more tightly
    # to show the complete sprite data
    full_width = 6 * 32  # 6 blocks wide
    full_height = 6 * 32  # 6 blocks tall
    full_canvas = Image.new("RGBA", (full_width, full_height), (0, 0, 0, 0))

    # Place blocks in a way that might show Heavy Lobster better
    # Based on the patterns I see, let me try a different arrangement
    block_positions = [
        # First attempt at logical layout
        (0, 0, 0), (1, 32, 0), (2, 64, 0), (3, 96, 0),
        (4, 0, 32), (5, 32, 32), (6, 64, 32), (7, 96, 32),
        (8, 128, 0), (9, 160, 0),
        (10, 128, 32), (11, 160, 32),
        (12, 0, 64), (13, 32, 64), (14, 64, 64), (15, 96, 64),
        (16, 128, 64), (17, 160, 64),
        (18, 0, 96), (19, 32, 96), (20, 64, 96), (21, 96, 96),
        (22, 128, 96), (23, 160, 96),
        (24, 0, 128), (25, 32, 128), (26, 64, 128), (27, 96, 128),
        (28, 128, 128), (29, 160, 128),
        (30, 0, 160), (31, 32, 160),
    ]

    for block_idx, x, y in block_positions:
        if block_idx < len(blocks):
            full_canvas.paste(blocks[block_idx], (x, y), blocks[block_idx])

    full_canvas.save("heavy_lobster_full_data.png")
    print("Saved: heavy_lobster_full_data.png (all sprite data)")

    print()
    print("Note: For exact in-game positioning, you need to capture Heavy Lobster")
    print("in Mesen2 while it's on screen - the capture will include exact OAM positions.")


if __name__ == "__main__":
    main()
