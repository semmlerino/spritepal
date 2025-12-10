#!/usr/bin/env python3
"""
Examine the alternative GFX table location
"""

import sys
import os
sys.path.insert(0, '/mnt/c/CustomScripts/KirbyMax/workshop/exhal-master/spritepal')

from pathlib import Path
from core.rom_extractor import ROMExtractor
import struct

def examine_alt_table():
    """Examine alternative table location at PC $1C8596"""
    
    rom_path = "Kirby Super Star (USA).sfc"
    
    with open(rom_path, 'rb') as f:
        rom_data = f.read()
    
    print("Examining alternative GFX table location")
    print("=" * 60)
    
    # Try the alternative offset from Method 1 alt: PC $1C8596  
    alt_offset = 0x1C8596
    
    print(f"\nExamining PC ${alt_offset:06X}:")
    print("First 128 bytes:")
    
    for i in range(0, 128, 16):
        if alt_offset + i + 16 <= len(rom_data):
            line = rom_data[alt_offset + i:alt_offset + i + 16]
            hex_str = ' '.join(f'{b:02X}' for b in line)
            print(f"  ${alt_offset + i:06X}: {hex_str}")
    
    print("\nInterpreting as table of 3-byte pointers:")
    for i in range(16):  # First 16 entries
        offset = alt_offset + (i * 3)
        if offset + 3 <= len(rom_data):
            entry = rom_data[offset:offset+3]
            entry_bank = entry[2]
            entry_addr = entry[0] | (entry[1] << 8)
            print(f"  Entry ${i:02X}: ${entry_bank:02X}:{entry_addr:04X} (bytes: {' '.join(f'{b:02X}' for b in entry)})")
            
            # Show if this is entry 0x03
            if i == 0x03:
                print(f"    ^^ This is entry 0x03 (Cappy's pack)")
                
                # Convert to PC offset
                # Standard LoROM conversion
                if entry_bank >= 0xC0:
                    # Fast ROM area
                    pc = ((entry_bank - 0xC0) * 0x10000) + (entry_addr & 0xFFFF)
                elif entry_bank >= 0x80:
                    # Normal high banks
                    if entry_addr >= 0x8000:
                        pc = ((entry_bank - 0x80) * 0x10000) + (entry_addr - 0x8000)
                    else:
                        pc = ((entry_bank & 0x7F) * 0x10000) + (entry_addr | 0x8000)
                else:
                    # Low banks
                    pc = (entry_bank * 0x10000) + (entry_addr | 0x8000)
                
                print(f"    Converted to PC: ${pc:06X}")
                
                # Check what's there
                if pc < len(rom_data):
                    preview = rom_data[pc:pc+32]
                    print(f"    Data at ${pc:06X}: {' '.join(f'{b:02X}' for b in preview[:16])}")
                    print(f"                      {' '.join(f'{b:02X}' for b in preview[16:32])}")
                    
                    # Try extracting from this location
                    print(f"\n    Attempting extraction from ${pc:06X}...")
                    
                    extractor = ROMExtractor()
                    try:
                        output_path, info = extractor.extract_sprite_from_rom(
                            rom_path, pc, "cappy_alt", sprite_name="Cappy_Alt"
                        )
                        
                        if output_path and Path(output_path).exists():
                            print(f"    ✓ Extracted: {output_path}")
                            print(f"    Tile count: {info.get('tile_count', 'unknown')}")
                        else:
                            print(f"    ✗ Extraction failed")
                    except Exception as e:
                        print(f"    ✗ Error: {e}")

if __name__ == '__main__':
    examine_alt_table()