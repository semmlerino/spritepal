# 00 Stable SNES Facts

This document contains stable, externally verifiable SNES hardware facts. It deliberately
avoids emulator- or tool-specific behavior.

## VRAM Addressing (PPU)
- VRAM addresses set via $2116/$2117 are **word addresses** (16-bit words).
- Convert word to byte address with `byte = word * 2`.
- Any byte addressing you see in a tool/API is an abstraction on top of word-based VRAM.

**Hardware vs API Translation:**
```
PPU hardware:  word-addressed, $0000-$7FFF (32K words = 64KB)
Lua API:       byte-addressed, $0000-$FFFF (64K bytes)

Conversion:    lua_byte_addr = ppu_word_addr * 2
               ppu_word_addr = lua_byte_addr // 2
```
See `01_BUILD_SPECIFIC_CONTRACT.md` § "VRAM Read Semantics" for API-specific behavior.

### VMAIN Register ($2115) - Address Control

The VMAIN register controls VRAM address increment and translation behavior:

```
Bit:    7      6  5  4   3  2   1  0
        I      -  -  -   T  T   S  S
        │                └─┬─┘  └─┬─┘
        │                  │      └─ Step: 00=1, 01=32, 10=128
        │                  └──────── Translation mode (address remapping)
        └─────────────────────────── Increment after: 0=$2118, 1=$2119
```

**Increment Step (bits 1-0):**
| Value | Step | Use Case |
|-------|------|----------|
| 00 | 1 word | Sequential tile data |
| 01 | 32 words | 8x8 tile column writes |
| 10 | 128 words | 32-column tilemap writes |
| 11 | 128 words | Same as 10 |

**Address Translation / Remapping (bits 3-2):**

These modes rearrange address bits for optimized tilemap writes. The translation
applies to the logical address before accessing physical VRAM.

Reference: https://snes.nesdev.org/wiki/PPU_registers#VMAIN

```
Mode 00 (No remapping):
  Address bits unchanged.
  Input:  fedcba9876543210
  Output: fedcba9876543210

Mode 01 (8-bit rotation):
  Bits 8:6 moved to bits 2:0
  Input:  rrrrrrrrBBBccccc  (r=remaining, B=bits 8-6, c=bits 5-0)
  Output: rrrrrrrrcccccBBB

Mode 10 (9-bit rotation):
  Bits 9:7 moved to bits 2:0
  Input:  rrrrrrrrBBBcccccc  (r=remaining, B=bits 9-7, c=bits 6-0)
  Output: rrrrrrrrccccccBBB

Mode 11 (10-bit rotation):
  Bits 10:8 moved to bits 2:0
  Input:  rrrrrrrBBBccccccc  (r=remaining, B=bits 10-8, c=bits 7-0)
  Output: rrrrrrrcccccccBBB
```

**Worked Example (Mode 01):**
```
Input address:  0x1234 = 0001001000110100
Decompose:      rrrrrrrr BBB ccccc
                00010010 001 10100

Move BBB to end:
Output:         00010010 10100 001
                = 0001001010100001
                = 0x12A1
```

| Mode | Summary | Typical Use |
|------|---------|-------------|
| 00 | No remapping | Tile data, sequential access |
| 01 | Rotate bits 8:6 to 2:0 | 8x8 tile row optimization |
| 10 | Rotate bits 9:7 to 2:0 | 16x8 tilemap optimization |
| 11 | Rotate bits 10:8 to 2:0 | 32-column tilemap optimization |

**Why this matters for capture pipelines:**
- Most games use mode 00 (no remapping) for tile data
- If sprites appear corrupted or mis-aligned, check if the game uses non-zero
  translation modes for tilemap writes (rare for sprite data, common for BG maps)
- See `01_BUILD_SPECIFIC_CONTRACT.md` § "VRAM Read Semantics" for API behavior

## OBJSEL ($2101) Tile Tables
- `name_base = obsel & 0x07` (bits 0-2)
  - **Valid values:** 0-3. Each step = 0x2000 word addresses within 64KB VRAM.
  - **Values 4-7:** **UNDEFINED BEHAVIOR.**
    - Hardware: Likely wraps/mirrors within 64KB VRAM (not verified on real hardware).
    - Emulators: Behavior varies between implementations.
    - Pipeline: Reject captures with `name_base >= 4` and log a warning.
  - SNES VRAM is fixed at 64KB. Claims about "128KB expansion" are speculation.
- `name_select = (obsel >> 3) & 0x03` (bits 3-4)
- `size_select = (obsel >> 5) & 0x07` (bits 5-7) — selects small/large sprite dimensions
- **OAM base (word address):** `oam_base_word = name_base << 13`
  - Each step advances by **0x2000 word addresses** (spanning **16KB** of byte-addressable VRAM).
- **OAM offset (word address):** `oam_offset_word = (name_select + 1) << 12`
  - Each step advances by **0x1000 word addresses** (spanning **8KB** of byte-addressable VRAM).
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
  - Attribute bit 0 is the **tile high bit** (selects the second OBJ tile table).

### OAM Attribute Byte (Byte 3) Bit Layout
```
Bit:    7    6    5    4    3    2    1    0
        V    H    P    P    C    C    C    t
        │    │    └─┬──┘    └───┬───┘    │
        │    │      │           │        └─ Tile high bit (second table select)
        │    │      │           └────────── Palette (0-7, CGRAM 128-255)
        │    │      └────────────────────── Priority (0-3)
        │    └───────────────────────────── Horizontal flip
        └────────────────────────────────── Vertical flip
```
Source: https://snes.nesdev.org/wiki/OAM

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

**Coordinate ranges:**
- X: signed 9-bit, range **-256 to +255** (off-screen left/right)
- Y: unsigned 8-bit, range **0 to 255**
  - Y=0 is top of visible area
  - Y ∈ [224, 240): Overscan region (hidden on 224-line displays; 16 lines)
  - Y ∈ [240, 255]: Effectively off-screen top (sprites wrap to top of next frame)

In JSON captures, `x` is exported as signed int; `y` is raw unsigned.

## Sprite Overlap Ordering

**Sprite-sprite ordering is determined by OAM index**, not by the priority bits in the OAM attribute byte.
Lower OAM index = appears in front when sprites overlap on the same scanline.

- OAM index 0 appears in front of index 1, which appears in front of index 2, etc.
- The priority field (bits 4-5 of OAM attribute byte) affects **OBJ vs BG layer** ordering only.
- Priority 3 renders OBJ in front of all BG layers; Priority 0 renders OBJ behind all BG layers.

**Common misconception:** The priority field does NOT determine which sprite "wins" when two
sprites overlap. Only OAM slot order matters for sprite-sprite overlap.

Source: https://snes.nesdev.org/wiki/OAM

**Implications for capture pipelines:**
- When reconstructing composites, render sprites in reverse OAM index order (highest index first)
- Priority bits are still important for determining visibility relative to backgrounds
- If comparing visible sprites to captures, expect the lower-indexed sprite's pixels to dominate

### Priority Rotation ($2103)

By default, OAM 0 has highest priority (appears in front). The SNES supports **priority rotation**
via the OAMADDH register ($2103):

- **Bit 7 of $2103 (OAMADDH)**: When set during VBlank, the sprite at the OAM address specified
  in bits 1-7 becomes the "first" sprite (highest priority) instead of OAM 0.
- This effectively rotates which OAM index is treated as highest priority.
- Without priority rotation (bit 7 = 0), OAM 0 is always highest priority.

**Pipeline scope:** SpritePal capture/mapping does not track priority rotation state.
The "lower index = in front" rule applies to **default behavior only**. For games that use
priority rotation, sprite overlap ordering in captures may not match rendered output.

Source: https://snes.nesdev.org/wiki/PPU_registers

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

**Hardware reference:** Subtiles wrap within a 16×16 tile grid (256 tiles total per table).
Source: https://snes.nesdev.org/wiki/OAM

**Example: 32x32 sprite (4 subtiles) starting at tile index 0x45:**
```
Tile grid (16x16 tiles per table):
       col 0   1   2   3   4   5   6   7  ...  F
row 0  [00] [01] [02] [03] [04] [05] [06] [07] ... [0F]
row 1  [10] [11] [12] [13] [14] [15] [16] [17] ... [1F]
row 2  [20] [21] [22] [23] [24] [25] [26] [27] ... [2F]
row 3  [30] [31] [32] [33] [34] [35] [36] [37] ... [3F]
row 4  [40] [41] [42] [43] [44] [45] [46] [47] ... [4F]  ← OAM tile=0x45
row 5  [50] [51] [52] [53] [54] [55] [56] [57] ... [5F]
...

32x32 sprite uses 4 subtiles (2x2 grid):
  +------+------+
  | 0x45 | 0x46 |   ← row 4, cols 5-6
  +------+------+
  | 0x55 | 0x56 |   ← row 5, cols 5-6
  +------+------+

Wrapping example: tile index 0x4F with 32x32 sprite:
  +------+------+
  | 0x4F | 0x40 |   ← col F wraps to col 0 (same row)
  +------+------+
  | 0x5F | 0x50 |
  +------+------+
```

### Flip Behavior (Subtile Reordering)

When `flip_h` or `flip_v` are set in OAM:
- **flip_h**: Subtile columns are mirrored (rightmost becomes leftmost)
- **flip_v**: Subtile rows are mirrored (bottom becomes top)
- **Both**: 180° rotation of subtile grid

**Visual example (32x32 sprite, tiles labeled A-D):**
```
Original (no flip):     flip_h:             flip_v:             flip_h + flip_v:
  +---+---+              +---+---+           +---+---+           +---+---+
  | A | B |              | B | A |           | C | D |           | D | C |
  +---+---+              +---+---+           +---+---+           +---+---+
  | C | D |              | D | C |           | A | B |           | B | A |
  +---+---+              +---+---+           +---+---+           +---+---+

VRAM tile data is unchanged. Subtile grid order changes at render time.
```

The PPU applies flips at **render time**. OAM tile index and VRAM data are unchanged.
Capture scripts record pre-flip subtile order; apply flips when reconstructing images.

## CGRAM Format (Palettes)
- 15-bit BGR (often called **BGR555**), little-endian:
  - bits 0-4: Red
  - bits 5-9: Green
  - bits 10-14: Blue
- Sprite palettes are CGRAM entries 128-255.

## DMA Transfer Modes
The SNES has 8 DMA channels ($4300-$43x0) with 8 transfer modes configured via the mode
bits (0-2) of register $43x0. The "A" register is the destination ($21xx).

| Mode | Bytes | Pattern | Description |
|------|-------|---------|-------------|
| 0 | 1 | A | Single register (e.g., WRAM $2180) |
| 1 | 2 | A, A+1 | Two consecutive registers (e.g., VRAM $2118-$2119) |
| 2 | 2 | A, A | Same register twice (e.g., OAM, CGRAM) |
| 3 | 4 | A, A, A+1, A+1 | Two registers, paired writes (e.g., scroll positions) |
| 4 | 4 | A, A+1, A+2, A+3 | Four consecutive registers (e.g., window) |
| 5 | 4 | A, A+1, A, A+1 | Two registers, alternating (undocumented) |
| 6 | 2 | A, A | Same as mode 2 (undocumented) |
| 7 | 4 | A, A, A+1, A+1 | Same as mode 3 (undocumented) |

Source: https://snes.nesdev.org/wiki/DMA

**Common usage:**
- Mode 1: VRAM writes via $2118/$2119 (word writes)
- Mode 0: WRAM writes via $2180 (byte writes)
- Mode 2: OAM writes via $2104, CGRAM writes via $2122

---

## Glossary

### BW-RAM (Bitmap Work RAM)
SA-1 cartridge-side RAM (up to 256KB) used for expanded data storage. Accessible by both
the main SNES CPU and the SA-1 coprocessor. In SA-1 games like Kirby Super Star, BW-RAM
often holds decompressed graphics, level data, or work buffers before DMA to VRAM.
Not to be confused with WRAM (main system Work RAM at $7E0000-$7FFFFF).

### HDMA (H-Blank DMA)
DMA transfers that occur during the horizontal blanking period of each scanline.
Unlike general-purpose DMA (which runs during VBlank or when explicitly triggered),
HDMA can modify PPU registers **mid-frame** to create effects like:
- Gradient backgrounds (palette changes per scanline)
- Wavy distortion effects (scroll position changes)
- Window shape animation

HDMA is configured via registers $4300-$43x0 with the HDMA enable register at $420C.
Each bit of $420C enables one of 8 HDMA channels.

**Key difference from DMA:** Regular DMA halts the CPU and transfers a block of data.
HDMA transfers a small amount per scanline without halting execution, driven by a
table in memory specifying per-scanline values.

### Overscan / Display Modes
The SNES supports multiple vertical display modes controlled by $2133 (SETINI):

| Mode | Visible Lines | Total Lines | Notes |
|------|---------------|-------------|-------|
| 224-line (default) | 224 | 262 (NTSC) / 312 (PAL) | Most common |
| 239-line | 239 | 262 (NTSC) | Rarely used |
| 240-line (interlaced) | 240 | 525 (interlaced) | Hi-res mode |

**Overscan region** (Y coordinates 224-239 in 224-line mode):
- These scanlines exist but are hidden outside the safe display area
- Sprites with Y coordinates in this range are effectively off-screen
- Some TVs display partial overscan; emulators typically crop it

**Sprite Y coordinate wrapping:**
- Y=0 is the top of the visible area
- Y values 240-255 wrap to the *top* of the display (Y=240 appears at scanline -16)
- This allows sprites to smoothly scroll off the top of the screen

Source: https://snes.nesdev.org/wiki/Rendering_overview
