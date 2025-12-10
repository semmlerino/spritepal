# Cappy Sprite Search Summary
## Kirby Super Star (USA) ROM - Mushroom Enemy (Sprite ID 06)

## Overview
Searching for Cappy (mushroom enemy) sprite graphics in Kirby Super Star ROM.
- **ROM**: Kirby Super Star (USA).sfc
- **CRC32**: 89D0F7DC (verified USA v1.0)
- **Target**: Cappy sprite (ID 06) - mushroom-shaped enemy with round cap and eyes
- **Room**: First Green Greens room loads sprite packs: 4E 57 15 03

## Pointer Chain Investigation

### Starting Point: GFX Table
- **Table Base**: PC 0x0D8596 (verified location)
- **Entry Format**: 3 bytes little-endian `<lo, hi, bank>`

### Pack Locations from GFX Table
1. **Pack 0x03**: Entry at 0x0D859F = `FD 00 8E` → $8E:00FD → PC 0x0700FD
2. **Pack 0x15**: Entry at 0x0D85D5 = `00 08 EB` → $EB:0800 → PC 0x358800
3. **Pack 0x4E**: Entry at 0x0D8680 = `0A 08 70` → $70:080A → PC 0x38080A
4. **Pack 0x57**: Entry at 0x0D869B = `61 78 00` → $00:7861 → PC 0x007861 (all FF - empty)

## Pack 0x03 Deep Dive (PC 0x0700FD)

### Discovery: Not Direct Graphics
- First bytes at 0x0700FD: `21 3D 21 1D 21 2D 21 3D...`
- **Finding**: This is NOT HAL-compressed graphics data
- **Actually**: This is a pointer table (16-bit offsets in bank $8E)

### Pointer Chain Traced
```
Level 1: GFX table entry #03 → PC 0x0700FD
Level 2: PC 0x0700FD contains pointer table:
  - Entry 0: 0x3D21 → PC 0x073D21
  - Entry 1: 0x1D21 → PC 0x071D21
  - Entry 2: 0x2D21 → PC 0x072D21
  - Entry 3: 0x3D21 → PC 0x073D21
  - Entry 4: 0x9D21 → PC 0x079D21
  - Entry 5: 0xAD21 → PC 0x07AD21
  - Entry 6: 0x8D21 → PC 0x078D21
  - Entry 7: 0x8D21 → PC 0x078D21

Level 3: PC 0x073D21 contains another pointer table:
  - Entry 0: 0x5841 → PC 0x075841
  - Entry 1: 0x6841 → PC 0x076841
  - Entry 2: 0x7841 → PC 0x077841
  - Entry 3: 0x7841 → PC 0x077841
  - Entry 4: 0x8841 → PC 0x078841
  - Entry 5: 0x9841 → PC 0x079841
  - Entry 6: 0xA841 → PC 0x07A841
  - Entry 7: 0xA841 → PC 0x07A841

Level 4: Following to actual data...
```

### Successful Decompressions from Pack 0x03 Chain
1. **PC 0x079841** (Entry 5):
   - Decompressed: 473 bytes (14 tiles)
   - Files: `test_entry5_079841.bin`, `CAPPY_CANDIDATE_test_entry5_079841_w*.png`
   - **Result**: Small graphics data, not Cappy

2. **PC 0x07A841** (Entry 6/7):
   - Decompressed: 13,521 bytes (422 tiles)
   - Files: `test_entry6_07A841.bin`, `CAPPY_CANDIDATE_test_entry6_07A841_w*.png`
   - **Result**: Large sprite sheet but appears to be UI/effects, not Cappy

## Direct Pack Decompressions

### Pack 0x15 (PC 0x358800)
- **Decompressed**: 11,830 bytes (369 tiles)
- **Compression Ratio**: 4.30:1
- **Files**: `pack_15_hal.bin`, `PACK_15_HAL_w*.png`
- **Result**: Various sprites visible but Cappy not clearly identified

### Pack 0x4E (PC 0x38080A)
- **Decompressed**: 18,087 bytes (565 tiles)
- **Compression Ratio**: 3.14:1
- **Files**: `pack_4E_hal.bin`, `PACK_4E_HAL_w*.png`
- **Result**: Large sprite sheet with recognizable shapes, but Cappy not definitively found

### Pack 0x57 (PC 0x007861)
- **Status**: Empty (all 0xFF bytes)
- **Result**: No data to decompress

## HAL Compression Notes
- Uses exhal tool from SpritePal successfully
- Command format verified: `0x21 = RLE command (repeat next byte twice)`
- Decompression working correctly for valid compressed data
- Some pointer destinations are not HAL-compressed (error: output >64KB)

## Current Status
**Cappy NOT definitively found yet** in any of the decompressed images.

## What We've Learned
1. Pack 0x03 at PC 0x0700FD is a multi-level pointer table, not direct graphics
2. Following the pointer chain leads to various graphics data
3. Packs 0x15 and 0x4E decompress successfully and contain sprite data
4. The sprite data appears to be UI elements, effects, and some character sprites
5. Cappy may be:
   - In a different part of the pointer chain we haven't explored
   - In one of the images but not easily recognizable without proper palette
   - Stored in a different format or location

## Next Steps to Try
1. **Explore other pointer chains**: Follow entries 1-7 from the Level 2 table at 0x0700FD
2. **Check all Level 3 entries**: We only checked entries 5 and 6/7 from 0x073D21
3. **Try other Level 2 entries**: 
   - PC 0x071D21 (entry 1)
   - PC 0x072D21 (entry 2)
   - PC 0x079D21 (entry 4)
   - PC 0x07AD21 (entry 5)
   - PC 0x078D21 (entry 6/7)
4. **Apply palettes**: The grayscale images might make Cappy hard to identify
5. **Cross-reference with sprite placement data**: We found 1,675 mushroom placements in ROM
6. **Check if pack 0x03 decompression is needed**: Try decompressing the pointer table itself

## Files Generated
- Images: `PACK_*_HAL_*.png`, `CAPPY_CANDIDATE_*.png`, `pack_*_w*.png`
- Binary: `pack_*_hal.bin`, `test_entry*_*.bin`, `pack_*_decompressed.bin`
- Scripts: `extract_all_packs.py`, `decompress_cappy_correct.py`, `extract_cappy_0700FD.py`

## Technical Details
- LoROM conversion formula: `pc = (bank & 0x7F) * 0x8000 + (addr & 0x7FFF)`
- SNES 4bpp format: 32 bytes per 8x8 tile
- HAL compression identified by commands, not magic bytes
- Multiple levels of indirection common in Kirby Super Star

---
*Generated: 2025-08-31*
*Search continues for the elusive Cappy sprite...*