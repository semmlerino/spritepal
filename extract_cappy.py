#!/usr/bin/env python3
"""
Extract Cappy (mushroom enemy) sprite using pointer chain from FurtherInfo.md
"""

import sys
import os
sys.path.insert(0, '/mnt/c/CustomScripts/KirbyMax/workshop/exhal-master/spritepal')

from pathlib import Path
from core.rom_extractor import ROMExtractor
import struct

def extract_cappy():
    """Extract Cappy sprite by following pointer chain"""
    
    rom_path = "Kirby Super Star (USA).sfc"
    
    with open(rom_path, 'rb') as f:
        rom_data = f.read()
    
    print("Following pointer chain to find Cappy (mushroom) sprite...")
    print("=" * 60)
    
    # Step 1: Read pointer at PC $3F0002
    pointer_addr = 0x3F0002
    f = open(rom_path, 'rb')
    f.seek(pointer_addr)
    
    # Read 24-bit pointer (little-endian)
    ptr_bytes = f.read(3)
    ptr_value = struct.unpack('<I', ptr_bytes + b'\x00')[0]  # Add 4th byte for unpacking
    
    # Extract bank and address
    ptr_bank = (ptr_value >> 16) & 0xFF
    ptr_addr = ptr_value & 0xFFFF
    
    print(f"Step 1: Pointer at PC ${pointer_addr:06X} = ${ptr_bank:02X}:{ptr_addr:04X}")
    
    # Convert SNES pointer to PC offset using LoROM formula
    # For banks $80-$FF: pc = ((bank - 0x80) * 0x8000) + (addr - 0x8000)
    # For banks $00-$7F: pc = (bank * 0x8000) + (addr & 0x7FFF)
    if ptr_bank >= 0x80:
        gfx_table_offset = ((ptr_bank - 0x80) * 0x8000) + (ptr_addr - 0x8000)
    else:
        gfx_table_offset = (ptr_bank * 0x8000) + (ptr_addr & 0x7FFF)
    
    print(f"Step 2: GFX table offset = PC ${gfx_table_offset:06X}")
    
    # Step 3: Read entry 0x03 from the GFX table (Cappy's pack)
    # Each entry is a 3-byte pointer
    entry_index = 0x03
    entry_offset = gfx_table_offset + (entry_index * 3)
    
    f.seek(entry_offset)
    cappy_ptr_bytes = f.read(3)
    cappy_ptr_value = struct.unpack('<I', cappy_ptr_bytes + b'\x00')[0]
    
    cappy_bank = (cappy_ptr_value >> 16) & 0xFF
    cappy_addr = cappy_ptr_value & 0xFFFF
    
    print(f"Step 3: Entry 0x03 at PC ${entry_offset:06X} = ${cappy_bank:02X}:{cappy_addr:04X}")
    
    # Convert to PC offset
    if cappy_bank >= 0x80:
        cappy_offset = ((cappy_bank - 0x80) * 0x8000) + (cappy_addr - 0x8000)
    else:
        cappy_offset = (cappy_bank * 0x8000) + (cappy_addr & 0x7FFF)
    
    print(f"Step 4: Cappy graphics offset = PC ${cappy_offset:06X}")
    
    # Verify what's at this offset
    f.seek(cappy_offset)
    header = f.read(16)
    print(f"\nData at ${cappy_offset:06X}: {' '.join(f'{b:02X}' for b in header)}")
    
    # Check if it looks like HAL compression
    if header[0] in [0x00, 0x01, 0x02, 0x03]:
        comp_type = header[0]
        size = header[1] | (header[2] << 8)
        print(f"Looks like HAL compression: type={comp_type}, size=${size:04X}")
    else:
        print(f"May not be HAL compressed (first byte: ${header[0]:02X})")
        # Try different HAL compression formats
        if header[0] == 0xE4:  # E4 compression
            print("Detected E4 compression format")
    
    f.close()
    
    # Step 5: Extract and decompress using SpritePal
    print(f"\nStep 5: Extracting Cappy sprite from ${cappy_offset:06X}...")
    
    extractor = ROMExtractor()
    
    try:
        output_path, info = extractor.extract_sprite_from_rom(
            rom_path, cappy_offset, "cappy_mushroom", sprite_name="Cappy"
        )
        
        if output_path and Path(output_path).exists():
            print(f"\n✓ SUCCESS! Extracted Cappy sprite: {output_path}")
            print(f"  Info: {info}")
        else:
            print(f"✗ SpritePal extraction failed")
            
    except Exception as e:
        print(f"✗ Error during extraction: {e}")
    
    # Also check the room's graphics header to confirm
    print("\n" + "=" * 60)
    print("Verification: Checking room graphics header...")
    
    room_gfx_header = 0x00302105
    f = open(rom_path, 'rb')
    f.seek(room_gfx_header)
    
    # Read backwards to find the sprite GFX pack IDs
    f.seek(room_gfx_header + 10)  # Skip to near the end
    data = f.read(10)
    
    # Look for the pattern ending in 4E 57 15 03
    for i in range(len(data) - 3):
        if data[i:i+4] == bytes([0x4E, 0x57, 0x15, 0x03]):
            print(f"Found sprite GFX packs at offset +{i}: {' '.join(f'{b:02X}' for b in data[i:i+4])}")
            print("  Pack A: 4E")
            print("  Pack B: 57")
            print("  Pack C: 15")
            print("  Pack D: 03 <- Cappy is in this pack!")
            break
    
    f.close()
    
    print("\n✓ Cappy extraction complete!")
    print("The 'mushroom' enemy is actually called Cappy (sprite ID 06)")
    print("It's part of sprite GFX pack 03 loaded by the first Green Greens room")

if __name__ == '__main__':
    extract_cappy()