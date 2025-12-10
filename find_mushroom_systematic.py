#!/usr/bin/env python3
"""
Systematically extract and visualize sprites from the enemy sprite ROM area
to find the mushroom enemy
"""

import subprocess
import os
from pathlib import Path
from PIL import Image

def extract_sprite(rom_path, offset, output_path):
    """Extract sprite using exhal tool"""
    cmd = [
        './archive/obsolete_test_images/ultrathink/exhal',
        rom_path,
        f'0x{offset:06X}',
        output_path
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        # Check if extraction succeeded
        if 'Uncompressed size:' in result.stdout:
            # Parse uncompressed size
            for line in result.stdout.split('\n'):
                if 'Uncompressed size:' in line:
                    size_str = line.split(':')[1].strip().split()[0]
                    return int(size_str)
        return 0
    except:
        return 0

def decode_4bpp_sprite(data):
    """Decode 4bpp SNES sprite data to image"""
    tiles_count = len(data) // 32
    if tiles_count == 0:
        return None
    
    # Calculate dimensions
    tiles_per_row = max(1, int((tiles_count ** 0.5) + 0.5))
    tiles_per_col = (tiles_count + tiles_per_row - 1) // tiles_per_row
    
    width = tiles_per_row * 8
    height = tiles_per_col * 8
    
    img = Image.new('L', (width, height), 0)
    pixels = img.load()
    
    for tile_idx in range(min(tiles_count, tiles_per_row * tiles_per_col)):
        tile_x = (tile_idx % tiles_per_row) * 8
        tile_y = (tile_idx // tiles_per_row) * 8
        
        tile_offset = tile_idx * 32
        if tile_offset + 32 > len(data):
            break
        
        tile_data = data[tile_offset:tile_offset + 32]
        
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
                    
                    pixels[tile_x + x, tile_y + y] = pixel * 17
    
    return img

def main():
    rom_path = "Kirby Super Star (USA).sfc"
    
    # Search ranges for enemy sprites
    search_ranges = [
        (0x300000, 0x310000, "Main enemy area"),
        (0x2F0000, 0x300000, "Secondary enemy area"),
    ]
    
    print("Systematically searching for mushroom sprite...")
    print("=" * 60)
    
    os.makedirs('sprite_candidates', exist_ok=True)
    
    candidates = []
    
    for start, end, description in search_ranges:
        print(f"\nSearching {description} (${start:06X}-${end:06X})...")
        
        # Try every 0x100 bytes (sprites are usually aligned)
        for offset in range(start, end, 0x100):
            # Skip if we're at the very end
            if offset >= end - 0x20:
                break
            
            # Try to extract
            temp_bin = f'temp_{offset:06X}.bin'
            size = extract_sprite(rom_path, offset, temp_bin)
            
            if size > 100 and size < 5000:  # Reasonable sprite size
                # Visualize it
                try:
                    with open(temp_bin, 'rb') as f:
                        data = f.read()
                    
                    img = decode_4bpp_sprite(data)
                    if img and img.width >= 16 and img.height >= 16:
                        # Save as PNG
                        output_png = f'sprite_candidates/sprite_{offset:06X}.png'
                        img.save(output_png)
                        
                        candidates.append({
                            'offset': offset,
                            'size': size,
                            'width': img.width,
                            'height': img.height,
                            'path': output_png
                        })
                        
                        print(f"  Found sprite at ${offset:06X}: {size} bytes, {img.width}x{img.height} pixels")
                except:
                    pass
                
                # Clean up temp file
                if os.path.exists(temp_bin):
                    os.remove(temp_bin)
    
    # Create summary HTML
    print(f"\n\nFound {len(candidates)} sprite candidates")
    print("Creating visual summary...")
    
    with open('sprite_candidates/index.html', 'w') as f:
        f.write("""<html>
<head><title>Sprite Candidates</title></head>
<body style="background: #333; color: white;">
<h1>Sprite Candidates for Mushroom Enemy</h1>
<p>Look for a mushroom-shaped enemy sprite</p>
<div style="display: flex; flex-wrap: wrap;">
""")
        
        for candidate in candidates:
            filename = os.path.basename(candidate['path'])
            f.write(f"""
<div style="margin: 10px; text-align: center; border: 1px solid #666; padding: 10px;">
    <img src="{filename}" style="image-rendering: pixelated; width: 128px; height: auto; background: white;">
    <br>Offset: ${candidate['offset']:06X}
    <br>Size: {candidate['size']} bytes
    <br>{candidate['width']}x{candidate['height']} px
</div>
""")
        
        f.write("""
</div>
</body>
</html>""")
    
    print(f"Visual summary saved to sprite_candidates/index.html")
    print(f"Open this file in a browser to visually identify the mushroom sprite")

if __name__ == '__main__':
    main()