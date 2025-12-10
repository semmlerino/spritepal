#!/usr/bin/env python3
"""
Use SpritePal's own extraction code to extract sprites properly
"""

import sys
from pathlib import Path

# Add spritepal to path
sys.path.insert(0, str(Path(__file__).parent / 'spritepal'))

from core.rom_extractor import ROMExtractor
from core.hal_compression import HALCompressionError

def extract_sprites_with_spritepal():
    """Use SpritePal's ROMExtractor to extract sprites"""
    
    rom_path = "Kirby Super Star (USA).sfc"
    extractor = ROMExtractor()
    
    # Test offsets - let's try the ones we found earlier
    test_offsets = [
        (0x27D800, "sprite_27D800_spritepal"),  # The promising one
        (0x280000, "sprite_280000_spritepal"),  # Character sprite area
        (0x302238, "enemy_302238_spritepal"),   # Enemy sprite
        (0x3033C4, "mushroom_3033C4_spritepal"), # Potential mushroom
        # Try some of the HAL marker positions
        (0x270176, "hal_270176_spritepal"),
        (0x301458, "enemy_301458_spritepal"),
    ]
    
    successful = []
    
    for offset, name in test_offsets:
        print(f"\nExtracting sprite at ${offset:06X} using SpritePal...")
        
        try:
            output_path, info = extractor.extract_sprite_from_rom(
                rom_path, 
                offset, 
                name,
                sprite_name=""
            )
            
            print(f"  Success! Output: {output_path}")
            print(f"  Info: {info}")
            successful.append((offset, output_path))
            
        except HALCompressionError as e:
            print(f"  HAL compression error: {e}")
        except Exception as e:
            print(f"  Error: {e}")
    
    print("\n" + "=" * 60)
    print(f"Successfully extracted {len(successful)} sprites:")
    for offset, path in successful:
        print(f"  ${offset:06X} -> {path}")
    
    print("\nCheck the PNG files to see if they're recognizable sprites!")

if __name__ == '__main__':
    extract_sprites_with_spritepal()