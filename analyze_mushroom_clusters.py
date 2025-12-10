#!/usr/bin/env python3
"""
Analyze mushroom placement clusters to identify high-concentration areas
"""

from pathlib import Path
from collections import defaultdict

def analyze_mushroom_clusters():
    """Analyze where mushroom placements cluster in ROM"""
    
    rom_path = Path("Kirby Super Star (USA).sfc")
    
    with open(rom_path, 'rb') as f:
        rom_data = f.read()
    
    # Find all mushroom placements
    mushroom_offsets = []
    
    for i in range(0, len(rom_data) - 6):
        behavior = rom_data[i]
        sprite_id = rom_data[i + 1]
        x_pos = rom_data[i + 2]
        screen = rom_data[i + 3]
        y_pos = rom_data[i + 4]
        v_screen = rom_data[i + 5]
        
        if sprite_id == 0x06:
            if behavior in [0x00, 0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70, 0x80, 0x90, 0xA0]:
                if screen < 0x10 and v_screen < 0x10:
                    if x_pos < 0xFF and y_pos < 0xFF:
                        mushroom_offsets.append(i)
    
    # Cluster analysis - group by 0x10000 regions
    clusters = defaultdict(list)
    for offset in mushroom_offsets:
        region = (offset // 0x10000) * 0x10000
        clusters[region].append(offset)
    
    # Sort by number of mushrooms
    sorted_clusters = sorted(clusters.items(), key=lambda x: len(x[1]), reverse=True)
    
    print(f"Found {len(mushroom_offsets)} mushroom placements")
    print("\nMushroom clusters by ROM region:")
    print("=" * 60)
    
    for region, offsets in sorted_clusters:
        if len(offsets) > 10:  # Only show significant clusters
            print(f"\nRegion ${region:06X}-${region+0xFFFF:06X}: {len(offsets)} mushrooms")
            print(f"  First: ${min(offsets):06X}")
            print(f"  Last:  ${max(offsets):06X}")
            print(f"  Range: ${max(offsets)-min(offsets):04X} bytes")
            
            # More detailed sub-clustering within region
            subclusters = defaultdict(list)
            for offset in offsets:
                subregion = (offset // 0x1000) * 0x1000
                subclusters[subregion].append(offset)
            
            # Show dense sub-regions
            dense_subs = [(sr, offs) for sr, offs in subclusters.items() if len(offs) >= 3]
            if dense_subs:
                print("  Dense sub-regions:")
                for subregion, suboffs in sorted(dense_subs, key=lambda x: len(x[1]), reverse=True)[:5]:
                    print(f"    ${subregion:06X}: {len(suboffs)} mushrooms")

    # Now look for graphics data near the densest clusters
    print("\n" + "=" * 60)
    print("Searching for sprite graphics near dense mushroom clusters...")
    
    # Focus on the densest regions
    for region, offsets in sorted_clusters[:3]:
        if len(offsets) > 10:
            print(f"\nSearching near region ${region:06X} ({len(offsets)} mushrooms)...")
            
            # Look before the first mushroom in this region
            first_mushroom = min(offsets)
            search_start = max(0, first_mushroom - 0x2000)
            search_end = first_mushroom
            
            # Look for HAL compression headers (common patterns)
            for i in range(search_start, search_end - 4):
                # HAL compression often starts with specific patterns
                if rom_data[i] in [0x00, 0x01, 0x02, 0x03]:  # Compression type
                    if rom_data[i+1] != 0x00 or rom_data[i+2] != 0x00:  # Non-zero size
                        # Could be compressed data
                        size = rom_data[i+1] | (rom_data[i+2] << 8)
                        if 0x100 <= size <= 0x2000:  # Reasonable sprite size
                            print(f"  Potential compressed sprite at ${i:06X}: type={rom_data[i]:02X}, size=${size:04X}")
                            
                            # Check if followed by more compressed data (sprite set)
                            next_offset = i + 3 + size
                            if next_offset < len(rom_data) - 3:
                                if rom_data[next_offset] in [0x00, 0x01, 0x02, 0x03]:
                                    print(f"    -> Likely part of sprite set (next header at ${next_offset:06X})")

if __name__ == '__main__':
    analyze_mushroom_clusters()