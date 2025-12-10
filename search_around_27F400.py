#!/usr/bin/env python3
"""
Search densely around $27F400 where we found recognizable sprites with eyes
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
        f'found_{offset:06X}.bin'
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if 'Uncompressed size:' in result.stdout:
            for line in result.stdout.split('\n'):
                if 'Uncompressed size:' in line:
                    size_str = line.split(':')[1].strip().split()[0]
                    size = int(size_str)
                    # Focus on small to medium sprites (mushroom likely 256-2048 bytes)
                    if 200 < size < 2500:
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
    print("Searching densely around $27F400 (where we found eyes)...")
    print("=" * 60)
    
    # Search very densely around $27F400
    # Search from $27F000 to $280000 every 0x80 bytes
    offsets = []
    for offset in range(0x27F000, 0x280000, 0x80):
        offsets.append(offset)
    
    print(f"Testing {len(offsets)} offsets...")
    
    results = []
    
    for i, offset in enumerate(offsets):
        if i % 10 == 0:
            print(f"Progress: {i}/{len(offsets)} offsets checked...")
        
        size = extract_sprite(offset)
        
        if size > 0:
            bin_file = f'found_{offset:06X}.bin'
            png_file = f'found_{offset:06X}.png'
            
            if visualize_sprite(bin_file, png_file):
                try:
                    img = Image.open(png_file)
                    width, height = img.size
                    
                    # Look for small sprites (mushroom is probably 16x16 or 32x32)
                    if 16 <= width <= 64 and 16 <= height <= 64:
                        print(f"  Found small sprite at ${offset:06X}: {size} bytes, {width}x{height} pixels")
                        results.append((offset, size, width, height))
                except:
                    pass
            
            # Clean up binary
            if os.path.exists(bin_file):
                os.remove(bin_file)
    
    print("\n" + "=" * 60)
    print(f"Found {len(results)} small sprites that could be enemies:")
    
    # Sort by size (mushroom likely to be small)
    results.sort(key=lambda x: x[1])
    
    for offset, size, width, height in results:
        print(f"  ${offset:06X}: {size:4} bytes, {width:2}x{height:2} pixels - found_{offset:06X}.png")
    
    # Create HTML viewer for easy browsing
    with open('mushroom_candidates.html', 'w') as f:
        f.write("""<html>
<head><title>Mushroom Enemy Candidates near $27F400</title></head>
<body style="background: #333; color: white; font-family: monospace;">
<h1>Small Sprites near $27F400 (where we found eyes)</h1>
<p>Look for a mushroom-shaped enemy!</p>
<div style="display: flex; flex-wrap: wrap;">
""")
        
        for offset, size, width, height in results:
            png_file = f'found_{offset:06X}.png'
            if os.path.exists(png_file):
                f.write(f"""
<div style="margin: 10px; text-align: center; border: 2px solid #0f0; padding: 10px; background: #111;">
    <img src="{png_file}" style="image-rendering: pixelated; width: 128px; height: 128px; background: white; object-fit: contain;">
    <br><b>${offset:06X}</b>
    <br>{size} bytes
    <br>{width}x{height} px
</div>
""")
        
        f.write("""
</div>
</body>
</html>""")
    
    print(f"\nCreated mushroom_candidates.html - open to visually search for the mushroom!")

if __name__ == '__main__':
    main()