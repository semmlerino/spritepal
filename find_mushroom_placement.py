#!/usr/bin/env python3
"""
Search ROM for mushroom enemy placement data (sprite ID 06)
According to wiki, sprite data format is:
[behavior, sprite_id, x_pos, screen, y_pos, v_screen]
"""

from pathlib import Path

def search_mushroom_placements():
    """Search for mushroom enemy placements in ROM"""
    
    rom_path = Path("Kirby Super Star (USA).sfc")
    
    with open(rom_path, 'rb') as f:
        rom_data = f.read()
    
    print("Searching for mushroom enemy placements (sprite ID 06)...")
    print("=" * 60)
    
    # Search for patterns where second byte is 06 (mushroom)
    # Common behavior bytes are 00, 10, 20, etc.
    mushroom_placements = []
    
    for i in range(0, len(rom_data) - 6):
        # Check if this could be sprite placement data
        behavior = rom_data[i]
        sprite_id = rom_data[i + 1]
        x_pos = rom_data[i + 2]
        screen = rom_data[i + 3]
        y_pos = rom_data[i + 4]
        v_screen = rom_data[i + 5]
        
        # Look for mushroom (sprite ID 06)
        if sprite_id == 0x06:
            # Validate other bytes look reasonable
            if behavior in [0x00, 0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70, 0x80, 0x90, 0xA0]:
                if screen < 0x10 and v_screen < 0x10:  # Reasonable screen numbers
                    if x_pos < 0xFF and y_pos < 0xFF:  # Valid positions
                        mushroom_placements.append({
                            'offset': i,
                            'behavior': behavior,
                            'x_pos': x_pos,
                            'screen': screen,
                            'y_pos': y_pos,
                            'v_screen': v_screen
                        })
    
    print(f"Found {len(mushroom_placements)} potential mushroom placements:")
    
    for placement in mushroom_placements[:20]:  # Show first 20
        print(f"  ${placement['offset']:06X}: {placement['behavior']:02X} 06 {placement['x_pos']:02X} {placement['screen']:02X} {placement['y_pos']:02X} {placement['v_screen']:02X}")
        print(f"          Behavior: ${placement['behavior']:02X}, Position: ({placement['x_pos']}, {placement['y_pos']}), Screen: ({placement['screen']}, {placement['v_screen']})")
    
    # Look for graphics loading patterns near these placements
    print("\n" + "=" * 60)
    print("Checking for sprite graphics headers near mushroom placements...")
    
    # According to wiki, graphics headers have pattern like "4E 57 15 03" for sprite GFX
    for placement in mushroom_placements[:5]:
        offset = placement['offset']
        
        # Search backwards for graphics header (usually within 0x200 bytes)
        for back in range(0x10, 0x200, 0x10):
            if offset - back >= 0:
                # Look for repeating values (like "6A 6A" in the example)
                check_offset = offset - back
                if check_offset + 4 < len(rom_data):
                    if rom_data[check_offset] == rom_data[check_offset + 1]:
                        print(f"\n  Potential graphics header at ${check_offset:06X} (near mushroom at ${offset:06X}):")
                        print(f"    {' '.join(f'{rom_data[check_offset + j]:02X}' for j in range(16))}")
                        break

if __name__ == '__main__':
    search_mushroom_placements()