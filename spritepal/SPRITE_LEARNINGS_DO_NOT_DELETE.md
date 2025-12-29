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

---

## 3. Savestate Format (MSS Files)

**NOTE**: Savestate formats may vary between Mesen2 versions/builds. These observations
are from our Dec 2025 testing on Mesen2 2.1.1+137ae7c (Windows) and may not apply universally.

### 2.1 File Structure (Observed)
```
Offset 0x00-0x02: "MSS" header (3 bytes)
Offset 0x03: Version byte (0x01 in our samples)
Offset 0x04-0x22: Header/metadata (exact structure unknown)
~Offset 0x23: zlib compressed data typically starts around here
```

### 3.2 Decompression Code

**Note:** This is note-quality code for understanding the format. The header scan heuristic
can false-positive on certain data patterns. Use defensively.

```python
import zlib

def decompress_savestate(path: str) -> bytes | None:
    """Decompress Mesen2 savestate. Returns None if zlib header not found."""
    with open(path, 'rb') as f:
        data = f.read()

    # Scan for zlib header bytes (0x78 followed by valid compression level)
    # In our samples, found around offset 0x23, but scan to be safe
    zlib_start = None
    for i in range(4, min(100, len(data) - 1)):
        if data[i] == 0x78 and data[i+1] in [0x01, 0x5E, 0x9C, 0xDA]:
            zlib_start = i
            break

    if zlib_start is None:
        return None  # No zlib header found

    # Decompress
    decompressed = zlib.decompress(data[zlib_start:])
    return decompressed
```

### 3.3 VRAM Location in Savestate

**⚠️ BUILD-SPECIFIC:** In Mesen2 2.1.1+137ae7c, the decompressed blob appears to contain a raw
VRAM dump where VRAM byte-address equals blob offset. This alignment is **not guaranteed** across
Mesen versions—always verify by checking for known tile patterns.

- VRAM data found at offset 0x6A00 in decompressed savestate (in our build)
- 64KB total VRAM size in SNES
- Target mushroom sprite at VRAM $6A00-$6A80 (byte addresses)

---

## 4. Address Translation Formula

### 4.1 Mesen2 Debugger PRG-ROM View (SPECIAL CASE)

> **🚫 DO NOT BUILD LOGIC ON THIS**
>
> This −$300000 trick is a **Mesen debugger artifact** we used during a single debugging
> session to correlate runtime addresses with file offsets. It is NOT cartridge mapping
> and will break if applied as a general rule.

**What we used it for:** Temporary correlation during interactive debugger sessions to
find where in the ROM file a sprite came from. We then used the real SA-1 mapping
(Section 13.2) for all actual code.

When viewing addresses in Mesen2's PRG-ROM memory type/debugger view:
```
File Offset = Mesen PRG-ROM View Address - 0x300000
```

**Examples we observed (debugger-specific, not generalizable):**
- Mesen PRG view $3D2238 → File offset $0D2238
- Mesen PRG view $57D800 → File offset $27D800

**For real CPU→ROM mapping:** Use Section 13.2 (SA-1 ROM Mapping) instead.

### 4.2 Validation Method
Used exhal tool to confirm sprites exist at calculated ROM offsets

---

## 5. DMA Monitoring Challenges

### 4.1 VRAM Address Reading Issue
**Problem**: Reading VRAM address from $2116/$2117 during DMA always returned $0000

```lua
-- This approach FAILED - always got VRAM $0000
function on_dma_enable_write(address, value)
    local vram_addr_low = emu.read(0x2116, emu.memType.snesMemory)
    local vram_addr_high = emu.read(0x2117, emu.memType.snesMemory)
    local vram_addr = (vram_addr_low | (vram_addr_high << 8)) * 2
    -- vram_addr was always 0!
end
```

### 4.2 Possible Reasons
1. VRAM address registers cleared after DMA
2. Timing issue - need to read before DMA executes
3. DMA might use different addressing mechanism

---

## 6. Mushroom Sprite Findings

### 5.1 Location Confirmed
- **VRAM Address**: $6A00-$6A80
- **Sprite Size**: 16x16 pixels
- **Tile Index**: $A0
- **Palette**: 3

### 5.2 Savestate Comparison Results
```
Before.mss (no mushroom) vs Sprite.mss (mushroom visible):
- 120 bytes differ at VRAM $6A00
- Pattern found: 87 7E 87 7E... (repeating)
- This appears to be fill/initialization data, not actual sprite graphics
```

### 5.3 ROM Search Results
- Searched for 87 7E pattern - not found as graphics data
- Found potential compressed sprite at ROM $3033C4 (131 bytes)
- When extracted with exhal, doesn't match mushroom appearance

---

## 7. Working Code Patterns

### 6.1 Successful Savestate Loading in Lua
```lua
-- Read savestate file
local f = io.open(SAVESTATE_PATH, "rb")
local state_bytes = f:read("*a")
f:close()

-- Load from exec callback
local load_ref
load_ref = emu.addMemoryCallback(function(address, value)
    if not state_loaded then
        state_loaded = true
        emu.loadSavestate(state_bytes)
        -- remove_memory_callback_compat is defined in the Mesen2 Lua API learnings doc
        remove_memory_callback_compat(load_ref, emu.callbackType.exec, 0x8000, 0xFFFF)
    end
end, emu.callbackType.exec, 0x8000, 0xFFFF)
```

### 6.2 Successful Sprite Extraction
```bash
# Using exhal tool
./tools/exhal "roms/Kirby Super Star (USA).sfc" 0x280000 sprite.bin
# Other known good offsets: 0x1B0000 (Kirby), 0x1A0000 (enemies), 0x180000 (items)
```

### 6.3 Sprite Visualization (4bpp SNES format)
```python
def decode_4bpp_tile(tile_data):
    # Each tile is 8x8 pixels, 32 bytes
    pixels = []
    for y in range(8):
        row_offset = y * 2
        byte1 = tile_data[row_offset]
        byte2 = tile_data[row_offset + 1]
        byte3 = tile_data[row_offset + 16]
        byte4 = tile_data[row_offset + 17]
        
        for x in range(8):
            bit = 7 - x
            pixel = ((byte1 >> bit) & 1) | \
                    (((byte2 >> bit) & 1) << 1) | \
                    (((byte3 >> bit) & 1) << 2) | \
                    (((byte4 >> bit) & 1) << 3)
            pixels.append(pixel)
    return pixels
```

---

## 8. Key Files Created

1. **Lua Scripts**:
   - `mushroom_entering_monitor.lua` - Monitors room transition for sprite loading
   - `mushroom_monitor_sprite_state.lua` - Monitors sprite when already visible
   - `vram_write_monitor.lua` - Direct VRAM write monitoring

2. **Python Scripts**:
   - `find_mushroom_in_savestate.py` - Compares savestates to find sprite data
   - `search_rom_for_mushroom.py` - Searches ROM for sprite patterns
   - `visualize_sprite.py` - Converts binary to PNG

3. **Data Files**:
   - `mushroom_sprite_candidate_006A00.bin` - Extracted VRAM data
   - Savestates: `Before.mss`, `Entering.mss`, `Sprite.mss`

---

## 9. Unresolved Challenges

### 8.1 Sprite Loading Mechanism
- The 87 7E pattern suggests we're seeing initialized/cleared VRAM, not the actual sprite
- Need to catch the exact moment when real sprite data is written
- Sprite might be cached elsewhere and copied during screen refresh

### 8.2 DMA Monitoring
- Cannot reliably read VRAM destination address during DMA
- Need alternative approach to track sprite transfers

### 8.3 Compression
- Mushroom sprite likely HAL compressed in ROM
- Need to identify correct compression markers and offsets

---

## 10. Next Steps Recommendations

1. **Try Different Savestate Timing**:
   - Create savestate during sprite animation frame
   - Capture at different points in room transition

2. **Monitor Different Memory Regions**:
   - WRAM where sprites might be cached
   - OAM (Object Attribute Memory) for sprite metadata

3. **Pattern Matching Approach**:
   - Extract actual mushroom pixels from screenshot
   - Search ROM for those specific patterns
   - Consider different compression methods

4. **Manual Analysis**:
   - Use Mesen2 debugger GUI to manually trace sprite loading
   - Set breakpoints on VRAM writes to $6A00

5. **Alternative Extraction** ✅ RESOLVED:
   - ~~Try extracting all potential sprites in $300000-$310000 range~~ **Wrong region**
   - **CORRECT**: Scan **0x180000-0x200000** range - this is where sprites actually are
   - See Section 12 for confirmed working offsets

---

## 11. Critical Insights

1. **The Bridge Problem**: User correctly identified the core issue - "focusing too much on cataloging, and not enough on the bridge between sprite you can see and rom position"

2. **Savestate Approach Works**: Comparing savestates successfully identified where sprite should be in VRAM

3. **Timing is Everything**: Sprite loading happens at specific moments (room transitions, spawn events) - must catch exact timing

4. **Tool Limitations**: Mesen2 Lua API has build-specific quirks; see `docs/mesen2/MESEN2_LUA_API_LEARNINGS_DO_NOT_DELETE.md`

5. **Address Translation (Debugger-Specific)**: The Mesen PRG-ROM view trick (−0x300000) worked for specific debugger sessions; it is not cartridge mapping. See Section 13.2 for the real SA-1 ROM mapping.

---

## 12. CONFIRMED WORKING SPRITE OFFSETS (December 2025)

### 11.1 Successful Sprite Extraction Workflow

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

### 11.2 Known Working ROM Offsets

| Offset | Content | Size | Tiles | Notes |
|--------|---------|------|-------|-------|
| **0x1B0000** | **KIRBY SPRITES** | 11,264 bytes | 352 | Main character animations, faces, poses |
| 0x1A0000 | Enemy/creature sprites | 11,936 bytes | 373 | Small enemies with eyes, animation frames |
| 0x180000 | Items/UI graphics | 17,408 bytes | 544 | Collectibles, small icons |
| 0x190000 | Background tiles | 15,488 bytes | 484 | Trees, terrain, environment |
| 0x1C0000 | Background gradients | 11,392 bytes | 356 | Sky/water textures |
| 0x280000 | Sprites | 1,185 bytes | 37 | Valid sprite data |
| 0xE0000 | Title screen/fonts | 57,290 bytes | 1,790 | "KIRBY" text, UI fonts |

### 11.3 Offsets That Need Care

| Offset | Notes |
|--------|-------|
| 0x0C8000 | Not valid HAL-compressed data at this exact offset |
| 0x0C0000, 0x0CC100, 0x07B500 | Pass validation metrics - may need correct palette/arrangement |

### 11.4 Why Previous "Perfect Score" Extractions Failed

The SpriteFinder validation metrics (coherence, entropy, edges, diversity) detect **structurally sprite-like** data but cannot distinguish real game art from random data that happens to have similar properties.

**Key insight**: Visual verification is essential. Validation scores alone are insufficient.

### 11.5 Recommended Scan Strategy

1. **Start with known good region**: 0x180000-0x200000
2. **Scan in 0x4000 (16KB) steps** within sprite areas
3. **Check extraction size**: Real sprites are typically 10-60KB uncompressed
4. **Verify visually** with grayscale render before applying palettes
5. **Good compression ratios**: 10:1 to 30:1 indicate real sprite data

### 11.6 Palette Reference

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

## 13. KIRBY SUPER STAR SA-1 MEMORY MAPPING (CRITICAL)

### 12.1 SA-1 Overview

Kirby Super Star (USA) uses the **SA-1 enhancement chip**:
- ROM Header map mode: **$23** (SA-1)
- ROM type: **$35** (SA-1 + RAM + Battery)
- ROM size: 4MB (0x400000 bytes)

### 12.2 SA-1 ROM Mapping Formula

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

### 12.3 Verified ROM Access Examples

| ROM Offset | SA-1 CPU Address | Content |
|------------|------------------|---------|
| $000000 | $C00000 | Reset vectors |
| $100000 | $D00000 | Game code |
| $1A0000 | $DA0000 | Enemy sprites |
| $1B0000 | $DB0000 | Kirby sprites |
| $200000 | $E00000 | Backgrounds |
| $300000 | $F00000 | Music/SFX |

### 12.4 Why Standard LoROM Mapping Fails

Standard LoROM uses banks $00-$3F at $8000-$FFFF:
- CPU $368000 should map to ROM $1B0000
- **But this is WRONG for SA-1 games!**

SA-1 games use banks $C0-$FF for direct ROM access, not banks $00-$3F.

### 12.5 Callback Registration for SA-1 ROM Reads

```lua
-- To monitor reads from ROM $1A0000-$1FFFFF:
emu.addMemoryCallback(function(addr, value)
    local rom_offset = ((addr >> 16) - 0xC0) << 16 | (addr & 0xFFFF)
    -- Process rom_offset
end, emu.callbackType.read, 0xDA0000, 0xDFFFFF, emu.memType.snesMemory)
```

---

## 14. SPRITE GRAPHICS DATA FLOW (SA-1 Games)

### 13.1 The Decompression Pipeline

```
ROM (HAL compressed) → SA-1 CPU decompresses → WRAM buffer → DMA → VRAM
     ↑                      ↑                       ↑
   $1B0000            SA-1 coprocessor          $7E2000
   (use sa1Memory)    (runs own code)           (can trace DMA)
```

### 13.2 Why We Can't Easily Track ROM→VRAM

1. **SA-1 coprocessor handles decompression** - runs independently from main CPU
2. **Callbacks on `snesMemory` only capture main CPU activity** - SA-1 ROM reads require
   hooking `sa1Memory` memory type instead (see `docs/mesen2/MESEN2_LUA_API_LEARNINGS_DO_NOT_DELETE.md`)
3. **DMA shows WRAM→VRAM, not ROM source** - by the time DMA happens, data is already decompressed

**Note**: SA-1 activity is not truly "invisible" - it requires using `emu.memType.sa1Memory`
callbacks instead of main CPU callbacks. We did not explore this approach in depth.

### 13.3 DMA Observations

From 900 frames of Kirby Super Star (observed behavior, not a universal law):
```
ROM→VRAM transfers: Only from low offsets ($000060, $0000A4, $000500)
WRAM→VRAM transfers: From $7E2000-$7E20BB range
```

**Observation:** In our captures, VRAM DMA sources were WRAM buffers; ROM offsets aren't
visible at the DMA stage because decompression happens earlier. Other games or SA-1 bank
configurations may behave differently.

### 13.4 Practical Implication

**In this game, we could not trace ROM offsets via DMA monitoring alone.**

Alternative approaches (what we used instead):
1. **Pre-build ROM→VRAM pattern database** (see Section 18)
2. **Pattern match VRAM content against known ROM sprites**
3. **Use tile hash lookup**

---

## 15. WORKING SPRITE CAPTURE SYSTEM

### 14.1 F9 Hotkey Capture Script

Located at: `mesen2_integration/lua_scripts/mesen2_sprite_capture.lua`

**Captures:**
- All 128 OAM entries with positions, tiles, palettes, flips
- VRAM tile data (32 bytes per 8x8 tile)
- Sprite palettes (8 palettes × 16 colors)
- OBSEL settings (sprite sizes, tile base)

### 14.2 Output Format

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

### 14.3 Exchange Directory

Files written to: `mesen2_exchange/`
- `sprite_capture_<timestamp>.json` - Full capture data
- `capture_summary.txt` - Human-readable summary

### 14.4 OAM Entry Structure (SNES)

```
Main table (544 bytes total):
- Bytes 0-511: 128 entries × 4 bytes each
  - Byte 0: X position (low 8 bits)
  - Byte 1: Y position
  - Byte 2: Tile index
  - Byte 3: Attributes (palette, priority, flips, name table)

High table (bytes 512-543):
- 32 bytes for 128 entries (2 bits each)
  - Bit 0: X position bit 9
  - Bit 1: Size (0=small, 1=large)
```

### 14.5 OBSEL Sprite Size Table

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

## 16. TESTRUNNER MODE (Headless Automation)

### 15.1 Command Line Usage

```bash
# From PowerShell (NOT cmd.exe - cmd doesn't work from WSL)
powershell.exe -Command "cd 'C:\path\to\spritepal'; .\tools\mesen2\Mesen2.exe --testrunner 'roms\game.sfc' 'script.lua'"
```

### 15.2 Script Requirements for Testrunner

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

### 15.3 File I/O in Testrunner

```lua
-- MUST use full Windows paths (not WSL paths)
local f = io.open("C:\\path\\to\\output.txt", "w")
f:write("content")
f:close()
```

### 15.4 Headless Screenshot Capture

`emu.takeScreenshot()` returns PNG bytes and works in `--testrunner` mode.

```lua
local png_data = emu.takeScreenshot()
local file = io.open(output_dir .. "\\\\frame_700.png", "wb")
file:write(png_data)
file:close()
```

---

## 17. VRAM WORD-ADDRESSING (CRITICAL BUG FIX)

### 16.1 The Problem

**SNES VRAM is word-addressed (16-bit), NOT byte-addressed!**

```lua
-- WRONG: Treats VRAM as byte-addressed
for i = 0, 31 do
    tile_data[i + 1] = emu.read(vram_addr + i, emu.memType.snesVideoRam)
end
-- Result: Each "byte" is actually a 16-bit word, giving wrong data
```

### 16.2 The Fix

```lua
-- CORRECT: VRAM is word-addressed
local word_addr = math.floor(vram_addr / 2)  -- Convert byte address to word address
for i = 0, 15 do  -- 16 words = 32 bytes
    local word = emu.read(word_addr + i, emu.memType.snesVideoRam)
    tile_data[i * 2 + 1] = word & 0xFF         -- Low byte
    tile_data[i * 2 + 2] = (word >> 8) & 0xFF  -- High byte
end
```

### 16.3 How to Detect the Bug

If captured tile data has a pattern like `00 42 01 53 02 43...` where:
- Every **even** byte (0,2,4,6...) is sequential (0,1,2,3...)
- Every **odd** byte has the actual data

This indicates the loop index leaked into the data due to word-vs-byte confusion.

### 16.4 Follow-up Diagnostic: VRAM vs OAM Tile Mapping

- Full VRAM dumps contained tiles that matched the ROM hash database, so VRAM reads and hashing are working.
- OAM-derived tiles from the same capture still produced no hash matches.
- Conclusion: word-addressing is necessary but not sufficient; focus on OAM tile→VRAM address math
  (OBSEL base, name table bit, size select) rather than VRAM read or hash logic.

---

## 18. TILE HASH DATABASE (IMPLEMENTED)

### 17.1 Purpose

Instead of parsing complex game pointer tables, we:
1. Pre-extract tiles from known ROM offsets (decompress with HAL)
2. Hash each 8x8 tile (32 bytes MD5)
3. Create database mapping hash → (rom_offset, tile_index)
4. When VRAM tiles are captured, hash and lookup to find ROM source

### 17.2 Implementation Files

```
core/mesen_integration/
├── tile_hash_database.py      # Hash-based tile lookup
├── capture_to_rom_mapper.py   # Maps captures to ROM offsets
├── gfx_pointer_table.py       # ROM pointer table analysis (partial)
```

### 17.3 Usage

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
print(f"Primary ROM offset: ${result.primary_rom_offset:06X}")
```

### 17.4 Database Statistics (Kirby Super Star)

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

---

## 19. GFX POINTER TABLE ANALYSIS

### 18.1 Location

- **GFX pointer table**: $FF:0002 (ROM $3F0002)
- **Level pointer table**: $FF:000C (ROM $3F000C)

### 18.2 Structure

The table at $3F0002 contains 16-bit values that appear to be **relative offsets**
within bank $3F, not absolute addresses:

```
$3F0002: 0596 089C 013F 0102 0043 0022 002A 0038
$3F0012: 0040 0044 0056 0068 006A 006C 0076 007C
```

### 18.3 Sprite Address References Found

24-bit pointers to sprite banks exist throughout the ROM. Examples at $040A4A:

```
$040A4A: CPU $DA0000 -> ROM $1A0000 (Enemy sprites)
$040A56: CPU $DC0000 -> ROM $1C0000 (Backgrounds)
$0409B4: CPU $D80000 -> ROM $180000 (Items/UI)
```

### 18.4 Limitation

**No clean mapping from "sprite ID" → ROM offset exists in the pointer table.**
The game uses complex graphics loading via SA-1 coprocessor that is not easily traced.

The tile hash database approach (Section 18) is more practical.

---

## 20. ADDITIONAL SPRITE OFFSETS (DISCOVERED)

### 19.1 Extra Sprite Blocks

| ROM Offset | Size (bytes) | Tiles | Notes |
|------------|--------------|-------|-------|
| $110000 | 3,696 | 115 | Valid HAL data |
| $120000 | 2,952 | 92 | Valid HAL data |
| $140000 | ~3,000 | ~90 | Valid HAL data |

### 19.2 How to Add to Database

```python
additional_offsets = [
    (0x110000, "Extra sprites 1"),
    (0x120000, "Extra sprites 2"),
]
db.build_database(additional_offsets=additional_offsets)
```

---

## 21. COMPLETE WORKFLOW

### 20.1 Setup (One-time)

1. Run `TileHashDatabase.build_database()` on the ROM
2. Save database JSON for reuse

### 20.2 During Gameplay

1. Run Mesen 2 with `mesen2_sprite_capture.lua`
2. Press **F9** to capture visible sprites
3. Lua writes `sprite_capture.json` to exchange directory

### 20.3 In SpritePal

1. Load `sprite_capture.json` with `MesenCaptureParser`
2. Use `CaptureToROMMapper` to find ROM offsets
3. Extract and render using `CaptureRenderer`
4. Display with actual palettes from CGRAM capture

---

## 22. GLOSSARY

Quick reference for terms used throughout this document. See Section 2 for address conventions.

| Term | Definition |
|------|------------|
| **VRAM byte address** | Offset in VRAM as bytes (0x0000-0xFFFF). What you see in hex dumps. |
| **VRAM word address** | Index for `emu.read(addr, snesVideoRam)`. `word = byte / 2`. |
| **ROM offset** | Position in the .sfc file (0x000000-0x3FFFFF for 4MB ROM). |
| **SA-1 CPU address** | Address seen by the SA-1 coprocessor. Banks $C0-$FF map to ROM. |
| **OAM tile index** | Tile number in OAM entry, relative to OBSEL name base. |
| **OBSEL** | $2101 register. Controls sprite tile base address and size modes. |
| **Name base** | OBSEL bits 0-2. Tile address = `(name_base << 13) + (tile_index << 4)`. |
| **Name table bit** | OAM attribute bit 0. Adds 0x2000 words to tile address when set. |
| **Size select** | OBSEL bits 5-7. Determines small/large sprite dimensions. |
| **4bpp tile** | 4 bits per pixel, 8×8 pixels, 32 bytes. Standard SNES sprite format. |
| **HAL compression** | Proprietary compression used by HAL Laboratory games. |

---

## 23. TILE HASH DATABASE ASSUMPTIONS

The tile hash database (Section 18) was built with these assumptions. Violating them
produces hash mismatches.

### 22.1 Hash Computation

| Property | Value | Notes |
|----------|-------|-------|
| Hash algorithm | MD5 | Fast, sufficient for tile matching |
| Input format | Raw 32-byte 4bpp planar data | As extracted by exhal, no reordering |
| Flip normalization | **None** | Horizontally/vertically flipped tiles have different hashes |
| Palette independence | **Yes** | Hashes ignore palette; same tile with different palette = same hash |

### 22.2 Multi-Tile Sprites

| Property | Value | Notes |
|----------|-------|-------|
| 16×16 sprites | Hashed as 4 separate 8×8 tiles | Each tile in the 2×2 grid is independent |
| Tile order | Top-left, top-right, bottom-left, bottom-right | OAM order, not left-to-right scan |
| Combined hash | Not used | We match individual tiles, not sprite groups |

### 22.3 Known Limitations

1. **No flip detection:** A sprite flipped horizontally in-game won't match its unflipped ROM source.
2. **No partial matches:** If VRAM contains corrupted or partially loaded tiles, no match.
3. **ROM coverage:** Only offsets we explicitly extracted are in the database.

---

*Last Updated: December 29, 2025*
- Added Address & Units Rules section (Section 2)
- Added glossary (Section 22)
- Added tile hash database assumptions (Section 23)
- Strengthened warnings throughout (PRG-ROM view, savestate format, DMA observations)
- Fixed savestate decompression code quality

**DO NOT DELETE - This document contains critical technical discoveries essential for the sprite discovery workflow**
