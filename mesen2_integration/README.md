# Mesen 2 Sprite Extraction Toolkit

Complete toolkit for tracing and extracting sprites from Kirby Super Star using Mesen 2's debugging features.

## 🎯 Fastest Method: Click-to-Find (sprite_rom_finder.lua v44)

**One-click ROM offset lookup** - no manual breakpoints needed.

### NEW in v44: Bank-Aware Attribution + Palette Dump

**Bank Comparison Fix:**
- Fixed incorrect attribution for sprites not in the FE52 table (like Poppy Bros)
- When different sprites share staging buffer space, attributions are now correctly assigned based on ROM bank
- Poppy Bros sprites now show correct ROM offsets instead of incorrectly inheriting Kirby's attribution

**Palette Dump on Click:**
Clicking a sprite now shows its CGRAM palette colors:
```
OAM palette: 3 (CGRAM $160-$17F)
PALETTE BGR555: 0000 7FFF 5294 3DEF 2D6B 1CE7 0C63 0000 ...
PALETTE RGB[0-7]: #000000 #FFFFFF #A5A5A5 #7B7B7B #5A5A5A #393939 #181818 #000000
```
This lets you capture the exact runtime palette for any sprite to use in SpritePal.

### How it works
```
visible sprite → OAM entry → VRAM tile address → DMA tracking → idx session → ROM offset
```

### NEW in v33: Always-On Automatic Attribution

Instead of clicking sprites one-by-one, v33 can continuously label ALL visible sprites:

- **Press R** - Toggle always-on sprite labels:
  - **Green numbers** = attributed idx (you know the ROM offset)
  - **Red "?"** = unresolved (tiles were loaded before tracking started)
- **Press X** - Cycle filter mode: ALL → NO_HUD → LARGE_ONLY → MOVING
- **LEFT/RIGHT arrows** - Navigate through sprites (logs attribution to console)
- **Auto-watch** - Unresolved sprites automatically log "WATCH RESOLVED" when they reload

The always-on mode uses **proximity clustering** to group multi-OAM sprites (like enemies made of multiple sprite tiles) into single labels.

### Key implementation details (v32-v33)
- **Reset hotkey**: Press `L` to clear VRAM/owner/session history for a fresh capture window
- **Lookback guard**: Unmatched sessions skip lookback attribution to avoid poisoning
- **Unmatched sessions**: Optional sessions for valid DP ptrs not in FE52 table (see `ALLOW_UNMATCHED_DP_PTR`)
- **Session dedup**: Skips duplicate pointer sessions within a short window
- **Safe draw clamps**: OAM boxes and hover highlights are clamped to screen bounds
- **Wider lookback**: Default lookback window raised to 90 frames for slow decode cases
- **Larger staging queue**: Tracks 512 staging DMAs to avoid evicting older uploads
- **Session boundary guard**: Optionally skips lookback DMAs from earlier sessions
- **Crash guards**: All callbacks and `on_frame` are wrapped; errors log a stack trace and disable tracking
- **Safe varargs**: Wrapper forwards callback args safely (fixes Lua vararg error)
- **Delayed activation**: Tracking/UI starts at `ACTIVATE_AT_FRAME` (default 500) to avoid early slowdown
- **Safe state fallback**: `emu.getState()` guarded to avoid early-frame nil crashes
- **Guarded inputs**: OAM reads and mouse state are skipped if unavailable (prevents nil crashes)
- **Multi-slot DP pointer tracking**: Watches 00:0002/0005/0008 (lo/hi/bank) for asset pointer caches
- **Slot-preference attribution**: When multiple sessions overlap, 0x0002 beats 0x0005/0x0008
- **FE52 off-by-one fix**: Prefill loop now clamps to avoid reading past table boundary
- **PPU edge clamp**: Prevents relativeX/Y=1.0 from producing out-of-bounds coords
- **Unmatched sessions impossible**: Deleted ALLOW_UNMATCHED_DP_PTR path entirely (not just off by default)
- **Pre-populated FE52 table**: Reads all ~143 valid idx→ptr entries from ROM at activation (deterministic)
- **Pure VRAM attribution**: Click uses only `vram_owner_map` (no session guessing)
- **O(1) ptr→idx lookup**: Reverse map `ptr_to_idx` for fast resolution (synced in runtime reads too)
- **No stale blanking**: Age is not invalidation - old uploads still show attribution
- **Flip-aware cursor tile**: Handles H-flip/V-flip for multi-tile sprites
- **Click targeting fixes**: Uses `relativeX`/`relativeY` for accurate PPU coordinates
- **X-wrap handling**: Sprites wrapping at screen edge are correctly detected
- **PPU state key casing fix**: Uses correct capitalization (`OamMode`, `OverscanMode`)
- **OAM priority handling**: Respects `EnableOamPriority` + `InternalOamAddress` for correct sprite draw order
- **Overscan mode support**: Detects 239-line mode (was hardcoded to 224)
- **Multi-tile warning**: Warns when looking up sprites >8x8 (attribution is for base tile only)
- **Tuneable parameters**: Session windows and staging ranges documented at top of script
- **SA-1 memType fix**: Uses `sa1Memory` for SA-1 callbacks (not `snesMemory`)
- **VALID_BANKS expansion**: Accepts all banks C0-FF
- **OAM memory type fix**: Uses correct `snesSpriteRam`
- **Multi-channel DMA fix**: Advances VRAM destination per channel when $420B enables multiple channels
- **Multi-candidate picker**: Collects ALL sprites under cursor, sorted by draw order (topmost wins)
- **Candidate cycling**: Scroll wheel or arrow keys to cycle through overlapping sprites
- **HUD ignore toggle**: Filter out HUD sprites (y < 32) with Select button
- **Bounding box overlay**: Toggle with Start button to see all OAM hitboxes
- **DMA reg shadowing**: Captures $4300-$437F writes (post-DMA reads return garbage)
- **VMADD shadowing**: Captures $2116/$2117 writes (reading registers returns garbage)
- **Session queue**: 64-entry queue with 45-frame window (handles SA-1 decode latency)
- **Look-back attribution**: When session starts, attributes DMAs from ~30 frames
- **Persistent owner map**: `vram_owner_map` never purges - attribution survives indefinitely
- **SA-1 full-bank mapping**: `file = (bank - 0xC0) * 0x10000 + addr`
- **Staging-only fallback**: Only uses persistent owner for staging DMAs (prevents BG misattribution)
- **CPU-keyed pending**: Keys pending table reads by CPU to prevent SA-1/SNES interleave
- **Cached debug counts**: Updates table counts every 30 frames for performance
- **Word-based throughout**: No unit conversion foot-guns
- **Strict mode guard**: Catches Lua global variable bugs at runtime

### Usage
```batch
# From spritepal directory, double-click:
run_sprite_rom_finder.bat
```

1. **Wait** for movie to reach gameplay (sprites loading)
   - By default, tracking starts at frame 500 (`ACTIVATE_AT_FRAME` in the script)
2. **Pause** (Space or P) when target sprite is visible
3. **Hover** cursor over target sprite (see candidate list)
4. **Cycle** with scroll wheel or arrows if multiple sprites overlap
5. **Left-click** to lookup ROM offset for selected sprite
6. **Read** the panel and console output:
   - `idx` = asset selector index
   - `ptr` = CPU address (e.g., `E9:E667`)
   - `FILE: 0x0NNNNN` = ROM file offset
   - `OAM palette: N` = palette index (v44)
   - `PALETTE BGR555:` = raw CGRAM colors (v44)
   - `PALETTE RGB:` = converted RGB hex colors (v44)

### Controls
| Input | Action |
|-------|--------|
| Left-click | Lookup ROM source for **selected** sprite |
| Scroll wheel / ↑↓ | Cycle through candidates under cursor |
| R key | Toggle always-on sprite labels (v33) |
| X key | Cycle filter mode: ALL/NO_HUD/LARGE/MOVING (v33) |
| ←/→ (d-pad) | Navigate sprites, log attribution (v33) |
| Select (controller) | Toggle HUD ignore (sprites with y < 32) |
| Start (controller) | Toggle bounding box debug overlay |
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
- v13's look-back attribution (~30 frames) usually catches these
- If still unattributed: the sprite's tiles are very old or from a non-standard path
- v13 staging-only fallback: if a BG/font DMA overwrote the tile, old attribution is hidden
- **Fix**: Let game run until sprite despawns and respawns, then click again

---

## 🎯 Quick Start (Manual Method)

### 1. Direct Extraction (when you have a ROM offset)
```bash
# Extract from a specific ROM offset (from sprite_rom_finder.lua)
uv run python scripts/extract_rom_sprite.py \
    --rom "roms/Kirby Super Star (USA).sfc" \
    --offset 0x3C6EF1 \
    --output extracted_sprites/ \
    --name my_sprite
```

### 2. Batch Extraction (multiple sprites)
```bash
# Process multiple sprites from a file
uv run python mesen2_integration/batch_sprite_extractor.py known_sprites.json
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
# Convert SNES address to ROM offset, then extract
# For SA-1 HiROM (Kirby): file = (bank - 0xC0) * 0x10000 + addr
# Example: $E9:E667 → (0xE9 - 0xC0) * 0x10000 + 0xE667 = 0x29E667

uv run python scripts/extract_rom_sprite.py \
    --rom "roms/Kirby Super Star (USA).sfc" \
    --offset 0x29E667 \
    --output extracted_sprites/
```

## 🛠️ Tools Overview

### `scripts/extract_rom_sprite.py`
Main extraction tool that:
- Decompresses HAL data with exhal
- Converts 4bpp tiles to PNG
- Saves metadata JSON

**Usage:**
```bash
uv run python scripts/extract_rom_sprite.py \
    --rom "roms/Kirby Super Star (USA).sfc" \
    --offset 0x3C6EF1 \
    --output extracted_sprites/ \
    --name sprite_name
```

### `mesen2_integration/batch_sprite_extractor.py`
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
uv run python mesen2_integration/batch_sprite_extractor.py sprites.json
uv run python mesen2_integration/batch_sprite_extractor.py addresses.txt --report my_sprites
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
- Try nearby offsets (±1 to ±16 bytes)
- Verify address with sprite_rom_finder.lua in Mesen 2

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

- [SNES Hardware Facts](../docs/mesen2/00_STABLE_SNES_FACTS.md) - VRAM, OAM, tile formats
- [Kirby SA-1 Mapping](../docs/mesen2/03_GAME_MAPPING_KIRBY_SA1.md) - SA-1 address conversion
- [Architecture Documentation](../docs/architecture.md) - Mesen Integration Subsystem section
- [Data Crystal Wiki](https://datacrystal.tcrf.net/wiki/Kirby_Super_Star) - ROM info
- [SNESdev Wiki](https://snes.nesdev.org/wiki/Memory_map) - SNES memory

## ✨ Example Session

```bash
# 1. Run sprite_rom_finder.lua in Mesen2
# Double-click run_sprite_rom_finder.bat
# Click on sprite -> get ROM offset (e.g., FILE: 0x3C6EF1)

# 2. Extract sprite
$ uv run python scripts/extract_rom_sprite.py \
    --rom "roms/Kirby Super Star (USA).sfc" \
    --offset 0x3C6EF1 \
    --output extracted_sprites/ \
    --name cappy

Decompressing from offset 0x3C6EF1...
Decompressed: 22528 bytes
Raw data saved: extracted_sprites/cappy.bin
PNG saved: extracted_sprites/cappy.png (704 tiles)
Metadata saved: extracted_sprites/cappy_metadata.json

# 3. View results
$ ls extracted_sprites/
cappy.bin  cappy.png  cappy_metadata.json
```

## 🎮 Using Captured Offsets with SpritePal's Embedded Editor

Once you have a ROM offset from sprite_rom_finder.lua, you can open it directly in SpritePal's embedded Sprite Editor:

### Quick Workflow

1. **Run sprite_rom_finder.lua** in Mesen 2 (click on sprite, get offset)
2. **Open SpritePal** - the Mesen 2 captures are loaded automatically
3. **See Recent Captures panel** - shows last 5 clicked offsets
4. **Double-click an offset** → Sprite Editor tab opens with that offset loaded
5. **Edit sprites directly** - Extract, Edit, Inject all in one place

### Features

- **Keyboard shortcut F6**: Jump to last Mesen 2 capture in Sprite Editor
- **Ctrl+3**: Quick switch to Sprite Editor tab
- **Status bar indicator**: Green dot shows when Mesen 2 log watcher is active

### Example

```
┌─────────────────────────────────────────┐
│  SpritePal Main Window                  │
├─────────────────────────────────────────┤
│  Tabs: [ROM] [VRAM] [Sprite Editor]     │
│                                         │
│  Recent Captures:                       │
│  ├─ 0x3C6EF1  ← Double-click here       │
│  ├─ 0x3C5200                            │
│  └─ ...                                 │
│                                         │
│  (Double-click jumps to Sprite Editor   │
│   with offset pre-loaded)               │
└─────────────────────────────────────────┘
```

---

## 🖼️ Runtime Sprite Reconstruction (NEW)

Reconstruct sprites directly from Mesen 2 memory dumps - no ROM offset needed.

### Quick Start

1. **Pause** Mesen 2 on frame with target sprite visible
2. **Export** from Debug → Memory Viewer:
   - OAM (Sprites) → `MySprite_OAM.dmp`
   - VRAM → `MySprite_VRAM.dmp`
   - CGRAM → `MySprite_CGRAM.dmp`
3. **Run** reconstruction:
   ```bash
   python scripts/reconstruct_from_dumps.py /path/to/dumps --obsel 0x63 -o output.png
   ```

### OBSEL Values

| Game | OBSEL | Notes |
|------|-------|-------|
| Kirby Super Star | `0x63` | name_base=3, size_select=3 (16×16/32×32) |

### Example Output

```bash
$ python scripts/reconstruct_from_dumps.py DededeDMP --obsel 0x63 -o dedede.png

OAM:   Dedede_F71_OAM.dmp (544 bytes)
VRAM:  Dedede_F71_VRAM.dmp (65536 bytes)
CGRAM: Dedede_F71_CGRAM.dmp (512 bytes)
OBSEL: 0x63 (size_select=3)
Parsed 128 OAM entries, 12 potentially visible
Drew 12 sprite instances
Saved: dedede.png
```

### Scripts

| Script | Purpose |
|--------|---------|
| `scripts/reconstruct_from_dumps.py` | Reconstruct PNG from OAM/VRAM/CGRAM dumps |
| `scripts/compare_memory_dumps.py` | Verify Lua captures match Mesen exports |
| `lua_scripts/mesen2_sprite_capture.lua` | Runtime capture with OBSEL latch |

### Garbage Tile Filtering

Some frames have remnant VRAM data in unused tiles. Filter specific tiles:
```python
garbage_tiles = {0x03, 0x04}
clean = [e for e in entries if e.tile not in garbage_tiles]
```

### Full Documentation

See `copy/EXTRACTION_SUMMARY.md` for complete technical reference including:
- OAM structure (544 bytes)
- OBSEL register fields
- Tile address calculation
- 4bpp planar format
- All bugs fixed

---

*Toolkit for Kirby Super Star sprite extraction via Mesen 2 debugging*
