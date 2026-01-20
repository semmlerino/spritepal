# SNES Sprite Reconstruction Workflow

**Author:** Claude (with user guidance)
**Date:** January 2026
**Status:** Validated and Working

---

## Overview

This document details the exact approach and workflow for extracting and reconstructing SNES sprites from runtime memory dumps, developed through iterative debugging of King Dedede sprite extraction from Kirby Super Star.

---

## The Problem

**Goal:** Render pixel-perfect sprites as they appear in-game, using emulator memory state.

**Challenge:** SNES sprite rendering involves multiple interacting systems:
- OAM (Object Attribute Memory) defines sprite positions, sizes, attributes
- VRAM (Video RAM) stores tile graphics data
- CGRAM (Color RAM) stores palette colors
- OBSEL ($2101) configures tile addressing and sprite sizes

Without understanding ALL of these correctly, reconstruction produces garbage.

---

## Approach: Dump-First Debugging

### Philosophy

Instead of writing a Lua capture script and hoping it works, we:

1. **Export memory directly from Mesen's Memory Viewer** (ground truth)
2. **Write Python reconstruction against these dumps** (validate logic)
3. **Only then** verify Lua captures match the dumps

This separates "capture correctness" from "reconstruction correctness" - when something breaks, you know which half to debug.

### Why This Works

- Mesen's Memory Viewer exports are **guaranteed correct** (it's the emulator's own view)
- Python reconstruction can be debugged with print statements, breakpoints, etc.
- Once reconstruction works against dumps, Lua capture bugs become obvious (dumps don't match)

---

## Step-by-Step Workflow

### Step 1: Capture Ground Truth Dumps

1. **Launch game in Mesen 2**, navigate to frame with target sprite
2. **Pause emulation** (Space or F5)
3. **Open Debug → Memory Viewer**
4. **Export each memory type:**

   | Memory Type | Menu Selection | Typical Size | Filename Pattern |
   |-------------|----------------|--------------|------------------|
   | OAM | "OAM (Sprites)" | 544 bytes | `*_OAM.dmp` |
   | VRAM | "Video RAM" | 65536 bytes | `*_VRAM.dmp` |
   | CGRAM | "CG RAM" | 512 bytes | `*_CGRAM.dmp` |

5. **Take a screenshot** for visual reference

### Step 2: Determine OBSEL Value

OBSEL ($2101) is critical - it controls:
- **name_base** (bits 0-2): Where sprite tiles start in VRAM
- **name_select** (bits 3-4): Second tile table offset
- **size_select** (bits 5-7): Which sprite size mode

**Method 1: Trial and error**
```bash
for obsel in 0x00 0x20 0x40 0x60 0x02 0x22 0x42 0x62 0x03 0x23 0x43 0x63; do
    python scripts/reconstruct_from_dumps.py dumps/ --obsel $obsel -o test_$obsel.png
done
# Visually inspect outputs to find which produces recognizable sprites
```

**Method 2: Check Mesen's PPU state**
- Debug → PPU Viewer shows current OBSEL
- Or use Lua script with OBSEL latch (Step A in our patches)

**Kirby Super Star uses OBSEL = 0x63:**
- name_base = 3 → tiles at VRAM word address 0x6000 (byte 0xC000)
- size_select = 3 → 16×16 small / 32×32 large

### Step 3: Run Reconstruction

```bash
python scripts/reconstruct_from_dumps.py /path/to/dumps --obsel 0x63 -o output.png
```

**What the script does:**

1. **Parse OAM dump** (544 bytes):
   - Main table: 128 entries × 4 bytes = 512 bytes
   - High table: 128 entries × 2 bits = 32 bytes (at offset 0x200)

2. **For each OAM entry, extract:**
   - X position (9-bit signed)
   - Y position (8-bit)
   - Tile index (8-bit)
   - Attributes: palette, priority, flips, name table, size

3. **Calculate sprite dimensions** from OBSEL size_select + entry's size bit

4. **For multi-tile sprites, iterate tiles** using SNES nibble wrapping:
   ```python
   base_x = tile & 0x0F
   base_y = (tile >> 4) & 0x0F
   for ty in range(tiles_y):
       for tx in range(tiles_x):
           tile_x = (base_x + tx) & 0x0F  # Wrap in low nibble
           tile_y = (base_y + ty) & 0x0F  # Wrap in high nibble
           tile_idx = (tile_y << 4) | tile_x
   ```

5. **Calculate VRAM address** for each tile:
   ```python
   word_addr = (name_base << 13) + (tile_idx << 4)
   if use_second_table:
       word_addr += (name_select + 1) << 12
   byte_addr = (word_addr & 0x7FFF) << 1
   ```

6. **Read 32 bytes of 4bpp tile data** from VRAM dump

7. **Decode 4bpp planar format:**
   ```python
   for row in range(8):
       bp0 = tile_data[row * 2]
       bp1 = tile_data[row * 2 + 1]
       bp2 = tile_data[16 + row * 2]
       bp3 = tile_data[16 + row * 2 + 1]
       for col in range(8):
           bit = 7 - col
           pixel = ((bp0 >> bit) & 1) |
                   (((bp1 >> bit) & 1) << 1) |
                   (((bp2 >> bit) & 1) << 2) |
                   (((bp3 >> bit) & 1) << 3)
   ```

8. **Apply palette** from CGRAM:
   - Sprite palettes are at CGRAM $100-$1FF (8 palettes × 16 colors × 2 bytes)
   - Convert BGR555 to RGB888: `r = (bgr & 0x1F) << 3`

9. **Handle flips** (H/V) by reversing pixel/row order

10. **Composite sprites** in OAM ID order (lower ID = on top)

### Step 4: Identify and Filter Garbage

Some OAM entries may reference tiles containing remnant VRAM data:

```bash
# Render each sprite individually
python -c "
from scripts.reconstruct_from_dumps import *
# ... render each entry to separate image
"
```

Identify garbage tiles visually, then filter:
```python
garbage_tiles = {0x03, 0x04}  # Frame-specific
clean = [e for e in entries if e.tile not in garbage_tiles]
```

### Step 5: Verify Lua Capture (Optional)

Once dump-based reconstruction works, verify Lua captures match:

```bash
# Run Lua script, press D to dump memory
# Compare against Mesen exports
python scripts/compare_memory_dumps.py --dir /path/to/both/dumps
```

If dumps match → Lua capture is correct
If dumps differ → Debug Lua memory reading

---

## Key Technical Details

### OAM Structure (544 bytes)

```
Offset 0x000-0x1FF: Main table (512 bytes)
  Entry N at offset N*4:
    Byte 0: X low (bits 0-7)
    Byte 1: Y (8 bits, wraps at 256)
    Byte 2: Tile index (8 bits)
    Byte 3: Attributes
      Bit 0: Name table (0=first, 1=second)
      Bits 1-3: Palette (0-7)
      Bits 4-5: Priority (0-3)
      Bit 6: Horizontal flip
      Bit 7: Vertical flip

Offset 0x200-0x21F: High table (32 bytes)
  Entry N uses 2 bits at:
    Byte: 0x200 + (N / 4)
    Bit position: (N % 4) * 2
      Bit 0: X bit 9 (for signed X: if set, X -= 512)
      Bit 1: Size (0=small, 1=large per OBSEL)
```

### OBSEL Register ($2101)

```
Bits 0-2: name_base
  Sprite tile base = name_base << 13 (word address)

Bits 3-4: name_select
  Second table offset = (name_select + 1) << 12 (words)

Bits 5-7: size_select
  0: 8×8 / 16×16
  1: 8×8 / 32×32
  2: 8×8 / 64×64
  3: 16×16 / 32×32  ← Kirby Super Star
  4: 16×16 / 64×64
  5: 32×32 / 64×64
  6: 16×32 / 32×64
  7: 16×32 / 32×32
```

### SNES Sprite Rendering Rules

1. **Draw order:** Lower OAM index is ALWAYS on top (within OBJ layer)
   - Priority bits only affect OBJ vs BG layering

2. **Y wrapping:** Y is 8-bit, wraps at 256
   - Sprite at Y=250 with height 32 also appears at Y=-6

3. **Tile indexing:** No carry between nibbles
   - Tile 0x1F + 1 horizontal = 0x10 (not 0x20)
   - Tile 0xF0 + 1 vertical = 0x00 (not 0x100)

4. **Transparency:** Color index 0 is always transparent

### 4bpp Planar Tile Format (32 bytes per 8×8 tile)

```
Bytes 0-15:  Bitplanes 0 and 1 (interleaved, 2 bytes per row)
Bytes 16-31: Bitplanes 2 and 3 (interleaved, 2 bytes per row)

Row R:
  BP0 = byte[R*2]
  BP1 = byte[R*2 + 1]
  BP2 = byte[16 + R*2]
  BP3 = byte[16 + R*2 + 1]

Pixel at column C:
  bit = 7 - C
  index = ((BP0 >> bit) & 1) |
          ((BP1 >> bit) & 1) << 1 |
          ((BP2 >> bit) & 1) << 2 |
          ((BP3 >> bit) & 1) << 3
```

### BGR555 to RGB888 Conversion

```python
def bgr555_to_rgb888(bgr555):
    r = (bgr555 & 0x1F) << 3         # Bits 0-4 → R
    g = ((bgr555 >> 5) & 0x1F) << 3  # Bits 5-9 → G
    b = ((bgr555 >> 10) & 0x1F) << 3 # Bits 10-14 → B
    return (r, g, b)
```

Note: `<< 3` is bit replication (RRRRR → RRRRR000), NOT `* 255 // 31`.

---

## Bugs Encountered and Fixed

### Bug 1: OAM High Table Offset
- **Symptom:** X positions completely wrong
- **Cause:** Read high table at 0x200 instead of 0x0100 relative to OAM base
- **Fix:** High table is at byte 512 (0x200) in the 544-byte dump

### Bug 2: Palette Color Conversion
- **Symptom:** Colors slightly off (255 vs 248)
- **Cause:** Used `* 255 // 31` instead of `<< 3`
- **Fix:** Use bit shift for proper bit replication

### Bug 3: Tile Index Carry
- **Symptom:** Multi-tile sprites scrambled
- **Cause:** Linear math allowed carry from X nibble to Y nibble
- **Fix:** Wrap X and Y independently within their nibbles

### Bug 4: Sprite Draw Order
- **Symptom:** Sprites layered incorrectly
- **Cause:** Sorted by priority instead of OAM index
- **Fix:** Lower OAM index always on top

### Bug 5: Wrong OBSEL Value
- **Symptom:** Tiles from wrong VRAM region
- **Cause:** Assumed OBSEL=0x62, actual was 0x63
- **Fix:** Trial different OBSEL values or capture from PPU state

---

## File Reference

| File | Purpose |
|------|---------|
| `scripts/reconstruct_from_dumps.py` | Main reconstruction from Mesen dumps |
| `scripts/compare_memory_dumps.py` | Verify Lua vs Mesen dumps match |
| `mesen2_integration/lua_scripts/mesen2_sprite_capture.lua` | Runtime capture with OBSEL latch |
| `copy/EXTRACTION_SUMMARY.md` | Quick reference documentation |

---

## Example Session

```bash
# 1. Export dumps from Mesen (OAM, VRAM, CGRAM) to MySprite/

# 2. Find correct OBSEL (if unknown)
for obsel in 0x60 0x61 0x62 0x63; do
    python scripts/reconstruct_from_dumps.py MySprite/ --obsel $obsel -o test_$obsel.png
done
# → 0x63 produces recognizable output

# 3. Generate final reconstruction
python scripts/reconstruct_from_dumps.py MySprite/ --obsel 0x63 -o sprite.png

# 4. (Optional) Render with bounds to debug positioning
python scripts/reconstruct_from_dumps.py MySprite/ --obsel 0x63 --bounds -o debug.png

# 5. (Optional) Identify garbage tiles
python -c "
from scripts.reconstruct_from_dumps import *
# Render each OAM entry individually...
"
# → Tiles 0x03, 0x04 contain garbage

# 6. Filter and regenerate if needed
```

---

## Lessons Learned

1. **Dump first, script second** — Ground truth dumps eliminate guesswork
2. **OBSEL is critical** — Wrong value = tiles from wrong VRAM region
3. **SNES has quirks** — Nibble wrapping, Y wrap at 256, OAM ID ordering
4. **Garbage happens** — VRAM contains remnants; filter or accept
5. **Bit replication matters** — `<< 3` not `* 255 // 31` for color conversion

---

*Document created during Kirby Super Star King Dedede extraction project*
