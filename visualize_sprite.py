#!/usr/bin/env python3
"""Quick sprite visualizer for extracted data"""

from PIL import Image
import sys
from pathlib import Path

def decode_4bpp_sprite(data):
    """Decode 4bpp SNES sprite data to image"""
    # Each tile is 8x8 pixels, 32 bytes (4 bits per pixel)
    tiles_count = len(data) // 32
    if tiles_count == 0:
        return None
    
    # Calculate dimensions (try to make it roughly square)
    tiles_per_row = max(1, int((tiles_count ** 0.5) + 0.5))
    tiles_per_col = (tiles_count + tiles_per_row - 1) // tiles_per_row
    
    width = tiles_per_row * 8
    height = tiles_per_col * 8
    
    # Create image
    img = Image.new('L', (width, height), 0)
    pixels = img.load()
    
    for tile_idx in range(min(tiles_count, tiles_per_row * tiles_per_col)):
        tile_x = (tile_idx % tiles_per_row) * 8
        tile_y = (tile_idx // tiles_per_row) * 8
        
        tile_offset = tile_idx * 32
        if tile_offset + 32 > len(data):
            break
        
        tile_data = data[tile_offset:tile_offset + 32]
        
        # Decode 4bpp tile
        for y in range(8):
            # Get the 4 bytes for this row
            row_offset = y * 2
            if row_offset + 16 < len(tile_data):
                byte1 = tile_data[row_offset]
                byte2 = tile_data[row_offset + 1]
                byte3 = tile_data[row_offset + 16]
                byte4 = tile_data[row_offset + 17]
                
                for x in range(8):
                    bit = 7 - x
                    # Combine bits from all 4 bytes to get 4-bit value
                    pixel = ((byte1 >> bit) & 1) | \
                            (((byte2 >> bit) & 1) << 1) | \
                            (((byte3 >> bit) & 1) << 2) | \
                            (((byte4 >> bit) & 1) << 3)
                    
                    # Convert 4-bit to 8-bit grayscale
                    pixels[tile_x + x, tile_y + y] = pixel * 17
    
    return img

def main():
    if len(sys.argv) != 3:
        print("Usage: python visualize_sprite.py input.bin output.png")
        sys.exit(1)
    
    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    
    # Read binary data
    with open(input_path, 'rb') as f:
        data = f.read()
    
    print(f"Input: {input_path} ({len(data)} bytes)")
    
    # Try to decode as 4bpp sprite
    img = decode_4bpp_sprite(data)
    
    if img:
        img.save(output_path)
        print(f"Saved to: {output_path} ({img.width}x{img.height} pixels)")
    else:
        print("Failed to decode sprite data")

if __name__ == '__main__':
    main()