# Lua Script Hotkey-Triggered Offset Display with Collision Avoidance

## Problems Solved
1. The continuous offset display was causing visual accumulation and overlapping text because it was drawing permanently (60 times per second). This created messy, unreadable displays.
2. When multiple sprites were close together, their offset labels would overlap, making them unreadable.
3. All sprites were showing the same ROM offset due to using only tile number as the mapping key, which wasn't unique enough.

## Solutions Implemented
1. Added a **hotkey-triggered temporary display** that shows all sprite offsets on demand.
2. Implemented **collision detection** to automatically reposition overlapping labels.
3. Added **connecting lines** to show which label belongs to which sprite when repositioned.
4. Fixed **unique offset mapping** by using tile+palette composite keys instead of just tile numbers.

## How to Use

### Primary Method: Hotkey Display (Recommended)

**Press 9** - Display all sprite offsets for 3 seconds
- Clears screen first to ensure clean display
- Shows yellow boxes with black text containing ROM offsets
- Automatically disappears after 3 seconds
- Perfect for checking offsets without visual clutter

**Press 0** - Copy sprite offset to clipboard file
- Copies the first visible sprite's offset
- Creates `sprite_clipboard.txt` in Mesen2 folder
- Use SpritePal's "📋 Paste" button to navigate to this offset

### Additional Controls

**Press 3** - Export sprite session
- Saves all discovered sprites to JSON file
- Includes offset, tile, palette, size, and position
- Can be imported into SpritePal for batch processing

**Press 6** - Toggle continuous offset display
- Off by default to prevent accumulation
- If enabled, shows offsets continuously with 2-frame refresh
- Use sparingly as it can still cause some visual noise

**Press 8** - Clear screen
- Removes all drawings immediately
- Useful if you have leftover graphics

**Press 7** - Toggle debug mode
- Shows additional tile information when enabled

## Display Format

When you press 9, you'll see:
- **Yellow boxes** with **black text** showing ROM offsets
- **Red borders** around the yellow boxes for visibility
- **Red lines** connecting offsets to their sprites
- Format: `$XXXXXX` (hexadecimal ROM offset)

## Technical Details

### Collision Avoidance Algorithm
1. **Collision Detection**: Checks if label rectangles overlap using boundary intersection
2. **Smart Repositioning**: Tries positions in this order:
   - Original position (above sprite)
   - Up, Down, Left, Right
   - Diagonal positions (up-left, up-right, down-left, down-right)
3. **Visual Connection**: Draws red lines from sprites to repositioned labels
4. **Consistent Layout**: Sprites sorted by Y position for predictable label placement

### Sprite ROM Offset Mapping
- **Unique Keys**: Uses composite key format `tile_palette` (e.g., "2D_3" for tile 0x2D, palette 3)
- **Prevents Duplicates**: Different sprites with same tile number but different palettes get unique offsets
- **Persistent Storage**: Maintains ROM offset mappings across frames for sprites not currently in DMA

### Temporary Display (Key 9)
- Uses `frameCount = 180` (3 seconds at 60fps)
- Clears screen before drawing to ensure clean display
- Shows all sprites that have been detected with DMA transfers
- Automatically repositions overlapping labels

### Continuous Display (Key 6)
- Uses `frameCount = 2` (refreshes every 2 frames)
- Prevents permanent accumulation
- Still shows some flickering but much cleaner than before

### Color Scheme
- Background: `0xFFFFFF00` (Opaque yellow)
- Text: `0xFF000000` (Opaque black)
- Border: `0xFFFF0000` (Opaque red)
- Connecting lines: `0xFFFF0000` (Opaque red)

## Benefits

1. **Clean Display** - No more accumulation or overlapping
2. **Collision Avoidance** - Labels automatically reposition to prevent overlap
3. **User Control** - Show offsets exactly when needed
4. **Readable** - High contrast yellow/black clearly visible
5. **Visual Clarity** - Red lines connect repositioned labels to their sprites
6. **Temporary** - Automatically cleans up after 3 seconds
7. **Performance** - Not constantly drawing every frame

## Usage Tips

1. Let the game run for a bit to build up the sprite database
2. Press 9 whenever you want to see current sprite offsets
3. The more sprites you've seen, the more offsets will display
4. Use key 8 to clear if you see any leftover graphics

This approach gives you precise control over when and how sprite offsets are displayed!