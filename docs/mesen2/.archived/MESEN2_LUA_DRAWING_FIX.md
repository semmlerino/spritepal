# Mesen2 Lua Drawing API - Complete Fix

## Problems Identified

1. **Drawing Duration**: Default frameCount is 1, causing drawings to disappear after 1/60th second
2. **Alpha Channel Confusion**: Mesen uses ARGB where 0x00 can mean transparent OR opaque depending on context
3. **Sprite Mapping**: ROM offsets only shown when DMA actively happening (too restrictive)
4. **Parameter Order**: C++ reads parameters in reverse from Lua stack

## Actual Mesen2 API (from source code)

### drawString
```cpp
// C++ reads parameters in reverse order from stack
int LuaApi::DrawString(lua_State *lua) {
    // Parameters: x, y, text, color, backgroundColor, maxWidth, frameCount, delay
    // Only first 3 required
    // Default color: 0xFFFFFF (white)
    // Default frameCount: 1
}
```

Lua usage:
```lua
emu.drawString(x, y, text, color, backgroundColor, maxWidth, frameCount, delay)
-- For permanent display: frameCount = 0
emu.drawString(10, 10, "Text", 0xFF000000, 0, 0, 0)  -- Black text, permanent
```

### drawRectangle
```cpp
// Parameters: x, y, width, height, color, fill, frameCount, delay
// Only first 4 required
// Default color: 0xFFFFFF (white)
// Default fill: false
// Default frameCount: 1
```

Lua usage:
```lua
emu.drawRectangle(x, y, width, height, color, fill, frameCount, delay)
-- For permanent display: frameCount = 0
emu.drawRectangle(10, 10, 50, 20, 0xFFFFFF00, true, 0)  -- Yellow filled, permanent
```

## Color Format

ARGB format where colors use 0xFF prefix for opacity:
- 0xFF000000 = Opaque black
- 0xFFFFFF00 = Opaque yellow  
- 0xFFFF0000 = Opaque red
- 0xFFFFFFFF = Opaque white
- 0x80FFFFFF = Semi-transparent white

## Solutions Applied

### 1. Permanent Display
Added `frameCount = 0` to all drawing calls for permanent display:
```lua
-- Yellow background box
emu.drawRectangle(x, y, width, height, 0xFFFFFF00, true, 0)
-- Black text
emu.drawString(x, y, text, 0xFF000000, 0, 0, 0)
```

### 2. Persistent ROM Mapping
Added persistent storage that doesn't clear every frame:
```lua
state.persistent_rom_map = {}  -- Maps tile -> ROM offset
-- Store by tile number for persistence
state.persistent_rom_map[sprite.tile] = rom_offset
```

### 3. Improved Offset Display Logic
Show offsets from either current DMA or persistent map:
```lua
local rom_offset = state.sprite_rom_map[sprite.id] or state.persistent_rom_map[sprite.tile]
```

## Final Working Configuration

```lua
-- Colors that work correctly
offset_text_color = 0xFF000000    -- Opaque black text
offset_bg_color = 0xFFFFFF00      -- Opaque yellow background
offset_border_color = 0xFFFF0000  -- Opaque red border

-- Drawing with permanent display
emu.drawRectangle(x-4, y-4, w+8, h+8, 0xFFFF0000, true, 0)  -- Red border
emu.drawRectangle(x-1, y-1, w+2, h+2, 0xFFFFFF00, true, 0)  -- Yellow bg
emu.drawString(x+4, y+4, text, 0xFF000000, 0, 0, 0)         -- Black text
```

## Result

- **Yellow boxes with black text** now display permanently
- **ROM offsets persist** even when DMA not actively happening
- **Clear visibility** against any game background
- **No flickering** from 1-frame duration issue