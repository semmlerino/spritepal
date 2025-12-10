#!/usr/bin/env python3
"""
Use SpritePal to extract the promising small sprites we found
"""

import sys
from pathlib import Path

# Add spritepal to path
sys.path.insert(0, str(Path(__file__).parent / 'spritepal'))

from core.rom_extractor import ROMExtractor
from core.hal_compression import HALCompressionError

def extract_focused_sprites():
    """Extract the most promising small sprites using SpritePal"""
    
    rom_path = "Kirby Super Star (USA).sfc"
    extractor = ROMExtractor()
    
    # Focus on the smallest sprites (likely enemies)
    test_offsets = [
        (0x27F280, "enemy_27F280"),  # 224 bytes, 24x24
        (0x27F000, "enemy_27F000"),  # 307 bytes, 24x24
        (0x27F200, "enemy_27F200"),  # 358 bytes, 24x32
        (0x27FF00, "enemy_27FF00"),  # 421 bytes, 32x32
        (0x27F780, "enemy_27F780"),  # 422 bytes, 32x32
        (0x27FC80, "enemy_27FC80"),  # 523 bytes, 32x32
        (0x27FB00, "enemy_27FB00"),  # 549 bytes, 32x40
        (0x27F700, "enemy_27F700"),  # 674 bytes, 40x40
        (0x27FC00, "enemy_27FC00"),  # 705 bytes, 40x40
    ]
    
    successful = []
    
    for offset, name in test_offsets:
        print(f"\nExtracting ${offset:06X} with SpritePal...")
        
        try:
            output_path, info = extractor.extract_sprite_from_rom(
                rom_path, 
                offset, 
                name + "_spritepal",
                sprite_name=""
            )
            
            tiles = info.get('tile_count', 0)
            size = info.get('extraction_size', 0)
            
            # Check if it could be a mushroom (small enemy sprite)
            if tiles <= 32:  # Small sprite
                print(f"  ✓ Success! {tiles} tiles, {size} bytes -> {output_path}")
                successful.append((offset, output_path, tiles))
            else:
                print(f"  Success but large: {tiles} tiles")
            
        except HALCompressionError as e:
            print(f"  HAL error: {e}")
        except Exception as e:
            print(f"  Error: {e}")
    
    print("\n" + "=" * 60)
    print(f"Extracted {len(successful)} small sprites:")
    for offset, path, tiles in successful:
        print(f"  ${offset:06X}: {tiles:2} tiles -> {path}")
    
    print("\nCheck these PNG files for the mushroom enemy!")

if __name__ == '__main__':
    extract_focused_sprites()