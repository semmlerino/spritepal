-- SpritePal Mesen 2 Sprite Capture Script
-- Press F9 to capture all visible OAM entries with their VRAM tile data
-- Output: sprite_capture.json for SpritePal to process

local OUTPUT_DIR = "C:\\CustomScripts\\KirbyMax\\workshop\\exhal-master\\spritepal\\mesen2_exchange\\"
local LOG_FILE = OUTPUT_DIR .. "capture_log.txt"
local MEM = {
    oam = emu.memType.snesOam or emu.memType.snesSpriteRam,
    vram = emu.memType.snesVram or emu.memType.snesVideoRam,
    cgram = emu.memType.snesCgram or emu.memType.snesCgRam,
}

-- Create output directory if needed (will fail silently if exists)
os.execute('mkdir "' .. OUTPUT_DIR:gsub("\\", "\\\\") .. '" 2>NUL')

-- Logging
local function log(msg)
    local f = io.open(LOG_FILE, "a")
    if f then
        f:write(os.date("%H:%M:%S") .. " " .. msg .. "\n")
        f:close()
    end
end

log("SpritePal capture script loaded")

-- BGR555 to RGB888 conversion function
-- Converts SNES CGRAM 15-bit color to 8-bit RGB
local function bgr555_to_rgb888(bgr555)
    local r = (bgr555 & 0x1F) * 255 // 31
    local g = ((bgr555 >> 5) & 0x1F) * 255 // 31
    local b = ((bgr555 >> 10) & 0x1F) * 255 // 31
    return {r, g, b}
end

-- Frame counter (emu.getState().ppu doesn't exist for SNES in Mesen 2)
local frameCount = 0

-- SNES sprite size table (size_select -> [small_w, small_h, large_w, large_h])
local SIZE_TABLE = {
    [0] = {8, 8, 16, 16},   -- 8x8 / 16x16
    [1] = {8, 8, 32, 32},   -- 8x8 / 32x32
    [2] = {8, 8, 64, 64},   -- 8x8 / 64x64
    [3] = {16, 16, 32, 32}, -- 16x16 / 32x32
    [4] = {16, 16, 64, 64}, -- 16x16 / 64x64
    [5] = {32, 32, 64, 64}, -- 32x32 / 64x64
    [6] = {16, 32, 32, 64}, -- 16x32 / 32x64
    [7] = {16, 32, 32, 32}, -- 16x32 / 32x32
}

-- Get OBSEL settings
local function get_obsel()
    local obsel = emu.read(0x2101, emu.memType.snesMemory)
    local name_base = (obsel & 0x07)
    local name_sel = (obsel >> 3) & 0x03
    local size_sel = (obsel >> 5) & 0x07
    local oam_base_addr = name_base << 13
    local oam_addr_offset = (name_sel + 1) << 12

    return {
        raw = obsel,
        name_base = name_base,
        name_select = name_sel,
        size_select = size_sel,
        -- Sprite tile base in VRAM (byte address for emu.read)
        tile_base_addr = oam_base_addr * 2,
        -- Word-addressed values used by the PPU formula
        oam_base_addr = oam_base_addr,
        oam_addr_offset = oam_addr_offset,
    }
end

-- Parse a single OAM entry
local function parse_oam_entry(index)
    local base = index * 4

    -- Main table (4 bytes per entry)
    local x_low = emu.read(base + 0, MEM.oam)
    local y = emu.read(base + 1, MEM.oam)
    local tile = emu.read(base + 2, MEM.oam)
    local attr = emu.read(base + 3, MEM.oam)

    -- High table (2 bits per entry at offset 0x200)
    local hi_byte_idx = 0x200 + math.floor(index / 4)
    local hi_byte = emu.read(hi_byte_idx, MEM.oam)
    local hi_bit_pos = (index % 4) * 2
    local x_bit9 = (hi_byte >> hi_bit_pos) & 1
    local size_bit = (hi_byte >> (hi_bit_pos + 1)) & 1

    -- Calculate full X position (signed)
    local x = x_low + (x_bit9 * 256)
    if x >= 256 then x = x - 512 end

    -- Parse attributes
    local name_table = (attr & 0x01)  -- Bit 0: tile index bit 8 / second table select
    local palette = (attr >> 1) & 0x07  -- Bits 1-3: palette
    local priority = (attr >> 4) & 0x03  -- Bits 4-5: priority
    local flip_h = ((attr >> 6) & 0x01) == 1
    local flip_v = ((attr >> 7) & 0x01) == 1

    return {
        id = index,
        x = x,
        y = y,
        tile = tile,
        name_table = name_table,
        palette = palette,
        priority = priority,
        flip_h = flip_h,
        flip_v = flip_v,
        size_large = size_bit == 1
    }
end

-- Get sprite size based on OBSEL and size bit
local function get_sprite_size(obsel, is_large)
    local sizes = SIZE_TABLE[obsel.size_select] or {8, 8, 16, 16}
    if is_large then
        return sizes[3], sizes[4]
    else
        return sizes[1], sizes[2]
    end
end

-- Check if sprite is visible on screen (roughly)
local function is_visible(entry)
    -- Y in overscan zone [224, 240) means off-screen (canonical spec)
    if entry.y >= 224 and entry.y < 240 then return false end
    -- X completely off left
    if entry.x <= -64 then return false end
    -- X completely off right
    if entry.x >= 256 then return false end
    return true
end

-- Read a single 4bpp 8x8 tile from VRAM
-- Mesen2 Lua exposes VRAM as byte-addressed memory.
-- A 4bpp tile is 32 bytes = 16 words.
local vram_read_mode = "word"  -- Force word mode; byte mode broken in some Mesen2 builds

local function read_vram_word(byte_addr)
    -- Try emu.readWord first (returns 16-bit word)
    if emu.readWord then
        local ok, word = pcall(emu.readWord, byte_addr, MEM.vram)
        if ok and word then
            return word
        end
    end
    -- Fallback: read two consecutive bytes and combine them
    local lo = emu.read(byte_addr, MEM.vram) or 0
    local hi = emu.read(byte_addr + 1, MEM.vram) or 0
    return lo | (hi << 8)
end

local function read_vram_tile_word(vram_addr)
    local tile_data = {}
    local high_nonzero = false

    for i = 0, 15 do
        local word = read_vram_word(vram_addr + (i * 2))
        -- Mesen2 readWord returns big-endian; swap bytes for correct tile order
        tile_data[i * 2 + 1] = (word >> 8) & 0xFF
        tile_data[i * 2 + 2] = word & 0xFF
        if tile_data[i * 2 + 2] ~= 0 then
            high_nonzero = true
        end
    end

    return tile_data, high_nonzero
end

local function read_vram_tile_byte(vram_addr)
    local tile_data = {}
    local odd_nonzero = false

    for i = 0, 31 do
        local b = emu.read(vram_addr + i, MEM.vram)
        tile_data[i + 1] = b
        if (i % 2 == 1) and b ~= 0 then
            odd_nonzero = true
        end
    end

    return tile_data, odd_nonzero
end

local function read_vram_tile(vram_addr)
    if vram_read_mode == "word" then
        local tile_data = read_vram_tile_word(vram_addr)
        return tile_data
    end
    if vram_read_mode == "byte" then
        local tile_data = read_vram_tile_byte(vram_addr)
        return tile_data
    end

    local word_data, high_nonzero = read_vram_tile_word(vram_addr)
    if high_nonzero then
        vram_read_mode = "word"
        return word_data
    end

    local byte_data, odd_nonzero = read_vram_tile_byte(vram_addr)
    if odd_nonzero then
        vram_read_mode = "byte"
        return byte_data
    end

    -- Ambiguous: default to byte mode (safer for Mesen2 Lua VRAM reads).
    vram_read_mode = "byte"
    return byte_data
end

-- Calculate VRAM address for a tile index (PPU math is word-based)
local function tile_to_vram_addr(tile_idx, use_second_table, obsel)
    local word_addr = obsel.oam_base_addr + (tile_idx << 4)
    if use_second_table then
        word_addr = word_addr + obsel.oam_addr_offset
    end
    word_addr = word_addr & 0x7FFF
    return word_addr << 1
end

-- Capture all visible sprites
local function capture_sprites()
    log("F9 pressed - capturing sprites at frame " .. frameCount)

    local obsel = get_obsel()
    local frame = frameCount
    local entries = {}
    local visible_count = 0
    local tile_count = 0
    local odd_nonzero_tiles = 0

    -- Parse all 128 OAM entries
    for i = 0, 127 do
        local entry = parse_oam_entry(i)

        if is_visible(entry) then
            visible_count = visible_count + 1

            local width, height = get_sprite_size(obsel, entry.size_large)
            entry.width = width
            entry.height = height

            -- Calculate tiles needed for this sprite
            local tiles_x = width / 8
            local tiles_y = height / 8
            entry.tile_data = {}

            -- Read all tiles for this sprite
            local tile_row = (entry.tile >> 4) & 0x0F
            local tile_col = entry.tile & 0x0F
            local use_second_table = entry.name_table == 1
            for ty = 0, tiles_y - 1 do
                local row = (tile_row + ty) & 0x0F
                for tx = 0, tiles_x - 1 do
                    local col = (tile_col + tx) & 0x0F
                    local tile_index = (row << 4) | col
                    local vram_addr = tile_to_vram_addr(tile_index, use_second_table, obsel)

                    local tile_bytes = read_vram_tile(vram_addr)
                    tile_count = tile_count + 1
                    local has_odd_nonzero = false
                    for idx = 2, #tile_bytes, 2 do
                        if tile_bytes[idx] ~= 0 then
                            has_odd_nonzero = true
                            break
                        end
                    end
                    if has_odd_nonzero then
                        odd_nonzero_tiles = odd_nonzero_tiles + 1
                    end

                    -- Convert to hex string for JSON
                    local hex = ""
                    for _, b in ipairs(tile_bytes) do
                        hex = hex .. string.format("%02X", b)
                    end

                    table.insert(entry.tile_data, {
                        tile_index = tile_index,
                        vram_addr = vram_addr,
                        pos_x = tx,
                        pos_y = ty,
                        data_hex = hex
                    })
                end
            end

            table.insert(entries, entry)
        end
    end

    -- Read palette data for sprites (palettes 0-7 at CGRAM $100-$1FF)
    local palettes = {}
    for pal_idx = 0, 7 do
        local colors = {}
        for col = 0, 15 do
            local cgram_addr = 0x100 + (pal_idx * 32) + (col * 2)
            local lo = emu.read(cgram_addr, MEM.cgram)
            local hi = emu.read(cgram_addr + 1, MEM.cgram)
            local color = lo + (hi * 256)
            table.insert(colors, color)
        end
        palettes[pal_idx] = colors
    end

    if tile_count > 0 and odd_nonzero_tiles == 0 then
        log("ERROR: VRAM tiles have zero odd-byte data; aborting capture (bad VRAM reads).")
        return nil
    end

    -- Build JSON output
    local timestamp = os.time()
    local filename = OUTPUT_DIR .. "sprite_capture_" .. timestamp .. ".json"

    local f = io.open(filename, "w")
    if not f then
        log("ERROR: Could not create output file: " .. filename)
        return
    end

    -- Write JSON manually (Lua doesn't have native JSON)
    f:write("{\n")
    f:write('  "schema_version": "1.0",\n')
    f:write(string.format('  "timestamp": %d,\n', timestamp))
    f:write(string.format('  "frame": %d,\n', frame))
    f:write('  "obsel": {\n')
    f:write(string.format('    "raw": %d,\n', obsel.raw))
    f:write(string.format('    "name_base": %d,\n', obsel.name_base))
    f:write(string.format('    "name_select": %d,\n', obsel.name_select))
    f:write(string.format('    "size_select": %d,\n', obsel.size_select))
    f:write(string.format(
        '    "tile_base_addr": %d, "oam_base_addr": %d, "oam_addr_offset": %d\n',
        obsel.tile_base_addr, obsel.oam_base_addr, obsel.oam_addr_offset))
    f:write('  },\n')

    f:write(string.format('  "visible_count": %d,\n', visible_count))
    f:write('  "entries": [\n')

    for idx, entry in ipairs(entries) do
        f:write('    {\n')
        f:write(string.format('      "id": %d,\n', entry.id))
        f:write(string.format('      "x": %d,\n', entry.x))
        f:write(string.format('      "y": %d,\n', entry.y))
        f:write(string.format('      "tile": %d,\n', entry.tile))
        f:write(string.format('      "width": %d,\n', entry.width))
        f:write(string.format('      "height": %d,\n', entry.height))
    f:write(string.format('      "name_table": %d,\n', entry.name_table))
    f:write(string.format('      "tile_page": %d,\n', entry.name_table))
    f:write(string.format('      "tile_page": %d,\n', entry.name_table))
        f:write(string.format('      "palette": %d,\n', entry.palette))
        f:write(string.format('      "priority": %d,\n', entry.priority))
        f:write(string.format('      "flip_h": %s,\n', entry.flip_h and "true" or "false"))
        f:write(string.format('      "flip_v": %s,\n', entry.flip_v and "true" or "false"))
        f:write(string.format('      "size_large": %s,\n', entry.size_large and "true" or "false"))
        f:write('      "tiles": [\n')

        for tidx, tile in ipairs(entry.tile_data) do
            f:write('        {\n')
            f:write(string.format('          "tile_index": %d,\n', tile.tile_index))
            f:write(string.format('          "vram_addr": %d,\n', tile.vram_addr))
            f:write(string.format('          "pos_x": %d,\n', tile.pos_x))
            f:write(string.format('          "pos_y": %d,\n', tile.pos_y))
            f:write(string.format('          "data_hex": "%s"\n', tile.data_hex))
            f:write('        }')
            if tidx < #entry.tile_data then f:write(',') end
            f:write('\n')
        end
        f:write('      ]\n')
        f:write('    }')
        if idx < #entries then f:write(',') end
        f:write('\n')
    end
    f:write('  ],\n')

    -- Write palettes (converted to RGB888)
    f:write('  "palettes": {\n')
    for pal_idx = 0, 7 do
        f:write(string.format('    "%d": [', pal_idx))
        for col_idx, bgr555_color in ipairs(palettes[pal_idx]) do
            local rgb = bgr555_to_rgb888(bgr555_color)
            f:write(string.format('[%d, %d, %d]', rgb[1], rgb[2], rgb[3]))
            if col_idx < #palettes[pal_idx] then f:write(', ') end
        end
        f:write(']')
        if pal_idx < 7 then f:write(',') end
        f:write('\n')
    end
    f:write('  }\n')

    f:write('}\n')
    f:close()

    log("Captured " .. visible_count .. " visible sprites to " .. filename)
    print("SpritePal: Captured " .. visible_count .. " sprites to " .. filename)
end

-- Track previous state for edge detection
local lastCaptureState = false

-- Register frame callback
emu.addEventCallback(function()
    frameCount = frameCount + 1

    -- Draw on-screen indicator
    emu.drawString(8, 8, "SpritePal: Start+Select=Capture", 0xFFFFFF, 0x80000000)
    emu.drawString(8, 20, "Frame: " .. frameCount, 0xFFFFFF, 0x80000000)

    -- Use controller input: Start+Select together triggers capture
    local input = emu.getInput(0)
    local capturePressed = input.start and input.select

    -- Edge detection: only trigger once per press
    if capturePressed and not lastCaptureState then
        log("Start+Select detected at frame " .. frameCount)
        emu.drawString(8, 32, "CAPTURING...", 0x00FF00, 0x80000000)
        capture_sprites()
    end
    lastCaptureState = capturePressed
end, emu.eventType.endFrame)

-- Startup message
log("Script running, press Start+Select during gameplay to capture sprites")
print("SpritePal: Press Start+Select together to capture sprites")
print("Look for on-screen indicator to confirm script is active")
