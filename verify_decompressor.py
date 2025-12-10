#!/usr/bin/env python3
"""
Verify decompressor workflow with known compressed tiles at SNES address DF14FF
"""

import sys
import os
sys.path.insert(0, '/mnt/c/CustomScripts/KirbyMax/workshop/exhal-master/spritepal')

from pathlib import Path
from core.rom_extractor import ROMExtractor
from PIL import Image
import subprocess

def verify_decompressor():
    """Test decompression with known compressed tile block"""
    
    rom_path = "Kirby Super Star (USA).sfc"
    
    # SNES address DF14FF -> ROM offset
    # For HiROM banks $C0-$FF: ROM offset = (bank - $C0) * $10000 + (address & $FFFF)
    snes_bank = 0xDF
    snes_addr = 0x14FF
    rom_offset = (snes_bank - 0xC0) * 0x10000 + snes_addr
    
    print(f"Verifying decompressor workflow...")
    print(f"SNES address: ${snes_bank:02X}:{snes_addr:04X}")
    print(f"ROM offset: ${rom_offset:06X}")
    print("=" * 60)
    
    # Method 1: Use SpritePal's extractor
    print("\nMethod 1: SpritePal ROMExtractor")
    try:
        extractor = ROMExtractor()
        output_path, info = extractor.extract_sprite_from_rom(
            rom_path, rom_offset, "unused_tiles_test", sprite_name=""
        )
        
        if output_path and Path(output_path).exists():
            print(f"  ✓ Extracted with SpritePal: {output_path}")
            img = Image.open(output_path)
            print(f"  Image size: {img.width}x{img.height} pixels")
            print(f"  Tiles: {(img.width // 8) * (img.height // 8)} tiles")
        else:
            print(f"  ✗ SpritePal extraction failed")
    except Exception as e:
        print(f"  ✗ Error: {e}")
    
    # Method 2: Direct exhal command
    print("\nMethod 2: Direct exhal command")
    try:
        # Extract compressed data to temp file
        temp_compressed = "temp_compressed.bin"
        temp_decompressed = "temp_decompressed.bin"
        
        with open(rom_path, 'rb') as f:
            f.seek(rom_offset)
            # Read a chunk (we don't know exact compressed size)
            compressed_data = f.read(0x2000)  # Read 8KB chunk
        
        with open(temp_compressed, 'wb') as f:
            f.write(compressed_data)
        
        # Run exhal
        exhal_path = "/mnt/c/CustomScripts/KirbyMax/workshop/exhal-master/spritepal/tools/exhal"
        result = subprocess.run(
            [exhal_path, temp_compressed, temp_decompressed],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0 and Path(temp_decompressed).exists():
            decompressed_size = Path(temp_decompressed).stat().st_size
            print(f"  ✓ Decompressed {decompressed_size} bytes")
            
            # Convert to image
            with open(temp_decompressed, 'rb') as f:
                tile_data = f.read()
            
            # Convert 4bpp to image
            img = convert_4bpp_to_image(tile_data)
            img.save("unused_tiles_direct.png")
            print(f"  ✓ Saved as: unused_tiles_direct.png")
            print(f"  Image size: {img.width}x{img.height} pixels")
            print(f"  Tiles: {len(tile_data) // 32} tiles")
        else:
            print(f"  ✗ exhal failed: {result.stderr}")
        
        # Cleanup
        for temp_file in [temp_compressed, temp_decompressed]:
            if Path(temp_file).exists():
                os.remove(temp_file)
                
    except Exception as e:
        print(f"  ✗ Error: {e}")
    
    # Method 3: Check what's actually at this offset
    print("\nMethod 3: Raw data inspection")
    with open(rom_path, 'rb') as f:
        f.seek(rom_offset)
        header = f.read(16)
        
        print(f"  First 16 bytes at ${rom_offset:06X}:")
        print(f"  {' '.join(f'{b:02X}' for b in header)}")
        
        # Check if it looks like HAL compression
        if header[0] in [0x00, 0x01, 0x02, 0x03]:
            comp_type = header[0]
            size = header[1] | (header[2] << 8)
            print(f"  Looks like HAL compression: type={comp_type}, size=${size:04X}")
        else:
            print(f"  May not be HAL compressed data (first byte: ${header[0]:02X})")

def convert_4bpp_to_image(tile_data):
    """Convert 4bpp SNES tile data to image"""
    import numpy as np
    
    num_tiles = len(tile_data) // 32
    if num_tiles == 0:
        return Image.new('L', (8, 8), 0)
    
    # Arrange in grid
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
    
    return Image.fromarray(pixels, 'L')

if __name__ == '__main__':
    verify_decompressor()