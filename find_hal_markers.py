#!/usr/bin/env python3
"""
Find HAL compression markers in ROM and extract sprites from those positions
"""

import subprocess
import os
from pathlib import Path

def find_hal_markers(rom_path, start_offset, end_offset):
    """Find HAL compression markers in ROM"""
    markers = []
    
    with open(rom_path, 'rb') as f:
        f.seek(start_offset)
        data = f.read(end_offset - start_offset)
    
    # HAL compression markers
    hal_markers = [0xE3, 0xE7, 0xF3, 0xF7]
    
    for i in range(len(data) - 4):
        if data[i] in hal_markers:
            # Check if next bytes look like size/header
            # HAL format usually has size in next 2 bytes
            if i + 3 < len(data):
                size_low = data[i + 1]
                size_high = data[i + 2]
                size = size_low | (size_high << 8)
                
                # Reasonable sprite size (100 bytes to 10KB)
                if 100 < size < 10000:
                    offset = start_offset + i
                    markers.append((offset, data[i], size))
    
    return markers

def extract_and_visualize(rom_path, offset, marker_byte):
    """Extract sprite at offset and visualize"""
    output_bin = f'hal_{offset:06X}.bin'
    output_png = f'hal_{offset:06X}.png'
    
    # Extract with exhal
    cmd = [
        './archive/obsolete_test_images/ultrathink/exhal',
        rom_path,
        f'0x{offset:06X}',
        output_bin
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        
        # Check if extraction succeeded
        if 'Uncompressed size:' in result.stdout:
            # Get uncompressed size
            for line in result.stdout.split('\n'):
                if 'Uncompressed size:' in line:
                    size_str = line.split(':')[1].strip().split()[0]
                    size = int(size_str)
                    
                    # Visualize
                    vis_cmd = ['python3', 'visualize_sprite.py', output_bin, output_png]
                    subprocess.run(vis_cmd, capture_output=True, timeout=5)
                    
                    # Clean up binary
                    if os.path.exists(output_bin):
                        os.remove(output_bin)
                    
                    return size, os.path.exists(output_png)
    except Exception as e:
        print(f"    Error: {e}")
    
    # Clean up on failure
    if os.path.exists(output_bin):
        os.remove(output_bin)
    
    return 0, False

def main():
    rom_path = 'Kirby Super Star (USA).sfc'
    
    print("Searching for HAL compression markers...")
    print("=" * 60)
    
    # Search in known sprite areas
    search_areas = [
        (0x270000, 0x280000, "UI/Character area"),
        (0x280000, 0x290000, "Character sprite area"),
        (0x300000, 0x310000, "Enemy sprite area"),
    ]
    
    all_sprites = []
    
    for start, end, description in search_areas:
        print(f"\nSearching {description} (${start:06X}-${end:06X})...")
        markers = find_hal_markers(rom_path, start, end)
        
        print(f"Found {len(markers)} HAL markers")
        
        # Extract first few from each area
        for offset, marker, expected_size in markers[:10]:
            marker_name = {0xE3: 'E3', 0xE7: 'E7', 0xF3: 'F3', 0xF7: 'F7'}.get(marker, hex(marker))
            print(f"\n  ${offset:06X}: Marker {marker_name}, expected size ~{expected_size} bytes")
            
            size, success = extract_and_visualize(rom_path, offset, marker)
            
            if success:
                print(f"    Extracted: {size} bytes -> hal_{offset:06X}.png")
                all_sprites.append((offset, size, marker_name))
            else:
                print(f"    Failed to extract/visualize")
    
    print("\n" + "=" * 60)
    print(f"Successfully extracted {len(all_sprites)} sprites:")
    for offset, size, marker in all_sprites:
        print(f"  ${offset:06X} (marker {marker}): {size} bytes -> hal_{offset:06X}.png")
    
    print("\nCheck the PNG files for recognizable sprites!")

if __name__ == '__main__':
    main()