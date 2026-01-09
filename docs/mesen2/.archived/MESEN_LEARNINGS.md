# Mesen-S Sprite Finder - Complete Learnings

> **SUPERSEDED**: This file contains historical learnings from early development.
> Some content is now outdated or contradicts current canonical documentation:
> - Callbacks **do work** (see `01_BUILD_SPECIFIC_CONTRACT.md` for correct signatures)
> - Kirby Super Star uses **SA-1 mapping**, not LoROM (see `03_GAME_MAPPING_KIRBY_SA1.md`)
> - Bootstrap offsets have been updated in `03_GAME_MAPPING_KIRBY_SA1.md`
>
> Refer to `docs/mesen2/00-04_*.md` for current documentation.

## Critical Discoveries

### 1. Correct Mesen-S Memory Types (From PDF)

```lua
-- WORKING - Correct API
emu.memType.snesSpriteRam   -- OAM (sprite data)
emu.memType.snesVideoRam    -- VRAM (graphics)
emu.memType.snesPrgRom      -- ROM data
emu.memType.snesCgRam       -- Palette data
emu.memType.snesDebug       -- Registers (no side effects)

-- BROKEN - What we tried first
"cpu", "oam", "vram", "prgRom"  -- All wrong!
emu.read(addr, "cpu")            -- Doesn't work
```

### 2. Callback API is Broken

```lua
-- THIS DOESN'T EXIST (despite documentation)
emu.memCallbackType              -- nil
emu.addMemoryCallback(..., emu.memCallbackType.cpuWrite, ...)  -- Fails

-- SOLUTION: Use polling instead
function poll_every_frame()
    local dma = emu.read(0x420B, emu.memType.snesDebug)
    -- Check for changes
end
```

### 3. DMA Tracking Strategy

**Key Insight**: DMA transfers sprite data from ROM to VRAM instantly. We catch these by:

1. **Poll $420B** (DMA enable register) every frame
2. **Rising edge detection** - Only process when value changes from 0
3. **Read DMA parameters** immediately ($4300-$437F)
4. **Calculate ROM offset** from source address

```lua
-- Working DMA detection
local last_dma = 0
function check_dma()
    local dma = emu.read(0x420B, emu.memType.snesDebug)
    if dma ~= 0 and dma ~= last_dma then
        -- New DMA transfer!
        for channel = 0, 7 do
            if (dma & (1 << channel)) ~= 0 then
                -- Read channel parameters
                local base = 0x4300 + (channel * 0x10)
                -- Process transfer...
            end
        end
    end
    last_dma = dma
end
```

### 4. OAM Reading (Sprites)

```lua
-- Correct way to read sprite data
function read_sprite(index)
    local base = index * 4
    local y = emu.read(base, emu.memType.snesSpriteRam)
    local tile = emu.read(base + 1, emu.memType.snesSpriteRam)
    
    -- 9th X bit is stored separately!
    local high_x_addr = 0x200 + math.floor(index / 8)
    local high_x_byte = emu.read(high_x_addr, emu.memType.snesSpriteRam)
    local x_high_bit = (high_x_byte >> (index % 8)) & 1
    
    -- Y < 0xF0 means sprite is on-screen
    return y < 0xF0
end
```

### 5. ROM Offset Calculation

```lua
-- LoROM (used by Kirby)
function lorom_offset(bank, addr)
    local offset = ((bank & 0x7F) * 0x8000) + (addr & 0x7FFF)
    
    -- Check for SMC header
    local test = emu.read(0x7FC0 + 512 + 0x15, emu.memType.snesPrgRom)
    if test ~= 0 and test ~= 0xFF then
        offset = offset + 512  -- Add header
    end
    
    return offset
end
```

## Kirby-Specific Findings

### HAL Compression
- Sprites are **compressed** in ROM
- Direct pattern matching **won't work**
- Must track DMA to find compressed location
- Use `exhal` to decompress

### Common Offsets
```
$05:A200 → 0x02A200 (Walking Kirby)
$06:8000 → 0x030000 (Abilities)
$07:0000 → 0x038000 (Enemies)
```

### Workflow with exhal
```bash
# Script finds: 0x02A200
exhal kirby.sfc 0x02A200 sprite.bin
# Edit sprite.bin in SpritePal
inhal sprite.bin kirby.sfc 0x02A200
```

## What Didn't Work

1. **getRomSize()** - Function doesn't exist
2. **Memory callbacks** - API is broken/different
3. **Pattern matching** - HAL compression prevents direct matching
4. **Mouse input** - getMouseState() may not work
5. **String memory types** - Must use emu.memType enums

## Final Working Solution

**Script**: `mesen_kirby_finder_final.lua`

**Features**:
- ✅ Correct memory types
- ✅ DMA polling (no callbacks)
- ✅ Automatic offset detection
- ✅ exhal command generation
- ✅ Rising edge detection
- ✅ Duplicate prevention

**Key Code**:
```lua
-- Poll DMA every frame
local last_dma = 0
function check_dma()
    local dma = emu.read(0x420B, emu.memType.snesDebug)
    if dma ~= 0 and dma ~= last_dma then
        -- Process DMA channels
        for ch = 0, 7 do
            if (dma & (1 << ch)) ~= 0 then
                -- Get source, calculate offset
                -- Output exhal command
            end
        end
    end
    last_dma = dma
end
```

## Lessons Learned

1. **Don't trust documentation** - Test everything
2. **PDF guide was crucial** - Had correct memory types
3. **Polling > Callbacks** - More reliable
4. **Compression matters** - Can't ignore it
5. **DMA is the key** - Tracks all graphics loads
6. **Rising edge detection** - Prevents duplicates
7. **Debug memory type** - Avoids side effects

## Resources That Helped

- **PDF**: "Using Mesen-S Lua Scripting to Read Sprite Data"
- **exhal/inhal**: Essential for Kirby games
- **Trial and error**: Tested every API variation
- **SNES hardware docs**: Understanding DMA/OAM

## Complete Workflow

1. Load `mesen_kirby_finder_final.lua`
2. Play Kirby game
3. Script detects sprite loads
4. Press S for exhal commands
5. Run exhal to decompress
6. Edit in SpritePal
7. Recompress with inhal

**This is the complete, working solution!**