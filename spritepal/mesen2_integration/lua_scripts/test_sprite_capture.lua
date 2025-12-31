-- Test version: Auto-capture at a target frame (configurable via env)
local DEFAULT_OUTPUT = "C:\\CustomScripts\\KirbyMax\\workshop\\exhal-master\\"
    .. "spritepal\\mesen2_exchange\\"
local OUTPUT_DIR = os.getenv("OUTPUT_DIR") or DEFAULT_OUTPUT
local TARGET_FRAME = tonumber(os.getenv("TARGET_FRAME")) or 700
local SKIP_INPUT = os.getenv("SKIP_INPUT") == "1"
local SAVESTATE_PATH = os.getenv("SAVESTATE_PATH")
local PRELOADED_STATE = os.getenv("PRELOADED_STATE") == "1"
local FRAME_EVENT = os.getenv("FRAME_EVENT")
local DEBUG_FRAME_KEYS = os.getenv("DEBUG_FRAME_KEYS") == "1"
local MASTER_CLOCK_FALLBACK = os.getenv("MASTER_CLOCK_FALLBACK")
local MASTER_CLOCK_FPS = tonumber(os.getenv("MASTER_CLOCK_FPS"))
local MASTER_CLOCK_MAX_SECONDS = tonumber(os.getenv("MASTER_CLOCK_MAX_SECONDS"))
local LOG_EVERY_FRAME = tonumber(os.getenv("LOG_EVERY_FRAME"))
local DEBUG_CAPTURE_MATCH = tonumber(os.getenv("DEBUG_CAPTURE_MATCH") or "0")
local debug_capture_logs = 0
local CAPTURE_FRAMES_ENV = os.getenv("CAPTURE_FRAMES")
local DOOR_UP_START = tonumber(os.getenv("DOOR_UP_START"))
local DOOR_UP_END = tonumber(os.getenv("DOOR_UP_END"))
local DUMP_VRAM = os.getenv("DUMP_VRAM") ~= "0"
local MAX_FRAMES = tonumber(os.getenv("MAX_FRAMES"))
local fr = 0
local frame_event_registered = false
local STATE_LOADED = false

if PRELOADED_STATE then
    STATE_LOADED = true
end

if not FRAME_EVENT or FRAME_EVENT == "" then
    FRAME_EVENT = SAVESTATE_PATH and "exec" or "endFrame"
end

if MASTER_CLOCK_FALLBACK == nil then
    MASTER_CLOCK_FALLBACK = FRAME_EVENT == "exec" and "1" or "0"
end
local MASTER_CLOCK_FALLBACK_ENABLED = MASTER_CLOCK_FALLBACK == "1"

if not OUTPUT_DIR:match("[/\\]$") then
    OUTPUT_DIR = OUTPUT_DIR .. "\\"
end

local LOG_FILE = OUTPUT_DIR .. "test_capture_log.txt"

-- Ensure output directory exists
os.execute('mkdir "' .. OUTPUT_DIR:gsub("\\", "\\\\") .. '" 2>NUL')

local function log(msg)
    local f = io.open(LOG_FILE, "a")
    if f then
        f:write(os.date("%H:%M:%S") .. " " .. msg .. "\n")
        f:close()
    end
end

local function set_input(input_state, port)
    local ok, err = pcall(emu.setInput, input_state, port or 0)
    if not ok then
        log("setInput failed: " .. tostring(err))
    end
end

local function parse_capture_frames(value)
    if not value or value == "" then
        return nil
    end

    local frames = {}
    for token in string.gmatch(value, "[^,]+") do
        local num = tonumber(token)
        if num then
            table.insert(frames, num)
        end
    end

    table.sort(frames)
    if #frames == 0 then
        return nil
    end
    return frames
end

local CAPTURE_FRAMES = parse_capture_frames(CAPTURE_FRAMES_ENV)
local capture_index = 1

if SAVESTATE_PATH and DOOR_UP_START == nil then
    DOOR_UP_START = 5
end
if SAVESTATE_PATH and DOOR_UP_END == nil then
    DOOR_UP_END = 35
end
local MEM = {
    oam = emu.memType.snesOam or emu.memType.snesSpriteRam,
    vram = emu.memType.snesVram or emu.memType.snesVideoRam,
    cgram = emu.memType.snesCgram or emu.memType.snesCgRam,
}

-- SNES sprite size table
local SIZE_TABLE = {
    [0] = {8, 8, 16, 16},
    [1] = {8, 8, 32, 32},
    [2] = {8, 8, 64, 64},
    [3] = {16, 16, 32, 32},
    [4] = {16, 16, 64, 64},
    [5] = {32, 32, 64, 64},
    [6] = {16, 32, 32, 64},
    [7] = {16, 32, 32, 32},
}

local function add_memory_callback_compat(callback, cb_type, start_addr, end_addr, cpu_type, mem_type)
    if cpu_type ~= nil and mem_type ~= nil then
        local ok, id = pcall(emu.addMemoryCallback, callback, cb_type, start_addr, end_addr, cpu_type, mem_type)
        if ok then
            return id
        end
    end
    if cpu_type ~= nil then
        local ok, id = pcall(emu.addMemoryCallback, callback, cb_type, start_addr, end_addr, cpu_type)
        if ok then
            return id
        end
    end
    local ok, id = pcall(emu.addMemoryCallback, callback, cb_type, start_addr, end_addr)
    if ok then
        return id
    end
    return nil
end

local function remove_memory_callback_compat(callback_id, cb_type, start_addr, end_addr, cpu_type, mem_type)
    if pcall(emu.removeMemoryCallback, callback_id) then
        return true
    end
    if cb_type ~= nil then
        if pcall(emu.removeMemoryCallback, callback_id, cb_type, start_addr or 0, end_addr or 0) then
            return true
        end
        if cpu_type ~= nil and mem_type ~= nil then
            local ok = pcall(emu.removeMemoryCallback, callback_id, cb_type,
            start_addr or 0, end_addr or 0, cpu_type, mem_type)
        if ok then
                return true
            end
        end
        if cpu_type ~= nil then
            if pcall(emu.removeMemoryCallback, callback_id, cb_type, start_addr or 0, end_addr or 0, cpu_type) then
                return true
            end
        end
    end
    return false
end

local function register_frame_event()
    if frame_event_registered then
        return
    end
    frame_event_registered = true
    if FRAME_EVENT == "exec" then
        local cpu_type = emu.cpuType and (emu.cpuType.cpu or emu.cpuType.snes) or nil
        local last_frame = nil
        local last_master_clock = nil
        local clock_accum = 0
        local fallback_logged = false
        local logged_state = false
        local post_load_logs = 0
        local max_master_delta = nil
        local start_master_clock = nil
        local stop_requested = false

        local function detect_fps(state)
            if MASTER_CLOCK_FPS and MASTER_CLOCK_FPS > 0 then
                return MASTER_CLOCK_FPS
            end
            local region = state and state.region or nil
            if type(region) == "string" and region:lower():find("pal") then
                return 50
            end
            return 60
        end

        local function tick_from_master_clock(state, frame_advanced)
            if not MASTER_CLOCK_FALLBACK_ENABLED or not state then
                return
            end
            local master_clock = state.masterClock
            local clock_rate = state.clockRate
            if master_clock == nil or clock_rate == nil or clock_rate == 0 then
                return
            end
            if start_master_clock == nil then
                start_master_clock = master_clock
                if MASTER_CLOCK_MAX_SECONDS and MASTER_CLOCK_MAX_SECONDS > 0 then
                    max_master_delta = clock_rate * MASTER_CLOCK_MAX_SECONDS
                end
            end
            if max_master_delta and (master_clock - start_master_clock) >= max_master_delta then
                if not stop_requested then
                    stop_requested = true
                    log("MasterClock max seconds reached; stopping")
                    emu.stop(1)
                end
                return
            end
            if last_master_clock == nil then
                last_master_clock = master_clock
                return
            end
            local delta = master_clock - last_master_clock
            if delta < 0 then
                delta = 0
            end
            last_master_clock = master_clock
            if frame_advanced then
                clock_accum = 0
                return
            end
            local fps = detect_fps(state)
            local ticks_per_frame = clock_rate / fps
            clock_accum = clock_accum + delta
            while clock_accum >= ticks_per_frame do
                clock_accum = clock_accum - ticks_per_frame
                if not fallback_logged then
                    fallback_logged = true
                    log("Using masterClock fallback ticks (fps=" .. tostring(fps) .. ")")
                end
                on_end_frame()
            end
        end

        local function exec_tick()
            local state = emu.getState and emu.getState() or nil
            local frame_count = nil
            if state then
                frame_count = state["ppu.frameCount"]
                    or state.frameCount
                    or state.framecount
                    or state["ppu.framecount"]
                    or state["snes.ppu.framecount"]
                if DEBUG_FRAME_KEYS and not logged_state then
                    logged_state = true
                    local keys = {}
                    local scanline_keys = {}
                    for k, _ in pairs(state) do
                        if type(k) == "string" then
                            if k:find("frame") then
                                table.insert(keys, k)
                            end
                            if k:find("scanline") then
                                table.insert(scanline_keys, k)
                            end
                        end
                    end
                    table.sort(keys)
                    table.sort(scanline_keys)
                    log("state frame keys: " .. table.concat(keys, ", "))
                    log("state scanline keys: " .. table.concat(scanline_keys, ", "))
                    log("state.frameCount=" .. tostring(state.frameCount))
                    log("state[\"ppu.frameCount\"]=" .. tostring(state["ppu.frameCount"]))
                    log("state[\"ppu.scanline\"]=" .. tostring(state["ppu.scanline"]))
                end
                if DEBUG_FRAME_KEYS and STATE_LOADED and post_load_logs < 3 then
                    post_load_logs = post_load_logs + 1
                    log("post-load exec_tick frameCount=" .. tostring(frame_count)
                        .. " scanline=" .. tostring(state["ppu.scanline"])
                        .. " masterClock=" .. tostring(state.masterClock))
                end
            end
            if frame_count ~= nil and frame_count ~= last_frame then
                last_frame = frame_count
                on_end_frame()
                tick_from_master_clock(state, true)
            else
                tick_from_master_clock(state, false)
            end
        end
        local ref = add_memory_callback_compat(exec_tick, emu.callbackType.exec, 0x0000, 0xFFFF, cpu_type, nil)
        if ref then
            log("Registered frame callback: exec (frameCount via emu.getState)")
        else
            log("Failed to register exec frame callback")
        end
        return
    end

    local evt = emu.eventType and emu.eventType[FRAME_EVENT] or nil
    if evt == nil then
        evt = emu.eventType and emu.eventType.endFrame or nil
    end
    if evt == nil then
        log("Failed to register frame event: emu.eventType missing")
        return
    end
    emu.addEventCallback(on_end_frame, evt)
    log("Registered frame callback: " .. tostring(FRAME_EVENT))
end

local function load_savestate_if_needed()
    if not SAVESTATE_PATH or SAVESTATE_PATH == "" then
        return
    end

    local f = io.open(SAVESTATE_PATH, "rb")
    if not f then
        emu.log("Failed to open savestate: " .. SAVESTATE_PATH)
        return
    end

    local state_bytes = f:read("*a")
    f:close()

    local state_loaded = false
    local load_ref
    local cpu_type = emu.cpuType and (emu.cpuType.cpu or emu.cpuType.snes) or nil
    load_ref = add_memory_callback_compat(function(address, value)
        if not state_loaded then
            state_loaded = true
            STATE_LOADED = true
            emu.loadSavestate(state_bytes)
            pcall(emu.resume)
            fr = 0
            capture_index = 1
            debug_capture_logs = 0
            log("Savestate loaded; reset frame counter")
            remove_memory_callback_compat(load_ref, emu.callbackType.exec, 0x8000, 0xFFFF, cpu_type, nil)
            register_frame_event()
        end
    end, emu.callbackType.exec, 0x8000, 0xFFFF, cpu_type, nil)
    if not load_ref then
        log("Failed to register savestate callback")
    end
end

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
        oam_base_addr = oam_base_addr,
        oam_addr_offset = oam_addr_offset,
        tile_base_addr = oam_base_addr * 2,
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
        name_table = (attr & 0x01),
        palette = (attr >> 1) & 0x07,
        priority = (attr >> 4) & 0x03,
        flip_h = ((attr >> 6) & 0x01) == 1,
        flip_v = ((attr >> 7) & 0x01) == 1,
        size_large = size_bit == 1
    }
end

local function get_sprite_size(obsel, is_large)
    local sizes = SIZE_TABLE[obsel.size_select] or {8, 8, 16, 16}
    return is_large and sizes[3] or sizes[1], is_large and sizes[4] or sizes[2]
end

local function is_visible(entry)
    if entry.y >= 224 and entry.y < 240 then return false end
    if entry.x <= -64 or entry.x >= 256 then return false end
    return true
end

local vram_read_mode = os.getenv("VRAM_READ_MODE")  -- "word" or "byte", default "word"
if vram_read_mode ~= "word" and vram_read_mode ~= "byte" then
    vram_read_mode = "word"  -- Default to word mode; byte mode broken in some Mesen2 builds
end

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

local function dump_vram(path)
    local size_bytes = 0x10000
    if emu.getMemorySize then
        local ok, size = pcall(emu.getMemorySize, MEM.vram)
        if ok and type(size) == "number" and size > 0 then
            size_bytes = size
        end
    end

    local f = io.open(path, "wb")
    if not f then
        return
    end

    for i = 0, size_bytes - 1 do
        local b = emu.read(i, MEM.vram)
        f:write(string.char(b))
    end

    f:close()
end

local function looks_like_index_leak(tile_data)
    local matches = 0
    for i = 0, 15 do
        local expected = i
        local expected_mod = i % 8
        local value = tile_data[i * 2 + 1]
        if value == expected or value == expected_mod then
            matches = matches + 1
        end
    end
    return matches >= 12
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
    if high_nonzero and not looks_like_index_leak(word_data) then
        vram_read_mode = "word"
        return word_data
    end

    local byte_data, odd_nonzero = read_vram_tile_byte(vram_addr)
    if odd_nonzero or looks_like_index_leak(word_data) then
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

    -- Read palettes
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

    return obsel, entries, visible_count, palettes, tile_count, odd_nonzero_tiles
end

local function is_capture_frame(frame)
    if SAVESTATE_PATH and not STATE_LOADED then
        return false, false
    end
    if DEBUG_CAPTURE_MATCH and debug_capture_logs < DEBUG_CAPTURE_MATCH then
        debug_capture_logs = debug_capture_logs + 1
        log(
            "Capture check frame=" .. tostring(frame)
            .. " capture_frames=" .. tostring(CAPTURE_FRAMES)
            .. " count=" .. tostring(CAPTURE_FRAMES and #CAPTURE_FRAMES or 0)
            .. " index=" .. tostring(capture_index)
            .. " expected=" .. tostring(CAPTURE_FRAMES and CAPTURE_FRAMES[capture_index] or "nil")
        )
    end
    if CAPTURE_FRAMES then
        if capture_index <= #CAPTURE_FRAMES and frame == CAPTURE_FRAMES[capture_index] then
            if DEBUG_CAPTURE_MATCH and DEBUG_CAPTURE_MATCH > 0 then
                log("Capture match at frame " .. tostring(frame) .. " (index " .. tostring(capture_index) .. ")")
            end
            capture_index = capture_index + 1
            return true, capture_index > #CAPTURE_FRAMES
        end
        return false, false
    end
    return frame == TARGET_FRAME, true
end

local function write_capture(frame)
    local obsel, entries, visible_count, palettes, tile_count, odd_nonzero_tiles = capture_sprites()
    if tile_count > 0 and odd_nonzero_tiles == 0 then
        log("ERROR: VRAM tiles have zero odd-byte data; aborting capture (bad VRAM reads).")
        emu.stop(2)
        return
    end
    local suffix = CAPTURE_FRAMES and ("_" .. frame) or ""
    log("Capturing frame " .. frame .. " (suffix=" .. suffix .. ")")

    -- Write screenshot (headless-safe)
    local png_data = emu.takeScreenshot()
    if png_data then
        local sf = io.open(OUTPUT_DIR .. "test_frame_" .. frame .. ".png", "wb")
        if sf then
            sf:write(png_data)
            sf:close()
        else
            log("Failed to open screenshot output")
        end
    end

    if DUMP_VRAM then
        dump_vram(OUTPUT_DIR .. "test_vram_dump" .. suffix .. ".bin")
    end

    -- Write to file
    local f = io.open(OUTPUT_DIR .. "test_capture" .. suffix .. ".json", "w")
    if not f then
        log("Failed to open capture json output")
        return
    end
    f:write("{\n")
    f:write('  "schema_version": "1.0",\n')
    f:write(string.format('  "frame": %d,\n', frame))
    f:write('  "obsel": {\n')
    f:write(string.format('    "raw": %d, "name_base": %d, "name_select": %d,\n',
        obsel.raw, obsel.name_base, obsel.name_select))
    f:write(string.format(
        '    "size_select": %d, "tile_base_addr": %d, "oam_base_addr": %d, "oam_addr_offset": %d\n',
        obsel.size_select, obsel.tile_base_addr, obsel.oam_base_addr, obsel.oam_addr_offset))
    f:write('  },\n')
    f:write(string.format('  "visible_count": %d,\n', visible_count))
    f:write('  "entries": [\n')

    for idx, entry in ipairs(entries) do
        f:write('    {\n')
        f:write(string.format('      "id": %d, "x": %d, "y": %d, "tile": %d,\n',
            entry.id, entry.x, entry.y, entry.tile))
        f:write(string.format('      "width": %d, "height": %d,\n', entry.width, entry.height))
        f:write(string.format('      "palette": %d, "priority": %d, "flip_h": %s, "flip_v": %s,\n',
            entry.palette, entry.priority, entry.flip_h and "true" or "false", entry.flip_v and "true" or "false"))
        f:write(string.format('      "name_table": %d, "tile_page": %d,\n',
            entry.name_table, entry.name_table))
        f:write('      "tiles": [\n')
        for tidx, tile in ipairs(entry.tile_data) do
            f:write(string.format(
                '        {"tile_index": %d, "vram_addr": %d, "pos_x": %d, "pos_y": %d, "data_hex": "%s"}',
                tile.tile_index,
                tile.vram_addr,
                tile.pos_x,
                tile.pos_y,
                tile.data_hex
            ))
            if tidx < #entry.tile_data then f:write(',') end
            f:write('\n')
        end
        f:write('      ]\n')
        f:write('    }')
        if idx < #entries then f:write(',') end
        f:write('\n')
    end
    f:write('  ],\n')

    -- Palettes
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

    -- Write summary
    local s = io.open(OUTPUT_DIR .. "capture_summary" .. suffix .. ".txt", "w")
    if not s then
        log("Failed to open capture summary output")
        return
    end
    s:write("Sprite Capture Summary\n")
    s:write("======================\n")
    s:write(string.format("Frame: %d\n", frame))
    s:write(string.format(
        "OBSEL: $%02X (base=%d, select=%d, size=%d, oam_base=%d, oam_offset=%d)\n",
        obsel.raw, obsel.name_base, obsel.name_select, obsel.size_select, obsel.oam_base_addr, obsel.oam_addr_offset))
    s:write(string.format("VRAM read mode: %s\n", vram_read_mode or "auto"))
    s:write(string.format("Visible sprites: %d\n\n", visible_count))

    for _, entry in ipairs(entries) do
        s:write(string.format("OAM #%d: pos=(%d,%d) tile=$%02X size=%dx%d pal=%d\n",
            entry.id, entry.x, entry.y, entry.tile, entry.width, entry.height, entry.palette))
    end
    s:close()
end

function on_end_frame()
    fr = fr + 1
    if LOG_EVERY_FRAME and LOG_EVERY_FRAME > 0 then
        if fr % LOG_EVERY_FRAME == 0 then
            log("Frame tick: " .. tostring(fr))
        end
    end
    if DEBUG_CAPTURE_MATCH and DEBUG_CAPTURE_MATCH > 0 and fr <= DEBUG_CAPTURE_MATCH then
        log(
            "on_end_frame debug fr=" .. tostring(fr)
            .. " max_frames=" .. tostring(MAX_FRAMES)
            .. " capture_frames=" .. tostring(CAPTURE_FRAMES)
            .. " capture_index=" .. tostring(capture_index)
        )
    end

    if not SKIP_INPUT then
        if SAVESTATE_PATH then
            if STATE_LOADED and DOOR_UP_START and DOOR_UP_END then
                if fr >= DOOR_UP_START and fr <= DOOR_UP_END then
                    set_input({up=true}, 0)
                else
                    set_input({}, 0)
                end
            end
        else
            -- Menu navigation
            if fr == 60 then set_input({start=true}, 0) end
            if fr == 120 then set_input({start=true}, 0) end
            if fr == 180 then set_input({a=true}, 0) end
            if fr == 240 then set_input({a=true}, 0) end
            if fr == 300 then set_input({a=true}, 0) end
            if fr == 360 then set_input({start=true}, 0) end
            if fr == 420 then set_input({start=true}, 0) end
            if fr == 480 then set_input({a=true}, 0) end
            if fr > 500 and fr < 650 then
                if fr % 4 < 2 then set_input({right=true}, 0) else set_input({}, 0) end
            end
        end
    end

    if DEBUG_CAPTURE_MATCH and DEBUG_CAPTURE_MATCH > 0 and fr <= DEBUG_CAPTURE_MATCH then
        log("before is_capture_frame fr=" .. tostring(fr))
    end
    local should_capture, stop_after = is_capture_frame(fr)
    if DEBUG_CAPTURE_MATCH and DEBUG_CAPTURE_MATCH > 0 and fr <= DEBUG_CAPTURE_MATCH then
        log("after is_capture_frame fr=" .. tostring(fr) .. " should_capture=" .. tostring(should_capture)
            .. " stop_after=" .. tostring(stop_after))
    end
    if should_capture then
        write_capture(fr)
        if stop_after then
            log("Capture complete; stopping")
            emu.stop()
        end
    end

    if MAX_FRAMES and (not SAVESTATE_PATH or STATE_LOADED) and fr >= MAX_FRAMES then
        log("Reached MAX_FRAMES without completing capture; stopping")
        emu.stop()
    end
end

log("Script start: target=" .. TARGET_FRAME
    .. " capture_frames=" .. (CAPTURE_FRAMES_ENV or "nil")
    .. " capture_count=" .. tostring(CAPTURE_FRAMES and #CAPTURE_FRAMES or 0)
    .. " capture_first=" .. tostring(CAPTURE_FRAMES and CAPTURE_FRAMES[1] or "nil")
    .. " savestate=" .. (SAVESTATE_PATH or "nil")
    .. " preloaded=" .. tostring(PRELOADED_STATE)
    .. " frame_event=" .. tostring(FRAME_EVENT)
    .. " master_clock_fallback=" .. tostring(MASTER_CLOCK_FALLBACK)
    .. " master_clock_fps=" .. tostring(MASTER_CLOCK_FPS)
    .. " master_clock_max_seconds=" .. tostring(MASTER_CLOCK_MAX_SECONDS)
    .. " debug_capture=" .. tostring(DEBUG_CAPTURE_MATCH)
    .. " door_up=" .. tostring(DOOR_UP_START) .. "-" .. tostring(DOOR_UP_END)
    .. " dump_vram=" .. tostring(DUMP_VRAM)
    .. " max_frames=" .. tostring(MAX_FRAMES))

if SAVESTATE_PATH and not PRELOADED_STATE then
    load_savestate_if_needed()
else
    register_frame_event()
end
