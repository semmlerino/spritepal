#!/usr/bin/env python3
"""
Densely search the enemy sprite area $300000-$310000 for mushroom
"""

import sys
from pathlib import Path

# Add spritepal to path
sys.path.insert(0, str(Path(__file__).parent / 'spritepal'))

from core.rom_extractor import ROMExtractor
from core.hal_compression import HALCompressionError

def search_enemy_area():
    """Search enemy area with fine increments"""
    
    rom_path = "Kirby Super Star (USA).sfc"
    extractor = ROMExtractor()
    
    print("Searching enemy sprite area $300000-$310000...")
    print("Looking for small sprites (mushroom is likely 8-32 tiles)")
    print("=" * 60)
    
    found_sprites = []
    
    # Search every 0x40 bytes (64 bytes) for fine coverage
    for offset in range(0x300000, 0x310000, 0x40):
        if (offset - 0x300000) % 0x1000 == 0:
            print(f"Progress: ${offset:06X}...")
        
        try:
            # Try to extract sprite
            output_name = f"enemy_test_{offset:06X}"
            output_path, info = extractor.extract_sprite_from_rom(
                rom_path, 
                offset, 
                output_name,
                sprite_name=""
            )
            
            tiles = info.get('tile_count', 0)
            size = info.get('extraction_size', 0)
            
            # Look for small enemy sprites (mushroom likely 4-32 tiles)
            if 4 <= tiles <= 32:
                print(f"  Found small sprite at ${offset:06X}: {tiles} tiles, {size} bytes")
                found_sprites.append({
                    'offset': offset,
                    'tiles': tiles,
                    'size': size,
                    'path': output_path
                })
                
        except HALCompressionError:
            pass  # Normal - not all offsets have sprites
        except Exception:
            pass  # Skip other errors
    
    print("\n" + "=" * 60)
    print(f"Found {len(found_sprites)} small enemy sprites:")
    
    # Sort by tile count (mushroom likely small)
    found_sprites.sort(key=lambda x: x['tiles'])
    
    # Create HTML viewer
    with open('enemy_sprites_dense.html', 'w') as f:
        f.write("""<html>
<head><title>Enemy Sprites from $300000-$310000</title></head>
<body style="background: #333; color: white; font-family: monospace;">
<h1>Small Enemy Sprites (Mushroom Search)</h1>
<p>Looking for a mushroom enemy sprite (compare with MushroomSprite.png)</p>
<div style="display: flex; flex-wrap: wrap;">
""")
        
        for sprite in found_sprites[:30]:  # Show first 30
            f.write(f"""
<div style="margin: 10px; text-align: center; border: 2px solid #f90; padding: 10px; background: #111;">
    <img src="{sprite['path']}" style="image-rendering: pixelated; width: 128px; height: 128px; background: white; object-fit: contain;">
    <br><b>${sprite['offset']:06X}</b>
    <br>{sprite['tiles']} tiles
    <br>{sprite['size']} bytes
</div>
""")
            print(f"  ${sprite['offset']:06X}: {sprite['tiles']:2} tiles, {sprite['size']:4} bytes -> {sprite['path']}")
        
        f.write("""
</div>
</body>
</html>""")
    
    print(f"\nCreated enemy_sprites_dense.html - check for mushroom!")
    return found_sprites

if __name__ == '__main__':
    sprites = search_enemy_area()