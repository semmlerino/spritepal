# Mushroom Enemy Sprite Search Summary

## Goal
Find the ROM offset of the mushroom enemy sprite (ID 06) in Kirby Super Star

## What We Know
1. **VRAM Location**: Mushroom appears at VRAM $6A00 in savestates
2. **Sprite ID**: Mushroom is sprite ID 06 (from wiki)
3. **Expected Size**: Small enemy, likely 4-8 tiles (128-256 bytes)
4. **Shape**: Cap on top, stem below (classic mushroom shape)

## What We've Found

### 1. Mushroom Placements (1675 total)
- **Highest concentration**: Region $0F0000 (296 mushrooms)
- **Dense sub-regions**: 
  - $0FE000: 95 mushrooms
  - $0FD000: 90 mushrooms  
  - $0FF000: 65 mushrooms

### 2. Compressed Data Near Placements
- Found many compressed blocks at $0EE7D4-$0F0000
- Extracted 10 small sprites from these areas
- Results: Mostly noise or partial data (alignment issues)

### 3. Enemy Area Sprites ($300000-$310000)
- Extracted 746 sprites from enemy area
- Small 4-tile sprites at:
  - $300380 (4 tiles)
  - $300E40 (4 tiles)
  - $301140 (4 tiles)
  - $300500 (6 tiles)
  - $301100 (4 tiles)

### 4. Successful Extractions
- Kirby sprites: $27D800, $280000 (confirmed working)
- UI elements: $27F700
- Background/stage: $27FD80
- Unused tiles: $1F14FF (verification successful)

## Challenges
1. **Palette Issue**: Sprites appear as noise without correct palette
2. **Compression Alignment**: Many extractions have byte alignment issues
3. **Offset Accuracy**: Compressed data boundaries are unclear

## Next Steps

### Option 1: Search Sprite Definition Tables
- Look for sprite ID 06 in sprite definition tables
- These tables often point to graphics offsets
- Search pattern: `?? 06 ?? ?? ?? ??` where first byte is behavior

### Option 2: Monitor VRAM During Gameplay
- Use Mesen2 to set breakpoint on VRAM $6A00 writes
- Trace back to ROM address that initiated the transfer
- More direct but requires active debugging

### Option 3: Analyze Sprite Loading Routines  
- Find the code that loads sprite ID 06
- This will contain the graphics offset lookup
- Search for `CMP #$06` or `LDA #$06` in ASM

### Option 4: Try Different Palettes
- Apply common enemy palettes to extracted sprites
- Mushroom might already be extracted but unrecognizable
- Focus on small sprites from enemy area

## Key Insights
- Mushroom graphics are likely separate from placement data
- Placement data tells WHERE mushrooms appear
- Graphics data contains the actual sprite image
- Need to find the lookup table connecting ID 06 to graphics offset

## Files Created
- `SPRITE_GALLERY_MASTER.html`: 782 extracted sprites
- `MUSHROOM_CANDIDATES.html`: 10 small sprites from placement areas
- `MUSHROOM_VISUALIZATION.html`: Visualization techniques applied
- `discovered_sprite_offsets.txt`: List of all found offsets

## Recommendation
The mushroom sprite graphics are likely:
1. In a sprite graphics table separate from placement data
2. Already extracted but unrecognizable due to palette
3. Possibly compressed differently than expected

Best approach: Search for sprite definition tables that map ID 06 to a graphics offset.