# LEARNINGS - DO NOT DELETE

## Mesen2 Sprite Offset Discovery Project
*Critical technical learnings from connecting visible sprites to ROM offsets*

## Tested On
- Mesen2 2.1.1+137ae7ce3bf3f539d007e2c4ef3cb3b6c97672a1 (Windows build, `tools/mesen2/Mesen2.exe`)
- OS: Windows via WSL2 interop
- Core: SNES (SA-1, Kirby Super Star)

---

## 1. Mesen2 Lua API Reference (Canonical)

All API-specific behavior (enums, callbacks, savestate loading, state structure quirks, memType aliases)
is documented in `docs/mesen2/MESEN2_LUA_API_LEARNINGS_DO_NOT_DELETE.md`. This file keeps only
sprite-offset-specific findings to avoid API drift between documents.

---

## 2. ADDRESS & UNITS RULES (READ FIRST)

**All addresses in this document follow these conventions. Violating them causes off-by-2 or off-by-bank bugs.**

### 2.1 VRAM Addresses

| Convention | Meaning | Example |
|------------|---------|---------|
| **VRAM $XXXX** | **Byte address** (what you'd see in a hex dump) | VRAM $6A00 = byte offset 0x6A00 |
| **VRAM word XXXX** | Word index (used by `emu.read` with `snesVideoRam`) | word 0x3500 = byte $6A00 |

**Conversion:** `word_index = byte_addr / 2` and `byte_addr = word_index * 2`

**Why this matters:** Mesen2's `emu.read(addr, snesVideoRam)` treats `addr` as a **word index**, not a byte offset. Passing a byte address gives you data from the wrong location.

### 2.2 ROM Offsets vs CPU Addresses

| Type | Format | Example | Use Case |
|------|--------|---------|----------|
| **ROM offset** | `$XXXXXX` or `0xXXXXXX` | $1B0000 | File position in the .sfc ROM |
| **SA-1 CPU address** | `$XX:XXXX` or `$XXXXXX` | $DB:0000 or $DB0000 | What the SA-1 coprocessor sees |
| **Main CPU address** | Same format | $7E2000 | What the main 65816 CPU sees |

**Mapping (SA-1 banks $C0-$FF):** `ROM_offset = ((CPU_bank - 0xC0) << 16) | CPU_addr_low16`

### 2.3 Debugger Views vs Real Mapping

| Source | What It Shows | Safe to Build Logic On? |
|--------|---------------|-------------------------|
| Mesen2 PRG-ROM view | Internal debugger offset (−$300000 trick) | ❌ **NO** - debugger artifact only |
| SA-1 CPU address ($C0-$FF banks) | Real cartridge mapping | ✅ Yes |
| DMA source/dest registers | WRAM/VRAM addresses at DMA time | ✅ Yes (but data already decompressed) |

### 2.4 Tile Data Sizes

| Unit | Size | Notes |
|------|------|-------|
| 8×8 tile (4bpp) | 32 bytes | Standard SNES sprite tile |
| 16×16 sprite | 4 tiles = 128 bytes | Arranged in 2×2 grid |
| OAM entry | 4 bytes main + 2 bits high table | 128 entries total |

### 2.5 Canonical Units Policy

**For all VRAM address calculations:**

1. **Compute in VRAM word addresses** - this is what `emu.read(..., snesVideoRam)` expects
2. **Never mix units in the same formula** - don't add word offsets to byte offsets
3. **Convert to bytes only at the end** - when exporting for humans/hex dumps

```lua
-- GOOD: All in words, convert at end
local vram_word = base_word + table_word + tile_word
local vram_byte = vram_word * 2  -- Convert only for display

-- BAD: Mixed units
local vram_addr = (base_bytes / 2) + table_word + (tile_index * 32)  -- Don't do this
```

---

## 3. Savestate Format (MSS Files)

**⚠️ BUILD-SPECIFIC - We explored this approach but found the tile hash database (Section 13) more reliable.**

**Quick reference (Mesen2 2.1.1+137ae7c):**
- MSS files: "MSS" header (3 bytes) + zlib-compressed blob starting ~offset 0x23
- Scan for zlib header `0x78` followed by `0x01|0x5E|0x9C|0xDA`, then `zlib.decompress()`
- Decompressed blob may contain raw VRAM where byte-address = blob offset (not guaranteed)
- Always validate by matching a known tile hash—don't assume offsets are stable across builds

---

## 4. Address Translation Notes

> **🚫 Mesen2 PRG-ROM View (−$300000 trick):** Debugger artifact only. Do NOT use in code. For real SA-1 mapping, see Section 8.2.

**Validation:** We confirmed ROM offsets by extracting with `exhal` and visually verifying sprites.

---

## 5. DMA Monitoring (Dead End)

**Tried:** Reading $2116/$2117 during DMA callbacks to get VRAM destination. Always returned $0000.

**Why it failed:** Timing issues, wrong memType, or registers already cleared by the time callback fires.

**Untested alternative:** Hook *writes* to $2116/$2117 and cache values instead of reading during DMA. See `docs/mesen2/MESEN2_LUA_API_LEARNINGS_DO_NOT_DELETE.md` for callback helpers.

**Resolution:** We abandoned DMA tracing in favor of the tile hash database (Section 18).

---

## 6. Investigation History (Condensed)

This section summarizes approaches we tried before arriving at the tile hash database solution.

### 6.1 Mushroom Sprite Investigation

**Goal:** Track a specific in-game mushroom sprite back to its ROM offset.

**What we tried:**
- Savestate comparison (Before.mss vs Sprite.mss) → Found VRAM $6A00 changed but showed fill pattern (87 7E), not actual graphics
- Pattern search in ROM → No direct matches; HAL compression obscures data
- DMA monitoring → Couldn't reliably read VRAM destination (see Section 5)

**Why it didn't work:** By the time data reaches VRAM, it's already decompressed. The SA-1 coprocessor handles decompression invisibly to main CPU callbacks.

### 6.2 Key Insight

> "Focusing too much on cataloging, and not enough on the bridge between sprite you can see and ROM position"

**Resolution:** Instead of tracing runtime data flow, we pre-built a tile hash database from known ROM offsets (Section 13) and match VRAM captures against it.

### 6.3 Working Code Patterns (Reference)

**4bpp tile decode:** Each 8×8 tile is 32 bytes. Bitplanes are interleaved: bytes 0-15 hold planes 0-1, bytes 16-31 hold planes 2-3. See `core/tile_renderer.py` for implementation.

**Savestate loading in Lua:** Must use exec callback, not direct call. See `docs/mesen2/MESEN2_LUA_API_LEARNINGS_DO_NOT_DELETE.md`.

---

## 7. CONFIRMED WORKING SPRITE OFFSETS (December 2025)

### 7.1 Successful Sprite Extraction Workflow

**What finally worked:**
1. Use `exhal` tool directly on ROM at offsets in the **0x180000-0x1C0000 region**
2. Render with `TileRenderer` using grayscale first to verify shapes
3. Apply palette 8 (Kirby pink) for character sprites

```bash
# Extract sprite data
./tools/exhal "roms/Kirby Super Star (USA).sfc" 0x1B0000 sprite.bin

# Render with Python
from core.tile_renderer import TileRenderer
renderer = TileRenderer()
img = renderer.render_tiles(data, width_tiles=16, height_tiles=22, palette_index=8)
```

### 7.2 Known Working ROM Offsets

| Offset | Content | Size | Tiles | Notes |
|--------|---------|------|-------|-------|
| **0x1B0000** | **KIRBY SPRITES** | 11,264 bytes | 352 | Main character animations, faces, poses |
| 0x1A0000 | Enemy/creature sprites | 11,936 bytes | 373 | Small enemies with eyes, animation frames |
| 0x180000 | Items/UI graphics | 17,408 bytes | 544 | Collectibles, small icons |
| 0x190000 | Background tiles | 15,488 bytes | 484 | Trees, terrain, environment |
| 0x1C0000 | Background gradients | 11,392 bytes | 356 | Sky/water textures |
| 0x280000 | Sprites | 1,185 bytes | 37 | Valid sprite data |
| 0x110000 | Extra sprites | 3,696 bytes | 115 | Valid HAL data |
| 0x120000 | Extra sprites | 2,952 bytes | 92 | Valid HAL data |
| 0x140000 | Extra sprites | ~3,000 bytes | ~90 | Valid HAL data |
| 0x0E0000 | Title screen/fonts | 57,290 bytes | 1,790 | "KIRBY" text, UI fonts |

### 7.3 Offsets That Need Care

| Offset | Notes |
|--------|-------|
| 0x0C8000 | Not valid HAL-compressed data at this exact offset |
| 0x0C0000, 0x0CC100, 0x07B500 | Pass validation metrics - may need correct palette/arrangement |

### 7.4 Why Previous "Perfect Score" Extractions Failed

The SpriteFinder validation metrics (coherence, entropy, edges, diversity) detect **structurally sprite-like** data but cannot distinguish real game art from random data that happens to have similar properties.

**Key insight**: Visual verification is essential. Validation scores alone are insufficient.

### 7.5 Recommended Scan Strategy

1. **Start with known good region**: 0x180000-0x200000
2. **Scan in 0x4000 (16KB) steps** within sprite areas
3. **Check extraction size**: Real sprites are typically 10-60KB uncompressed
4. **Verify visually** with grayscale render before applying palettes
5. **Good compression ratios**: 10:1 to 30:1 indicate real sprite data

### 7.6 Palette Reference

| Palette | Use For |
|---------|---------|
| 8 | Kirby (pink) - main character |
| 9 | Kirby alt |
| 10 | Helper characters |
| 11 | Enemies (green/orange) |
| None | Grayscale - best for initial verification |

---

*Last Updated: December 2025 - Added confirmed working sprite offsets from systematic ROM scanning*

---

## 8. KIRBY SUPER STAR SA-1 MEMORY MAPPING (CRITICAL)

### 8.1 SA-1 Overview

Kirby Super Star (USA) uses the **SA-1 enhancement chip**:
- ROM Header map mode: **$23** (SA-1)
- ROM type: **$35** (SA-1 + RAM + Battery)
- ROM size: 4MB (0x400000 bytes)

### 8.2 SA-1 ROM Mapping Formula

**CPU Address → ROM Offset:**
```
Banks $C0-$FF map to ROM linearly:
ROM Offset = ((CPU_Bank - 0xC0) << 16) | CPU_Address_Low16

Example:
CPU $DB0000 → ROM $1B0000
CPU $DA0000 → ROM $1A0000
CPU $E00000 → ROM $200000
CPU $F00000 → ROM $300000
```

### 8.3 Verified ROM Access Examples

| ROM Offset | SA-1 CPU Address | Content |
|------------|------------------|---------|
| $000000 | $C00000 | Reset vectors |
| $100000 | $D00000 | Game code |
| $1A0000 | $DA0000 | Enemy sprites |
| $1B0000 | $DB0000 | Kirby sprites |
| $200000 | $E00000 | Backgrounds |
| $300000 | $F00000 | Music/SFX |

### 8.4 Why Standard LoROM Mapping Fails

Standard LoROM uses banks $00-$3F at $8000-$FFFF:
- CPU $368000 should map to ROM $1B0000
- **But this is WRONG for SA-1 games!**

SA-1 games use banks $C0-$FF for direct ROM access, not banks $00-$3F.

### 8.5 Callback Registration for SA-1 ROM Reads

```lua
-- To monitor reads from ROM $1A0000-$1FFFFF:
emu.addMemoryCallback(function(addr, value)
    -- NOTE: This assumes addr is a 24-bit CPU address (bank:offset).
    -- Verify actual address width on your build before doing bank math.
    local rom_offset = ((addr >> 16) - 0xC0) << 16 | (addr & 0xFFFF)
    -- Process rom_offset
end, emu.callbackType.read, 0xDA0000, 0xDFFFFF, emu.memType.snesMemory)  -- memType optional on some builds
```

**Address-width caveat:** Mesen2 may pass 16-bit or linearized addresses depending on
`memType`. Log `addr` values on a known access to confirm how ranges are interpreted.

---

## 9. SPRITE GRAPHICS DATA FLOW (SA-1 Games)

### 9.1 The Decompression Pipeline

```
ROM (HAL compressed) → SA-1 CPU decompresses → WRAM buffer → DMA → VRAM
     ↑                      ↑                       ↑
   $1B0000            SA-1 coprocessor          $7E2000
   (use sa1Memory)    (runs own code)           (can trace DMA)
```

### 9.2 Why We Can't Easily Track ROM→VRAM

1. **SA-1 coprocessor handles decompression** - runs independently from main CPU
2. **Callbacks on `snesMemory` only capture main CPU activity** - SA-1 ROM reads require
   hooking `sa1Memory` memory type instead (see `docs/mesen2/MESEN2_LUA_API_LEARNINGS_DO_NOT_DELETE.md`)
3. **DMA shows WRAM→VRAM, not ROM source** - by the time DMA happens, data is already decompressed

**Note**: SA-1 activity is not truly "invisible" - it requires using `emu.memType.sa1Memory`
callbacks instead of main CPU callbacks. We did not explore this approach in depth.

### 9.3 DMA Observations

From 900 frames of Kirby Super Star (observed behavior, not a universal law):
```
Low16 source values we logged: $0060, $00A4, $0500
WRAM→VRAM transfers: From $7E2000-$7E20BB range
```

**⚠️ Measurement caveat:** We may have only captured A1TxL/A1TxH (low 16 bits of source)
without combining A1Bx (bank byte). If so, apparent "low offsets" are just the low16 portion
of a full 24-bit address. Don't generalize from these numbers.

**Observation:** In our captures, most VRAM DMA sources appeared to be WRAM buffers ($7Exxxx);
the "ROM→VRAM" entries above may be incomplete addresses. Sprite data isn't visible at the
DMA stage because decompression happens earlier (SA-1 → WRAM → DMA → VRAM).

### 9.4 Practical Implication

**In this game, we could not trace ROM offsets via DMA monitoring alone.**

Alternative approaches (what we used instead):
1. **Pre-build ROM→VRAM pattern database** (see Section 18)
2. **Pattern match VRAM content against known ROM sprites**
3. **Use tile hash lookup**

---

## 10. WORKING SPRITE CAPTURE SYSTEM

### 10.1 F9 Hotkey Capture Script

Located at: `mesen2_integration/lua_scripts/mesen2_sprite_capture.lua`

**Captures:**
- All 128 OAM entries with positions, tiles, palettes, flips
- VRAM tile data (32 bytes per 8x8 tile)
- Sprite palettes (8 palettes × 16 colors)
- OBSEL settings (sprite sizes, tile base)

### 10.2 Output Format

```json
{
  "frame": 700,
  "obsel": {"raw": 0, "name_base": 0, "size_select": 0},
  "visible_count": 128,
  "entries": [
    {
      "id": 0, "x": 165, "y": 125, "tile": 131,
      "width": 16, "height": 16, "palette": 1,
      "flip_h": true, "flip_v": false,
      "tiles": [
        {"tile_index": 131, "vram_addr": 12384, "data_hex": "0042015302430328..."}
      ]
    }
  ],
  "palettes": {"0": [0, 1234, 5678, ...], "1": [...]}
}
```

### 10.3 Exchange Directory

Files written to: `mesen2_exchange/`
- `sprite_capture_<timestamp>.json` - Full capture data
- `capture_summary.txt` - Human-readable summary

### 10.4 OAM Entry Structure (SNES)

```
Main table (544 bytes total):
- Bytes 0-511: 128 entries × 4 bytes each
  - Byte 0: X position (low 8 bits)
  - Byte 1: Y position
  - Byte 2: Tile index
  - Byte 3: Attributes (palette, priority, flips, tile index bit 8)

High table (bytes 512-543):
- 32 bytes for 128 entries (2 bits each)
  - Bit 0: X position bit 9
  - Bit 1: Size (0=small, 1=large)
```

**Addressing note:** In Mesen2, OAM is byte-addressed. `emu.read(i, emu.memType.snesSpriteRam)`
returns a byte; the high table starts at byte offset 0x200.

### 10.5 OBSEL Sprite Size Table

| size_select | Small | Large |
|-------------|-------|-------|
| 0 | 8×8 | 16×16 |
| 1 | 8×8 | 32×32 |
| 2 | 8×8 | 64×64 |
| 3 | 16×16 | 32×32 |
| 4 | 16×16 | 64×64 |
| 5 | 32×32 | 64×64 |
| 6 | 16×32 | 32×64 |
| 7 | 16×32 | 32×32 |

---

## 11. TESTRUNNER MODE (Headless Automation)

### 11.1 Command Line Usage

```bash
# From PowerShell (NOT cmd.exe - cmd doesn't work from WSL)
powershell.exe -Command "cd 'C:\path\to\spritepal'; .\tools\mesen2\Mesen2.exe --testrunner 'roms\game.sfc' 'script.lua'"
```

### 11.2 Script Requirements for Testrunner

```lua
-- Script MUST call emu.stop() to exit
local fr = 0
emu.addEventCallback(function()
    fr = fr + 1
    if fr == 600 then
        -- Do final processing
        emu.stop()  -- REQUIRED: exits testrunner
    end
end, emu.eventType.endFrame)
```

### 11.3 File I/O in Testrunner

```lua
-- MUST use full Windows paths (not WSL paths)
local f = io.open("C:\\path\\to\\output.txt", "w")
f:write("content")
f:close()
```

### 11.4 Headless Screenshot Capture

`emu.takeScreenshot()` returns PNG bytes and works in `--testrunner` mode.

```lua
local png_data = emu.takeScreenshot()
local file = io.open(output_dir .. "\\\\frame_700.png", "wb")
file:write(png_data)
file:close()
```

---

## 12. VRAM WORD-ADDRESSING (CRITICAL BUG FIX)

### 12.1 The Problem

**SNES VRAM is word-addressed (16-bit), NOT byte-addressed!**

```lua
-- WRONG: Treats VRAM as byte-addressed
for i = 0, 31 do
    tile_data[i + 1] = emu.read(vram_addr + i, emu.memType.snesVideoRam)
end
-- Result: Each "byte" is actually a 16-bit word, giving wrong data
```

### 12.2 The Fix

```lua
-- CORRECT: VRAM is word-addressed
local word_addr = math.floor(vram_addr / 2)  -- Convert byte address to word address
for i = 0, 15 do  -- 16 words = 32 bytes
    local word = emu.read(word_addr + i, emu.memType.snesVideoRam)
    tile_data[i * 2 + 1] = word & 0xFF         -- Low byte
    tile_data[i * 2 + 2] = (word >> 8) & 0xFF  -- High byte
end
```

### 12.3 How to Detect the Bug

If captured tile data shows every other byte missing/zero, byte-swapped words, or repeating
2-byte patterns, double-check word addressing and stride. A strictly sequential
`00 01 02 03 ...` pattern usually indicates you're accidentally emitting a loop index or
address counter, not VRAM bytes.

### 12.4 Follow-up Diagnostic: VRAM vs OAM Tile Mapping

- Full VRAM dumps contained tiles that matched the ROM hash database, so VRAM reads and hashing are working.
- OAM-derived tiles from the same capture still produced no hash matches.
- Conclusion: word-addressing is necessary but not sufficient; focus on OAM tile→VRAM address math
  (OBSEL base, tile index bit 8, size select) rather than VRAM read or hash logic.

---

## 13. TILE HASH DATABASE (IMPLEMENTED)

### 13.1 Purpose

Instead of parsing complex game pointer tables, we:
1. Pre-extract tiles from known ROM offsets (decompress with HAL)
2. Hash each 8x8 tile (32 bytes MD5)
3. Create database mapping hash → **list of candidates** `(rom_offset, tile_index)`
4. When VRAM tiles are captured, hash and lookup to find ROM source candidates
5. Aggregate votes across the capture to produce a **ranked** set of ROM offsets

### 13.2 Implementation Files

```
core/mesen_integration/
├── tile_hash_database.py      # Hash-based tile lookup
├── capture_to_rom_mapper.py   # Maps captures to ROM offsets
├── gfx_pointer_table.py       # ROM pointer table analysis (partial)
```

### 13.3 Usage

```python
from core.mesen_integration import TileHashDatabase, CaptureToROMMapper

# Build database (one-time)
db = TileHashDatabase(rom_path)
db.build_database()
db.save_database("tile_database.json")

# Map capture to ROM offsets
mapper = CaptureToROMMapper(rom_path, "tile_database.json")
mapper.build_database()
result = mapper.map_capture(capture_result)
print(f"Primary ROM offset (top vote): ${result.primary_rom_offset:06X}")
print(f"Offset summary: {result.rom_offset_summary}")
```

### 13.4 Database Statistics (Kirby Super Star)

| ROM Offset | Description | Tiles | Unique Hashes |
|------------|-------------|-------|---------------|
| $1B0000 | Kirby sprites | 352 | ~280 |
| $1A0000 | Enemy sprites | 373 | ~310 |
| $180000 | Items/UI | 544 | ~420 |
| $190000 | Background tiles | 484 | ~380 |
| $1C0000 | Background gradients | 356 | ~290 |
| $280000 | Additional sprites | 37 | ~30 |
| $0E0000 | Title screen/fonts | 1790 | ~950 |
| **Total** | | **3936** | **2643** |

### 13.5 Collision Handling (Required)

Tile hashes are **not unique**. Many tiles are solid fills or common patterns and appear
in multiple ROM regions. Treat matching as a **voting problem**:

- Store **all** candidate ROM locations per hash (the current implementation keeps only one).
- Tally votes per ROM region/bank across all tiles in a capture.
- Report confidence and ambiguity (e.g., top region vs runner-up).

---

## 14. GFX POINTER TABLE (Limited Use)

**Location:** GFX pointer table at ROM $3F0002, level pointers at $3F000C.

**Finding:** 24-bit pointers to sprite banks exist (e.g., $040A4A → CPU $DA0000 → ROM $1A0000), but **no clean "sprite ID → ROM offset" mapping** exists. The SA-1 coprocessor makes tracing impractical.

**Recommendation:** Use the tile hash database (Section 13) instead of parsing pointer tables.

---

## 15. COMPLETE WORKFLOW

### 15.1 Setup (One-time)

1. Run `TileHashDatabase.build_database()` on the ROM
2. Save database JSON for reuse

### 15.2 During Gameplay

1. Run Mesen 2 with `mesen2_sprite_capture.lua`
2. Press **F9** to capture visible sprites
3. Lua writes `sprite_capture.json` to exchange directory

### 15.3 In SpritePal

1. Load `sprite_capture.json` with `MesenCaptureParser`
2. Use `CaptureToROMMapper` to find ROM offsets
3. Extract and render using `CaptureRenderer`
4. Display with actual palettes from CGRAM capture

---

## 16. GLOSSARY

Quick reference for terms used throughout this document. See Section 2 for address conventions.

| Term | Definition |
|------|------------|
| **VRAM byte address** | Offset in VRAM as bytes (0x0000-0xFFFF). What you see in hex dumps. |
| **VRAM word address** | Index for `emu.read(addr, snesVideoRam)`. `word = byte / 2`. |
| **ROM offset** | Position in the .sfc file (0x000000-0x3FFFFF for 4MB ROM). |
| **SA-1 CPU address** | Address seen by the SA-1 coprocessor. Banks $C0-$FF map to ROM. |
| **OAM tile index** | Tile number in OAM entry byte 2. Combined with OBSEL + tile index bit 8 for VRAM address. |
| **OBSEL** | $2101 register. Controls sprite tile base address and size modes. |
| **Name base** | OBSEL bits 0-2. Each step = 0x1000 words (8KB). See Section 24 for formula. |
| **Tile index bit 8** | OAM attribute bit 0. Adds 0x1000 words (8KB) when set. See Section 24. |
| **Size select** | OBSEL bits 5-7. Determines small/large sprite dimensions. |
| **4bpp tile** | 4 bits per pixel, 8×8 pixels, 32 bytes. Standard SNES sprite format. |
| **HAL compression** | Proprietary compression used by HAL Laboratory games. |

---

## 17. TILE HASH DATABASE ASSUMPTIONS

The tile hash database (Section 13) was built with these assumptions. Violating them
produces hash mismatches.

### 17.1 Hash Computation

| Property | Value | Notes |
|----------|-------|-------|
| Hash algorithm | MD5 | Fast, sufficient for tile matching |
| Input format | Raw 32-byte 4bpp planar data | As extracted by exhal, no reordering |
| Flip normalization | **None** | Horizontally/vertically flipped tiles have different hashes |
| Palette independence | **Yes** | Hashes ignore palette; same tile with different palette = same hash |

### 17.2 Multi-Tile Sprites

| Property | Value | Notes |
|----------|-------|-------|
| 16×16 sprites | Hashed as 4 separate 8×8 tiles | Each tile in the 2×2 grid is independent |
| Tile order | 16×16: TL, TR, BL, BR; 32×32+: 16×16 block layout | See Section 18.4 |
| Combined hash | Not used | We match individual tiles, not sprite groups |

### 17.3 Known Limitations

1. **No flip detection:** A sprite flipped horizontally in-game won't match its unflipped ROM source.
2. **No partial matches:** If VRAM contains corrupted or partially loaded tiles, no match.
3. **ROM coverage:** Only offsets we explicitly extracted are in the database.

---

## 18. OAM TILE → VRAM ADDRESS MATH (CANONICAL)

This is the formula for converting an OAM sprite entry to a VRAM tile address. **All values are in VRAM word addresses** (what `emu.read(addr, snesVideoRam)` expects).

### 18.1 The Formula

```lua
-- CANONICAL: All arithmetic in VRAM word addresses
local name_base = bit.band(obsel, 0x07)           -- OBSEL bits 0-2
local tile_hi_bit = bit.band(oam_attr, 0x01)      -- OAM byte 3, bit 0 (tile index bit 8)
local tile_index = oam_tile                        -- OAM byte 2

local base_word  = name_base * 0x1000              -- Each step = 8KB = 0x1000 words
local table_word = tile_hi_bit * 0x1000            -- Tile index bit 8: +8KB
local tile_word  = tile_index * 16                 -- Each tile = 32 bytes = 16 words

local vram_word = base_word + table_word + tile_word
```

### 18.2 Worked Example

Given capture data:
- OBSEL = 0x02 (name_base = 2)
- OAM tile = 0x40 (tile_index = 64)
-- OAM attr = 0x31 (tile_hi_bit = 1)

```
base_word  = 2 * 0x1000     = 0x2000
table_word = 1 * 0x1000     = 0x1000
tile_word  = 64 * 16        = 0x0400

vram_word  = 0x2000 + 0x1000 + 0x0400 = 0x3400
vram_byte  = 0x3400 * 2 = 0x6800  (for hex dumps/humans)
```

### 18.3 Common Mistakes

| Mistake | Symptom | Fix |
|---------|---------|-----|
| Using 0x2000 for tile_hi_bit | Addresses 16KB too high | Use 0x1000 words (8KB) |
| Mixing byte/word units | Off-by-2x errors | Stay in words; convert only at end |
| Forgetting tile_hi_bit | Wrong pattern table entirely | Always extract bit 0 from OAM attr |
| Using name_base << 14 | Off-by-2x | Use `name_base * 0x1000` (word address) |

### 18.4 For 16×16 and Larger Sprites

For sprites larger than 8×8, OAM specifies the **top-left tile**. Derive subtiles:

```lua
-- 16×16: 4 tiles in 2×2 grid
local subtile_offsets = {
    {dx = 0, dy = 0, tile_add = 0},   -- top-left
    {dx = 8, dy = 0, tile_add = 1},   -- top-right
    {dx = 0, dy = 8, tile_add = 16},  -- bottom-left
    {dx = 8, dy = 8, tile_add = 17},  -- bottom-right
}

for _, sub in ipairs(subtile_offsets) do
    local subtile_vram_word = vram_word + (sub.tile_add * 16)
    -- Read 16 words (32 bytes) starting at subtile_vram_word
end
```

**32×32 and larger:** Tile numbering is **not sequential**. The hardware arranges tiles in
16×16 blocks. A working model (verify on your build):

```lua
-- width/height in pixels from OBSEL + size bit
local tiles_w = width / 8
local tiles_h = height / 8
local blocks_x = tiles_w / 2   -- 16px blocks
local blocks_y = tiles_h / 2

local block_offsets = {0, 1, 16, 17} -- TL, TR, BL, BR within a 16×16 block

for by = 0, blocks_y - 1 do
    for bx = 0, blocks_x - 1 do
        local block_base = (by * 32) + (bx * 2) -- 2 tiles wide, 2 tiles tall
        for _, off in ipairs(block_offsets) do
            local tile_index = base_tile + block_base + off
            -- tile_index -> vram word via formula above
        end
    end
end
```

If this layout doesn't match, log known tiles to derive the true ordering.

---

## 19. CGRAM (PALETTE) FORMAT

### 19.1 SNES Color Format

CGRAM entries are **15-bit BGR** (not RGB):

```
Bit:  15  14-10   9-5    4-0
      0   Blue   Green   Red
          (5b)   (5b)   (5b)
```

### 19.2 Addressing in Mesen2

Observed behavior: `emu.read(addr, emu.memType.snesCgRam)` returns a byte and CGRAM is
byte-addressed. Each color is two bytes at `color_index * 2` (little-endian).

### 19.3 Conversion Code

```python
def cgram_to_rgb(cgram_word: int) -> tuple[int, int, int]:
    """Convert SNES CGRAM entry to 8-bit RGB."""
    r5 = cgram_word & 0x1F
    g5 = (cgram_word >> 5) & 0x1F
    b5 = (cgram_word >> 10) & 0x1F
    # Scale 5-bit to 8-bit
    return (r5 << 3) | (r5 >> 2), (g5 << 3) | (g5 >> 2), (b5 << 3) | (b5 >> 2)
```

### 19.4 Sprite Palettes

Sprites use CGRAM entries 128-255 (palettes 8-15). Each OAM palette index (0-7) maps to:
```
cgram_index = 128 + (oam_palette * 16) + color_index
```

---

## 20. GENERALITY TAGS

### 20.1 GENERAL (Applies to Most SNES Games)

- VRAM word-addressing for `emu.read(..., snesVideoRam)`
- OAM tile → VRAM formula (Section 18)
- CGRAM 15-bit BGR format
- `emu.callbackType` values (observed: write=1, exec=2; re-check per build)
- `emu.memType.snes*` naming convention
- OAM structure (544 bytes, high table format)
- OBSEL size modes table

### 20.2 KIRBY SUPER STAR / SA-1 SPECIFIC

- Working ROM offsets ($1A0000, $1B0000, etc.)
- SA-1 bank mapping ($C0-$FF → ROM)
- HAL compression format
- Specific DMA observations (WRAM buffers at $7E2000)
- Tile hash database contents
- Mushroom sprite findings

### 20.3 BUILD-SPECIFIC (Mesen2 2.1.1+137ae7c)

- Savestate format/offsets
- `emu.loadSavestate()` only from exec callbacks
- memType enum aliases (`snesOam` vs `snesSpriteRam`)
- `emu.convertAddress()` returning 0

---

*Last Updated: December 29, 2025*
- Condensed document from ~1060 lines to ~790 lines
- Merged investigation dead-ends into Section 6 (Investigation History)
- Condensed savestate, DMA monitoring, and pointer table sections
- Renumbered sections 1-20 for consistency
- Fixed internal section references

**DO NOT DELETE - This document contains critical technical discoveries essential for the sprite discovery workflow**
