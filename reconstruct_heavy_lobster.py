#!/usr/bin/env python3
"""
Reconstruct Heavy Lobster from decompressed tiles.

Heavy Lobster is a large boss made up of multiple 32x32 sprite parts.
This script assembles the parts using SNES 16-tile row stride.
"""

from pathlib import Path
from PIL import Image
from core.hal_compression import HALCompressor
from core.tile_renderer import TileRenderer

BYTES_PER_TILE = 32
SNES_STRIDE = 16  # 16 tiles per row in SNES VRAM

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

    print("=" * 60)
    print("RECONSTRUCTING HEAVY LOBSTER")
    print("=" * 60)

    # Load tiles
    hal = HALCompressor()
    tiles_data = hal.decompress_from_rom(str(rom_path), offset)
    num_tiles = len(tiles_data) // BYTES_PER_TILE
    print(f"Loaded {num_tiles} tiles from offset 0x{offset:X}")

    renderer = TileRenderer()

    # Heavy Lobster parts - each 32x32 block (4x4 tiles)
    # Based on SNES sprite conventions, large bosses are made of multiple 32x32 OAM entries

    # The tilesheet is 16 tiles wide, so:
    # - Block at tile 0: tiles 0-3, 16-19, 32-35, 48-51 (first 32x32)
    # - Block at tile 4: tiles 4-7, 20-23, 36-39, 52-55 (second 32x32)
    # - Block at tile 8: tiles 8-11, 24-27, 40-43, 56-59 (third 32x32)
    # - etc.

    # Extract individual 32x32 blocks
    blocks = []
    for start_tile in range(0, min(num_tiles, 128), 4):  # Every 4th tile starts a new column
        if start_tile + 3 + (3 * SNES_STRIDE) < num_tiles:  # Make sure we have enough tiles
            block = extract_sprite_block(tiles_data, start_tile, 4, 4, renderer)
            if block:
                blocks.append((start_tile, block))

    print(f"Extracted {len(blocks)} 32x32 blocks")

    # Save individual blocks for inspection
    for i, (start_tile, block) in enumerate(blocks):
        block.save(f"heavy_lobster_block_{i:02d}_tile{start_tile}.png")
    print(f"Saved {len(blocks)} individual blocks")

    # Try to assemble Heavy Lobster
    # Looking at the tile sheet, Heavy Lobster appears to be arranged as:
    # - Blocks 0-3: Upper body parts (claws, head)
    # - Blocks 4-7: Middle body parts
    # - Blocks 8+: Lower body, legs, etc.

    # Create a larger canvas to assemble the sprite
    # Heavy Lobster is roughly 4 blocks wide x 3 blocks tall = 128x96 pixels

    # Try arrangement 1: Simple grid of first 12 blocks (3 rows x 4 cols)
    canvas_width = 4 * 32
    canvas_height = 3 * 32
    canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))

    for idx, (start_tile, block) in enumerate(blocks[:12]):
        col = idx % 4
        row = idx // 4
        x = col * 32
        y = row * 32
        canvas.paste(block, (x, y), block)

    canvas.save("heavy_lobster_assembled_grid.png")
    print("Saved: heavy_lobster_assembled_grid.png (4x3 grid)")

    # Try arrangement 2: Adjusted for typical boss sprite layout
    # Heavy Lobster: Main body in center, claws on sides
    # Let's try a 5x3 arrangement with offset positioning

    canvas2_width = 5 * 32
    canvas2_height = 4 * 32
    canvas2 = Image.new("RGBA", (canvas2_width, canvas2_height), (0, 0, 0, 0))

    # Manual positioning based on visual inspection of tile sheet
    # This may need adjustment based on actual sprite layout
    positions = [
        # (block_index, x_offset, y_offset)
        (0, 0, 0),      # Top-left claw
        (1, 32, 0),     #
        (2, 64, 0),     # Body top
        (3, 96, 0),     #
        (4, 0, 32),     # Middle-left
        (5, 32, 32),    #
        (6, 64, 32),    # Body middle
        (7, 96, 32),    #
        (8, 0, 64),     # Bottom-left
        (9, 32, 64),    #
        (10, 64, 64),   # Body bottom
        (11, 96, 64),   #
    ]

    for block_idx, x, y in positions:
        if block_idx < len(blocks):
            _, block = blocks[block_idx]
            canvas2.paste(block, (x, y), block)

    canvas2.save("heavy_lobster_assembled_v2.png")
    print("Saved: heavy_lobster_assembled_v2.png (manual layout)")

    # Also save a larger composite showing all available tiles as 32x32 blocks
    all_blocks_cols = 4
    all_blocks_rows = (len(blocks) + all_blocks_cols - 1) // all_blocks_cols
    all_canvas = Image.new("RGBA", (all_blocks_cols * 32, all_blocks_rows * 32), (0, 0, 0, 0))

    for idx, (start_tile, block) in enumerate(blocks):
        col = idx % all_blocks_cols
        row = idx // all_blocks_cols
        all_canvas.paste(block, (col * 32, row * 32), block)

    all_canvas.save("heavy_lobster_all_blocks.png")
    print(f"Saved: heavy_lobster_all_blocks.png (all {len(blocks)} blocks)")

    print()
    print("=" * 60)
    print("RECONSTRUCTION COMPLETE")
    print("=" * 60)
    print()
    print("Output files:")
    print("  - heavy_lobster_tilesheet.png    (raw 8x8 tiles)")
    print("  - heavy_lobster_block_XX_tileN.png (individual 32x32 blocks)")
    print("  - heavy_lobster_all_blocks.png   (all blocks in grid)")
    print("  - heavy_lobster_assembled_grid.png (simple 4x3 grid)")
    print("  - heavy_lobster_assembled_v2.png (manual layout attempt)")
    print()
    print("To get the exact in-game layout, you would need to:")
    print("1. Capture Heavy Lobster in Mesen2 when fully visible")
    print("2. The capture will include OAM positions for each sprite part")
    print("3. Use those positions to correctly assemble the full boss")


if __name__ == "__main__":
    main()
