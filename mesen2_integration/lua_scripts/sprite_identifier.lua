-- Sprite Identifier v1
-- Combines idx→ptr tracking with F9 hotkey capture for sprite identification
--
-- Usage: Play game normally, press F9 when target sprite is visible
-- Output shows all visible OAM entries + recently active idx sessions
-- Match screen position to find which idx corresponds to your sprite
--
-- Pipeline traced: idx → ROM[01:FE52 + idx*3] → DP[00:0002-0004] → staging → VRAM

local OUTPUT_DIR = os.getenv("OUTPUT_DIR") or "C:\\CustomScripts\\KirbyMax\\workshop\\exhal-master\\spritepal\\mesen2_exchange\\"
local LOG_FILE = OUTPUT_DIR .. "sprite_identifier.log"

local log_handle = nil
local frame_count = 0

-- ROM pointer table
local TABLE_CPU_BASE = 0x01FE52
local TABLE_CPU_END = 0x01FFFF
local ENTRY_SIZE = 3

-- DP pointer slot
local DP_PTR_BASE = 0x0002

-- WRAM staging range
local STAGING_START = 0x7E2000
local STAGING_END = 0x7E2FFF

-- Valid asset banks
local VALID_BANKS = {
    [0xC0] = true, [0xC1] = true, [0xC2] = true, [0xC3] = true,
    [0xE0] = true, [0xE1] = true, [0xE2] = true, [0xE3] = true,
    [0xE4] = true, [0xE5] = true, [0xE6] = true, [0xE7] = true,
    [0xE8] = true, [0xE9] = true, [0xEA] = true, [0xEB] = true,
    [0xEC] = true, [0xED] = true, [0xEE] = true, [0xEF] = true,
    [0x7E] = true,
}

-- OAM sprite sizes
local SPRITE_SIZES = {
    [0] = {8, 16},   [1] = {8, 32},   [2] = {8, 64},
    [3] = {16, 32},  [4] = {16, 64},  [5] = {32, 64},
    [6] = {16, 32},  [7] = {16, 32}
}

-- ============================================================================
-- STATE TRACKING
-- ============================================================================

-- Per-idx tracking
local idx_database = {}      -- {idx: {ptr, ptr_hex, last_frame, session_count}}

-- Recent sessions (ring buffer, last 50)
local recent_sessions = {}
local session_ring_idx = 0
local SESSION_RING_SIZE = 50

-- Active session
local active_session = nil
local session_counter = 0
local SESSION_TIMEOUT = 4

-- Pending DP writes for pointer assembly
local pending_dp = {}
local current_ptr = {}

-- Pending table reads
local pending_tbl = {}

-- F9 hotkey state
local last_f9_state = false

-- OBSEL config
local obsel_config = nil

-- ============================================================================
-- HELPERS
-- ============================================================================

local function log(msg)
    if not log_handle then
        log_handle = io.open(LOG_FILE, "w")
    end
    if log_handle then
        log_handle:write(msg .. "\n")
        log_handle:flush()
    end
    print(msg)
end

local function fmt_addr(addr)
    local bank = math.floor(addr / 65536)
    local offset = addr % 65536
    return string.format("%02X:%04X", bank, offset)
end

local function is_valid_ptr(ptr)
    local bank = math.floor(ptr / 65536)
    local offset = ptr % 65536
    if not VALID_BANKS[bank] then return false end
    if ptr == 0xFFFFFF or ptr == 0x000000 then return false end
    if bank == 0xFF then return false end
    if bank >= 0xC0 and bank <= 0xDF then
        if offset < 0x8000 then return false end
    end
    if bank == 0x7E then
        if offset < 0x2000 or offset > 0x7FFF then return false end
    end
    return true
end

local function read_byte(addr)
    local ok, val = pcall(function()
        return emu.read(addr, emu.memType.snesMemory)
    end)
    if ok then return val end
    return nil
end

-- FNV-1a hash
local function compute_hash(data, len)
    local hash = 0x811c9dc5
    for i = 1, math.min(len, 64) do
        local byte = data[i] or 0
        hash = hash ~ byte
        hash = (hash * 0x01000193) & 0xFFFFFFFF
    end
    return string.format("%08X", hash)
end

-- ============================================================================
-- SESSION MANAGEMENT
-- ============================================================================

local function close_session(reason, staging_info)
    if not active_session then return end

    active_session.close_reason = reason
    active_session.close_frame = frame_count

    if staging_info then
        active_session.staging = staging_info
    end

    -- Add to ring buffer
    session_ring_idx = (session_ring_idx % SESSION_RING_SIZE) + 1
    recent_sessions[session_ring_idx] = active_session

    -- Update idx database
    local idx = active_session.idx
    if idx and idx_database[idx] then
        idx_database[idx].session_count = (idx_database[idx].session_count or 0) + 1
        idx_database[idx].last_frame = frame_count
        if staging_info then
            idx_database[idx].last_staging = staging_info
        end
    end

    active_session = nil
end

local function open_session(idx, ptr, record_type)
    if active_session then
        close_session("new_session")
    end

    session_counter = session_counter + 1
    active_session = {
        id = session_counter,
        idx = idx,
        ptr = ptr,
        ptr_hex = fmt_addr(ptr),
        record_type = record_type,
        frame_start = frame_count,
    }

    -- Ensure idx entry exists
    if not idx_database[idx] then
        idx_database[idx] = {
            ptr = ptr,
            ptr_hex = fmt_addr(ptr),
            first_frame = frame_count,
            last_frame = frame_count,
            session_count = 0,
        }
    end
end

-- ============================================================================
-- CALLBACKS: TABLE READ
-- ============================================================================

local function on_table_read(addr, value)
    local rel_addr = addr - TABLE_CPU_BASE
    if rel_addr < 0 then return nil end

    local entry_idx = math.floor(rel_addr / ENTRY_SIZE)
    local byte_offset = rel_addr % ENTRY_SIZE

    -- Start new entry if byte 0
    if byte_offset == 0 then
        pending_tbl[entry_idx] = { [0] = value }
    elseif pending_tbl[entry_idx] then
        pending_tbl[entry_idx][byte_offset] = value
    end

    -- Complete 3-byte read
    if byte_offset == 2 and pending_tbl[entry_idx] then
        local ent = pending_tbl[entry_idx]
        if ent[0] and ent[1] and ent[2] then
            local ptr = ent[0] + (ent[1] * 256) + (ent[2] * 65536)
            if is_valid_ptr(ptr) then
                -- Update idx database immediately
                if not idx_database[entry_idx] then
                    idx_database[entry_idx] = {
                        ptr = ptr,
                        ptr_hex = fmt_addr(ptr),
                        first_frame = frame_count,
                        last_frame = frame_count,
                        session_count = 0,
                    }
                end
                idx_database[entry_idx].last_frame = frame_count
            end
        end
        pending_tbl[entry_idx] = nil
    end

    return nil
end

-- ============================================================================
-- CALLBACKS: DP WRITE
-- ============================================================================

local function on_dp_write(addr, value)
    local cpu = 0  -- Assume SNES for now

    -- Track 3-byte pointer writes to DP 0x02-0x04
    if addr >= DP_PTR_BASE and addr <= DP_PTR_BASE + 2 then
        if not pending_dp[cpu] then pending_dp[cpu] = {} end
        pending_dp[cpu][addr - DP_PTR_BASE] = value

        -- Complete 3-byte pointer
        if addr == DP_PTR_BASE + 2 then
            local dp = pending_dp[cpu]
            if dp[0] and dp[1] and dp[2] then
                local ptr = dp[0] + (dp[1] * 256) + (dp[2] * 65536)
                if is_valid_ptr(ptr) then
                    current_ptr[cpu] = ptr

                    -- Find matching idx
                    local matched_idx = nil
                    for idx, db in pairs(idx_database) do
                        if db.ptr == ptr then
                            matched_idx = idx
                            break
                        end
                    end

                    if matched_idx then
                        local record_type = read_byte(ptr) or 0xFF
                        open_session(matched_idx, ptr, record_type)
                    end
                end
            end
            pending_dp[cpu] = {}
        end
    end

    return nil
end

-- ============================================================================
-- CALLBACKS: STAGING WRITE (for session closure)
-- ============================================================================

local staging_batch = nil

local function on_staging_write(addr, value)
    if not active_session then return nil end

    -- Track staging writes
    if not staging_batch then
        staging_batch = {
            wram_start = addr,
            wram_end = addr,
            frame = frame_count,
            data = {},
        }
    end

    staging_batch.wram_end = math.max(staging_batch.wram_end, addr)
    table.insert(staging_batch.data, value)

    return nil
end

-- ============================================================================
-- OAM PARSING
-- ============================================================================

local function update_obsel()
    local obsel = emu.read(0x2101, emu.memType.snesMemory)
    local name_base = obsel & 0x07
    local name_select = (obsel >> 3) & 0x03
    local oam_base_addr = name_base << 13
    local oam_addr_offset = (name_select + 1) << 12
    obsel_config = {
        name_base = name_base,
        name_select = name_select,
        size_select = (obsel >> 5) & 0x07,
        oam_base_addr = oam_base_addr,
        oam_addr_offset = oam_addr_offset,
        raw = obsel
    }
end

local function parse_oam()
    local oam = {}
    for i = 0, 543 do
        oam[i] = emu.read(i, emu.memType.snesSpriteRam)
    end

    local sprites = {}

    for i = 0, 127 do
        local base = i * 4
        local x = oam[base]
        local y = oam[base + 1]
        local tile = oam[base + 2]
        local attr = oam[base + 3]

        local high_index = 512 + math.floor(i / 4)
        local high_shift = (i % 4) * 2
        local high_byte = oam[high_index]
        local x_msb = (high_byte >> high_shift) & 0x01
        local size_bit = (high_byte >> (high_shift + 1)) & 0x01

        x = x | (x_msb * 256)
        if x >= 256 then x = x - 512 end

        -- Skip off-screen sprites
        local visible = not (y >= 224 and y < 240) and (x > -64 and x < 256)

        if visible then
            local palette = (attr >> 1) & 0x07
            local priority = (attr >> 4) & 0x03
            local flip_h = (attr & 0x40) ~= 0
            local flip_v = (attr & 0x80) ~= 0
            local name_table = attr & 0x01

            local width = 8
            local height = 8
            if obsel_config then
                local sizes = SPRITE_SIZES[obsel_config.size_select] or {8, 16}
                local size = sizes[size_bit + 1]
                width = size
                height = size
            end

            -- Calculate VRAM address
            local vram_addr = nil
            if obsel_config then
                local word_addr = obsel_config.oam_base_addr + (tile << 4)
                if name_table ~= 0 then
                    word_addr = word_addr + obsel_config.oam_addr_offset
                end
                word_addr = word_addr & 0x7FFF
                vram_addr = word_addr << 1
            end

            table.insert(sprites, {
                oam_id = i,
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

    return sprites
end

-- ============================================================================
-- CAPTURE ON F9
-- ============================================================================

local function do_capture()
    log("")
    log("==============================================================")
    log(string.format("CAPTURE at frame %d", frame_count))
    log("==============================================================")

    -- 1) Parse all visible OAM entries
    local sprites = parse_oam()
    log("")
    log(string.format("=== VISIBLE SPRITES (%d) ===", #sprites))
    log("OAM_ID     X     Y   SIZE  TILE  PAL  VRAM_ADDR")
    log("------  ----  ----  -----  ----  ---  ---------")

    for _, s in ipairs(sprites) do
        log(string.format("%6d  %4d  %4d  %2dx%-2d  0x%02X   %d   0x%04X",
            s.oam_id, s.x, s.y, s.width, s.height, s.tile, s.palette, s.vram_addr or 0))
    end

    -- 2) List all idx sessions active recently (last 10 frames)
    log("")
    log("=== RECENTLY ACTIVE IDX SESSIONS ===")
    log("(Sessions with asset loading in last 10 frames)")
    log("IDX   PTR        RECORD  LAST_FRAME  SESSIONS  STATUS")
    log("---   ---------  ------  ----------  --------  ------")

    local active_indices = {}
    for idx, db in pairs(idx_database) do
        if db.last_frame and (frame_count - db.last_frame) <= 10 then
            table.insert(active_indices, {idx = idx, db = db})
        end
    end
    table.sort(active_indices, function(a, b) return a.db.last_frame > b.db.last_frame end)

    for _, item in ipairs(active_indices) do
        local idx = item.idx
        local db = item.db
        local record_str = "?"
        if db.ptr then
            local rec = read_byte(db.ptr)
            if rec then record_str = string.format("0x%02X", rec) end
        end
        local status = "idle"
        if active_session and active_session.idx == idx then
            status = "ACTIVE"
        end
        log(string.format("%3d   %s  %6s  %10d  %8d  %s",
            idx, db.ptr_hex or "?", record_str, db.last_frame or 0, db.session_count or 0, status))
    end

    -- 3) Current active session
    if active_session then
        log("")
        log("=== CURRENT ACTIVE SESSION ===")
        log(string.format("idx=%d ptr=%s record=0x%02X since_frame=%d",
            active_session.idx or 0, active_session.ptr_hex or "?",
            active_session.record_type or 0xFF, active_session.frame_start or 0))
    end

    -- 4) Full idx database summary
    log("")
    log("=== FULL IDX DATABASE ===")
    local all_indices = {}
    for idx, _ in pairs(idx_database) do
        table.insert(all_indices, idx)
    end
    table.sort(all_indices)

    log("IDX   PTR        FIRST_FRAME  LAST_FRAME  SESSIONS")
    log("---   ---------  -----------  ----------  --------")
    for _, idx in ipairs(all_indices) do
        local db = idx_database[idx]
        log(string.format("%3d   %s  %11d  %10d  %8d",
            idx, db.ptr_hex or "?", db.first_frame or 0, db.last_frame or 0, db.session_count or 0))
    end

    -- 5) Write JSON for external processing
    local json_file = OUTPUT_DIR .. string.format("sprite_identify_%d.json", frame_count)
    local jf = io.open(json_file, "w")
    if jf then
        jf:write("{\n")
        jf:write(string.format('  "frame": %d,\n', frame_count))

        -- Sprites
        jf:write('  "sprites": [\n')
        for i, s in ipairs(sprites) do
            jf:write(string.format('    {"oam_id": %d, "x": %d, "y": %d, "width": %d, "height": %d, "tile": %d, "palette": %d, "vram_addr": %d}',
                s.oam_id, s.x, s.y, s.width, s.height, s.tile, s.palette, s.vram_addr or 0))
            if i < #sprites then jf:write(',') end
            jf:write('\n')
        end
        jf:write('  ],\n')

        -- Active indices
        jf:write('  "active_indices": [\n')
        for i, item in ipairs(active_indices) do
            local db = item.db
            jf:write(string.format('    {"idx": %d, "ptr": "%s", "last_frame": %d, "sessions": %d}',
                item.idx, db.ptr_hex or "", db.last_frame or 0, db.session_count or 0))
            if i < #active_indices then jf:write(',') end
            jf:write('\n')
        end
        jf:write('  ]\n')

        jf:write('}\n')
        jf:close()
        log("")
        log(string.format("JSON saved: %s", json_file))
    end

    log("==============================================================")
    log("")

    emu.displayMessage("Capture", string.format(
        "Frame %d: %d sprites, %d active indices",
        frame_count, #sprites, #active_indices))
end

-- ============================================================================
-- FRAME HANDLER
-- ============================================================================

local function on_frame()
    frame_count = frame_count + 1

    -- Update OBSEL
    update_obsel()

    -- Process staging batch from last frame
    if staging_batch and staging_batch.frame < frame_count then
        local size = staging_batch.wram_end - staging_batch.wram_start + 1
        local hash = compute_hash(staging_batch.data, #staging_batch.data)
        close_session("staging", {
            wram_start = staging_batch.wram_start,
            wram_end = staging_batch.wram_end,
            size = size,
            hash = hash,
        })
        staging_batch = nil
    end

    -- Session timeout
    if active_session and (frame_count - active_session.frame_start) >= SESSION_TIMEOUT then
        close_session("timeout")
    end

    -- Check F9 hotkey (edge detection)
    local f9_pressed = emu.isKeyPressed("F9")
    if f9_pressed and not last_f9_state then
        do_capture()
    end
    last_f9_state = f9_pressed

    -- Periodic status
    if frame_count % 300 == 0 then
        local idx_count = 0
        for _ in pairs(idx_database) do idx_count = idx_count + 1 end
        emu.displayMessage("Status", string.format(
            "Frame %d | %d indices tracked | Press F9 to capture",
            frame_count, idx_count))
    end
end

-- ============================================================================
-- INITIALIZATION
-- ============================================================================

local function init()
    log("==============================================================")
    log("  Sprite Identifier v1")
    log("==============================================================")
    log("Press F9 when target sprite is visible to capture")
    log("Output shows OAM entries + recently active idx sessions")
    log("")
    log(string.format("Started: %s", os.date()))
    log("")

    -- Register callbacks for SNES CPU (type 0)
    local cpu = 0

    pcall(function()
        emu.addMemoryCallback(on_table_read, emu.callbackType.read,
            TABLE_CPU_BASE, TABLE_CPU_END, cpu, emu.memType.snesMemory)
        log("Table read callback registered (01:FE52-01:FFFF)")
    end)

    pcall(function()
        emu.addMemoryCallback(on_dp_write, emu.callbackType.write,
            0x000000, 0x0000FF, cpu, emu.memType.snesMemory)
        log("DP write callback registered (00:0000-00:00FF)")
    end)

    pcall(function()
        emu.addMemoryCallback(on_staging_write, emu.callbackType.write,
            STAGING_START, STAGING_END, cpu, emu.memType.snesMemory)
        log("Staging write callback registered (7E:2000-7E:2FFF)")
    end)

    -- Also register for SA-1 CPU (type 3) if available
    pcall(function()
        emu.addMemoryCallback(on_table_read, emu.callbackType.read,
            TABLE_CPU_BASE, TABLE_CPU_END, 3, emu.memType.snesMemory)
        log("SA-1: Table read callback registered")
    end)

    pcall(function()
        emu.addMemoryCallback(on_dp_write, emu.callbackType.write,
            0x000000, 0x0000FF, 3, emu.memType.snesMemory)
        log("SA-1: DP write callback registered")
    end)

    -- Frame callback
    emu.addEventCallback(on_frame, emu.eventType.endFrame)
    log("Frame callback registered")

    -- Initial OBSEL
    update_obsel()

    log("")
    log("Ready. Play the game and press F9 when sprite is visible.")
    log("")
end

init()
