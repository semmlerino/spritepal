# Mesen 2 Sprite Extraction Toolkit

Complete toolkit for tracing and extracting sprites from Kirby Super Star using Mesen 2's debugging features.

## 🎯 Fastest Method: Click-to-Find (sprite_rom_finder.lua v17)

**One-click ROM offset lookup** - no manual breakpoints needed.

### How it works
```
visible sprite → OAM entry → VRAM tile address → DMA tracking → idx session → ROM offset
```

### Key implementation details (v17)
- **OAM memory type fix**: Uses correct `snesSpriteRam` (not `snesOam` which didn't exist, causing wrong reads)
- **Multi-channel DMA fix**: Advances VRAM destination per channel when $420B enables multiple channels
- **Multi-candidate picker**: Collects ALL sprites under cursor, sorted by OAM index (topmost wins)
- **Candidate cycling**: Scroll wheel or arrow keys to cycle through overlapping sprites
- **HUD ignore toggle**: Filter out HUD sprites (y < 32) with Select button
- **Bounding box overlay**: Toggle with Start button to see all OAM hitboxes
- **DMA reg shadowing**: Captures $4300-$437F writes (post-DMA reads return garbage)
- **VMADD shadowing**: Captures $2116/$2117 writes (reading registers returns garbage)
- **Session queue**: 64-entry queue with 45-frame window (handles SA-1 decode latency)
- **Look-back attribution**: When session starts, attributes DMAs from F-300 frames
- **Persistent owner map**: `vram_owner_map` never purges - attribution survives indefinitely
- **SA-1 full-bank mapping**: `file = (bank - 0xC0) * 0x10000 + addr` (v12 fix for E9:3AEB etc)
- **Staging-only fallback**: Only uses persistent owner for staging DMAs (prevents BG misattribution)
- **CPU-keyed pending**: Keys pending table reads by CPU to prevent SA-1/SNES interleave
- **Cached debug counts**: Updates table counts every 30 frames for performance
- **No unit-mismatch fallback**: Word-based throughout (v14 - removed v>>1/v<<1 foot-gun)
- **No vram_upload_map rewrite**: Look-back sets dma.* directly (v14 - avoids tagging wrong DMA)
- **Strict mode guard**: Catches Lua global variable bugs at runtime

### Usage
```batch
# From spritepal directory, double-click:
run_sprite_rom_finder.bat
```

1. **Wait** for movie to reach gameplay (sprites loading)
2. **Pause** (Space or P) when target sprite is visible
3. **Hover** cursor over target sprite (see candidate list)
4. **Cycle** with scroll wheel or arrows if multiple sprites overlap
5. **Left-click** to lookup ROM offset for selected sprite
6. **Read** the panel and console output:
   - `idx` = asset selector index
   - `ptr` = CPU address (e.g., `E9:E667`)
   - `FILE: 0x0NNNNN` = ROM file offset

### Controls
| Input | Action |
|-------|--------|
| Left-click | Lookup ROM source for **selected** sprite |
| Scroll wheel / ↑↓ | Cycle through candidates under cursor |
| Select button | Toggle HUD ignore (sprites with y < 32) |
| Start button | Toggle bounding box debug overlay |
| Right-click | Clear info panel |

### Selecting the right sprite (v15)
When you click, the picker collects ALL sprites whose bounding box contains your cursor, sorted by OAM index (highest = topmost = drawn last). The **topmost** sprite is selected by default.

If you keep hitting HUD/ability icons instead of enemies:
1. **Press Select** to enable HUD ignore (filters out y < 32)
2. **Press Start** to see bounding boxes and verify enemy hitboxes are correct
3. **Use scroll wheel** to cycle through overlapping sprites

### Debug info (top-right corner)
- `(x,y)` - mouse coordinates
- `spr:N` - visible sprite count
- `vram:N` - tracked VRAM uploads
- `f:N` - frame count
- `idx:N` - entries in idx_database (table reads working?)
- `ses:N` - sessions in queue (DP writes matching?)
- `own:N` - VRAM words with persistent attribution
- `HUD:OFF` / `BBOX:ON` - toggle states

### Technical details
- **SA-1 full-bank mapping**: `file = (bank - 0xC0) * 0x10000 + addr` (full 64KB banks)
- **Session tracking**: Watches `01:FE52` table reads and `00:0002` DP writes
- **DMA attribution**: Only tags staging WRAM (7E:2000-2FFF) → VRAM transfers
- **VMADD shadow**: Captures $2116/$2117 writes (register readback is unreliable)
- **History**: Persistent (no purge) - tiles may be loaded once and reused

### If "No attribution" appears
- Sprite tiles were uploaded before any idx session was created
- v13's look-back attribution (300 frames) usually catches these
- If still unattributed: the sprite's tiles are very old or from a non-standard path
- v13 staging-only fallback: if a BG/font DMA overwrote the tile, old attribution is hidden
- **Fix**: Let game run until sprite despawns and respawns, then click again

---

## 🎯 Quick Start (Manual Method)

### 1. Interactive Guided Workflow
```bash
python trace_sprite_guide.py
```
This walks you through the entire process step-by-step.

### 2. Direct Extraction (when you have a SNES address)
```bash
# Extract from a specific SNES address
python mesen2_sprite_extractor.py $95:B000

# Scan nearby if exact offset fails
python mesen2_sprite_extractor.py $95:B000 --scan
```

### 3. Batch Extraction (multiple sprites)
```bash
# Process multiple sprites from a file
python batch_sprite_extractor.py known_sprites.json
```

## 📖 Complete Workflow

### Step 1: Find Sprite in Game
1. Launch Kirby Super Star in Mesen 2
2. Navigate to where your target sprite appears
3. **Pause** when sprite is visible (F5)

### Step 2: Locate in VRAM
1. Open **Tools > Tile Viewer** (Ctrl+Shift+T)
2. Select "Type: Sprite"
3. Click on your sprite's tiles
4. Note the VRAM address (e.g., $1E00)

### Step 3: Set VRAM Breakpoint
1. Open **Debug > Debugger** (Ctrl+D)
2. Add breakpoint:
   - Memory Type: VRAM
   - Address: Your VRAM address
   - Check: Write only

### Step 4: Trigger Loading
1. Reset to before sprite appears
2. Resume execution (F5)
3. Debugger breaks when sprite loads

### Step 5: Find Source Address
Look for one of these patterns:

**Direct Store:**
```asm
LDA $95:B000,X  ; Source address
STA $2118       ; Write to VRAM
```

**DMA Transfer (common):**
```asm
STA $420B       ; DMA enable
```
Check DMA registers:
- $4304: Bank (XX)
- $4302-03: Address (YYYY)
- Combined: $XX:YYYY

### Step 6: Extract Sprite
```bash
python mesen2_sprite_extractor.py $XX:YYYY
```

## 🛠️ Tools Overview

### `mesen2_sprite_extractor.py`
Main extraction tool that:
- Converts SNES addresses to ROM offsets
- Decompresses HAL data with exhal
- Converts 4bpp tiles to PNG
- Supports nearby offset scanning

**Usage:**
```bash
python mesen2_sprite_extractor.py $95:B000 [--scan] [--range 32]
```

### `trace_sprite_guide.py`
Interactive guide that:
- Walks through each debugging step
- Validates inputs
- Saves trace logs
- Launches extractor automatically

**Usage:**
```bash
python trace_sprite_guide.py
# Follow the prompts
```

### `batch_sprite_extractor.py`
Batch processor that:
- Extracts multiple sprites at once
- Generates HTML report with previews
- Saves JSON results

**Input formats:**

JSON:
```json
[
  {"name": "Cappy", "address": "$95:B000", "notes": "Enemy"},
  {"name": "Kirby", "address": "$C0:0000", "notes": "Hero"}
]
```

Text:
```
$95:B000 Cappy # Enemy sprite
$C0:0000 Kirby # Main character
```

**Usage:**
```bash
python batch_sprite_extractor.py sprites.json
python batch_sprite_extractor.py addresses.txt --report my_sprites
```

## 📊 Known Sprites

See `known_sprites.json` for verified sprite locations:
- Kirby main graphics: $98:0000 (0x0C0000)
- Various pack table entries
- Placeholders for sprites to be found

## 🔧 Technical Details

### SNES Address Formats
- Mesen 2: `$XX:YYYY`
- Continuous: `XXYYYY`
- With prefix: `0xXXYYYY`

### LoROM Conversion
```python
ROM_offset = (Bank & 0x7F) * 0x8000 + (Address - 0x8000)
```

### HAL Compression
- Tool: `exhal` (ExHAL decompressor)
- Format: Custom HAL Laboratory compression
- Limit: 64KB default (some sprites larger)

### 4bpp Tile Format
- 32 bytes per 8×8 tile
- 4 bits per pixel (16 colors)
- Converter: `snes4bpp_to_png.py`

## 📁 Output Structure
```
extracted_sprites/
├── sprite_XXXXXX.bin     # Decompressed binary
├── sprite_XXXXXX.png     # Converted image
├── trace_logs/           # Debug session logs
└── reports/              # Batch extraction reports
    ├── report.json
    └── report.html
```

## 🐛 Troubleshooting

### "Decompressed to 0 bytes"
- Invalid compressed data at offset
- Try `--scan` to search nearby
- Verify address with Mesen 2

### "Output would exceed 64KB"
- Some sprites are > 64KB
- May need modified exhal
- Or split extraction

### "Can't find sprite in VRAM"
- Ensure sprite is on-screen
- Check Sprite vs Background tiles
- Try OAM Viewer for sprite info

### "Breakpoint doesn't trigger"
- Sprite may already be loaded
- Reset to before sprite appears
- Check VRAM range is correct

## 📚 References

- [KirbyTrace.md](../KirbyTrace.md) - Detailed tracing methodology
- [Data Crystal Wiki](https://datacrystal.tcrf.net/wiki/Kirby_Super_Star) - ROM info
- [SNESdev Wiki](https://snes.nesdev.org/wiki/Memory_map) - SNES memory

## ✨ Example Session

```bash
# 1. Use guided workflow
$ python trace_sprite_guide.py
> Which sprite? Cappy
> VRAM address? $1E00
> SNES address found? $95:B000

# 2. Extract sprite
$ python mesen2_sprite_extractor.py $95:B000
ROM loaded: Kirby Super Star (USA).sfc (4,194,304 bytes)
SNES Address: $95:B000
ROM Offset: 0x0AB000
Extracting from ROM offset 0x0AB000...
✓ Decompressed 2,048 bytes (64 tiles)
✓ Created sprite_0AB000.png

# 3. View results
$ ls extracted_sprites/
sprite_0AB000.bin  sprite_0AB000.png  trace_logs/
```

---

*Toolkit for Kirby Super Star sprite extraction via Mesen 2 debugging*