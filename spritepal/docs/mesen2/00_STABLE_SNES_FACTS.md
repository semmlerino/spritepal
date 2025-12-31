# 00 Stable SNES Facts

This document contains stable, externally verifiable SNES hardware facts. It deliberately
avoids emulator- or tool-specific behavior.

## VRAM Addressing (PPU)
- VRAM addresses set via $2116/$2117 are **word addresses** (16-bit words).
- Convert word to byte address with `byte = word * 2`.
- Any byte addressing you see in a tool/API is an abstraction on top of word-based VRAM.

## OBJSEL ($2101) Tile Tables
- `name_base = obsel & 0x07` (bits 0-2)
- `name_select = (obsel >> 3) & 0x03` (bits 3-4)
- `size_select = (obsel >> 5) & 0x07` (bits 5-7) — selects small/large sprite dimensions
- **OAM base (word address):** `oam_base_word = name_base << 13`
  - Each step advances by **0x2000 word addresses** (spanning **16KB** of byte-addressable VRAM).
- **OAM offset (word address):** `oam_offset_word = (name_select + 1) << 12`
  - Each step advances by **0x1000 word addresses** (spanning **8KB** of byte-addressable VRAM).
- OAM attribute bit 0 is **tile index bit 8 / second table select**, not a background name table.
- Bit 2 of `name_base` is reserved for a never-implemented VRAM expansion; in practice it
  should be 0. Warn if it is set.

## OAM Tile Address (Hardware Formula)
```
local use_second_table = (oam_attr & 0x01) ~= 0
local tile_index = oam_tile  -- 0-255

local tile_word = (oam_base_word + (tile_index << 4)
    + (use_second_table and oam_offset_word or 0)) & 0x7FFF
local vram_byte = tile_word << 1
```

## Tile Formats
- 8x8 tile @ 2bpp = **16 bytes**
- 8x8 tile @ 4bpp = **32 bytes**
- 8x8 tile @ 8bpp = **64 bytes**

SNES **sprites (OBJ)** are **always 4bpp** (32 bytes per 8x8 tile). Other bpp modes apply to
backgrounds, not sprites.

## OAM Structure
- Low table: 512 bytes (128 entries x 4 bytes)
  - Byte 0: X position (low 8 bits)
  - Byte 1: Y position
  - Byte 2: Tile index (low 8 bits)
  - Byte 3: Attributes (palette, priority, flips, tile index bit 8)
- High table: 32 bytes (2 bits per sprite)
  - Bit 0: X position bit 9
  - Bit 1: Size select (small/large)
  - Attribute bit 0 is the **tile high bit** (selects the second OBJ tile table).

### OAM High Table Extraction (Worked Example)
The high table packs 4 sprites' worth of data into each byte (2 bits per sprite).

```lua
-- Extract high-table bits for sprite index `sprite_idx` (0-127)
function get_oam_high_bits(oam_ram, sprite_idx)
    local high_table_offset = 0x200  -- high table starts at byte 512
    local byte_index = sprite_idx >> 2  -- which byte (0-31)
    local bit_shift = (sprite_idx & 0x03) * 2  -- which 2-bit pair (0, 2, 4, 6)

    local high_byte = oam_ram[high_table_offset + byte_index]
    local two_bits = (high_byte >> bit_shift) & 0x03

    local x_bit9 = (two_bits & 0x01)  -- bit 0: X position high bit
    local size_bit = (two_bits >> 1) & 0x01  -- bit 1: large/small select

    return x_bit9, size_bit
end

-- Example: Sprite 5 is at low-table offset 20 (5 * 4)
-- High-table byte = 5 >> 2 = 1 (byte offset 0x201)
-- Bit shift = (5 & 3) * 2 = 1 * 2 = 2
-- If oam_ram[0x201] = 0b11011001:
--   Sprite 4: bits 0-1 = 01 → x_bit9=1, size=0
--   Sprite 5: bits 2-3 = 10 → x_bit9=0, size=1 (large sprite)
--   Sprite 6: bits 4-5 = 10 → x_bit9=0, size=1
--   Sprite 7: bits 6-7 = 11 → x_bit9=1, size=1
```

**Signed X Position Reconstruction:**
```lua
local x_low = oam_ram[sprite_idx * 4]  -- byte 0: bits 0-7
local x_bit9, size_bit = get_oam_high_bits(oam_ram, sprite_idx)

-- Reconstruct signed 9-bit X (-256 to +255)
local x_full = x_low | (x_bit9 << 8)
if x_full >= 256 then
    x_full = x_full - 512  -- sign-extend: 256-511 → -256 to -1
end
```

## Sprite Size Modes (OBJSEL bits 5-7)
The `size_select` field from OBJSEL determines available sprite sizes. Each sprite's high-table
size bit selects between "small" and "large" for that sprite.

| size_select | Small | Large |
|-------------|-------|-------|
| 0 | 8x8 | 16x16 |
| 1 | 8x8 | 32x32 |
| 2 | 8x8 | 64x64 |
| 3 | 16x16 | 32x32 |
| 4 | 16x16 | 64x64 |
| 5 | 32x32 | 64x64 |
| 6 | 16x32 | 32x64 |
| 7 | 16x32 | 32x32 |

## Subtile Ordering (Large Sprites)
OAM specifies the **top-left tile**. Subtiles wrap in a 16x16 tile grid:
```
local tile_row = (tile_index >> 4) & 0x0F
local tile_col = tile_index & 0x0F

for ty = 0, tiles_h - 1 do
    local row = (tile_row + ty) & 0x0F
    for tx = 0, tiles_w - 1 do
        local col = (tile_col + tx) & 0x0F
        local subtile_index = (row << 4) | col
        -- use subtile_index with the OAM tile address formula above
    end
end
```

## CGRAM Format (Palettes)
- 15-bit BGR (often called **BGR555**), little-endian:
  - bits 0-4: Red
  - bits 5-9: Green
  - bits 10-14: Blue
- Sprite palettes are CGRAM entries 128-255.
