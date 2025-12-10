#!/usr/bin/env python3
"""
Extract Cappy from the verified location PC 0x0700FD
Following the chain: PC 0x3F8002 → $9B:8596 → PC 0x0D8596 → entry #03 → $8E:00FD → PC 0x0700FD
"""

import struct
from PIL import Image
import numpy as np

def decompress_hal(rom_data, offset, max_size=0x10000):
    """Decompress HAL-compressed data from ROM"""
    output = []
    pos = offset
    
    while pos < len(rom_data) and len(output) < max_size:
        cmd = rom_data[pos]
        pos += 1
        
        if cmd == 0xFF:
            # End marker
            break
            
        length = (cmd & 0x1F) + 1
        
        if cmd & 0x20:  # Bit 5 set: extended length
            if pos >= len(rom_data):
                break
            length = ((cmd & 0x3) << 8) | rom_data[pos] + 1
            pos += 1
            cmd = (cmd >> 2) & 0x7
        else:
            cmd = cmd >> 5
            
        if cmd == 0:  # Uncompressed
            for _ in range(length):
                if pos < len(rom_data):
                    output.append(rom_data[pos])
                    pos += 1
        elif cmd == 1:  # RLE
            if pos < len(rom_data):
                value = rom_data[pos]
                pos += 1
                output.extend([value] * length)
        elif cmd == 2:  # Incremental sequence
            if pos < len(rom_data):
                value = rom_data[pos]
                pos += 1
                for _ in range(length):
                    output.append(value & 0xFF)
                    value += 1
        elif cmd == 3:  # Copy from back-buffer (2 bytes)
            if pos + 1 < len(rom_data):
                offset_val = struct.unpack('<H', rom_data[pos:pos+2])[0]
                pos += 2
                for _ in range(length):
                    if offset_val < len(output):
                        output.append(output[offset_val])
                        offset_val += 1
        elif cmd == 4:  # Copy from back-buffer with XOR
            if pos + 1 < len(rom_data):
                offset_val = struct.unpack('<H', rom_data[pos:pos+2])[0]
                pos += 2
                for _ in range(length):
                    if offset_val < len(output) and pos < len(rom_data):
                        output.append(output[offset_val] ^ rom_data[pos])
                        offset_val += 1
                        pos += 1
        elif cmd == 5:  # Copy from back-buffer backwards
            if pos + 1 < len(rom_data):
                offset_val = struct.unpack('<H', rom_data[pos:pos+2])[0]
                pos += 2
                for _ in range(length):
                    if offset_val < len(output):
                        output.append(output[offset_val])
                        offset_val -= 1
        elif cmd == 6:  # Unknown
            break
        elif cmd == 7:  # Direct copy
            for _ in range(length):
                if pos < len(rom_data):
                    output.append(rom_data[pos])
                    pos += 1
                    
    return bytes(output)

def convert_4bpp_to_image(data, width_tiles=16, height_tiles=None):
    """Convert 4bpp tile data to image"""
    bytes_per_tile = 32
    num_tiles = len(data) // bytes_per_tile
    
    if height_tiles is None:
        height_tiles = (num_tiles + width_tiles - 1) // width_tiles
    
    width = width_tiles * 8
    height = height_tiles * 8
    
    pixels = np.zeros((height, width), dtype=np.uint8)
    
    for tile_idx in range(min(num_tiles, width_tiles * height_tiles)):
        tile_x = (tile_idx % width_tiles) * 8
        tile_y = (tile_idx // width_tiles) * 8
        tile_offset = tile_idx * bytes_per_tile
        
        if tile_offset + bytes_per_tile > len(data):
            break
            
        tile_data = data[tile_offset:tile_offset + bytes_per_tile]
        
        for y in range(8):
            row_offset = y * 2
            if row_offset + 1 < len(tile_data):
                plane0 = tile_data[row_offset]
                plane1 = tile_data[row_offset + 1]
                plane2 = tile_data[row_offset + 16] if row_offset + 16 < len(tile_data) else 0
                plane3 = tile_data[row_offset + 17] if row_offset + 17 < len(tile_data) else 0
                
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
    """Extract Cappy from PC 0x0700FD"""
    
    rom_path = "Kirby Super Star (USA).sfc"
    cappy_offset = 0x0700FD  # Direct PC offset where Cappy graphics are
    
    print(f"Extracting Cappy from PC 0x{cappy_offset:06X}")
    print("=" * 60)
    
    with open(rom_path, 'rb') as f:
        rom_data = f.read()
    
    # Show what's at this offset
    print(f"\nData at 0x{cappy_offset:06X}:")
    preview = rom_data[cappy_offset:cappy_offset+32]
    print(f"  First 32 bytes: {' '.join(f'{b:02X}' for b in preview)}")
    
    first_byte = preview[0]
    print(f"\n  First byte: 0x{first_byte:02X}")
    if first_byte == 0x07:
        print("  ✓ This is 0x07 - valid HAL compression (copy next 8 bytes)")
    
    # Try to decompress
    print("\nAttempting HAL decompression...")
    try:
        decompressed = decompress_hal(rom_data, cappy_offset)
        print(f"  Decompressed {len(decompressed)} bytes")
        
        # Convert to image
        if len(decompressed) >= 32:
            img = convert_4bpp_to_image(decompressed)
            
            # Save the image
            output_path = "CAPPY_EXTRACTED_0700FD.png"
            img.save(output_path)
            print(f"\n✓ Saved Cappy sprite to: {output_path}")
            print(f"  Image size: {img.size}")
            
            # Also save with different tile arrangements
            for width in [8, 16, 32]:
                img2 = convert_4bpp_to_image(decompressed, width_tiles=width)
                img2.save(f"CAPPY_0700FD_w{width}.png")
                print(f"  Also saved with width={width} tiles")
        else:
            print(f"  Warning: Only {len(decompressed)} bytes decompressed (need at least 32)")
    except Exception as e:
        print(f"  Error during decompression: {e}")
    
    # Also try raw extraction (no decompression)
    print("\nAlso trying raw extraction (no decompression)...")
    raw_size = 0x800  # Extract 2KB of raw data
    raw_data = rom_data[cappy_offset:cappy_offset+raw_size]
    
    raw_img = convert_4bpp_to_image(raw_data)
    raw_img.save("CAPPY_RAW_0700FD.png")
    print(f"  Saved raw extraction to: CAPPY_RAW_0700FD.png")
    
    print("\nDone! Check the generated images to see if we found Cappy!")

if __name__ == '__main__':
    main()