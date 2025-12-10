#!/usr/bin/env python3
"""
Extract sprites from areas near mushroom placement concentrations
"""

import sys
import os
sys.path.insert(0, '/mnt/c/CustomScripts/KirbyMax/workshop/exhal-master/spritepal')

from pathlib import Path
from core.rom_extractor import ROMExtractor
from PIL import Image
import numpy as np

def extract_mushroom_area_sprites():
    """Extract sprites from areas with high mushroom concentration"""
    
    rom_path = "Kirby Super Star (USA).sfc"
    extractor = ROMExtractor()
    
    # Key offsets found near mushroom concentrations
    # These are small compressed sprites (appropriate size for mushroom)
    mushroom_candidates = [
        (0x0EE8DA, "small_sprite_1", 0x100),  # size=$0100
        (0x0EE909, "small_sprite_2", 0x100),  # size=$0100  
        (0x0EE90A, "small_sprite_3", 0x101),  # size=$0101
        (0x0EEFCB, "small_sprite_4", 0x1C0),  # size=$01C0
        (0x0EF0E3, "small_sprite_5", 0x1B8),  # size=$01B8
        (0x0EF133, "small_sprite_6", 0x17F),  # size=$017F
        (0x0EF2C5, "small_sprite_7", 0x100),  # size=$0100
        (0x0F01A6, "small_sprite_8", 0x1A9),  # size=$01A9
        (0x0F05D2, "small_sprite_9", 0x200),  # size=$0200
        (0x0F05DA, "small_sprite_10", 0x1A0), # size=$01A0
    ]
    
    print("Extracting sprites from mushroom concentration areas...")
    print("=" * 60)
    
    extracted = []
    
    for offset, name, expected_size in mushroom_candidates:
        print(f"\nExtracting {name} from ${offset:06X} (size: ${expected_size:04X})...")
        
        try:
            # Try with SpritePal's extractor
            output_path, info = extractor.extract_sprite_from_rom(
                rom_path, offset, name, sprite_name=""
            )
            
            if output_path and Path(output_path).exists():
                print(f"  ✓ Extracted with SpritePal: {output_path}")
                extracted.append((name, output_path))
            else:
                print(f"  ✗ SpritePal extraction failed")
                
                # Try raw extraction
                raw_output = extract_raw_tiles(rom_path, offset, expected_size, name)
                if raw_output:
                    print(f"  ✓ Raw extraction: {raw_output}")
                    extracted.append((name, raw_output))
        
        except Exception as e:
            print(f"  ✗ Error: {e}")
    
    # Create comparison gallery
    if extracted:
        create_comparison_gallery(extracted)
    
    return extracted

def extract_raw_tiles(rom_path, offset, size, name):
    """Extract and visualize raw tiles without decompression"""
    
    try:
        with open(rom_path, 'rb') as f:
            f.seek(offset)
            data = f.read(size)
        
        # Assume 4bpp SNES format
        tiles_per_sprite = size // 32  # 32 bytes per 8x8 tile
        
        if tiles_per_sprite < 1:
            return None
        
        # Arrange tiles in a grid
        cols = min(8, tiles_per_sprite)
        rows = (tiles_per_sprite + cols - 1) // cols
        
        img_width = cols * 8
        img_height = rows * 8
        pixels = np.zeros((img_height, img_width), dtype=np.uint8)
        
        for tile_idx in range(min(tiles_per_sprite, len(data) // 32)):
            tile_data = data[tile_idx * 32:(tile_idx + 1) * 32]
            
            # Decode 4bpp tile
            tile_pixels = decode_4bpp_tile(tile_data)
            
            # Place in grid
            row = tile_idx // cols
            col = tile_idx % cols
            y_start = row * 8
            x_start = col * 8
            
            if y_start + 8 <= img_height and x_start + 8 <= img_width:
                pixels[y_start:y_start+8, x_start:x_start+8] = tile_pixels
        
        # Apply a simple grayscale palette
        img = Image.fromarray(pixels * 17, 'L')  # Scale to 0-255
        
        output_path = f"{name}_raw_{offset:06X}.png"
        img.save(output_path)
        
        return output_path
    
    except Exception as e:
        print(f"    Raw extraction error: {e}")
        return None

def decode_4bpp_tile(tile_data):
    """Decode a single 8x8 4bpp SNES tile"""
    
    if len(tile_data) < 32:
        return np.zeros((8, 8), dtype=np.uint8)
    
    pixels = np.zeros((8, 8), dtype=np.uint8)
    
    for row in range(8):
        # 4bpp: 2 bytes for planes 0-1, 2 bytes for planes 2-3
        plane01_offset = row * 2
        plane23_offset = 16 + row * 2
        
        if plane23_offset + 1 < len(tile_data):
            plane0 = tile_data[plane01_offset]
            plane1 = tile_data[plane01_offset + 1]
            plane2 = tile_data[plane23_offset]
            plane3 = tile_data[plane23_offset + 1]
            
            for col in range(8):
                bit = 7 - col
                pixel = ((plane0 >> bit) & 1) | \
                        (((plane1 >> bit) & 1) << 1) | \
                        (((plane2 >> bit) & 1) << 2) | \
                        (((plane3 >> bit) & 1) << 3)
                pixels[row, col] = pixel
    
    return pixels

def create_comparison_gallery(extracted_sprites):
    """Create HTML gallery comparing extracted sprites"""
    
    html = """<!DOCTYPE html>
<html>
<head>
    <title>Mushroom Candidate Sprites</title>
    <style>
        body { font-family: monospace; background: #1a1a1a; color: #fff; padding: 20px; }
        .container { max-width: 1400px; margin: 0 auto; }
        h1 { color: #4CAF50; }
        .sprite-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; }
        .sprite-card { background: #2a2a2a; border: 1px solid #444; padding: 15px; border-radius: 8px; }
        .sprite-card img { width: 100%; height: 256px; object-fit: contain; background: #000; 
                           image-rendering: pixelated; border: 1px solid #555; }
        .sprite-name { color: #4CAF50; font-weight: bold; margin-bottom: 10px; }
        .note { background: #333; padding: 10px; margin: 20px 0; border-left: 3px solid #4CAF50; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🍄 Mushroom Enemy Sprite Candidates</h1>
        <div class="note">
            These sprites were extracted from compressed data found immediately before 
            the highest concentration of mushroom enemy placements (296 mushrooms in region $0F0000).<br>
            Small sprites (0x100-0x200 bytes) are most likely to be the mushroom enemy.
        </div>
        <div class="sprite-grid">
"""
    
    for name, path in extracted_sprites:
        if Path(path).exists():
            html += f"""            <div class="sprite-card">
                <div class="sprite-name">{name}</div>
                <img src="{path}" alt="{name}">
            </div>
"""
    
    html += """        </div>
    </div>
</body>
</html>
"""
    
    gallery_path = "MUSHROOM_CANDIDATES.html"
    with open(gallery_path, 'w') as f:
        f.write(html)
    
    print(f"\n✓ Created comparison gallery: {gallery_path}")

if __name__ == '__main__':
    extract_mushroom_area_sprites()