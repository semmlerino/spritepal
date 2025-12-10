#!/usr/bin/env python3
"""
Properly decompress Cappy using correct HAL algorithm.
The user confirmed the data at 0x0700FD is HAL-compressed.
"""

import struct
from PIL import Image
import numpy as np

def decompress_hal_correct(rom_data, offset):
    """
    Correct HAL decompression based on the algorithm.
    HAL compression format:
    - Command byte: [CCC][E][LLLLL]
      - CCC = command type (3 bits)
      - E = extended length flag (1 bit)  
      - LLLLL = length - 1 (5 bits)
    """
    output = []
    pos = offset
    
    while pos < len(rom_data):
        cmd = rom_data[pos]
        pos += 1
        
        if cmd == 0xFF:
            # End marker
            break
        
        # Parse command byte
        if cmd & 0x20:  # Extended length mode (bit 5 set)
            # Extended: command is in bits 2-4, length spans two bytes
            if pos >= len(rom_data):
                break
            extra = rom_data[pos]
            pos += 1
            
            cmd_type = (cmd >> 2) & 0x07
            length = ((cmd & 0x03) << 8) | extra
            length += 1
        else:
            # Normal: command is in bits 5-7, length in bits 0-4
            cmd_type = (cmd >> 5) & 0x07
            length = (cmd & 0x1F) + 1
        
        # Execute command
        if cmd_type == 0:  # Direct copy
            for _ in range(length):
                if pos < len(rom_data):
                    output.append(rom_data[pos])
                    pos += 1
                else:
                    break
                    
        elif cmd_type == 1:  # RLE (byte fill)
            if pos < len(rom_data):
                fill_byte = rom_data[pos]
                pos += 1
                for _ in range(length):
                    output.append(fill_byte)
                    
        elif cmd_type == 2:  # Incremental fill
            if pos < len(rom_data):
                start_val = rom_data[pos]
                pos += 1
                for i in range(length):
                    output.append((start_val + i) & 0xFF)
                    
        elif cmd_type == 3:  # Copy from buffer (LZ77-style)
            if pos + 1 < len(rom_data):
                # 16-bit offset into decompressed buffer
                offset_val = rom_data[pos] | (rom_data[pos + 1] << 8)
                pos += 2
                
                for _ in range(length):
                    if offset_val < len(output):
                        output.append(output[offset_val])
                        offset_val += 1
                        
        elif cmd_type == 4:  # XOR copy from buffer
            if pos + 1 < len(rom_data):
                offset_val = rom_data[pos] | (rom_data[pos + 1] << 8)
                pos += 2
                
                for _ in range(length):
                    if offset_val < len(output) and pos < len(rom_data):
                        output.append(output[offset_val] ^ rom_data[pos])
                        offset_val += 1
                        pos += 1
                        
        elif cmd_type == 5:  # Reverse copy from buffer
            if pos + 1 < len(rom_data):
                offset_val = rom_data[pos] | (rom_data[pos + 1] << 8)
                pos += 2
                
                for _ in range(length):
                    if offset_val < len(output):
                        output.append(output[offset_val])
                        offset_val -= 1
                        
        else:
            # Unknown command type
            print(f"Unknown HAL command type {cmd_type} at offset 0x{pos-1:06X}")
            break
    
    return bytes(output)

def convert_4bpp_to_image(data, width_tiles=16):
    """Convert 4bpp SNES tile data to image"""
    bytes_per_tile = 32
    num_tiles = len(data) // bytes_per_tile
    
    if num_tiles == 0:
        return None
    
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
        
        # SNES 4bpp format
        for y in range(8):
            # Bitplanes are interleaved: plane0,plane1 for 8 rows, then plane2,plane3
            plane0 = tile_data[y * 2] if y * 2 < len(tile_data) else 0
            plane1 = tile_data[y * 2 + 1] if y * 2 + 1 < len(tile_data) else 0
            plane2 = tile_data[16 + y * 2] if 16 + y * 2 < len(tile_data) else 0
            plane3 = tile_data[16 + y * 2 + 1] if 16 + y * 2 + 1 < len(tile_data) else 0
            
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
    """Extract Cappy properly"""
    
    rom_path = "Kirby Super Star (USA).sfc"
    with open(rom_path, 'rb') as f:
        rom_data = f.read()
    
    # Entry #03 from GFX table points to PC 0x0700FD
    cappy_offset = 0x0700FD
    
    print(f"Decompressing Cappy from PC 0x{cappy_offset:06X}")
    print("=" * 60)
    
    # Show compressed data
    compressed = rom_data[cappy_offset:cappy_offset+32]
    print(f"Compressed data (first 32 bytes):")
    print(f"  {' '.join(f'{b:02X}' for b in compressed[:16])}")
    print(f"  {' '.join(f'{b:02X}' for b in compressed[16:32])}")
    
    # Parse first command byte
    first_cmd = compressed[0]
    print(f"\nFirst command byte: 0x{first_cmd:02X} (binary: {first_cmd:08b})")
    
    if first_cmd & 0x20:
        cmd_type = (first_cmd >> 2) & 0x07
        print(f"  Extended mode - command type: {cmd_type}")
    else:
        cmd_type = (first_cmd >> 5) & 0x07
        length = (first_cmd & 0x1F) + 1
        print(f"  Normal mode - command type: {cmd_type}, length: {length}")
    
    # Decompress
    print("\nDecompressing...")
    decompressed = decompress_hal_correct(rom_data, cappy_offset)
    print(f"  Decompressed {len(decompressed)} bytes")
    print(f"  Number of complete tiles: {len(decompressed) // 32}")
    
    if len(decompressed) > 0:
        # Show decompressed data
        print(f"\nDecompressed data (first 64 bytes):")
        for i in range(0, min(64, len(decompressed)), 16):
            line = decompressed[i:i+16]
            print(f"  {' '.join(f'{b:02X}' for b in line)}")
        
        # Save binary
        with open("cappy_decompressed_correct.bin", "wb") as f:
            f.write(decompressed)
        print(f"\nSaved decompressed data to: cappy_decompressed_correct.bin")
        
        # Generate images with different widths
        for width in [8, 16, 32]:
            img = convert_4bpp_to_image(decompressed, width_tiles=width)
            if img:
                img_path = f"cappy_correct_w{width}.png"
                img.save(img_path)
                print(f"Saved image: {img_path} ({img.size[0]}x{img.size[1]})")
    else:
        print("Warning: Decompression produced no data!")
    
    print("\n" + "=" * 60)
    print("Check the images - Cappy should be a mushroom enemy sprite!")

if __name__ == '__main__':
    main()