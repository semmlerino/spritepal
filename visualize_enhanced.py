#!/usr/bin/env python3
"""Enhanced sprite visualizer with better contrast"""

from PIL import Image, ImageEnhance
import sys
from pathlib import Path
import numpy as np

def decode_4bpp_sprite_enhanced(data):
    """Decode 4bpp SNES sprite with enhanced visibility"""
    tiles_count = len(data) // 32
    if tiles_count == 0:
        return None
    
    # Calculate dimensions
    tiles_per_row = max(1, int((tiles_count ** 0.5) + 0.5))
    tiles_per_col = (tiles_count + tiles_per_row - 1) // tiles_per_row
    
    width = tiles_per_row * 8
    height = tiles_per_col * 8
    
    # Create array to hold pixel values
    pixels = np.zeros((height, width), dtype=np.uint8)
    
    for tile_idx in range(min(tiles_count, tiles_per_row * tiles_per_col)):
        tile_x = (tile_idx % tiles_per_row) * 8
        tile_y = (tile_idx // tiles_per_row) * 8
        
        tile_offset = tile_idx * 32
        if tile_offset + 32 > len(data):
            break
        
        tile_data = data[tile_offset:tile_offset + 32]
        
        # Decode 4bpp tile
        for y in range(8):
            row_offset = y * 2
            if row_offset + 16 < len(tile_data):
                byte1 = tile_data[row_offset]
                byte2 = tile_data[row_offset + 1]
                byte3 = tile_data[row_offset + 16]
                byte4 = tile_data[row_offset + 17]
                
                for x in range(8):
                    bit = 7 - x
                    pixel = ((byte1 >> bit) & 1) | \
                            (((byte2 >> bit) & 1) << 1) | \
                            (((byte3 >> bit) & 1) << 2) | \
                            (((byte4 >> bit) & 1) << 3)
                    
                    pixels[tile_y + y, tile_x + x] = pixel
    
    # Create palette that makes shapes more visible
    # 0 = transparent/background (white)
    # 1-15 = different gray levels for visibility
    palette_img = Image.fromarray(pixels, mode='P')
    
    # Create a palette with better contrast
    palette = []
    palette.extend([255, 255, 255])  # 0 = white (background)
    
    # Use distinct colors for each palette index to see structure
    colors = [
        (0, 0, 0),       # 1 = black
        (255, 0, 0),     # 2 = red
        (0, 255, 0),     # 3 = green
        (0, 0, 255),     # 4 = blue
        (255, 255, 0),   # 5 = yellow
        (255, 0, 255),   # 6 = magenta
        (0, 255, 255),   # 7 = cyan
        (128, 128, 128), # 8 = gray
        (128, 0, 0),     # 9 = dark red
        (0, 128, 0),     # 10 = dark green
        (0, 0, 128),     # 11 = dark blue
        (128, 128, 0),   # 12 = olive
        (128, 0, 128),   # 13 = purple
        (0, 128, 128),   # 14 = teal
        (64, 64, 64),    # 15 = dark gray
    ]
    
    for r, g, b in colors:
        palette.extend([r, g, b])
    
    # Pad palette to 256 colors
    while len(palette) < 768:
        palette.extend([0, 0, 0])
    
    palette_img.putpalette(palette)
    
    # Convert to RGB for saving
    return palette_img.convert('RGB')

def main():
    if len(sys.argv) < 2:
        # Process all small enemy sprites
        sprites_to_check = [
            ('enemy_sprites/enemy_309000.png', 0x309000),
            ('enemy_sprites/enemy_30D000.png', 0x30D000),
            ('enemy_sprites/enemy_303400.png', 0x303400),
            ('enemy_sprites/enemy_30A000.png', 0x30A000),
            ('enemy_sprites/enemy_30F400.png', 0x30F400),
        ]
        
        for png_path, offset in sprites_to_check:
            # Extract the raw data again
            bin_file = f'enemy_{offset:06X}.bin'
            cmd = f'./archive/obsolete_test_images/ultrathink/exhal "Kirby Super Star (USA).sfc" 0x{offset:06X} {bin_file}'
            import subprocess
            subprocess.run(cmd, shell=True, capture_output=True)
            
            if Path(bin_file).exists():
                with open(bin_file, 'rb') as f:
                    data = f.read()
                
                img = decode_4bpp_sprite_enhanced(data)
                if img:
                    output_path = f'enemy_{offset:06X}_enhanced.png'
                    img.save(output_path)
                    print(f"Enhanced sprite saved: {output_path} ({img.width}x{img.height})")
                
                # Clean up
                Path(bin_file).unlink()
    else:
        input_path = Path(sys.argv[1])
        output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else input_path.with_suffix('_enhanced.png')
        
        with open(input_path, 'rb') as f:
            data = f.read()
        
        img = decode_4bpp_sprite_enhanced(data)
        if img:
            img.save(output_path)
            print(f"Enhanced sprite saved: {output_path} ({img.width}x{img.height})")

if __name__ == '__main__':
    main()