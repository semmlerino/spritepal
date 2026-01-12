-- Gameplay Capture: Navigates to Spring Breeze gameplay and captures
-- Waits until frame 1800 (~30 seconds) to ensure we're in actual gameplay
local OUTPUT_DIR = os.getenv("OUTPUT_DIR") or "C:\\CustomScripts\\KirbyMax\\workshop\\exhal-master\\spritepal\\mesen2_exchange\\"
local MEM = {
    oam = emu.memType.snesOam or emu.memType.snesSpriteRam,
    vram = emu.memType.snesVram or emu.memType.snesVideoRam,
    cgram = emu.memType.snesCgram or emu.memType.snesCgRam,
    prgRom = emu.memType.snesPrgRom or emu.memType.prgRom,
}

-- PRG ROM size fail-fast validation
local prg_size = nil
if MEM.prgRom then
    local ok, size = pcall(emu.getMemorySize, MEM.prgRom)
    if ok and size and size > 0 then
        prg_size = size
    end
end
if not prg_size or prg_size == 0 then
    error([[
PRG ROM size unavailable. Cannot proceed.

Possible causes:
1. ROM not loaded - ensure game is running before starting capture
2. Memory type not exposed - verify Mesen2 build supports prgRom
3. Lua API limitation - check Mesen2 version compatibility

Do not use fallback values. Fix the root cause.
]])
end
print(string.format("PRG ROM size validated: 0x%X bytes (%d KB)", prg_size, prg_size / 1024))

local SIZE_TABLE = {
    [0] = {8, 8, 16, 16}, [1] = {8, 8, 32, 32}, [2] = {8, 8, 64, 64},
    [3] = {16, 16, 32, 32}, [4] = {16, 16, 64, 64}, [5] = {32, 32, 64, 64},
    [6] = {16, 32, 32, 64}, [7] = {16, 32, 32, 32},
}

local function get_obsel()
    local obsel = emu.read(0x2101, emu.memType.snesMemory)
    local name_base = (obsel & 0x07)
    local name_select = (obsel >> 3) & 0x03
    local oam_base_addr = name_base << 13
    local oam_addr_offset = (name_select + 1) << 12
    return {
        raw = obsel,
        name_base = name_base,
        name_select = name_select,
        size_select = (obsel >> 5) & 0x07,
        tile_base_addr = oam_base_addr * 2,
        oam_base_addr = oam_base_addr,
        oam_addr_offset = oam_addr_offset,
    }
end

local function parse_oam_entry(index)
    local base = index * 4
    local x_low = emu.read(base + 0, MEM.oam)
    local y = emu.read(base + 1, MEM.oam)
    local tile = emu.read(base + 2, MEM.oam)
    local attr = emu.read(base + 3, MEM.oam)
    local hi_byte = emu.read(0x200 + math.floor(index / 4), MEM.oam)
    local hi_bit_pos = (index % 4) * 2
    local x_bit9 = (hi_byte >> hi_bit_pos) & 1
    local size_bit = (hi_byte >> (hi_bit_pos + 1)) & 1
    local x = x_low + (x_bit9 * 256)
    if x >= 256 then x = x - 512 end
    return {
        id = index, x = x, y = y, tile = tile,
        name_table = (attr & 0x01), palette = (attr >> 1) & 0x07,
        priority = (attr >> 4) & 0x03, flip_h = ((attr >> 6) & 0x01) == 1,
        flip_v = ((attr >> 7) & 0x01) == 1, size_large = size_bit == 1
    }
end

local function get_sprite_size(obsel, is_large)
    local sizes = SIZE_TABLE[obsel.size_select] or {8, 8, 16, 16}
    return is_large and sizes[3] or sizes[1], is_large and sizes[4] or sizes[2]
end

local function is_visible(entry)
    -- Y in overscan zone [224, 240) means off-screen (canonical spec)
    if entry.y >= 224 and entry.y < 240 then return false end
    if entry.x <= -64 or entry.x >= 256 then return false end
    return true
end

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

local function tile_to_vram_addr(tile_idx, use_second_table, obsel)
    local word_addr = obsel.oam_base_addr + (tile_idx << 4)
    if use_second_table then
        word_addr = word_addr + obsel.oam_addr_offset
    end
    word_addr = word_addr & 0x7FFF
    return word_addr << 1
end

local function capture_sprites()
    local obsel = get_obsel()
    local entries = {}
    local visible_count = 0
    local tile_count = 0
    local odd_nonzero_tiles = 0
    for i = 0, 127 do
        local entry = parse_oam_entry(i)
        if is_visible(entry) then
            visible_count = visible_count + 1
            local width, height = get_sprite_size(obsel, entry.size_large)
            entry.width = width
            entry.height = height
            entry.tile_data = {}
            local tiles_x, tiles_y = width / 8, height / 8
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
                    local hex = ""
                    for _, b in ipairs(tile_bytes) do hex = hex .. string.format("%02X", b) end
                    table.insert(entry.tile_data, {
                        tile_index = tile_index, vram_addr = vram_addr,
                        pos_x = tx, pos_y = ty, data_hex = hex
                    })
                end
            end
            table.insert(entries, entry)
        end
    end
    local palettes = {}
    for pal_idx = 0, 7 do
        local colors = {}
        for col = 0, 15 do
            local cgram_addr = 0x100 + (pal_idx * 32) + (col * 2)
            local lo = emu.read(cgram_addr, MEM.cgram)
            local hi = emu.read(cgram_addr + 1, MEM.cgram)
            table.insert(colors, lo + (hi * 256))
        end
        palettes[pal_idx] = colors
    end
    if tile_count > 0 and odd_nonzero_tiles == 0 then
        emu.log("ERROR: VRAM tiles have zero odd-byte data; aborting capture (bad VRAM reads).")
        return nil
    end
    return obsel, entries, visible_count, palettes
end

local fr = 0
local captured = false

emu.addEventCallback(function()
    fr = fr + 1

    -- Aggressive menu navigation for KSS
    -- Title screen
    if fr == 60 or fr == 90 then emu.setInput({start=true}, 0) end
    -- Main menu - select Spring Breeze (first option)
    if fr == 150 or fr == 180 then emu.setInput({a=true}, 0) end
    -- File select
    if fr == 240 or fr == 270 then emu.setInput({a=true}, 0) end
    -- Skip intro/cutscene
    if fr == 350 or fr == 400 or fr == 450 or fr == 500 then emu.setInput({start=true}, 0) end
    -- More skips
    if fr == 600 or fr == 700 or fr == 800 then emu.setInput({start=true}, 0) end
    -- Keep pressing A to skip dialogues
    if fr > 900 and fr < 1200 and fr % 60 == 0 then emu.setInput({a=true}, 0) end
    -- Move Kirby right during gameplay
    if fr > 1200 and fr < 1700 then
        if fr % 30 < 20 then emu.setInput({right=true}, 0) else emu.setInput({}, 0) end
    end
    -- Release all inputs before capture
    if fr == 1750 then emu.setInput({}, 0) end

    -- On-screen status
    if fr % 60 == 0 then
        emu.drawString(8, 8, "Gameplay Capture Script", 0xFFFFFF, 0x80000000)
        emu.drawString(8, 20, "Frame: " .. fr .. "/1800", 0xFFFFFF, 0x80000000)
        if fr < 1800 then
            emu.drawString(8, 32, "Navigating to gameplay...", 0xFFFF00, 0x80000000)
        end
    end

    -- Capture at frame 1800
    if fr == 1800 and not captured then
        captured = true
        local obsel, entries, visible_count, palettes = capture_sprites()
        if not obsel then
            emu.stop(2)
            return
        end

        local f = io.open(OUTPUT_DIR .. "gameplay_capture.json", "w")
        f:write("{\n")
        f:write('  "schema_version": "1.0",\n')
        f:write(string.format('  "frame": %d,\n', fr))
        f:write(string.format('  "visible_count": %d,\n', visible_count))
        f:write('  "obsel": {\n')
        f:write(string.format('    "raw": %d, "name_base": %d, "name_select": %d,\n',
            obsel.raw, obsel.name_base, obsel.name_select))
        f:write(string.format(
            '    "size_select": %d, "tile_base_addr": %d, "oam_base_addr": %d, "oam_addr_offset": %d\n',
            obsel.size_select, obsel.tile_base_addr, obsel.oam_base_addr, obsel.oam_addr_offset))
        f:write('  },\n')
        f:write('  "entries": [\n')

        for idx, entry in ipairs(entries) do
            f:write('    {\n')
            f:write(string.format('      "id": %d, "x": %d, "y": %d, "tile": %d,\n',
                entry.id, entry.x, entry.y, entry.tile))
            f:write(string.format(
                '      "width": %d, "height": %d, "palette": %d, "priority": %d,\n',
                entry.width, entry.height, entry.palette, entry.priority
            ))
            f:write(string.format('      "flip_h": %s, "flip_v": %s,\n',
                entry.flip_h and "true" or "false", entry.flip_v and "true" or "false"))
            f:write(string.format('      "name_table": %d, "tile_page": %d,\n',
                entry.name_table, entry.name_table))
            f:write('      "tiles": [\n')
            for tidx, tile in ipairs(entry.tile_data) do
                local tile_fmt = '        {"tile_index": %d, "vram_addr": %d, '
                .. '"pos_x": %d, "pos_y": %d, "data_hex": "%s"}'
            f:write(string.format(tile_fmt,
                    tile.tile_index, tile.vram_addr, tile.pos_x, tile.pos_y, tile.data_hex))
                if tidx < #entry.tile_data then f:write(',') end
                f:write('\n')
            end
            f:write('      ]\n')
            f:write('    }')
            if idx < #entries then f:write(',') end
            f:write('\n')
        end
        f:write('  ],\n')

        f:write('  "palettes": {\n')
        for pi = 0, 7 do
            f:write(string.format('    "%d": [', pi))
            for ci, c in ipairs(palettes[pi]) do
                f:write(tostring(c))
                if ci < 16 then f:write(',') end
            end
            f:write(']')
            if pi < 7 then f:write(',') end
            f:write('\n')
        end
        f:write('  }\n')
        f:write('}\n')
        f:close()

        print("Captured " .. visible_count .. " visible sprites at frame " .. fr)
        emu.stop()
    end
end, emu.eventType.endFrame)

print("Gameplay Capture: Will capture at frame 1800 (~30 seconds)")
print("Output: " .. OUTPUT_DIR .. "gameplay_capture.json")
