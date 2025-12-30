# LEARNINGS - DO NOT DELETE

## Mesen2 Sprite Offset Discovery Project
*Critical technical learnings from connecting visible sprites to ROM offsets*

## Tested On
- Mesen2 2.1.1+137ae7ce3bf3f539d007e2c4ef3cb3b6c97672a1 (Windows build, `tools/mesen2/Mesen2.exe`)
- OS: Windows via WSL2 interop
- Core: SNES (SA-1, Kirby Super Star)

---

## 0. Compatibility Contract

**Build-sensitive workflow.** Run `mesen2_integration/lua_scripts/mesen2_preflight_probe.lua` before any capture/mapper work. See `docs/mesen2/MESEN2_LUA_API_LEARNINGS_DO_NOT_DELETE.md` for full probe details.

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
| **VRAM $XXXX** | **Byte address** (what you'd see in a hex dump, and what Mesen2 uses) | VRAM $6A00 = byte offset 0x6A00 |
| **VRAM word XXXX** | SNES internal *word* address used in PPU/OAM math | word 0x3500 = byte $6A00 |

**Conversion:** `byte_addr = word_addr * 2` and `word_addr = byte_addr / 2`

**Why this matters:** Mesen2's `emu.read(addr, snesVideoRam)` treats `addr` as a **byte offset**. The
PPU/OAM formulas often operate in *word* units; convert to bytes before reading VRAM.

### 2.2 ROM Offsets vs CPU Addresses

| Type | Format | Example | Use Case |
|------|--------|---------|----------|
| **ROM offset** | `$XXXXXX` or `0xXXXXXX` | $1B0000 | File position in the .sfc ROM |
| **SA-1 CPU address** | `$XX:XXXX` or `$XXXXXX` | $DB:0000 or $DB0000 | What the SA-1 coprocessor sees |
| **Main CPU address** | Same format | $7E2000 | What the main 65816 CPU sees |

**Mapping (SA-1 banks $C0-$FF):** `ROM_offset = ((CPU_bank - 0xC0) << 16) | CPU_addr_low16`

**Hard rule:** memory callbacks may provide only **relative/16-bit** addresses. Do not compare
callback `addr` directly to 24-bit CPU ranges; reconstruct bank context separately.

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

1. **Keep units consistent** - PPU/OAM formulas are in word units; VRAM reads are byte units.
2. **Convert word → byte before reading** - `emu.read(..., snesVideoRam)` expects byte addresses.
3. **Never mix units in the same formula** - don't add word offsets to byte offsets.

```lua
-- GOOD: Compute in words (PPU formula), convert to bytes for emu.read
local vram_word = base_word + table_word + tile_word
local vram_byte = vram_word * 2
local b0 = emu.read(vram_byte, emu.memType.snesVideoRam)

-- BAD: Mixed units
local vram_addr = (base_bytes / 2) + table_word + (tile_index * 32)  -- Don't do this
```

---

## 3. Savestate Format (MSS Files) — DEPRECATED

**⚠️ Abandoned approach.** MSS files are zlib-compressed; internal offsets are build-specific and unreliable. Use the tile hash database (Section 13) instead.

---

## 4. Address Translation Notes

> **🚫 Mesen2 PRG-ROM View (−$300000 trick):** Debugger artifact only. Do NOT use in code. For real SA-1 mapping, see Section 8.2.

**Validation:** We confirmed ROM offsets by extracting with `exhal` and visually verifying sprites.

---

## 5. DMA Monitoring — DEAD END

**Tried:** Reading $2116/$2117 during DMA callbacks → always returned $0000 (timing/memType issues). Use tile hash database (Section 13) instead.

---

## 6. Investigation History (Condensed)

**Approaches tried before tile hash database:**
- Savestate comparison, pattern search in ROM, DMA monitoring — all failed because SA-1 decompresses data before it reaches VRAM (invisible to main CPU callbacks).

**Key insight:** Instead of tracing runtime data flow, pre-build a tile hash database from known ROM offsets (Section 13) and match VRAM captures against it.

**4bpp tile format:** 32 bytes per 8×8 tile; bitplanes interleaved (bytes 0-15 = planes 0-1, bytes 16-31 = planes 2-3). See `core/tile_renderer.py`.

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
    -- NOTE: Callback address is relative/16-bit in this build.
    -- If you register a single-bank range, supply the bank explicitly.
    local bank = 0xDA
    local rom_offset = ((bank - 0xC0) << 16) | (addr & 0xFFFF)
    -- Process rom_offset
end, emu.callbackType.read, 0xDA0000, 0xDAFFFF, emu.cpuType.sa1, emu.memType.snesMemory)  -- memType optional
```

**Address-width caveat:** Per `Mesen2/Core/Debugger/ScriptingContext.cpp`, callbacks always
receive `relAddr.Address` (relative/16-bit for CPU memory). Do not assume bank bits are present.
If you register a multi-bank range, **addr alone is ambiguous** — split per bank or track
bank context separately.

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

1. **SA-1 coprocessor handles decompression** - runs independently from main CPU; invisible to
   main-CPU callbacks unless you hook `emu.cpuType.sa1`
2. **Callbacks on `emu.cpuType.snes` (main CPU)** only capture main CPU activity - SA-1 ROM reads
   require using `emu.cpuType.sa1` instead (see `docs/mesen2/MESEN2_LUA_API_LEARNINGS_DO_NOT_DELETE.md`)
3. **DMA shows WRAM→VRAM, not ROM source** - by the time DMA happens, data is already decompressed

**Note**: SA-1 activity is not truly "invisible" - it requires using `emu.cpuType.sa1`
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
1. **Pre-build ROM→VRAM pattern database** (see Section 13)
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
- OBSEL settings (sprite sizes, OAM base/offset)

### 10.2 Output Format

**Schema (canonical):**
- `frame` (int): capture frame counter used by the script.
- `obsel` (object, required):
  - `raw` (int), `name_base` (int), `name_select` (int), `size_select` (int)
  - `tile_base_addr` (int, **byte** address), `oam_base_addr` (int, **word** address),
    `oam_addr_offset` (int, **word** address)
- `visible_count` (int): number of on-screen sprites captured.
- `entries` (array, required): each entry has:
  - `id` (int), `x` (int), `y` (int), `tile` (int)
  - `width` (int), `height` (int)
  - `palette` (int), `flip_h` (bool), `flip_v` (bool)
  - `tiles` (array, required): each tile has:
    - `tile_index` (int, **per-subtile index**), `vram_addr` (int, **byte address**),
      `data_hex` (string)
- `palettes` (object, required): keys `"0"`–`"7"` → array of 16 ints (raw 15-bit BGR words,
  little-endian as `lo | (hi << 8)`).

**`data_hex` rules:** must be exactly **64 hex chars** (32 bytes, uppercase, no separators).
If it is missing or the wrong length, treat the tile as invalid for hashing.

```json
{
  "frame": 700,
  "obsel": {
    "raw": 0, "name_base": 0, "name_select": 0, "size_select": 0,
    "tile_base_addr": 0, "oam_base_addr": 0, "oam_addr_offset": 0
  },
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

**CLI parsing (from source):**
- Test runner loads **exactly one non-`.lua` file** (the ROM). Any `.lua` files are scripts.
- Order does **not** matter; extension determines handling.
- There is **no** `--loadstate` switch; use `emu.loadSavestate()` in Lua instead.

Sources: `Mesen2/UI/Utilities/TestRunner.cs`, `Mesen2/UI/Utilities/CommandLineHelper.cs`,
`Mesen2/Core/Debugger/LuaApi.cpp` (`checksavestateconditions()` gate).

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

**Capture script controls (for `test_sprite_capture.lua`):**
- `FRAME_EVENT=exec` to drive capture via exec callback (useful after `emu.loadSavestate()`).
- `MASTER_CLOCK_FALLBACK=1` to synthesize frame ticks from `masterClock` if `frameCount` stalls.
- `MASTER_CLOCK_FPS=60|50` to override FPS detection (defaults to region or 60).
- `MASTER_CLOCK_MAX_SECONDS` to bail out if the run stalls after savestate load.

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

## 12. VRAM BYTE-ADDRESSING (CRITICAL BUG FIX)

### 12.1 The Problem

**Mesen2 Lua `snesVideoRam` is byte-addressed (not word-indexed).**

```lua
-- WRONG: Treats VRAM as word-addressed (skips every other byte)
local word_addr = math.floor(vram_addr / 2)
for i = 0, 15 do
    local word = emu.read(word_addr + i, emu.memType.snesVideoRam)
    tile_data[i * 2 + 1] = word & 0xFF
    tile_data[i * 2 + 2] = (word >> 8) & 0xFF
end
-- Result: Misaligned data because emu.read expects byte addresses
```

### 12.2 The Fix

```lua
-- CORRECT: VRAM is byte-addressed
for i = 0, 31 do
    tile_data[i + 1] = emu.read(vram_addr + i, emu.memType.snesVideoRam)
end

-- Also valid: use readWord with a byte address
for i = 0, 15 do
    local word = emu.readWord(vram_addr + (i * 2), emu.memType.snesVideoRam)
    tile_data[i * 2 + 1] = word & 0xFF
    tile_data[i * 2 + 2] = (word >> 8) & 0xFF
end
```

### 12.3 How to Detect the Bug

If captured tile data shows every other byte missing/zero, byte-swapped words, or repeating
2-byte patterns, double-check byte addressing and stride. A strictly sequential
`00 01 02 03 ...` pattern usually indicates you're accidentally emitting a loop index or
address counter, not VRAM bytes.

### 12.4 Follow-up Diagnostic: VRAM vs OAM Tile Mapping

- Full VRAM dumps contained tiles that matched the ROM hash database, so VRAM reads and hashing are working.
- OAM-derived tiles from the same capture still produced no hash matches.
- Conclusion: byte-addressing is necessary but not sufficient; focus on OAM tile→VRAM address math
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

- Store **all** candidate ROM locations per hash (now supported in `TileHashDatabase`).
- Tally votes per ROM region/bank across all tiles in a capture.
- Report confidence and ambiguity (e.g., top region vs runner-up).

### 13.6 Voting & Confidence Rules (Recommended)

Define explicit scoring so results are reproducible and ambiguity is visible:

- **Weight by rarity:** for each tile, weight each candidate as `1 / candidate_count`.
  (Tiles that appear everywhere contribute less.)
- **Ignore low-information tiles:** if a tile has ≤2 unique bytes, drop it or cap its weight.
- **Minimum evidence:** require at least `min_matched_tiles >= 4` *and* `score >= 2.0`
  before labeling an offset as "likely".
- **Tie/ambiguity rule:** if top score < `1.25 ×` runner-up *or* top–runner-up < 20%,
  mark result as **ambiguous** and report both.
- **Output:** always report top N offsets with scores, not just the winner.

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
| **VRAM word address** | Internal PPU word address (used in OBSEL/OAM math). Convert with `byte = word * 2`. |
| **ROM offset** | Position in the .sfc file (0x000000-0x3FFFFF for 4MB ROM). |
| **SA-1 CPU address** | Address seen by the SA-1 coprocessor. Banks $C0-$FF map to ROM. |
| **OAM tile index** | Tile number in OAM entry byte 2. Combined with OBSEL + tile index bit 8 for VRAM address. |
| **OBSEL** | $2101 register. Controls sprite tile base address and size modes. |
| **Name base** | OBSEL bits 0-2. Each step = 0x1000 words (8KB). See Section 18 for formula. |
| **Tile index bit 8** | OAM attribute bit 0. Selects the second OAM tile table; add `oam_offset` (words). |
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
| Tile order | Row/column wrap in 16×16 tile grid (applies to all sizes) | See Section 18.4 |
| Combined hash | Not used | We match individual tiles, not sprite groups |

### 17.3 Known Limitations

1. **No flip detection:** A sprite flipped horizontally in-game won't match its unflipped ROM source.
2. **No partial matches:** If VRAM contains corrupted or partially loaded tiles, no match.
3. **ROM coverage:** Only offsets we explicitly extracted are in the database.

---

## 18. OAM TILE → VRAM ADDRESS MATH (CANONICAL)

This is the formula for converting an OAM sprite entry to a VRAM tile address. **The PPU math
operates in word addresses; convert to byte addresses before calling `emu.read`.**

Source of truth: `Mesen2/Core/SNES/Debugger/SnesPpuTools.cpp` (`OamBaseAddress`, `OamAddressOffset`,
`TileAddress` calculation, and tile row/column wrap).

### 18.1 The Formula (Mesen2 Source)

```lua
-- OBSEL ($2101)
local name_base = obsel & 0x07           -- bits 0-2
local name_select = (obsel >> 3) & 0x03  -- bits 3-4

-- PPU state (word addresses)
local oam_base = name_base << 13                     -- OamBaseAddress (words)
local oam_offset = (name_select + 1) << 12           -- OamAddressOffset (words)

-- OAM entry
local use_second_table = (oam_attr & 0x01) ~= 0      -- tile index bit 8
local tile_index = oam_tile                           -- OAM byte 2 (0-255)

local tile_word = (oam_base + (tile_index << 4) + (use_second_table and oam_offset or 0)) & 0x7FFF
local vram_byte = tile_word << 1                      -- byte address for emu.read
```

### 18.2 Worked Example

Given capture data:
- OBSEL = 0x12 (name_base = 2, name_select = 2)
- OAM tile = 0x40 (tile_index = 64)
- OAM attr bit 0 = 1 (use second table)

```
oam_base   = 2 << 13 = 0x4000   (word)
oam_offset = (2 + 1) << 12 = 0x3000  (word)
tile_word  = (0x4000 + (0x40 << 4) + 0x3000) & 0x7FFF
          = (0x4000 + 0x0400 + 0x3000) & 0x7FFF
          = 0x7400
vram_byte  = 0x7400 << 1 = 0xE800
```

### 18.3 Common Mistakes

| Mistake | Symptom | Fix |
|---------|---------|-----|
| Ignoring `name_select` | Off-by-8KB/16KB errors | Use `oam_offset = (name_select + 1) << 12` |
| Treating attr bit 0 as “name table” | Confusing terminology | It is **tile index bit 8** / second table flag |
| Mixing byte/word units | Off-by-2x errors | Compute in words, convert to bytes at end |
| Using `name_base * 0x1000` without `<< 13` | Off-by-2x | `oam_base = name_base << 13` (word units) |

### 18.4 For 16×16 and Larger Sprites

For sprites larger than 8×8, OAM specifies the **top-left tile**. Mesen2 derives subtiles by
wrapping the tile index within a 16×16 tile grid:

```lua
local tiles_w = width / 8
local tiles_h = height / 8
local tile_row = (tile_index >> 4) & 0x0F
local tile_col = tile_index & 0x0F

for ty = 0, tiles_h - 1 do
    local row = (tile_row + ty) & 0x0F
    for tx = 0, tiles_w - 1 do
        local col = (tile_col + tx) & 0x0F
        local subtile_index = (row << 4) | col
        local subtile_word = (oam_base + (subtile_index << 4) + (use_second_table and oam_offset or 0)) & 0x7FFF
        local subtile_byte = subtile_word << 1
        -- Read 32 bytes at subtile_byte
    end
end
```

This row/column wrap logic matches `SnesPpuTools.cpp` and avoids incorrect 32×32 block assumptions.

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

- VRAM byte-addressing for `emu.read(..., snesVideoRam)`
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

*Last Updated: December 30, 2025*
- Further condensed from ~860 to ~817 lines
- Reduced redundancy with MESEN2_LUA_API_LEARNINGS (cross-references instead of duplication)

**DO NOT DELETE - This document contains critical technical discoveries essential for the sprite discovery workflow**
