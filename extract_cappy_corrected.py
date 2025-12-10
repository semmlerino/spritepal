#!/usr/bin/env python3
"""
Extract Cappy with CORRECTED LoROM conversion formula
"""

import sys
import os
sys.path.insert(0, '/mnt/c/CustomScripts/KirbyMax/workshop/exhal-master/spritepal')

from pathlib import Path
from core.rom_extractor import ROMExtractor
import struct

def lorom_to_pc(bank, addr):
    """Correct LoROM to PC conversion"""
    # Correct formula: pc = (bank & 0x7F) * 0x8000 + (addr & 0x7FFF)
    pc = (bank & 0x7F) * 0x8000 + (addr & 0x7FFF)
    return pc

def extract_cappy_correct():
    """Extract Cappy using corrected pointer math"""
    
    rom_path = "Kirby Super Star (USA).sfc"
    
    with open(rom_path, 'rb') as f:
        rom_data = f.read()
    
    # Check if ROM is headered
    rom_size = len(rom_data)
    print(f"ROM size: {rom_size} bytes (0x{rom_size:06X})")
    print(f"ROM size % 1024 = {rom_size % 1024}")
    if rom_size % 1024 == 0:
        print("ROM is unheadered (no +0x200 adjustment needed)")
        header_offset = 0
    else:
        print("ROM has copier header (+0x200 adjustment needed)")
        header_offset = 0x200
    
    print("\n" + "=" * 60)
    print("CORRECTED Cappy Extraction")
    print("=" * 60)
    
    # Step 1: Read pointer at PC $3F0002
    pointer_pc = 0x3F0002
    ptr_bytes = rom_data[pointer_pc:pointer_pc+3]
    ptr_bank = ptr_bytes[2]
    ptr_addr = ptr_bytes[0] | (ptr_bytes[1] << 8)
    
    print(f"\nStep 1: Pointer at PC 0x{pointer_pc:06X}")
    print(f"  Raw bytes: {' '.join(f'{b:02X}' for b in ptr_bytes)}")
    print(f"  SNES address: ${ptr_bank:02X}:{ptr_addr:04X}")
    
    # Step 2: Convert to PC using CORRECT formula
    gfx_table_pc = lorom_to_pc(ptr_bank, ptr_addr)
    print(f"\nStep 2: Convert to PC using correct LoROM formula")
    print(f"  pc = (0x{ptr_bank:02X} & 0x7F) * 0x8000 + (0x{ptr_addr:04X} & 0x7FFF)")
    print(f"  pc = 0x{(ptr_bank & 0x7F):02X} * 0x8000 + 0x{(ptr_addr & 0x7FFF):04X}")
    print(f"  pc = 0x{(ptr_bank & 0x7F) * 0x8000:05X} + 0x{(ptr_addr & 0x7FFF):04X}")
    print(f"  pc = 0x{gfx_table_pc:06X}")
    print(f"  GFX table at PC: 0x{gfx_table_pc:06X}")
    
    # Step 3: Read entry 0x03 from GFX table
    entry_index = 0x03
    entry_offset = gfx_table_pc + (entry_index * 3)
    
    entry_bytes = rom_data[entry_offset:entry_offset+3]
    entry_bank = entry_bytes[2]
    entry_addr = entry_bytes[0] | (entry_bytes[1] << 8)
    
    print(f"\nStep 3: Read entry 0x{entry_index:02X} from GFX table")
    print(f"  Entry offset: 0x{gfx_table_pc:06X} + (0x{entry_index:02X} * 3) = 0x{entry_offset:06X}")
    print(f"  Raw bytes: {' '.join(f'{b:02X}' for b in entry_bytes)}")
    print(f"  SNES address: ${entry_bank:02X}:{entry_addr:04X}")
    
    # Step 4: Convert to PC using CORRECT formula
    cappy_pc = lorom_to_pc(entry_bank, entry_addr)
    print(f"\nStep 4: Convert Cappy pointer to PC")
    print(f"  pc = (0x{entry_bank:02X} & 0x7F) * 0x8000 + (0x{entry_addr:04X} & 0x7FFF)")
    print(f"  pc = 0x{(entry_bank & 0x7F):02X} * 0x8000 + 0x{(entry_addr & 0x7FFF):04X}")
    print(f"  pc = 0x{(entry_bank & 0x7F) * 0x8000:05X} + 0x{(entry_addr & 0x7FFF):04X}")
    print(f"  pc = 0x{cappy_pc:06X}")
    
    # Apply header offset if needed
    cappy_pc_adjusted = cappy_pc + header_offset
    if header_offset:
        print(f"  Adjusted for header: 0x{cappy_pc_adjusted:06X}")
    
    # Step 5: Check what's at this location
    print(f"\nStep 5: Data at PC 0x{cappy_pc:06X}")
    preview = rom_data[cappy_pc:cappy_pc+32]
    print(f"  First 32 bytes: {' '.join(f'{b:02X}' for b in preview[:16])}")
    print(f"                  {' '.join(f'{b:02X}' for b in preview[16:32])}")
    
    first_byte = preview[0]
    print(f"\n  First byte: 0x{first_byte:02X}")
    if first_byte == 0x07:
        print("  This is VALID HAL compression!")
        print("  0x07 = binary 00000111 = 'output next 8 bytes uncompressed'")
        print("  (3 command bits: 000 = direct copy, 5 length bits: 00111 = 7+1 = 8 bytes)")
    
    # Step 6: Extract using SpritePal
    print(f"\nStep 6: Extracting Cappy sprite from PC 0x{cappy_pc:06X}...")
    
    extractor = ROMExtractor()
    try:
        output_path, info = extractor.extract_sprite_from_rom(
            rom_path, cappy_pc, "cappy_correct", sprite_name="Cappy"
        )
        
        if output_path and Path(output_path).exists():
            print(f"\n✓ SUCCESS! Extracted to: {output_path}")
            print(f"  Compressed size: {info.get('compressed_size', 'unknown')} bytes")
            print(f"  Tile count: {info.get('tile_count', 'unknown')} tiles")
            print(f"  Extraction size: {info.get('extraction_size', 'unknown')} bytes")
        else:
            print(f"✗ SpritePal extraction failed")
            
    except Exception as e:
        print(f"✗ Error: {e}")
    
    # Verify with direct exhal command
    print("\n" + "=" * 60)
    print("Verification: Direct exhal command")
    print(f"Command: exhal '{rom_path}' 0x{cappy_pc:X} cappy_exhal.bin")
    
    import subprocess
    exhal_path = "/mnt/c/CustomScripts/KirbyMax/workshop/exhal-master/spritepal/tools/exhal"
    result = subprocess.run(
        [exhal_path, rom_path, f"0x{cappy_pc:X}", "cappy_exhal.bin"],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0 and Path("cappy_exhal.bin").exists():
        size = Path("cappy_exhal.bin").stat().st_size
        print(f"✓ Direct exhal succeeded: {size} bytes decompressed")
        print(f"  Output: cappy_exhal.bin")
        
        # Convert to image
        with open("cappy_exhal.bin", 'rb') as f:
            tile_data = f.read()
        
        from PIL import Image
        import numpy as np
        
        num_tiles = len(tile_data) // 32
        cols = min(16, num_tiles)
        rows = (num_tiles + cols - 1) // cols
        
        img_width = cols * 8
        img_height = rows * 8
        pixels = np.zeros((img_height, img_width), dtype=np.uint8)
        
        for tile_idx in range(num_tiles):
            tile_start = tile_idx * 32
            if tile_start + 32 > len(tile_data):
                break
                
            tile = tile_data[tile_start:tile_start + 32]
            
            # Decode 4bpp tile
            for row in range(8):
                plane01_offset = row * 2
                plane23_offset = 16 + row * 2
                
                if plane23_offset + 1 < len(tile):
                    plane0 = tile[plane01_offset]
                    plane1 = tile[plane01_offset + 1]
                    plane2 = tile[plane23_offset]
                    plane3 = tile[plane23_offset + 1]
                    
                    for col in range(8):
                        bit = 7 - col
                        pixel = ((plane0 >> bit) & 1) | \
                                (((plane1 >> bit) & 1) << 1) | \
                                (((plane2 >> bit) & 1) << 2) | \
                                (((plane3 >> bit) & 1) << 3)
                        
                        # Place in grid
                        grid_row = tile_idx // cols
                        grid_col = tile_idx % cols
                        y = grid_row * 8 + row
                        x = grid_col * 8 + col
                        
                        if y < img_height and x < img_width:
                            pixels[y, x] = pixel * 17  # Scale to 0-255
        
        img = Image.fromarray(pixels, 'L')
        img.save("cappy_exhal.png")
        print(f"  Converted to: cappy_exhal.png ({img.width}x{img.height} pixels, {num_tiles} tiles)")
    else:
        print(f"✗ Direct exhal failed: {result.stderr}")
    
    print("\n" + "=" * 60)
    print("✓ COMPLETE!")
    print("Cappy (the 'mushroom' enemy) should now be correctly extracted.")
    print("It's sprite ID 06, part of GFX pack 0x03.")

if __name__ == '__main__':
    extract_cappy_correct()