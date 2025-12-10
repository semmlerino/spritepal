#!/usr/bin/env python3
"""
Find the correct GFX table by searching for $8E:00FD pattern
"""

import struct

def find_correct_table():
    """Search for the correct table structure"""
    
    rom_path = "Kirby Super Star (USA).sfc"
    
    with open(rom_path, 'rb') as f:
        rom_data = f.read()
    
    print("Searching for correct GFX table structure")
    print("=" * 60)
    
    # The user says entry 0x03 should be $8E:00FD
    # In little-endian 3-byte format: FD 00 8E
    target_bytes = bytes([0xFD, 0x00, 0x8E])
    
    print(f"\nSearching for pattern: {' '.join(f'{b:02X}' for b in target_bytes)}")
    print("This should be entry 0x03 ($8E:00FD) in the GFX table\n")
    
    # Search around the expected area
    search_start = 0x0E0000
    search_end = 0x0E1000
    
    found_locations = []
    for i in range(search_start, min(search_end, len(rom_data) - 3)):
        if rom_data[i:i+3] == target_bytes:
            found_locations.append(i)
    
    if found_locations:
        print(f"Found {len(found_locations)} location(s) with pattern FD 00 8E:")
        for loc in found_locations:
            print(f"\n  Location: 0x{loc:06X}")
            
            # Check if this could be entry 0x03 in a table
            # Entry 0x03 would be at offset = table_base + (3 * 3)
            # So table_base = loc - 9
            potential_table_base = loc - 9
            
            if potential_table_base >= 0:
                print(f"  If this is entry 0x03, table base would be: 0x{potential_table_base:06X}")
                
                # Show the potential table structure
                print(f"  Potential table entries:")
                for j in range(8):
                    entry_offset = potential_table_base + (j * 3)
                    if entry_offset + 3 <= len(rom_data):
                        entry = rom_data[entry_offset:entry_offset+3]
                        bank = entry[2]
                        addr = entry[0] | (entry[1] << 8)
                        print(f"    Entry 0x{j:02X}: ${bank:02X}:{addr:04X} (bytes: {' '.join(f'{b:02X}' for b in entry)})")
                        if j == 3:
                            print(f"      ^^ Entry 0x03 - should be $8E:00FD")
    else:
        print("Pattern FD 00 8E not found in search range")
    
    # Also check what's actually at 0x0E0596
    print("\n" + "=" * 60)
    print("Checking what's actually at 0x0E0596 (expected GFX table):")
    
    offset = 0x0E0596
    print(f"\nData at 0x{offset:06X}:")
    for i in range(0, 64, 16):
        if offset + i + 16 <= len(rom_data):
            line = rom_data[offset + i:offset + i + 16]
            hex_str = ' '.join(f'{b:02X}' for b in line)
            print(f"  0x{offset + i:06X}: {hex_str}")
    
    # Try interpreting with different offsets
    print("\nTrying different interpretations:")
    
    # Maybe the table starts a few bytes before or after
    for adjust in [-6, -3, 0, 3, 6]:
        test_offset = offset + adjust
        print(f"\n  Offset 0x{test_offset:06X} (adjustment: {adjust:+d}):")
        for j in range(4):
            entry_offset = test_offset + (j * 3)
            if entry_offset + 3 <= len(rom_data):
                entry = rom_data[entry_offset:entry_offset+3]
                bank = entry[2]
                addr = entry[0] | (entry[1] << 8)
                print(f"    Entry 0x{j:02X}: ${bank:02X}:{addr:04X}")
    
    # Search for the exact pointer the user mentioned
    print("\n" + "=" * 60)
    print("Direct search for correct offset:")
    
    # The user says: "Convert: pc = (0x8E & 0x7F)*0x8000 + 0x00FD = 0x0E*0x8000 + 0x00FD = **0x0700FD**"
    # So the correct Cappy offset should be 0x0700FD
    
    correct_offset = 0x0700FD
    print(f"\nUser indicates Cappy should be at PC 0x{correct_offset:06X}")
    print(f"Data at 0x{correct_offset:06X}:")
    
    if correct_offset < len(rom_data):
        preview = rom_data[correct_offset:correct_offset+32]
        print(f"  {' '.join(f'{b:02X}' for b in preview[:16])}")
        print(f"  {' '.join(f'{b:02X}' for b in preview[16:32])}")
        
        first_byte = preview[0]
        print(f"\n  First byte: 0x{first_byte:02X}")
        if first_byte == 0x07:
            print("  ✓ This IS 0x07 - valid HAL compression as user indicated!")
            print("  This should be the correct Cappy location.")

if __name__ == '__main__':
    find_correct_table()