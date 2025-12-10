#!/usr/bin/env python3
"""
Search around $27D800 for the mushroom sprite
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
        f'sprite_{offset:06X}.bin'
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if 'Uncompressed size:' in result.stdout:
            for line in result.stdout.split('\n'):
                if 'Uncompressed size:' in line:
                    size_str = line.split(':')[1].strip().split()[0]
                    return int(size_str)
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
    print("Searching around $27D800 for mushroom sprite...")
    print("=" * 60)
    
    # Search offsets around $27D800
    offsets = [
        0x27C000, 0x27C400, 0x27C800, 0x27CC00,
        0x27D000, 0x27D400, 0x27D800, 0x27DC00,
        0x27E000, 0x27E400, 0x27E800, 0x27EC00,
        0x27F000, 0x27F400, 0x27F800, 0x27FC00,
    ]
    
    results = []
    
    for offset in offsets:
        print(f"\nTrying ${offset:06X}...")
        size = extract_sprite(offset)
        
        if size > 100:  # Valid sprite
            bin_file = f'sprite_{offset:06X}.bin'
            png_file = f'sprite_{offset:06X}.png'
            
            if visualize_sprite(bin_file, png_file):
                # Get image dimensions
                try:
                    img = Image.open(png_file)
                    width, height = img.size
                    print(f"  Success! {size} bytes, {width}x{height} pixels")
                    results.append((offset, size, width, height))
                except:
                    print(f"  Extracted {size} bytes but visualization failed")
            else:
                print(f"  Extracted {size} bytes but visualization failed")
            
            # Clean up binary
            if os.path.exists(bin_file):
                os.remove(bin_file)
        else:
            print(f"  No valid sprite found")
    
    print("\n" + "=" * 60)
    print(f"Found {len(results)} sprites:")
    for offset, size, width, height in results:
        print(f"  ${offset:06X}: {size:5} bytes, {width:3}x{height:3} pixels - sprite_{offset:06X}.png")
    
    print("\nNow examine the PNG files to find the mushroom!")

if __name__ == '__main__':
    main()