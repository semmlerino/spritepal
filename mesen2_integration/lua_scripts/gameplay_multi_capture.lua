-- gameplay_multi_capture.lua
-- Captures screenshots and sprite data every 30 seconds starting from frame 2000
-- Usage: Mesen2.exe --testrunner "rom.sfc" "gameplay_multi_capture.lua"

local EXCHANGE_DIR = "mesen2_exchange"
local START_FRAME = 2000
local CAPTURE_INTERVAL = 1800  -- 30 seconds at 60fps
local MAX_CAPTURES = 10

local capture_count = 0
local next_capture_frame = START_FRAME

-- Ensure exchange directory exists
os.execute("mkdir -p " .. EXCHANGE_DIR .. " 2>/dev/null")

function capture_frame()
    local frame = emu.getState().ppu.frameCount
    local timestamp = os.time()

    -- Save screenshot
    local screenshot_path = string.format("%s/gameplay_frame_%d.png", EXCHANGE_DIR, frame)
    emu.savescreenshot(screenshot_path)

    -- Capture OAM and sprite data
    local capture_data = {
        timestamp = timestamp,
        frame = frame,
        capture_num = capture_count + 1,
        obsel = {},
        entries = {},
        palettes = {}
    }

    -- Read OBSEL register
    local obsel_raw = emu.read(0x2101, emu.memType.snesRegister)
    capture_data.obsel = {
        raw = obsel_raw,
        base_size = obsel_raw & 0x07,
        name_select = (obsel_raw >> 3) & 0x03,
        name_base = (obsel_raw >> 5) & 0x07
    }

    -- Read OAM (544 bytes: 512 main + 32 high table)
    local oam_main = {}
    local oam_high = {}

    for i = 0, 511 do
        oam_main[i] = emu.read(0x0000 + i, emu.memType.snesOamRam)
    end
    for i = 0, 31 do
        oam_high[i] = emu.read(0x0200 + i, emu.memType.snesOamRam)
    end

    -- Parse 128 OAM entries
    for i = 0, 127 do
        local base = i * 4
        local x_low = oam_main[base]
        local y = oam_main[base + 1]
        local tile = oam_main[base + 2]
        local attr = oam_main[base + 3]

        -- High table bits
        local high_byte = oam_high[math.floor(i / 4)]
        local high_shift = (i % 4) * 2
        local high_bits = (high_byte >> high_shift) & 0x03
        local x_high = high_bits & 0x01
        local size_large = (high_bits >> 1) & 0x01

        -- Full X coordinate (9-bit signed)
        local x = x_low + (x_high * 256)
        if x >= 256 then x = x - 512 end

        -- Parse attributes
        local name_table = (attr >> 0) & 0x01
        local palette = (attr >> 1) & 0x07
        local priority = (attr >> 4) & 0x03
        local flip_h = (attr >> 6) & 0x01
        local flip_v = (attr >> 7) & 0x01

        -- Determine sprite size
        local width, height = 8, 8
        local base_size = capture_data.obsel.base_size
        if size_large == 1 then
            if base_size == 0 then width, height = 16, 16
            elseif base_size == 1 then width, height = 32, 32
            elseif base_size == 2 then width, height = 64, 64
            elseif base_size == 3 then width, height = 32, 32
            elseif base_size == 4 then width, height = 64, 64
            elseif base_size == 5 then width, height = 32, 64
            elseif base_size == 6 then width, height = 32, 32
            elseif base_size == 7 then width, height = 32, 32
            end
        else
            if base_size == 5 then width, height = 16, 32
            elseif base_size == 6 then width, height = 16, 32
            end
        end

        -- Calculate VRAM address for tile
        local name_base_addr = capture_data.obsel.name_base * 0x2000
        local name_select_offset = name_table * (capture_data.obsel.name_select + 1) * 0x1000
        local tile_vram_word = name_base_addr + name_select_offset + (tile * 16)
        local tile_vram_byte = tile_vram_word * 2

        -- Read tile data from VRAM (32 bytes per 8x8 tile)
        local tiles = {}
        local tiles_h = width / 8
        local tiles_v = height / 8

        for ty = 0, tiles_v - 1 do
            for tx = 0, tiles_h - 1 do
                local tile_offset = (ty * 16) + tx  -- 16 tiles per row in VRAM layout
                local tile_addr = tile_vram_byte + (tile_offset * 32)

                local tile_bytes = {}
                for b = 0, 31 do
                    local vram_addr = (tile_addr + b) % 0x10000
                    tile_bytes[b + 1] = emu.read(vram_addr, emu.memType.snesVideoRam)
                end

                -- Convert to hex string
                local hex_str = ""
                for _, byte in ipairs(tile_bytes) do
                    hex_str = hex_str .. string.format("%02X", byte)
                end

                table.insert(tiles, {
                    tile_index = tile_offset,
                    vram_addr = tile_addr,
                    pos_x = tx * 8,
                    pos_y = ty * 8,
                    data_hex = hex_str
                })
            end
        end

        table.insert(capture_data.entries, {
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
            size_large = size_large,
            tiles = tiles
        })
    end

    -- Read sprite palettes (8 palettes, 16 colors each, 2 bytes per color)
    for pal = 0, 7 do
        local colors = {}
        for col = 0, 15 do
            local addr = 0x100 + (pal * 32) + (col * 2)
            local lo = emu.read(addr, emu.memType.snesCgRam)
            local hi = emu.read(addr + 1, emu.memType.snesCgRam)
            table.insert(colors, string.format("%02X%02X", hi, lo))
        end
        capture_data.palettes[tostring(pal)] = colors
    end

    -- Save JSON
    local json_path = string.format("%s/gameplay_capture_frame_%d.json", EXCHANGE_DIR, frame)
    local json_file = io.open(json_path, "w")
    if json_file then
        -- Simple JSON serialization
        json_file:write("{\n")
        json_file:write(string.format('  "timestamp": %d,\n', capture_data.timestamp))
        json_file:write(string.format('  "frame": %d,\n', capture_data.frame))
        json_file:write(string.format('  "capture_num": %d,\n', capture_data.capture_num))

        -- OBSEL
        json_file:write('  "obsel": {\n')
        json_file:write(string.format('    "raw": %d,\n', capture_data.obsel.raw))
        json_file:write(string.format('    "base_size": %d,\n', capture_data.obsel.base_size))
        json_file:write(string.format('    "name_select": %d,\n', capture_data.obsel.name_select))
        json_file:write(string.format('    "name_base": %d\n', capture_data.obsel.name_base))
        json_file:write('  },\n')

        -- Entries (simplified - just first 10 non-trivial for size)
        json_file:write('  "entries": [\n')
        local entry_count = 0
        for idx, entry in ipairs(capture_data.entries) do
            if entry_count > 0 then json_file:write(",\n") end
            json_file:write('    {\n')
            json_file:write(string.format('      "id": %d,\n', entry.id))
            json_file:write(string.format('      "x": %d,\n', entry.x))
            json_file:write(string.format('      "y": %d,\n', entry.y))
            json_file:write(string.format('      "tile": %d,\n', entry.tile))
            json_file:write(string.format('      "width": %d,\n', entry.width))
            json_file:write(string.format('      "height": %d,\n', entry.height))
            json_file:write(string.format('      "name_table": %d,\n', entry.name_table))
            json_file:write(string.format('      "palette": %d,\n', entry.palette))
            json_file:write(string.format('      "priority": %d,\n', entry.priority))
            json_file:write(string.format('      "flip_h": %d,\n', entry.flip_h))
            json_file:write(string.format('      "flip_v": %d,\n', entry.flip_v))
            json_file:write(string.format('      "size_large": %d,\n', entry.size_large))
            json_file:write('      "tiles": [\n')
            for tidx, tile in ipairs(entry.tiles) do
                if tidx > 1 then json_file:write(",\n") end
                json_file:write('        {\n')
                json_file:write(string.format('          "tile_index": %d,\n', tile.tile_index))
                json_file:write(string.format('          "vram_addr": %d,\n', tile.vram_addr))
                json_file:write(string.format('          "pos_x": %d,\n', tile.pos_x))
                json_file:write(string.format('          "pos_y": %d,\n', tile.pos_y))
                json_file:write(string.format('          "data_hex": "%s"\n', tile.data_hex))
                json_file:write('        }')
            end
            json_file:write('\n      ]\n')
            json_file:write('    }')
            entry_count = entry_count + 1
        end
        json_file:write('\n  ],\n')

        -- Palettes
        json_file:write('  "palettes": {\n')
        local pal_count = 0
        for pal_id, colors in pairs(capture_data.palettes) do
            if pal_count > 0 then json_file:write(",\n") end
            json_file:write(string.format('    "%s": [', pal_id))
            for cidx, color in ipairs(colors) do
                if cidx > 1 then json_file:write(", ") end
                json_file:write(string.format('"%s"', color))
            end
            json_file:write(']')
            pal_count = pal_count + 1
        end
        json_file:write('\n  }\n')

        json_file:write("}\n")
        json_file:close()
    end

    capture_count = capture_count + 1
    emu.log(string.format("Capture %d at frame %d saved", capture_count, frame))

    return capture_count
end

function on_frame()
    local frame = emu.getState().ppu.frameCount

    if frame >= next_capture_frame then
        local count = capture_frame()
        next_capture_frame = frame + CAPTURE_INTERVAL

        if count >= MAX_CAPTURES then
            emu.log("Max captures reached, stopping")
            emu.stop()
        end
    end
end

emu.addEventCallback(on_frame, emu.eventType.endFrame)
emu.log(string.format("Gameplay capture: starting at frame %d, interval %d frames, max %d captures",
    START_FRAME, CAPTURE_INTERVAL, MAX_CAPTURES))
