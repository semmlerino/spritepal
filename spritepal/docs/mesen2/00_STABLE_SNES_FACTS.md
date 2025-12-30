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
- **OAM base (word address):** `oam_base_word = name_base << 13`
  - Each step is **0x2000 words = 16KB**.
- **OAM offset (word address):** `oam_offset_word = (name_select + 1) << 12`
  - Each step is **0x1000 words = 8KB**.
- OAM attribute bit 0 is **tile index bit 8 / second table select**, not a background name table.

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

## Sprite Size Modes (OBSEL Size Select)
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
- 15-bit BGR, little-endian:
  - bits 0-4: Red
  - bits 5-9: Green
  - bits 10-14: Blue
- Sprite palettes are CGRAM entries 128-255.
