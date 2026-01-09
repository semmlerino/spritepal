# Mesen-S Sprite Finder for SpritePal

## Overview

The Mesen-S Sprite Finder is a Lua script that automates the complex process of finding ROM offsets for sprites you see in-game. Instead of manually using debuggers and calculating addresses, you can simply point at a sprite and capture its ROM offset instantly.

## Features

- **Real-time sprite tracking** - Hover over any sprite to see its data
- **DMA monitoring** - Automatically tracks graphics loading from ROM to VRAM
- **ROM offset calculation** - Converts SNES addresses to ROM file offsets
- **HAL compression detection** - Identifies Kirby game compression
- **Visual overlay** - Shows sprite boundaries and information
- **Export capability** - Save sprite maps for use in SpritePal

## Installation

1. Place `mesen_sprite_finder_corrected.lua` in your Mesen-S scripts folder
2. Load your ROM in Mesen-S
3. Go to **Debug → Script Window**
4. Click **File → Open Script** and select the script
5. The overlay will appear on screen

## Usage Guide

### Basic Workflow

1. **Start the game** - Load your ROM and play to the sprite you want
2. **Hover mouse** - Move cursor over the desired sprite
3. **Wait for DMA** - If no ROM offset shown, trigger sprite animation
4. **Capture (F9)** - Press F9 to capture the sprite's ROM offset
5. **Save (S)** - Press S to export all captured sprites to console
6. **Use in SpritePal** - Copy the ROM offset and paste into SpritePal

### Controls

| Key | Action |
|-----|--------|
| **F9** | Capture sprite under cursor |
| **S** | Save sprite map to console log |
| **F10** | Toggle overlay on/off |
| **Mouse** | Hover to select sprites |

### Understanding the Display

```
┌─────────────────────────────┐
│ SpritePal Sprite Finder v2.0│
│ Press F9 to capture sprite  │  <- Current status
│ F9: Capture | S: Save | F10 │  <- Available commands
│ Mouse: 128,96               │  <- Cursor position
│ Sprites captured: 3         │  <- Capture count
│ DMA transfers tracked: 47   │  <- DMA monitoring
└─────────────────────────────┘
```

When hovering over a sprite:
```
┌──────────────┐
│ Sprite #15   │  <- OAM sprite index
│ Tile: $4C    │  <- Tile number
│ Size: 16x16  │  <- Sprite dimensions
│ VRAM: $6000  │  <- Video RAM location
│ ROM: 0x02A200│  <- ROM offset (USE THIS!)
│ Src: $05:A200│  <- SNES address source
│ HAL: 512 bytes│  <- If HAL compressed
│ Frame: 1234  │  <- When loaded
└──────────────┘
```

## Integration with SpritePal

### Method 1: Direct Offset Entry

1. Capture sprite in Mesen-S (F9)
2. Note the ROM offset (e.g., `0x02A200`)
3. In SpritePal, open Manual Offset dialog
4. Enter the offset directly
5. SpritePal will show the sprite for editing

### Method 2: Sprite Map Import

1. Capture multiple sprites in Mesen-S
2. Press S to save sprite map
3. Copy JSON from Mesen-S console log
4. Save to `sprite_map.json`
5. In SpritePal, use Import feature (future enhancement)

### Example JSON Output

```json
{
  "rom": "Kirby Super Star.sfc",
  "captured_at": "2024-01-15 14:23:45",
  "total_sprites": 3,
  "sprites": [
    {
      "index": 1,
      "rom_offset": 172544,
      "rom_offset_hex": "0x02A200",
      "tile": 76,
      "size": "16x16",
      "vram": "$6000",
      "source": "$05:A200",
      "hal_compressed": true,
      "compressed_size": 512
    }
  ]
}
```

## Kirby Games Special Support

For Kirby SNES games (Super Star, Dream Land 3), the script:

1. **Detects HAL compression** - Shows when data is compressed
2. **Tracks compressed size** - Displays compression block size
3. **Works with exhal** - Offsets compatible with exhal tool

### Using with HAL Compression

When the script shows "HAL: XXX bytes":
1. Note the ROM offset
2. Use exhal to decompress: `exhal rom.sfc 0x02A200 sprite.bin`
3. Edit decompressed sprite in SpritePal
4. Recompress with inhal when done

## Troubleshooting

### "ROM: Unknown" Message

**Problem**: No ROM offset shown for sprite
**Solution**: 
- Trigger sprite animation to force DMA transfer
- Walk/move character to load graphics
- Change screens to trigger graphics load

### No Sprites Detected

**Problem**: Mouse hover doesn't highlight sprites
**Solution**:
- Make sure overlay is enabled (F10)
- Sprites may be background tiles, not OAM sprites
- Try different game areas

### Wrong Offsets

**Problem**: Offset doesn't show correct sprite in SpritePal
**Solution**:
- ROM may have 512-byte SMC header (script auto-detects)
- Sprite may be compressed (check for HAL indicator)
- Multiple sprites may share same graphics

### Script Errors

**Problem**: Script won't load or crashes
**Solution**:
- Use `mesen_sprite_finder_corrected.lua` (API-compatible version)
- Check Mesen-S version (requires recent version)
- Look for errors in Script Window console

## Technical Details

### How It Works

1. **DMA Monitoring**: Tracks Direct Memory Access transfers from ROM to VRAM
2. **OAM Analysis**: Reads Object Attribute Memory to find sprite positions
3. **VRAM Mapping**: Correlates VRAM tiles with their ROM sources
4. **Address Conversion**: Converts SNES addresses to ROM file offsets

### ROM Mapping Support

- **LoROM**: `((bank & 0x7F) << 15) | (addr & 0x7FFF)`
- **HiROM**: `((bank & 0x3F) << 16) | addr`
- **SMC Headers**: Auto-detected and compensated (+512 bytes)

### Memory Types Used

- **cpu**: CPU memory for DMA registers
- **oam**: Object Attribute Memory for sprites
- **vram**: Video RAM for tile data
- **prgRom**: Program ROM for offset verification

## Advanced Features

### DMA Log Analysis

Hold TAB to see recent DMA transfers (debug feature):
- Shows source → destination transfers
- Lists ROM offsets for each transfer
- Helps understand graphics loading patterns

### Batch Capture

Capture multiple sprites for comparison:
1. Capture different animation frames
2. Save complete sprite map
3. Analyze patterns in ROM organization

### Custom Modifications

Edit the CONFIG table in the script to customize:
- Colors and transparency
- Export format
- Hotkey bindings

## Limitations

- **Mouse required** - Needs mouse for sprite selection
- **No clipboard API** - Offsets logged to console (copy manually)
- **OAM sprites only** - Doesn't detect background layer graphics
- **Real-time only** - Must trigger actual sprite loads

## Future Enhancements

Planned SpritePal integration features:
- Import JSON sprite maps directly
- Auto-connect to running Mesen-S instance
- Batch sprite extraction from captures
- Pattern matching for similar sprites

## Credits

Created for SpritePal sprite editing workflow. Specifically optimized for Kirby SNES games with HAL compression support.