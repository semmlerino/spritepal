#!/usr/bin/env python3
"""
Search the enemy sprite area $300000-$310000 for the mushroom
"""

import subprocess
import os
from pathlib import Path
from PIL import Image

def extract_sprite(offset):
    """Extract sprite using exhal tool"""
    cmd = [
        './archive/obsolete_test_images/ultrathink/exhal',
        'Kirby Super Star (USA).sfc',
        f'0x{offset:06X}',
        f'enemy_{offset:06X}.bin'
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if 'Uncompressed size:' in result.stdout:
            for line in result.stdout.split('\n'):
                if 'Uncompressed size:' in line:
                    size_str = line.split(':')[1].strip().split()[0]
                    size = int(size_str)
                    # Only return if it's a reasonable sprite size
                    if 100 < size < 5000:
                        return size
        return 0
    except:
        return 0

def visualize_sprite(bin_path, png_path):
    """Convert sprite binary to PNG"""
    cmd = ['python3', 'visualize_sprite.py', bin_path, png_path]
    try:
        subprocess.run(cmd, capture_output=True, timeout=5)
        return os.path.exists(png_path)
    except:
        return False

def main():
    print("Searching enemy sprite area $300000-$310000 for mushroom...")
    print("=" * 60)
    
    # Create directory for enemy sprites
    os.makedirs('enemy_sprites', exist_ok=True)
    
    results = []
    
    # Search every 0x400 bytes (1KB) in the enemy area
    # Focus on likely areas first
    for offset in range(0x300000, 0x310000, 0x400):
        # Show progress every 16 sprites
        if (offset - 0x300000) % 0x4000 == 0:
            print(f"\nSearching ${offset:06X}...")
        
        size = extract_sprite(offset)
        
        if size > 0:
            bin_file = f'enemy_{offset:06X}.bin'
            png_file = f'enemy_sprites/enemy_{offset:06X}.png'
            
            if visualize_sprite(bin_file, png_file):
                try:
                    img = Image.open(png_file)
                    width, height = img.size
                    
                    # Check if it could be a mushroom (typically 16x16 or 32x32)
                    if 16 <= width <= 64 and 16 <= height <= 64:
                        print(f"  ${offset:06X}: {size:4} bytes, {width:2}x{height:2} pixels - potential enemy sprite")
                        results.append((offset, size, width, height))
                except:
                    pass
            
            # Clean up binary
            if os.path.exists(bin_file):
                os.remove(bin_file)
    
    print("\n" + "=" * 60)
    print(f"Found {len(results)} potential enemy sprites:")
    
    # Sort by size (mushroom likely to be small-medium)
    results.sort(key=lambda x: x[1])
    
    for offset, size, width, height in results[:20]:  # Show first 20
        print(f"  ${offset:06X}: {size:4} bytes, {width:2}x{height:2} pixels")
    
    # Create HTML viewer
    with open('enemy_sprites/index.html', 'w') as f:
        f.write("""<html>
<head><title>Enemy Sprites - Find the Mushroom!</title></head>
<body style="background: #333; color: white; font-family: monospace;">
<h1>Enemy Sprites from $300000-$310000</h1>
<p>Look for a mushroom-shaped enemy (compare with MushroomSprite.png)</p>
<div style="display: flex; flex-wrap: wrap;">
""")
        
        for offset, size, width, height in results:
            f.write(f"""
<div style="margin: 10px; text-align: center; border: 1px solid #666; padding: 10px; background: #222;">
    <img src="enemy_{offset:06X}.png" style="image-rendering: pixelated; width: 128px; height: 128px; background: white; object-fit: contain;">
    <br>${offset:06X}
    <br>{size} bytes
    <br>{width}x{height}
</div>
""")
        
        f.write("""
</div>
</body>
</html>""")
    
    print(f"\nCreated enemy_sprites/index.html with {len(results)} sprites")
    print("Open this file to visually search for the mushroom!")

if __name__ == '__main__':
    main()