# Mesen 2 Sprite Finder Usage Guide

## ⚠️ IMPORTANT: Script is detecting sprites but NOT DMA transfers!

**Current Issue**: The script sees 21 active sprites but 0 DMA transfers. This means we need to trigger DMA activity.

## How to Use the Script Effectively

### Step 1: Setup
1. Open Mesen 2
2. Load a Kirby SNES game ROM (Kirby Super Star, Dream Land 3, etc.)
3. Load the script: Script → Run Script → `mesen2_sprite_finder_working.lua`

### Step 2: Trigger DMA Activity
DMA (Direct Memory Access) happens when the game loads NEW graphics into VRAM. This occurs when:

#### DO THIS to trigger DMA:
1. **Start from title screen** - Press Start to begin game
2. **Enter gameplay** - Get past menus into actual game
3. **Move between areas** - Enter doors, pipes, or new screens
4. **Encounter new enemies** - Different enemies load different graphics
5. **Change Kirby's ability** - Each ability loads new sprites
6. **Die and respawn** - Forces graphics reload
7. **Enter/exit pause menu** - May trigger UI graphics DMA

#### DON'T expect DMA when:
- Standing still in one area
- In menus or title screen
- Fighting the same enemies repeatedly
- All graphics are already loaded

### Step 3: Monitor Output

The script outputs information in three places:

1. **Console Log** (Mesen 2's Script window)
   - Look for: `SPRITE_DMA:` messages when DMA is detected
   - Status updates every 300 frames (~5 seconds)
   
2. **Text File**: `mesen2_sprite_findings.txt`
   - Created in Mesen 2's folder
   - Updated every 300 frames
   - Contains ROM offset mappings

3. **JSON File**: `mesen2_sprite_data.json`
   - Machine-readable format for SpritePal
   - Contains all sprite-to-ROM mappings

### Step 4: Maximize DMA Captures

To capture the most sprite data:

```
1. Start at game beginning
2. Play through first level slowly
3. Enter every door/pipe
4. Collect different power-ups
5. Fight each enemy type
6. Let script run for 5-10 minutes of gameplay
```

## Troubleshooting

### "0 DMA transfers detected"
**Problem**: Script shows active sprites but no DMA
**Solution**: 
- Make sure you're in actual gameplay, not menus
- Move to a NEW area to force graphics loading
- Try dying and respawning
- Enter a door or pipe to load new level

### "No output files created"
**Problem**: Can't find the output files
**Solution**: 
- Check Mesen 2's installation folder
- Files only created when DMA is detected
- Wait for at least 300 frames (5 seconds)

### "Script stops responding"
**Problem**: Script seems frozen
**Solution**:
- Check Script window for errors
- Restart script
- Make sure game is not paused

## Expected Output When Working

When DMA is properly detected, you should see:

```
SPRITE_DMA: F=142 Ch=1 VRAM=$4000 ROM=$0A8F20 Size=512
SPRITE_MAPPED: id=3 pos=(120,80) tile=$40 size=16x16 -> ROM=$0A8F20
STATUS: Frame=300 Active=21 MaxFound=32 DMA=15 VRAM_DMA=12 Unique=8 Mappings=25
```

Key indicators of success:
- `DMA=` shows non-zero value
- `VRAM_DMA=` shows transfers to video RAM
- `Unique=` shows unique ROM offsets found
- `Mappings=` shows sprite-to-ROM correlations

## Quick Test

For a quick test to verify DMA detection:

1. Load Kirby Super Star
2. Start "Spring Breeze" mode
3. Run the script
4. Enter the first door you see
5. Check console for "SPRITE_DMA" messages

If you see DMA messages after entering the door, the script is working correctly!

## Files Produced

After successful capture, you'll have:

- **mesen2_sprite_findings.txt** - Human-readable results
- **mesen2_sprite_data.json** - For import into SpritePal

These files contain ROM offsets where sprite graphics are stored, ready for extraction!