-- Mesen 2 Click/Hotkey Sprite Extractor
-- Captures visible sprites with ROM offsets on F9 hotkey
-- For use with SpritePal extraction pipeline

-- ============================================================================
-- GLOBAL STATE
-- ============================================================================
local state = {
    frame_count = 0,
    dma_history = {},           -- Recent DMA captures (ring buffer)
    dma_history_max = 500,      -- Keep last 500 DMA transfers
    dma_history_index = 0,
    active_sprites = {},        -- Current frame's OAM sprites
    obsel_config = nil,         -- OBSEL register state
    last_f9_state = false,      -- For edge detection
    capture_pending = false,    -- Waiting for clean frame to capture
    output_dir = os.getenv("OUTPUT_DIR") or "C:\\CustomScripts\\KirbyMax\\workshop\\exhal-master\\spritepal\\mesen2_exchange\\",  -- Output directory for JSON
    last_dma_enable = 0,        -- For DMA polling edge detection
}

-- ============================================================================
-- CONSTANTS
-- ============================================================================
local DMA_ENABLE = 0x420B
local DMA_BASE = 0x4300
local VRAM_ADDR_L = 0x2116
local VRAM_ADDR_H = 0x2117

-- Sprite size lookup: OBSEL size_select -> {small_size, large_size}
local SPRITE_SIZES = {
    [0] = {8, 16},   [1] = {8, 32},   [2] = {8, 64},
    [3] = {16, 32},  [4] = {16, 64},  [5] = {32, 64},
    [6] = {16, 32},  [7] = {16, 32}
}

-- ============================================================================
-- HELPERS
-- ============================================================================

-- Convert CPU address to ROM file offset
local function cpu_to_rom_offset(cpu_addr)
    -- Try Mesen 2's built-in conversion
    local result = emu.convertAddress(cpu_addr)
    if result and result.memType == emu.memType.snesPrgRom then
        return result.address
    end

    -- Fallback: Manual LoROM calculation
    local bank = (cpu_addr >> 16) & 0xFF
    local addr = cpu_addr & 0xFFFF

    if addr < 0x8000 then
        return nil
    end

    local rom_offset = ((bank & 0x7F) * 0x8000) + (addr - 0x8000)
    return rom_offset
end

-- Read DMA channel registers
local function read_dma_channel(channel)
    local base = DMA_BASE + (channel * 0x10)

    local _control = emu.read(base + 0x00, emu.memType.snesMemory)  -- luacheck: ignore
    local dest_reg = emu.read(base + 0x01, emu.memType.snesMemory)
    local src_low = emu.read(base + 0x02, emu.memType.snesMemory)
    local src_mid = emu.read(base + 0x03, emu.memType.snesMemory)
    local src_bank = emu.read(base + 0x04, emu.memType.snesMemory)
    local size_low = emu.read(base + 0x05, emu.memType.snesMemory)
    local size_high = emu.read(base + 0x06, emu.memType.snesMemory)

    local source_addr = (src_bank << 16) | (src_mid << 8) | src_low
    local transfer_size = (size_high << 8) | size_low
    if transfer_size == 0 then
        transfer_size = 0x10000  -- 0 means 64KB
    end

    return {
        dest_reg = dest_reg,
        source_addr = source_addr,
        transfer_size = transfer_size
    }
end

-- Update OBSEL from PPU register (read directly, not from emu.getState().ppu which doesn't exist for SNES)
local function update_obsel()
    local obsel = emu.read(0x2101, emu.memType.snesMemory)
    local name_base = obsel & 0x07
    local name_select = (obsel >> 3) & 0x03
    local oam_base_addr = name_base << 13
    local oam_addr_offset = (name_select + 1) << 12
    state.obsel_config = {
        name_base = name_base,
        name_select = name_select,
        size_select = (obsel >> 5) & 0x07,
        tile_base_addr = oam_base_addr * 2,
        oam_base_addr = oam_base_addr,
        oam_addr_offset = oam_addr_offset,
        raw = obsel
    }
end

-- Simple JSON serialization
local function to_json(t, indent)
    indent = indent or 0
    local spaces = string.rep("  ", indent)

    if type(t) == "table" then
        local is_array = #t > 0
        local result = is_array and "[\n" or "{\n"
        local first = true

        if is_array then
            for _, v in ipairs(t) do
                if not first then result = result .. ",\n" end
                result = result .. spaces .. "  " .. to_json(v, indent + 1)
                first = false
            end
        else
            for k, v in pairs(t) do
                if not first then result = result .. ",\n" end
                result = result .. spaces .. '  "' .. tostring(k) .. '": ' .. to_json(v, indent + 1)
                first = false
            end
        end

        result = result .. "\n" .. spaces .. (is_array and "]" or "}")
        return result
    elseif type(t) == "string" then
        return '"' .. t:gsub('"', '\\"') .. '"'
    elseif type(t) == "boolean" then
        return t and "true" or "false"
    elseif t == nil then
        return "null"
    else
        return tostring(t)
    end
end

-- ============================================================================
-- DMA TRACKING (Using callbacks + polling for reliability)
-- ============================================================================

-- Record a DMA transfer to history
local function record_dma(channel, vram_addr, dma, source_type)
    local rom_offset = cpu_to_rom_offset(dma.source_addr)

    if rom_offset then
        -- Store in ring buffer
        state.dma_history_index = (state.dma_history_index % state.dma_history_max) + 1
        state.dma_history[state.dma_history_index] = {
            frame = state.frame_count,
            vram_addr = vram_addr * 2,  -- Word to byte
            vram_end = (vram_addr * 2) + dma.transfer_size,
            rom_offset = rom_offset,
            size = dma.transfer_size
        }

        -- Debug log
        emu.log(string.format(
            "DMA[%s]: Ch%d ROM=$%06X -> VRAM=$%04X Size=%d",
            source_type, channel, rom_offset, vram_addr * 2, dma.transfer_size
        ))
    end
end

-- Memory callback for DMA enable writes (fires at exact moment of write)
local function on_dma_enable_write(address, value)
    if value == 0 then return end

    -- Read current VRAM address
    local vram_low = emu.read(VRAM_ADDR_L, emu.memType.snesMemory)
    local vram_high = emu.read(VRAM_ADDR_H, emu.memType.snesMemory)
    local vram_addr = (vram_high << 8) | vram_low

    -- Process each enabled channel
    for channel = 0, 7 do
        if (value & (1 << channel)) ~= 0 then
            local dma = read_dma_channel(channel)

            -- Check if this is a VRAM transfer (dest = $2118 or $2119)
            if dma.dest_reg == 0x18 or dma.dest_reg == 0x19 then
                record_dma(channel, vram_addr, dma, "CB")
            end
        end
    end
end

-- Poll DMA register as backup (catches transfers if callbacks fail)
local function poll_dma()
    local dma_enable = emu.read(DMA_ENABLE, emu.memType.snesMemory)

    -- Only process when DMA is active (non-zero)
    if dma_enable ~= 0 then
        -- Read current VRAM address
        local vram_low = emu.read(VRAM_ADDR_L, emu.memType.snesMemory)
        local vram_high = emu.read(VRAM_ADDR_H, emu.memType.snesMemory)
        local vram_addr = (vram_high << 8) | vram_low

        -- Process each enabled channel
        for channel = 0, 7 do
            if (dma_enable & (1 << channel)) ~= 0 then
                local dma = read_dma_channel(channel)

                -- Check if this is a VRAM transfer (dest = $2118 or $2119)
                if dma.dest_reg == 0x18 or dma.dest_reg == 0x19 then
                    record_dma(channel, vram_addr, dma, "POLL")
                end
            end
        end
    end
end

-- ============================================================================
-- OAM PARSING
-- ============================================================================

-- Parse all 128 OAM entries
local function parse_oam()
    -- Read all OAM data
    local oam = {}
    for i = 0, 543 do  -- 512 bytes main + 32 bytes high table
        oam[i] = emu.read(i, emu.memType.snesSpriteRam)
    end

    state.active_sprites = {}

    for i = 0, 127 do
        local base = i * 4
        local x = oam[base]
        local y = oam[base + 1]
        local tile = oam[base + 2]
        local attr = oam[base + 3]

        -- High table: 2 bits per sprite (X MSB, size bit)
        local high_index = 512 + math.floor(i / 4)
        local high_shift = (i % 4) * 2
        local high_byte = oam[high_index]
        local x_msb = (high_byte >> high_shift) & 0x01
        local size_bit = (high_byte >> (high_shift + 1)) & 0x01

        -- Full X position (9-bit)
        x = x | (x_msb * 256)

        -- Skip off-screen sprites (Y >= 224 means hidden, unless wrapped)
        local visible = (y < 224) or (y >= 240)

        if visible then
            local palette = (attr >> 1) & 0x07
            local priority = (attr >> 4) & 0x03
            local flip_h = (attr & 0x40) ~= 0
            local flip_v = (attr & 0x80) ~= 0
            local name_table = attr & 0x01

            -- Calculate sprite size
            local width = 8
            local height = 8
            if state.obsel_config then
                local sizes = SPRITE_SIZES[state.obsel_config.size_select] or {8, 16}
                local size = sizes[size_bit + 1]
                width = size
                height = size
            end

            -- Calculate VRAM address for this sprite's tiles
            local vram_addr = nil
            if state.obsel_config then
                local word_addr = state.obsel_config.oam_base_addr + (tile << 4)
                if name_table ~= 0 then
                    word_addr = word_addr + state.obsel_config.oam_addr_offset
                end
                word_addr = word_addr & 0x7FFF
                vram_addr = word_addr << 1
            end

            table.insert(state.active_sprites, {
                id = i,
                x = x,
                y = y,
                tile = tile,
                width = width,
                height = height,
                palette = palette,
                priority = priority,
                flip_h = flip_h,
                flip_v = flip_v,
                name_table = name_table,
                vram_addr = vram_addr
            })
        end
    end
end

-- ============================================================================
-- SPRITE-ROM CORRELATION
-- ============================================================================

-- Find ROM offset for a sprite by matching its VRAM address to DMA history
local function find_rom_offset_for_sprite(sprite)
    if not sprite.vram_addr then
        return nil
    end

    local sprite_vram_start = sprite.vram_addr
    local tile_count = (sprite.width / 8) * (sprite.height / 8)
    local sprite_vram_end = sprite_vram_start + (tile_count * 32)

    -- Search DMA history for overlapping VRAM transfer
    -- Search backwards (most recent first)
    for i = 1, math.min(#state.dma_history, state.dma_history_max) do
        local idx = state.dma_history_index - i + 1
        if idx < 1 then idx = idx + state.dma_history_max end

        local dma = state.dma_history[idx]
        if dma then
            -- Check if DMA VRAM range overlaps sprite VRAM range
            if dma.vram_addr < sprite_vram_end and dma.vram_end > sprite_vram_start then
                return dma.rom_offset
            end
        end
    end

    return nil
end

-- Attach ROM offsets to all active sprites
local function correlate_all_sprites()
    for _, sprite in ipairs(state.active_sprites) do
        sprite.rom_offset = find_rom_offset_for_sprite(sprite)
    end
end

-- ============================================================================
-- CAPTURE & EXPORT
-- ============================================================================

-- Export current sprites with ROM offsets
local function export_capture()
    correlate_all_sprites()

    -- Build output data
    local oam_entries = {}
    local rom_sources = {}
    local rom_source_map = {}

    local min_x, min_y = 256, 224
    local max_x, max_y = 0, 0

    for _, sprite in ipairs(state.active_sprites) do
        -- Track bounding box
        if sprite.x < min_x then min_x = sprite.x end
        if sprite.y < min_y then min_y = sprite.y end
        if sprite.x + sprite.width > max_x then max_x = sprite.x + sprite.width end
        if sprite.y + sprite.height > max_y then max_y = sprite.y + sprite.height end

        -- Add OAM entry
        table.insert(oam_entries, {
            id = sprite.id,
            x = sprite.x,
            y = sprite.y,
            tile = sprite.tile,
            width = sprite.width,
            height = sprite.height,
            flip_h = sprite.flip_h,
            flip_v = sprite.flip_v,
            palette = sprite.palette,
            priority = sprite.priority,
            rom_offset = sprite.rom_offset,
            rom_offset_hex = sprite.rom_offset and string.format("0x%06X", sprite.rom_offset) or nil,
            vram_addr = sprite.vram_addr
        })

        -- Track unique ROM sources
        if sprite.rom_offset and not rom_source_map[sprite.rom_offset] then
            rom_source_map[sprite.rom_offset] = {
                offset = sprite.rom_offset,
                offset_hex = string.format("0x%06X", sprite.rom_offset),
                tiles = {}
            }
        end

        if sprite.rom_offset then
            table.insert(rom_source_map[sprite.rom_offset].tiles, sprite.tile)
        end
    end

    -- Convert rom_source_map to array
    for _, source in pairs(rom_source_map) do
        table.insert(rom_sources, source)
    end

    -- Build final capture data
    local capture = {
        timestamp = os.time(),
        capture_time = os.date("%Y-%m-%d %H:%M:%S"),
        frame = state.frame_count,
        sprite_count = #oam_entries,
        obsel = state.obsel_config and {
            raw = state.obsel_config.raw,
            name_base = state.obsel_config.name_base,
            name_select = state.obsel_config.name_select,
            size_select = state.obsel_config.size_select,
            tile_base_addr = state.obsel_config.tile_base_addr,
            oam_base_addr = state.obsel_config.oam_base_addr,
            oam_addr_offset = state.obsel_config.oam_addr_offset,
        } or nil,
        bounding_box = {
            x = min_x,
            y = min_y,
            width = max_x - min_x,
            height = max_y - min_y
        },
        oam_entries = oam_entries,
        rom_sources = rom_sources
    }

    -- Write JSON file
    local json_str = to_json(capture)
    local filename = state.output_dir .. "/sprite_capture.json"

    local file = io.open(filename, "w")
    if file then
        file:write(json_str)
        file:close()
        emu.log(string.format(
            "CAPTURE: Saved %d sprites to %s (ROM sources: %d)",
            #oam_entries, filename, #rom_sources
        ))
    else
        emu.log("ERROR: Could not write " .. filename)
    end

    -- Also display on screen
    emu.displayMessage("Capture", string.format(
        "Saved %d sprites (%d ROM sources)",
        #oam_entries, #rom_sources
    ))
end

-- ============================================================================
-- INPUT HANDLING
-- ============================================================================

-- Check for F9 hotkey (edge detection)
local function check_hotkey()
    local f9_pressed = emu.isKeyPressed("F9")

    -- Detect rising edge (key just pressed)
    if f9_pressed and not state.last_f9_state then
        emu.log("F9 pressed - capturing sprites...")
        export_capture()
    end

    state.last_f9_state = f9_pressed
end

-- ============================================================================
-- FRAME CALLBACKS
-- ============================================================================

-- Poll at frame start (backup for DMA that happens during vblank)
local function on_frame_start()
    poll_dma()
end

local function on_frame_end()
    state.frame_count = state.frame_count + 1

    -- Poll DMA register at frame end too (catches late-frame DMA)
    poll_dma()

    -- Update PPU state
    update_obsel()

    -- Parse OAM
    parse_oam()

    -- Check for capture hotkey
    check_hotkey()

    -- Periodic status (every 5 seconds)
    if state.frame_count % 300 == 0 then
        local dma_count = 0
        for _ in pairs(state.dma_history) do dma_count = dma_count + 1 end

        emu.log(string.format(
            "STATUS: Frame=%d Sprites=%d DMA_History=%d",
            state.frame_count, #state.active_sprites, dma_count
        ))

        if dma_count == 0 then
            emu.log("TIP: No DMA captured yet. Enter a door/warp or trigger sprite loading.")
        end
    end
end

-- ============================================================================
-- INITIALIZATION
-- ============================================================================

local callbacks = {}

local function init()
    emu.log("==============================================")
    emu.log("  Mesen 2 Click Extractor - SpritePal        ")
    emu.log("==============================================")
    emu.log("Press F9 to capture visible sprites + ROM offsets")
    emu.log("Output: sprite_capture.json")
    emu.log("")

    -- Register DMA callback (fires at exact moment of $420B write)
    -- This is the most reliable way to catch DMA transfers
    callbacks.dma = emu.addMemoryCallback(
        on_dma_enable_write,
        emu.callbackType.write,  -- Value 1
        DMA_ENABLE,
        DMA_ENABLE
    )
    emu.log("Registered DMA callback for $420B")

    -- Register frame start callback (polls DMA during vblank)
    callbacks.frame_start = emu.addEventCallback(
        on_frame_start,
        emu.eventType.startFrame
    )

    -- Register frame end callback (handles OAM parsing, hotkey check)
    callbacks.frame_end = emu.addEventCallback(
        on_frame_end,
        emu.eventType.endFrame
    )

    -- Get initial OBSEL
    update_obsel()

    emu.log("Ready. Play the game and press F9 when sprite is visible.")
    emu.log("Watch for 'DMA[CB]:' or 'DMA[POLL]:' messages in log.")
end

local function _cleanup()  -- luacheck: ignore (reserved for cleanup hook)
    emu.log("Cleaning up...")

    if callbacks.dma then
        emu.removeMemoryCallback(callbacks.dma)
    end
    if callbacks.frame_start then
        emu.removeEventCallback(callbacks.frame_start)
    end
    if callbacks.frame_end then
        emu.removeEventCallback(callbacks.frame_end)
    end

    emu.log(string.format("Session ended: %d frames", state.frame_count))
end

-- Start
init()
