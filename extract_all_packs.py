#!/usr/bin/env python3
"""
Extract all 4 sprite packs that the first Green Greens room loads.
Implements HAL decompression algorithm directly.
"""

import struct
from PIL import Image
import numpy as np

def decompress_hal(rom_data, offset):
    """HAL decompression algorithm"""
    output = []
    pos = offset
    
    while pos < len(rom_data):
        cmd = rom_data[pos]
        pos += 1
        
        if cmd == 0xFF:
            # End of compressed data
            break
            
        # Get length from lower 5 bits
        length = (cmd & 0x1F) + 1
        
        # Get command type from upper 3 bits
        cmd_type = cmd >> 5
        
        # Handle extended length (bit 5 set)
        if cmd & 0x20:
            if pos >= len(rom_data):
                break
            extra_byte = rom_data[pos]
            pos += 1
            length = ((cmd & 0x03) << 8) | extra_byte
            length += 1
            cmd_type = (cmd >> 2) & 0x07
        
        # Execute command based on type
        if cmd_type == 0:  # Direct copy
            for _ in range(length):
                if pos < len(rom_data):
                    output.append(rom_data[pos])
                    pos += 1
                    
        elif cmd_type == 1:  # Byte fill (RLE)
            if pos < len(rom_data):
                fill_byte = rom_data[pos]
                pos += 1
                output.extend([fill_byte] * length)
                
        elif cmd_type == 2:  # Incremental sequence
            if pos < len(rom_data):
                start_byte = rom_data[pos]
                pos += 1
                for i in range(length):
                    output.append((start_byte + i) & 0xFF)
                    
        elif cmd_type == 3:  # Copy from buffer (16-bit offset)
            if pos + 1 < len(rom_data):
                copy_offset = struct.unpack('<H', rom_data[pos:pos+2])[0]
                pos += 2
                for _ in range(length):
                    if copy_offset < len(output):
                        output.append(output[copy_offset])
                        copy_offset += 1
                        
        elif cmd_type == 4:  # Copy from buffer with XOR
            if pos + 1 < len(rom_data):
                copy_offset = struct.unpack('<H', rom_data[pos:pos+2])[0]
                pos += 2
                for _ in range(length):
                    if copy_offset < len(output) and pos < len(rom_data):
                        output.append(output[copy_offset] ^ rom_data[pos])
                        copy_offset += 1
                        pos += 1
                        
        elif cmd_type == 5:  # Copy from buffer backwards
            if pos + 1 < len(rom_data):
                copy_offset = struct.unpack('<H', rom_data[pos:pos+2])[0]
                pos += 2
                for _ in range(length):
                    if copy_offset < len(output):
                        output.append(output[copy_offset])
                        copy_offset -= 1
                        
        elif cmd_type == 6:  # Unused in HAL
            break
            
        elif cmd_type == 7:  # Another form of direct copy
            for _ in range(length):
                if pos < len(rom_data):
                    output.append(rom_data[pos])
                    pos += 1
    
    return bytes(output)

def convert_4bpp_to_image(data, width_tiles=16):
    """Convert 4bpp SNES tile data to grayscale image"""
    bytes_per_tile = 32
    num_tiles = len(data) // bytes_per_tile
    
    if num_tiles == 0:
        return None
    
    # Calculate dimensions
    height_tiles = (num_tiles + width_tiles - 1) // width_tiles
    width = width_tiles * 8
    height = height_tiles * 8
    
    pixels = np.zeros((height, width), dtype=np.uint8)
    
    for tile_idx in range(num_tiles):
        tile_x = (tile_idx % width_tiles) * 8
        tile_y = (tile_idx // width_tiles) * 8
        tile_offset = tile_idx * bytes_per_tile
        
        if tile_offset + bytes_per_tile > len(data):
            break
            
        tile_data = data[tile_offset:tile_offset + bytes_per_tile]
        
        # Decode 4bpp tile
        for y in range(8):
            row_offset = y * 2
            if row_offset + 17 < len(tile_data):
                # Read bit planes
                plane0 = tile_data[row_offset]
                plane1 = tile_data[row_offset + 1]
                plane2 = tile_data[row_offset + 16]
                plane3 = tile_data[row_offset + 17]
                
                for x in range(8):
                    bit = 7 - x
                    pixel = ((plane0 >> bit) & 1) | \
                            (((plane1 >> bit) & 1) << 1) | \
                            (((plane2 >> bit) & 1) << 2) | \
                            (((plane3 >> bit) & 1) << 3)
                    
                    if tile_y + y < height and tile_x + x < width:
                        pixels[tile_y + y, tile_x + x] = pixel * 17
    
    return Image.fromarray(pixels, mode='L')

def main():
    """Extract all 4 packs"""
    
    rom_path = "Kirby Super Star (USA).sfc"
    with open(rom_path, 'rb') as f:
        rom_data = f.read()
    
    # All 4 packs used by first Green Greens room
    packs = [
        (0x03, 0x0700FD),   # Pack 03 - possibly UI/common
        (0x15, 0x358800),   # Pack 15 
        (0x4E, 0x38080A),   # Pack 4E
        (0x57, 0x007861),   # Pack 57 - appears to be empty (all FF)
    ]
    
    print("Extracting and decompressing all 4 sprite packs")
    print("=" * 60)
    
    for pack_id, pc_offset in packs:
        print(f"\nPack 0x{pack_id:02X} at PC 0x{pc_offset:06X}:")
        print("-" * 40)
        
        # Check first bytes
        preview = rom_data[pc_offset:pc_offset+16]
        print(f"  First bytes: {' '.join(f'{b:02X}' for b in preview)}")
        
        # Skip if all FF (empty)
        if all(b == 0xFF for b in preview):
            print("  Skipping - appears to be empty (all 0xFF)")
            continue
        
        # Decompress
        try:
            decompressed = decompress_hal(rom_data, pc_offset)
            print(f"  Decompressed: {len(decompressed)} bytes")
            
            if len(decompressed) >= 32:
                # Save decompressed data
                bin_path = f"pack_{pack_id:02X}_decompressed.bin"
                with open(bin_path, 'wb') as f:
                    f.write(decompressed)
                print(f"  Saved binary: {bin_path}")
                
                # Convert to images with different widths
                for width in [8, 16, 32]:
                    img = convert_4bpp_to_image(decompressed, width_tiles=width)
                    if img:
                        img_path = f"pack_{pack_id:02X}_w{width}.png"
                        img.save(img_path)
                        print(f"  Saved image: {img_path} ({img.size[0]}x{img.size[1]})")
            else:
                print(f"  Warning: Only {len(decompressed)} bytes decompressed")
                
        except Exception as e:
            print(f"  Error: {e}")
    
    print("\n" + "=" * 60)
    print("Done! Check the generated images to identify Cappy.")
    print("\nCappy should be a mushroom-shaped enemy sprite.")
    print("Look for a round cap with eyes underneath.")

if __name__ == '__main__':
    main()