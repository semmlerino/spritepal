# Sprite ROM Mapping Guide

This guide explains how to trace SNES sprite tiles from VRAM back to their exact ROM addresses for modification.

## Overview

SNES games store sprite graphics in ROM and load them into VRAM during gameplay. To modify sprites, you need to find where the tile data lives in ROM. This toolset automates that process by:

1. Parsing OAM dumps to identify which tiles belong to a sprite
2. Extracting raw 4bpp tile data from VRAM dumps
3. Searching for exact byte matches in the ROM file
4. Building a complete address map

## Key Concepts

### Data Types

| Type | Description | Size |
|------|-------------|------|
| **4bpp Tile** | 8×8 pixel tile in SNES format | 32 bytes |
| **OAM Entry** | Sprite attributes (position, tile, palette) | 4 bytes + 2 bits |
| **16×16 Sprite** | 4 tiles arranged in 2×2 grid | 128 bytes |

### OAM Structure

Each OAM entry contains:
- **X/Y position**: Screen coordinates
- **Tile index**: Base tile number (0-255)
- **Palette**: Which sprite palette (0-7)
- **Flip flags**: Horizontal/vertical mirroring
- **Size bit**: 8×8 or 16×16 mode

### 16×16 Tile Layout

When a sprite uses 16×16 mode, 4 tiles form the sprite:
```
[t+0 ] [t+1 ]
[t+16] [t+17]
```
Where `t` is the OAM tile index.

### OBSEL Register

The OBSEL register ($2101) determines VRAM base addresses:
- **0x00**: Name base at VRAM $0000 (early boot)
- **0x63**: Name base at VRAM $6000 (Kirby gameplay)

The tool defaults to 0x63 for Kirby Super Star.

## Tools

### reconstruct_sprite.py - Sprite Reconstruction

Reconstructs a complete sprite image from a ROM map, using OAM for layout and CGRAM for colors.

```bash
# Reconstruct with full layout and colors
uv run python scripts/reconstruct_sprite.py \
    DededeDMP/dedede_f71_map.json \
    "roms/Kirby Super Star (USA).sfc" \
    --cgram DededeDMP/Dedede_F71_CGRAM.dmp \
    --oam DededeDMP/Dedede_F71_OAM.dmp \
    --palette 7 \
    -o dedede_f71.png

# Auto-detect CGRAM/OAM from same directory
uv run python scripts/reconstruct_sprite.py map.json rom.sfc -p 7
```

**Output:** PNG image with the sprite reconstructed at 4× scale (configurable with `-s`).

### sprite_rom_mapper.py - Single Frame Mapper

Maps sprites from one VRAM/OAM dump pair to ROM addresses.

```bash
# Basic usage - map palette 7 sprites
uv run python scripts/sprite_rom_mapper.py "roms/Kirby Super Star (USA).sfc" DededeDMP --palette 7

# Map all visible sprites (any palette)
uv run python scripts/sprite_rom_mapper.py roms/Kirby.sfc DededeDMP --all-palettes

# Export to JSON
uv run python scripts/sprite_rom_mapper.py roms/Kirby.sfc DededeDMP -p 7 -o map.json

# Custom OBSEL value
uv run python scripts/sprite_rom_mapper.py roms/Kirby.sfc DededeDMP --obsel 0x00
```

**Output:**
```
=== Sprite ROM Map: Dedede_F71 ===
Palette: 7
VRAM Base: 0x6000
OAM Tiles: [96, 97, 98, 99, 100, 101, ...]
Found: 24/24 tiles

ROM Addresses:
  Range: 0x017361 - 0x017941

  VRAM 0x6600 -> ROM 0x017681
  VRAM 0x6610 -> ROM 0x0176A1
  ...
```

### sprite_rom_batch.py - Multi-Frame Batch Processor

Recursively scans directories for dump files and merges results.

```bash
# Scan all subdirectories
uv run python scripts/sprite_rom_batch.py "roms/Kirby Super Star (USA).sfc" DededeDMP -p 7

# Export merged results
uv run python scripts/sprite_rom_batch.py roms/Kirby.sfc DededeDMP -p 7 -o all_frames.json

# Verbose output (show per-frame details)
uv run python scripts/sprite_rom_batch.py roms/Kirby.sfc DededeDMP -p 7 -v
```

**Output:**
```
Found 2 dump directories
Palette: 7

Processing: DededeDMP... 24 tiles
Processing: archive... 26 tiles

============================================================
MERGED SPRITE ROM MAP - Palette 7
============================================================
Total frames: 2
Total unique ROM offsets: 50
Distinct ROM regions: 4

ROM REGIONS:
  Region 1: 0x017361 - 0x017400 (160 bytes)
    Frames: Dedede_F71
  Region 2: 0x038000 - 0x03839F (928 bytes)
    Frames: Dedede_F2

PER-FRAME SUMMARY:
  Dedede_F71: 24 tiles @ 0x017361-0x017941
  Dedede_F2: 26 tiles @ 0x038000-0x038380
```

## Workflow

### Step 1: Capture Dumps in Mesen 2

1. Load the ROM in Mesen 2
2. Play until the target sprite is visible
3. Pause emulation
4. Open **Debug → Memory Viewer**
5. Export each memory type:
   - **VRAM**: 64KB dump
   - **OAM**: 544 bytes
   - **CGRAM**: 512 bytes (optional, for palette)

### Step 2: Name Files Consistently

Use this naming convention:
```
<Sprite>_F<frame>_VRAM.dmp
<Sprite>_F<frame>_OAM.dmp
<Sprite>_F<frame>_CGRAM.dmp
```

Example:
```
DededeDMP/
├── Dedede_F71_VRAM.dmp
├── Dedede_F71_OAM.dmp
├── Dedede_F71_CGRAM.dmp
└── archive/
    ├── Dedede_F2_VRAM.dmp
    ├── Dedede_F2_OAM.dmp
    └── Dedede_F2_CGRAM.dmp
```

### Step 3: Identify the Sprite's Palette

Look at OAM in Mesen's debugger to find which palette your target sprite uses. For King Dedede in Kirby Super Star, it's palette 7.

### Step 4: Run the Mapper

```bash
# Single frame
uv run python scripts/sprite_rom_mapper.py roms/Kirby.sfc DededeDMP -p 7 -o frame_map.json

# All frames at once
uv run python scripts/sprite_rom_batch.py roms/Kirby.sfc DededeDMP -p 7 -o all_frames.json
```

### Step 5: Use the ROM Addresses

The output tells you exactly where each tile lives in ROM. You can now:
- Modify tiles at those addresses
- Export/import using SpritePal's tools
- Build a complete sprite sheet across all animation frames

## JSON Output Format

### Single Frame (sprite_rom_mapper.py)

```json
{
  "frame_name": "Dedede_F71",
  "palette": 7,
  "vram_base": 24576,
  "oam_tiles": [96, 97, 98, ...],
  "found_count": 24,
  "total_tiles": 24,
  "rom_range": {
    "min": 95073,
    "max": 96577
  },
  "mappings": [
    {
      "vram_word": 26112,
      "vram_byte": 52224,
      "rom_offset": 95873,
      "rom_hex": "0x017681"
    }
  ],
  "not_found": []
}
```

### Merged (sprite_rom_batch.py)

```json
{
  "palette": 7,
  "total_frames": 2,
  "total_unique_offsets": 50,
  "regions": [
    {
      "start": "0x017361",
      "end": "0x017400",
      "size_bytes": 160,
      "frames": ["Dedede_F71"]
    }
  ],
  "frames": [
    { /* single frame format */ }
  ]
}
```

## Important Notes

### Boss Sprites vs Regular Sprites

Kirby Super Star stores sprites differently depending on type:

| Sprite Type | Storage | Tool |
|-------------|---------|------|
| **Boss sprites** (Dedede, etc.) | RAW 4bpp tiles | sprite_rom_mapper.py |
| **Regular sprites** (abilities, enemies) | HAL compressed | FE52 pointer table |

The FE52 pointer table at ROM address 0x00FE52 contains pointers to HAL-compressed sprite data. Use the Lua script's T key export for those.

### Animation Frames at Different ROM Locations

**Key finding:** Different animation frames of the same sprite can be stored at completely different ROM addresses.

Example for King Dedede:
- Frame F71: `0x017361 - 0x017941` (scattered)
- Frame F2: `0x038000 - 0x038380` (contiguous)

To find all animation frames, you need dumps from multiple frames during gameplay.

### Empty Tiles

Tiles that are all zeros (empty) are skipped in the search since they would match many locations in ROM.

### OBSEL Variation

The OBSEL register can change during gameplay:
- **Boot/menus**: Often 0x00
- **Gameplay**: Often 0x63 (Kirby)

If tiles aren't found, try a different OBSEL value with `--obsel 0x00`.

## Troubleshooting

### "0 tiles found"

1. **Wrong palette**: Check OAM in Mesen to verify the sprite's palette
2. **Wrong OBSEL**: Try `--obsel 0x00` or other values
3. **Offscreen sprites**: Use `--all-palettes` to see what's detected

### "Not found in ROM" for some tiles

- **Dynamic tiles**: Some tiles may be generated at runtime
- **Compressed storage**: The sprite might use HAL compression (see FE52 table)
- **DMA from different bank**: Tile data loaded from expansion RAM

### Tiles found at wrong addresses

- **Duplicate patterns**: Simple patterns (solid colors) may match multiple ROM locations
- **Verify visually**: Render the tiles at found addresses to confirm

## Sprite Editor Integration

The ROM map data can be imported directly into SpritePal's sprite editor for editing and reinjection.

### Workflow: Import → Edit → Reinject

1. **Create ROM Map**: Use `sprite_rom_mapper.py` to create a JSON map file
2. **Import in Editor**:
   - Open any sprite in SpritePal's sprite editor
   - Click **Arrange Tiles** to open the arrangement dialog
   - Click **Import ROM Map** and select:
     - The ROM map JSON file
     - The ROM file
     - (Optional) CGRAM dump for accurate palette
3. **Edit Tiles**: Use the editor's drawing tools to modify tiles
4. **Reinject**: Click **Save Raw Tiles** to write modified tiles back to ROM

### Technical Details

- **ArrangementResult.rom_map_data**: Stores ROM offset metadata through the editing workflow
- **RawTileInjector**: Writes individual 4bpp tiles to their mapped ROM addresses
- **Change Detection**: Only modified tiles are written (compares current vs original)
- **Output**: Creates `*_modified.sfc` file (original ROM preserved)

### Example: Editing King Dedede

```bash
# 1. Create ROM map
uv run python scripts/sprite_rom_mapper.py \
  "roms/Kirby Super Star (USA).sfc" \
  DededeDMP --palette 7 -o dedede_f71_map.json

# 2. In SpritePal:
#    - Load any ROM sprite (or create new)
#    - Arrange Tiles → Import ROM Map → select dedede_f71_map.json
#    - Edit the tiles visually
#    - Save Raw Tiles → creates Kirby Super Star (USA)_modified.sfc

# 3. Test in emulator
```

### Code Locations

| Component | File | Purpose |
|-----------|------|---------|
| ROMMapData | `core/mesen_integration/rom_map_importer.py` | Load tiles from ROM using map |
| RawTileInjector | `core/mesen_integration/raw_tile_injector.py` | Write tiles to scattered ROM addresses |
| ArrangementResult | `ui/grid_arrangement_dialog.py` | Pass ROM map through workflow |
| save_raw_tiles_to_rom | `ui/sprite_editor/controllers/rom_workflow_controller.py` | Injection entry point |

## Related Tools

- **sprite_rom_finder.lua**: Mesen 2 Lua script for real-time ROM offset discovery
- **vram_attribution.py**: Python module for loading VRAM→ROM attribution data
- **FE52 pointer table**: Static ROM table for HAL-compressed sprites (T key export)

## Example: Complete Dedede Mapping

```bash
# 1. Map both known frames
uv run python scripts/sprite_rom_batch.py \
  "roms/Kirby Super Star (USA).sfc" \
  DededeDMP \
  --palette 7 \
  --output DededeDMP/dedede_complete_map.json

# 2. View results
cat DededeDMP/dedede_complete_map.json | python -m json.tool | head -50

# Results:
# - F71: 24 tiles @ 0x017361-0x017941
# - F2: 26 tiles @ 0x038000-0x038380
# - 50 unique ROM offsets total
# - 4 distinct ROM regions
```

To map more frames, capture additional dumps and re-run the batch processor.
