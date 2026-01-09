# Lua Script Auto-Capture Instructions

Both Mesen2 Lua scripts have been modified to start capturing sprites automatically when loaded, with all features enabled by default.

## Changes Made

### Fixed Offsets Script (`mesen2_sprite_finder_fixed_offsets.lua`)
- ✅ **Auto-capture enabled** - Starts capturing immediately on load
- ✅ **All visual features on** - HUD, sprite highlighting, offset display
- ✅ **Auto-export every 30 seconds** - Data saved automatically
- ✅ **Updated messages** - Reflects auto-capture status

### Precise Offsets Script (`mesen2_sprite_finder_precise.lua`)  
- ✅ **Auto-capture enabled** - Starts capturing immediately on load
- ✅ **Debug logging enabled** - Detailed offset calculations in console
- ✅ **All visual features on** - HUD, sprite highlighting, offset display
- ✅ **Auto-export every 30 seconds** - Data saved automatically
- ✅ **Updated messages** - Shows debug mode active

## Usage

### Quick Start
1. Load either Lua script in Mesen2
2. **That's it!** Capture starts automatically
3. Play the game normally - sprites are being tracked
4. Data auto-exports every 30 seconds

### Manual Controls Still Available
- **2** - Pause/Resume capture (if you need to stop temporarily)
- **3** - Export data immediately (don't wait for auto-export)
- **4** - Reset all captured data
- **5** - Toggle HUD display
- **6** - Toggle ROM offset labels on sprites
- **7** - Toggle debug logging (Precise script only)

### Auto-Export Files
Files are saved to Mesen2's script data folder:
- `sprite_capture_YYYYMMDD_HHMMSS.txt` - Human-readable report
- `sprite_capture_YYYYMMDD_HHMMSS.json` - JSON data for validation

### Visual Indicators

#### On-Screen HUD Shows:
- **Status**: "ACTIVE" (green) or "PAUSED" (yellow)
- **Sprites**: Captured/Found count
- **ROM Offsets**: Number of unique offsets found
- **DMA Captures**: Total DMA transfers tracked
- **Time**: Seconds since capture started

#### Sprite Colors:
- 🟩 **Green outline** - Sprite captured with ROM offset
- 🟡 **Yellow outline** - Sprite detected but not yet mapped
- 🔴 **Red outline** - Sprite position with no DMA data

#### ROM Offset Labels:
- **Purple box with yellow text** - Shows hex ROM offset
- **Yellow line** - Connects label to sprite
- Displayed above each captured sprite

### Debug Output (Precise Script)

With debug logging enabled by default, the console shows:
```
DMA Ch0: ROM $240000 -> VRAM $6000 (size: $2000)
Sprite 12: Tile 4A at VRAM $6040 -> ROM $240040 (DMA base $240000 + $0040)
```

This helps verify exact offset calculations for each sprite.

## Benefits of Auto-Capture

1. **No missed data** - Capture starts immediately, no forgetting to press start
2. **Consistent results** - Same settings every time
3. **Debug visibility** - See offset calculations in real-time
4. **Auto-save** - Data exported regularly, no data loss
5. **Hands-free** - Focus on playing while script works

## Troubleshooting

### Too Much Console Output?
If debug logging is overwhelming:
- Press **7** in Precise script to toggle debug off
- Use Fixed Offsets script for less verbose output

### Want to Start Fresh?
- Press **4** to reset all captured data
- Press **2** to pause, **4** to reset, **2** to resume

### Need Different Export Timing?
Auto-export happens every 1800 frames (30 seconds at 60fps).
To change, modify line in script:
```lua
-- Change 1800 to desired frame count
if state.capture_active and state.frame_count % 1800 == 0 then
```

### Performance Impact?
The scripts are optimized for minimal impact:
- DMA monitoring is lightweight
- Visual updates only when sprites change
- Export runs in background

## Summary

The Lua scripts now work "out of the box" with optimal settings:
- **Fixed Offsets**: Best for general sprite discovery
- **Precise Offsets**: Best for exact offset validation with debug info

Just load and play - the scripts handle everything automatically!