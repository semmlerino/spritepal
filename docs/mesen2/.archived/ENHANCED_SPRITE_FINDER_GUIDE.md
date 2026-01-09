# Enhanced Sprite Finder User Guide

## Quick Start

1. Load your Kirby SNES game in Mesen 2
2. Run the script: **`mesen2_sprite_finder_enhanced.lua`**
3. Press **F1** to start capturing
4. Play the game - move between areas, encounter enemies
5. Press **F3** to export captured data

## Visual Features

### On-Screen HUD (Top-Left)
Shows real-time statistics:
- **Status**: ACTIVE (green) or PAUSED (yellow)
- **Sprites**: Captured/Total found
- **ROM Offsets**: Unique offsets discovered
- **DMA Captures**: Total VRAM transfers
- **Time**: Capture duration

### Sprite Highlighting
Colored rectangles around sprites:
- 🟢 **Green**: Successfully mapped to ROM
- 🟡 **Yellow**: Detected but not mapped yet  
- 🔴 **Red**: No DMA captured for this sprite

### Message System
Pop-up messages appear for:
- Milestone achievements (every 10 ROM offsets, 25 sprites)
- Export completion
- State changes (start/pause/reset)

## Hotkey Controls

| Key | Action | Description |
|-----|--------|-------------|
| **F1** | Start/Resume | Begin or resume capture |
| **F2** | Pause | Pause capture (keeps data) |
| **F3** | Export | Save current data to files |
| **F4** | Reset | Clear all captured data |
| **F5** | Toggle HUD | Show/hide visual overlay |

## File Output

### Location
Files are saved to the **script's data folder** (not Mesen's installation folder!)
- Check console log for exact path
- Typically in Mesen's scripts folder

### Filenames
- **With timestamps**: `sprite_capture_20250812_143022.txt`
- **Without timestamps**: `sprite_capture.txt` (overwrites)

### File Types
1. **`.txt`** - Human-readable results
2. **`.json`** - Machine-readable for SpritePal import

## Optimal Capture Strategy

### To Maximize Captures:
1. **Start at beginning** of a level
2. **Move slowly** through areas
3. **Enter every door/pipe** (triggers new graphics)
4. **Collect different power-ups** (loads ability sprites)
5. **Encounter each enemy type** at least once
6. **Die and respawn** occasionally (reloads graphics)

### What Triggers DMA:
- ✅ Entering new areas
- ✅ Loading new enemies
- ✅ Changing abilities
- ✅ Screen transitions
- ❌ Standing still
- ❌ Fighting same enemies
- ❌ Staying in one screen

## Understanding the Display

### HUD Statistics
- **Sprites: 45/128** = 45 sprites mapped to ROM out of 128 detected
- **ROM Offsets: 23** = 23 unique locations in ROM found
- **DMA Captures: 156** = 156 graphics transfers captured

### Visual Feedback
- **Green sprites** = Success! ROM offset known
- **Yellow sprites** = Detected, waiting for DMA
- **Red sprites** = Need to trigger graphics load

### Messages
- **"25 sprites captured!"** = Milestone reached
- **"Exported: sprite_capture_..."** = Files saved
- **"Capture PAUSED"** = F2 was pressed

## Tips & Tricks

### For Best Results:
1. **Let the game settle** before pressing F1 (wait 2-3 seconds after loading)
2. **Pause in menus** (F2) to avoid capturing UI sprites
3. **Export regularly** (F3) to save progress
4. **Watch the green highlights** increase as you play

### Common Issues:

**No sprites turning green:**
- Make sure capture is ACTIVE (check HUD status)
- Move to a new area to trigger DMA
- Try entering a door or pipe

**Too many red sprites:**
- These sprites haven't loaded graphics yet
- Move closer to them or change screens

**HUD blocking view:**
- Press F5 to toggle it off temporarily

## Advanced Usage

### Configuration
Edit the script's `config` table to customize:
```lua
config = {
    hud_x = 10,          -- HUD position
    hud_y = 10,
    use_timestamp = true, -- Timestamp filenames
    highlight_sprites = true  -- Show colored boxes
}
```

### Auto-Export
The script automatically exports every 30 seconds while capturing.

### Performance
- Visual overlays have minimal impact
- Disable sprite highlighting (F5) if needed
- Export is near-instant

## Output Format

### Text File Contains:
```
=== Enhanced Sprite Finder Results ===
Capture Time: 124.5 seconds
Sprites Captured: 89/156
ROM Offsets Found: 34

--- ROM Offsets ---
$0A8F20: 45 hits
$0B1234: 23 hits
...
```

### JSON File Contains:
```json
{
  "metadata": {
    "capture_time": 124.5,
    "sprites_captured": 89,
    "rom_offsets_found": 34
  },
  "rom_offsets": [
    {"offset": 692000, "hits": 45},
    ...
  ]
}
```

## Integration with SpritePal

1. Run the enhanced sprite finder
2. Capture sprites by playing the game
3. Press F3 to export
4. Import the JSON file into SpritePal
5. SpritePal can now extract sprites from those ROM offsets

## Troubleshooting

**Script won't start:**
- Make sure you're using the corrected API version
- Check that `emu.callbackType.write` exists

**No visual elements:**
- Some Mesen 2 versions may not support drawing
- Check script console for errors

**Files not found:**
- Check console log for export path
- Look in Mesen's script data folder
- Try searching for files with today's date

---

**Pro Tip**: The visual feedback makes it easy to see your progress. Aim to turn all sprites green before exporting!