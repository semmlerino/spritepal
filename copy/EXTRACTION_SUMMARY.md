# King Dedede Sprite Extraction: Complete Summary

**Status:** ✅ WORKING — Reconstruction validated with OBSEL=0x63

**Goal:** Extract pixel-perfect sprites from Kirby Super Star (SNES) using Mesen 2 memory dumps + Python reconstruction

---

## Quick Start

### Method 1: Direct from Mesen Dumps (Recommended)

1. Pause Mesen 2 on desired frame
2. Debug → Memory Viewer → Export:
   - OAM (Sprites) → `*_OAM.dmp`
   - VRAM → `*_VRAM.dmp`
   - CGRAM → `*_CGRAM.dmp`
3. Run reconstruction:
   ```bash
   python scripts/reconstruct_from_dumps.py /path/to/dumps --obsel 0x63 -o output.png
   ```

### Method 2: Lua Capture (Full Pipeline)

1. Load `mesen2_integration/lua_scripts/mesen2_sprite_capture.lua` in Mesen 2
2. Press **C** to capture (or Start+Select on controller)
3. Process JSON output with reconstruction scripts

---

## Key Finding: OBSEL = 0x63

For Kirby Super Star sprite extraction:

| Field | Value | Meaning |
|-------|-------|---------|
| `name_base` | 3 | Sprite tiles at VRAM 0xC000 (byte addr) |
| `name_select` | 0 | No second table offset |
| `size_select` | 3 | 16×16 small / 32×32 large sprites |

**Command:** `--obsel 0x63`

---

## Scripts

### 1. `reconstruct_from_dumps.py` ⭐ PRIMARY

**Location:** `scripts/reconstruct_from_dumps.py`

**Purpose:** Reconstruct sprites directly from Mesen memory dumps (bypasses Lua)

**Usage:**
```bash
# Basic reconstruction
python scripts/reconstruct_from_dumps.py DededeDMP --obsel 0x63 -o frame.png

# With bounding boxes
python scripts/reconstruct_from_dumps.py DededeDMP --obsel 0x63 --bounds -o frame.png
```

**Features:**
- Parses OAM dump (544 bytes: 512 main + 32 high table)
- Reads tiles directly from VRAM dump
- Converts CGRAM palettes (BGR555 → RGB888)
- Handles sprite flips, sizes, priorities
- SNES-accurate draw order (lower OAM ID on top)

---

### 2. `mesen2_sprite_capture.lua` (Lua)

**Location:** `mesen2_integration/lua_scripts/mesen2_sprite_capture.lua`

**Purpose:** Runtime capture inside Mesen 2 emulator

**Hotkeys:**
- **C** = Full capture (sprites + memory dumps)
- **D** = Memory dump only (for verification)
- **Start+Select** = Full capture (controller)

**Patches Applied:**
- **Step A:** OBSEL latch via memory callback ($2101 is write-only)
- **Step B:** Uses `emu.read16` for reliable VRAM reads
- **Step C:** Memory dump helper for Lua vs Mesen comparison

**Output:** JSON file + memory dumps in `mesen2_exchange/`

---

### 3. `compare_memory_dumps.py` (Verification)

**Location:** `scripts/compare_memory_dumps.py`

**Purpose:** Verify Lua captures match Mesen dumps byte-for-byte

**Usage:**
```bash
# Compare directory of dumps
python scripts/compare_memory_dumps.py --dir /path/to/dumps

# Compare specific files
python scripts/compare_memory_dumps.py lua_VRAM.dmp mesen_VRAM.dmp
```

---

## Verified Frame: DededeDMP/Frame 71

### OAM Entries

**Kirby (Palette 0):**
| ID | Position | Tile | Size | Notes |
|----|----------|------|------|-------|
| 5 | (116, 109) | 0x00 | 32×32 | Main body |
| 4 | (132, 109) | 0x02 | 16×16 | Body part |
| 3 | (132, 117) | 0x12 | 16×16 | Body part |
| 0 | (132, 125) | 0x13 | 16×16 | Feet |
| 1 | (124, 125) | 0x04 | 16×16 | ⚠️ Garbage tile |
| 2 | (116, 125) | 0x03 | 16×16 | ⚠️ Garbage tile |

**Dedede (Palette 7):**
| ID | Position | Tile | Size | Notes |
|----|----------|------|------|-------|
| 11 | (232, 89) | 0x60 | 32×32 | Top-left |
| 10 | (248, 89) | 0x62 | 32×32 | Top-right |
| 9 | (232, 105) | 0x64 | 32×32 | Mid-left |
| 8 | (248, 105) | 0x66 | 32×32 | Mid-right |
| 7 | (232, 121) | 0x68 | 32×32 | Bottom-left |
| 6 | (248, 121) | 0x6A | 32×32 | Bottom-right |

### Garbage Tiles

Tiles **0x03** and **0x04** contain remnant VRAM data that appears as noise. The game hides this behind background layers. Filter with:

```python
garbage_tiles = {0x03, 0x04}
clean = [e for e in entries if e.tile not in garbage_tiles]
```

---

## Bugs Fixed (Historical)

### 1. OAM High Table Offset ✅
- **Was:** `0x200` | **Fixed:** `0x0100`
- High table is at byte 512 in OAM dump

### 2. Palette Conversion ✅
- **Was:** `* 255 // 31` | **Fixed:** `<< 3`
- BGR555 to RGB888 uses bit replication

### 3. OBJ Tile Index Math ✅
- **Was:** Linear carry | **Fixed:** Nibble wrapping
- X wraps in low nibble, Y in high nibble, no carry between

### 4. Sprite Draw Order ✅
- **Was:** Priority-based | **Fixed:** OAM ID order
- Lower OAM index always on top within OBJ layer

### 5. Y Coordinate Wrapping ✅
- Y is 8-bit, wraps at 256
- Sprites with y+height > 256 also appear at y-256

---

## Technical Reference

### SNES OAM Structure (544 bytes)

```
Main Table (512 bytes): 128 entries × 4 bytes
  Byte 0: X position (low 8 bits)
  Byte 1: Y position (8 bits)
  Byte 2: Tile index (8 bits)
  Byte 3: Attributes
    Bit 0: Name table (second tile bank)
    Bits 1-3: Palette (0-7)
    Bits 4-5: Priority (0-3)
    Bit 6: Horizontal flip
    Bit 7: Vertical flip

High Table (32 bytes): 128 entries × 2 bits
  Bit 0: X position bit 9 (signed extension)
  Bit 1: Size select (0=small, 1=large)
```

### OBSEL Register ($2101)

```
Bits 0-2: Name base (sprite tile base address)
Bits 3-4: Name select (second table offset)
Bits 5-7: Size select (sprite size mode)

Size modes:
  0: 8×8 / 16×16
  1: 8×8 / 32×32
  2: 8×8 / 64×64
  3: 16×16 / 32×32  ← Kirby Super Star uses this
  4: 16×16 / 64×64
  5: 32×32 / 64×64
  6: 16×32 / 32×64
  7: 16×32 / 32×32
```

### Tile Address Calculation

```python
def get_tile_vram_addr(tile_idx, use_second_table, obsel):
    name_base = obsel & 0x07
    name_sel = (obsel >> 3) & 0x03

    word_addr = (name_base << 13) + (tile_idx << 4)
    if use_second_table:
        word_addr += (name_sel + 1) << 12
    word_addr &= 0x7FFF

    return word_addr << 1  # byte address
```

### 4bpp Planar Tile Format (32 bytes)

```
Bytes 0-15: Bitplanes 0,1 (2 bytes per row × 8 rows)
Bytes 16-31: Bitplanes 2,3 (2 bytes per row × 8 rows)

For each row:
  bp0 = byte[row*2]
  bp1 = byte[row*2 + 1]
  bp2 = byte[16 + row*2]
  bp3 = byte[16 + row*2 + 1]

  pixel[col] = ((bp0 >> (7-col)) & 1) |
               ((bp1 >> (7-col)) & 1) << 1 |
               ((bp2 >> (7-col)) & 1) << 2 |
               ((bp3 >> (7-col)) & 1) << 3
```

---

## Output Files

```
DededeDMP/
├── Dedede_F71_OAM.dmp      # Mesen OAM export (544 bytes)
├── Dedede_F71_VRAM.dmp     # Mesen VRAM export (65536 bytes)
├── Dedede_F71_CGRAM.dmp    # Mesen CGRAM export (512 bytes)
├── screen.jpg              # Reference screenshot
├── FINAL_reconstructed_0x63.png  # Working reconstruction
├── CLEAN_no_garbage.png    # With garbage tiles filtered
└── individual_sprites.png  # Each OAM entry rendered separately
```

---

## Workflow Checklist

- [x] Export OAM/VRAM/CGRAM from Mesen Memory Viewer
- [x] Determine correct OBSEL value (0x63 for Kirby Super Star)
- [x] Run reconstruction script
- [x] Identify and filter garbage tiles if needed
- [x] Verify output matches reference screenshot

---

## Files in This Directory

| File | Purpose |
|------|---------|
| `EXTRACTION_SUMMARY.md` | This documentation |
| `mesen2_sprite_capture.lua` | Backup of Lua capture script |
| `reconstruct_frame.py` | Legacy reconstruction (from JSON) |
| `verify_capture.py` | Tile verification tool |
