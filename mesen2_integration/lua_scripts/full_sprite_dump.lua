-- SpritePal Full Sprite Dump Script
-- Captures EVERYTHING needed for complete sprite reconstruction:
--   - All 128 OAM entries (not just visible)
--   - Complete sprite VRAM region (based on OBSEL)
--   - All 8 sprite palettes from CGRAM
--   - OBSEL configuration
--
-- Press F9 to capture full dump to JSON
-- Press F10 to capture raw binary dumps (OAM.dmp, VRAM.dmp, CGRAM.dmp)

local OUTPUT_DIR = os.getenv("OUTPUT_DIR") or "C:\\CustomScripts\\KirbyMax\\workshop\\exhal-master\\spritepal\\mesen2_exchange\\"
local LOG_FILE = OUTPUT_DIR .. "capture_log.txt"

-- Memory type references (correct names from Mesen2/Core/Shared/MemoryType.h)
-- The Lua API exposes enum names with first char lowercased
local MEM = {
    oam = emu.memType.snesSpriteRam,   -- SnesSpriteRam -> snesSpriteRam
    vram = emu.memType.snesVideoRam,   -- SnesVideoRam -> snesVideoRam
    cgram = emu.memType.snesCgRam,     -- SnesCgRam -> snesCgRam
}

os.execute('mkdir "' .. OUTPUT_DIR:gsub("\\", "\\\\") .. '" 2>NUL')

-- Logging
local function log(msg)
    local f = io.open(LOG_FILE, "a")
    if f then
        f:write(os.date("%H:%M:%S") .. " [FULL_DUMP] " .. msg .. "\n")
        f:close()
    end
    emu.log("[FULL_DUMP] " .. msg)
end

log("Full sprite dump script loaded")

-- ============================================================================
-- OBSEL Latch - capture writes to $2101
-- ============================================================================
local LAST_OBSEL = nil

local function install_obsel_latch()
    if not emu.addMemoryCallback then
        log("WARN: addMemoryCallback not available")
        return
    end

    local cbWrite = (emu.callbackType and emu.callbackType.write) or
                    (emu.memCallbackType and emu.memCallbackType.write)

    if not cbWrite then
        log("WARN: Could not find callbackType.write")
        return
    end

    emu.addMemoryCallback(function(address, value)
        LAST_OBSEL = value & 0xFF
    end, cbWrite, 0x2101, 0x2101, emu.cpuType.snes, emu.memType.snesMemory)

    log("OBSEL latch installed")
end

install_obsel_latch()

-- ============================================================================
-- SNES Constants
-- ============================================================================
local SIZE_TABLE = {
    [0] = {8, 8, 16, 16},   -- 8x8 / 16x16
    [1] = {8, 8, 32, 32},   -- 8x8 / 32x32
    [2] = {8, 8, 64, 64},   -- 8x8 / 64x64
    [3] = {16, 16, 32, 32}, -- 16x16 / 32x32 (Kirby Super Star)
    [4] = {16, 16, 64, 64}, -- 16x16 / 64x64
    [5] = {32, 32, 64, 64}, -- 32x32 / 64x64
    [6] = {16, 32, 32, 64}, -- 16x32 / 32x64
    [7] = {16, 32, 32, 32}, -- 16x32 / 32x32
}

local frameCount = 0

-- ============================================================================
-- Helper Functions
-- ============================================================================

local function get_obsel()
    local obsel
    if LAST_OBSEL ~= nil then
        obsel = LAST_OBSEL
    else
        obsel = emu.read(0x2101, emu.memType.snesMemory) or 0x63
        log(string.format("WARN: No latched OBSEL, using 0x%02X", obsel))
    end

    local name_base = obsel & 0x07
    local name_sel = (obsel >> 3) & 0x03
    local size_sel = (obsel >> 5) & 0x07

    return {
        raw = obsel,
        name_base = name_base,
        name_select = name_sel,
        size_select = size_sel,
        tile_base_addr = name_base << 14,  -- Byte address in VRAM
        second_table_offset = (name_sel + 1) << 13,  -- Byte offset
    }
end

local function bytes_to_hex(bytes)
    local hex = {}
    for i = 1, #bytes do
        hex[i] = string.format("%02X", bytes[i])
    end
    return table.concat(hex)
end

local function bgr555_to_rgb(bgr555)
    local r = (bgr555 & 0x1F) << 3
    local g = ((bgr555 >> 5) & 0x1F) << 3
    local b = ((bgr555 >> 10) & 0x1F) << 3
    return {r, g, b}
end

-- ============================================================================
-- Read Complete OAM (all 128 entries)
-- ============================================================================
local function read_full_oam(obsel)
    local entries = {}
    local size_info = SIZE_TABLE[obsel.size_select] or SIZE_TABLE[3]
    local small_w, small_h = size_info[1], size_info[2]
    local large_w, large_h = size_info[3], size_info[4]

    for i = 0, 127 do
        local base = i * 4

        -- Main table (4 bytes per entry)
        local x_low = emu.read(base, MEM.oam)
        local y = emu.read(base + 1, MEM.oam)
        local tile = emu.read(base + 2, MEM.oam)
        local attr = emu.read(base + 3, MEM.oam)

        -- High table (2 bits per entry at offset 0x200)
        local high_byte_idx = math.floor(i / 4)
        local high_bit_pos = (i % 4) * 2
        local high_byte = emu.read(0x200 + high_byte_idx, MEM.oam)
        local high_bits = (high_byte >> high_bit_pos) & 0x03

        local x_high = high_bits & 0x01
        local size_bit = (high_bits >> 1) & 0x01

        -- Calculate signed X (9-bit)
        local x = x_low | (x_high << 8)
        if x >= 256 then
            x = x - 512
        end

        -- Determine sprite size
        local width, height
        if size_bit == 1 then
            width, height = large_w, large_h
        else
            width, height = small_w, small_h
        end

        -- Parse attributes
        local name_table = attr & 0x01
        local palette = (attr >> 1) & 0x07
        local priority = (attr >> 4) & 0x03
        local flip_h = ((attr >> 6) & 0x01) == 1
        local flip_v = ((attr >> 7) & 0x01) == 1

        -- Read tile data from VRAM for ALL tiles in this sprite
        local tiles_x = width // 8
        local tiles_y = height // 8
        local tile_data_list = {}

        local base_tile_x = tile & 0x0F
        local base_tile_y = (tile >> 4) & 0x0F

        for ty = 0, tiles_y - 1 do
            for tx = 0, tiles_x - 1 do
                -- SNES nibble wrapping
                local tile_x = (base_tile_x + tx) & 0x0F
                local tile_y = (base_tile_y + ty) & 0x0F
                local tile_idx = (tile_y << 4) | tile_x

                -- Calculate VRAM address
                local word_addr = (obsel.name_base << 13) + (tile_idx << 4)
                if name_table == 1 then
                    word_addr = word_addr + ((obsel.name_select + 1) << 12)
                end
                local byte_addr = (word_addr & 0x7FFF) << 1

                -- Read 32 bytes of 4bpp tile data
                local tile_bytes = {}
                for b = 0, 31 do
                    tile_bytes[b + 1] = emu.read(byte_addr + b, MEM.vram)
                end

                table.insert(tile_data_list, {
                    tile_index = tile_idx,
                    vram_addr = byte_addr,
                    pos_x = tx,  -- Tile index, not pixel offset (renderer multiplies by 8)
                    pos_y = ty,  -- Tile index, not pixel offset
                    data_hex = bytes_to_hex(tile_bytes),
                })
            end
        end

        entries[i + 1] = {
            id = i,
            x = x,
            y = y,
            tile = tile,
            width = width,
            height = height,
            name_table = name_table,
            palette = palette,
            priority = priority,
            flip_h = flip_h,
            flip_v = flip_v,
            size_large = (size_bit == 1),
            tiles = tile_data_list,
        }
    end

    return entries
end

-- ============================================================================
-- Read All Sprite Palettes from CGRAM
-- ============================================================================
local function read_sprite_palettes()
    local palettes = {}

    -- Sprite palettes are at CGRAM $100-$1FF (8 palettes x 16 colors x 2 bytes)
    for pal = 0, 7 do
        local colors = {}
        local base = 0x100 + (pal * 32)  -- 16 colors * 2 bytes each

        for c = 0, 15 do
            local addr = base + (c * 2)
            local lo = emu.read(addr, MEM.cgram)
            local hi = emu.read(addr + 1, MEM.cgram)
            local bgr555 = lo | (hi << 8)
            colors[c + 1] = bgr555_to_rgb(bgr555)
        end

        palettes[pal] = colors
    end

    return palettes
end

-- ============================================================================
-- Capture to JSON (F9)
-- ============================================================================
local function capture_full_json()
    local obsel = get_obsel()
    local timestamp = os.time()
    local filename = OUTPUT_DIR .. "full_dump_" .. timestamp .. ".json"

    log(string.format("Capturing full dump (OBSEL=0x%02X, frame=%d)", obsel.raw, frameCount))

    local entries = read_full_oam(obsel)
    local palettes = read_sprite_palettes()

    -- Count visible sprites (Y not at 224-239 which is off-screen)
    local visible_count = 0
    for _, e in ipairs(entries) do
        if e.y < 224 or e.y >= 240 then
            visible_count = visible_count + 1
        end
    end

    -- Build JSON manually (Lua doesn't have native JSON)
    local f = io.open(filename, "w")
    if not f then
        log("ERROR: Could not open " .. filename)
        return
    end

    f:write('{\n')
    f:write('  "schema_version": "2.0",\n')
    f:write('  "capture_type": "full_dump",\n')
    f:write(string.format('  "timestamp": %d,\n', timestamp))
    f:write(string.format('  "capture_time": "%s",\n', os.date("%Y-%m-%d %H:%M:%S")))
    f:write(string.format('  "frame": %d,\n', frameCount))
    f:write('  "obsel": {\n')
    f:write(string.format('    "raw": %d,\n', obsel.raw))
    f:write(string.format('    "name_base": %d,\n', obsel.name_base))
    f:write(string.format('    "name_select": %d,\n', obsel.name_select))
    f:write(string.format('    "size_select": %d,\n', obsel.size_select))
    f:write(string.format('    "tile_base_addr": %d,\n', obsel.tile_base_addr))
    f:write(string.format('    "second_table_offset": %d\n', obsel.second_table_offset))
    f:write('  },\n')
    f:write(string.format('  "total_entries": 128,\n'))
    f:write(string.format('  "visible_count": %d,\n', visible_count))

    -- Write entries
    f:write('  "entries": [\n')
    for i, e in ipairs(entries) do
        f:write('    {\n')
        f:write(string.format('      "id": %d,\n', e.id))
        f:write(string.format('      "x": %d,\n', e.x))
        f:write(string.format('      "y": %d,\n', e.y))
        f:write(string.format('      "tile": %d,\n', e.tile))
        f:write(string.format('      "width": %d,\n', e.width))
        f:write(string.format('      "height": %d,\n', e.height))
        f:write(string.format('      "name_table": %d,\n', e.name_table))
        f:write(string.format('      "palette": %d,\n', e.palette))
        f:write(string.format('      "priority": %d,\n', e.priority))
        f:write(string.format('      "flip_h": %s,\n', e.flip_h and "true" or "false"))
        f:write(string.format('      "flip_v": %s,\n', e.flip_v and "true" or "false"))
        f:write(string.format('      "size_large": %s,\n', e.size_large and "true" or "false"))

        -- Write tiles array
        f:write('      "tiles": [\n')
        for j, t in ipairs(e.tiles) do
            f:write('        {\n')
            f:write(string.format('          "tile_index": %d,\n', t.tile_index))
            f:write(string.format('          "vram_addr": %d,\n', t.vram_addr))
            f:write(string.format('          "pos_x": %d,\n', t.pos_x))
            f:write(string.format('          "pos_y": %d,\n', t.pos_y))
            f:write(string.format('          "data_hex": "%s"\n', t.data_hex))
            if j < #e.tiles then
                f:write('        },\n')
            else
                f:write('        }\n')
            end
        end
        f:write('      ]\n')

        if i < #entries then
            f:write('    },\n')
        else
            f:write('    }\n')
        end
    end
    f:write('  ],\n')

    -- Write palettes
    f:write('  "palettes": {\n')
    for pal = 0, 7 do
        f:write(string.format('    "%d": [', pal))
        local colors = palettes[pal]
        for c = 1, 16 do
            f:write(string.format('[%d,%d,%d]', colors[c][1], colors[c][2], colors[c][3]))
            if c < 16 then f:write(',') end
        end
        if pal < 7 then
            f:write('],\n')
        else
            f:write(']\n')
        end
    end
    f:write('  }\n')

    f:write('}\n')
    f:close()

    log(string.format("Saved full dump to %s (%d entries, %d visible)", filename, 128, visible_count))
    emu.displayMessage("Full Dump", string.format("Saved %d entries to %s", 128, filename:match("[^\\]+$")))
end

-- ============================================================================
-- Capture Raw Binary Dumps (F10) - compatible with reconstruct_from_dumps.py
-- ============================================================================
local function capture_binary_dumps()
    local timestamp = os.time()
    local prefix = OUTPUT_DIR .. "dump_F" .. frameCount .. "_"

    log(string.format("Capturing binary dumps (frame=%d)", frameCount))

    -- OAM dump (544 bytes)
    local oam_file = prefix .. "OAM.dmp"
    local f = io.open(oam_file, "wb")
    if f then
        for i = 0, 543 do
            f:write(string.char(emu.read(i, MEM.oam)))
        end
        f:close()
        log("Saved " .. oam_file)
    end

    -- VRAM dump (64KB)
    local vram_file = prefix .. "VRAM.dmp"
    f = io.open(vram_file, "wb")
    if f then
        for i = 0, 65535 do
            f:write(string.char(emu.read(i, MEM.vram)))
        end
        f:close()
        log("Saved " .. vram_file)
    end

    -- CGRAM dump (512 bytes)
    local cgram_file = prefix .. "CGRAM.dmp"
    f = io.open(cgram_file, "wb")
    if f then
        for i = 0, 511 do
            f:write(string.char(emu.read(i, MEM.cgram)))
        end
        f:close()
        log("Saved " .. cgram_file)
    end

    -- Save OBSEL to a text file for reference
    local obsel = get_obsel()
    local obsel_file = prefix .. "OBSEL.txt"
    f = io.open(obsel_file, "w")
    if f then
        f:write(string.format("OBSEL: 0x%02X\n", obsel.raw))
        f:write(string.format("name_base: %d\n", obsel.name_base))
        f:write(string.format("name_select: %d\n", obsel.name_select))
        f:write(string.format("size_select: %d\n", obsel.size_select))
        f:write(string.format("Frame: %d\n", frameCount))
        f:close()
        log("Saved " .. obsel_file)
    end

    emu.displayMessage("Binary Dumps", string.format("Saved OAM/VRAM/CGRAM to %s*", prefix:match("[^\\]+$")))
end

-- ============================================================================
-- Key Bindings (using emu.isKeyPressed for keyboard detection)
-- ============================================================================
local lastF9State = false
local lastF10State = false

emu.addEventCallback(function()
    frameCount = frameCount + 1

    -- Draw on-screen status
    emu.drawString(8, 8, "SpritePal Full Dump: F9=JSON, F10=Binary", 0xFFFFFF, 0x80000000)
    emu.drawString(8, 20, "Frame: " .. frameCount .. (LAST_OBSEL and string.format(" OBSEL:0x%02X", LAST_OBSEL) or " OBSEL:??"), 0xFFFFFF, 0x80000000)

    -- F9 key detection with edge detection (only trigger once per press)
    local f9Pressed = emu.isKeyPressed("F9")
    if f9Pressed and not lastF9State then
        log("F9 pressed at frame " .. frameCount)
        emu.drawString(8, 32, "CAPTURING JSON...", 0x00FF00, 0x80000000)
        capture_full_json()
    end
    lastF9State = f9Pressed

    -- F10 key detection with edge detection
    local f10Pressed = emu.isKeyPressed("F10")
    if f10Pressed and not lastF10State then
        log("F10 pressed at frame " .. frameCount)
        emu.drawString(8, 32, "CAPTURING BINARY DUMPS...", 0xFFFF00, 0x80000000)
        capture_binary_dumps()
    end
    lastF10State = f10Pressed
end, emu.eventType.endFrame)

log("Ready! Press F9 for full JSON dump, F10 for binary dumps")
emu.displayMessage("Full Sprite Dump", "F9=JSON dump, F10=Binary dumps")
