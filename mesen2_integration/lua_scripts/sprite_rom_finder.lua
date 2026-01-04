-- sprite_rom_finder.lua v22
-- Click on any sprite to get its ROM source offset
--
-- LEFT-CLICK on sprite = lookup ROM offset (topmost wins)
-- SCROLL UP/DOWN = cycle through candidates under cursor
-- RIGHT-CLICK = clear panel
-- SELECT = toggle HUD ignore (sprites with y < 32)
-- START = toggle bounding box debug overlay
--
-- v9: callback registration logging
-- v10: comprehensive pipeline counters to diagnose attribution failure
-- v11: persistent vram_owner_map + look-back attribution on session start
-- v12: fixed cpu_to_file_offset for full-bank SA-1 mapping (E9:3AEB was failing)
-- v13: staging-only owner fallback, CPU-keyed pending_tbl, cached debug counts
-- v14: remove vram_upload_map rewrite in look-back, remove unit-mismatch fallback
-- v15: multi-candidate picker (topmost wins), cycling, HUD ignore, OAM bbox overlay
-- v16: fix multi-channel DMA (advance VRAM dest per channel), fix header comments
-- v17: fix OAM memory type (snesOam -> snesSpriteRam) - was causing wrong reads
-- v18: fix SA-1 memType (sa1Memory not snesMemory), expand VALID_BANKS to C0-FF
-- v19: fix PPU state key casing (OamMode/OverscanMode), add OAM priority handling, tuneable params
-- v20: use cursor tile (flip-aware) for multi-tile sprites, base-tile fallback
-- v21: allow unmatched DP ptr sessions + click-time closest-session override
-- v22: optional stale DMA filter, avoid future-session overrides
-- v22: fix click targeting (use relativeX/Y for PPU coords, fix OAM snapshot timing, add X-wrap)

--------------------------------------------------------------------------------
-- Strict mode: catch accidental globals at runtime
--------------------------------------------------------------------------------
local ALLOWED_GLOBALS = {
    -- Lua builtins
    _G=1, _VERSION=1, assert=1, collectgarbage=1, error=1, getmetatable=1,
    ipairs=1, load=1, next=1, pairs=1, pcall=1, print=1, rawequal=1,
    rawget=1, rawlen=1, rawset=1, select=1, setmetatable=1, tonumber=1,
    tostring=1, type=1, xpcall=1,
    -- Lua standard libs
    coroutine=1, debug=1, io=1, math=1, os=1, package=1, string=1, table=1, utf8=1,
    -- Mesen API
    emu=1,
}
setmetatable(_G, {
    __newindex = function(t, k, v)
        if not ALLOWED_GLOBALS[k] then
            error("STRICT: write to undeclared global '" .. tostring(k) .. "'", 2)
        end
        rawset(t, k, v)
    end,
    __index = function(t, k)
        if not ALLOWED_GLOBALS[k] then
            error("STRICT: read undeclared global '" .. tostring(k) .. "'", 2)
        end
        return nil
    end
})

local OUTPUT_DIR = os.getenv("OUTPUT_DIR") or "C:\\CustomScripts\\KirbyMax\\workshop\\exhal-master\\spritepal\\mesen2_exchange\\"
local LOG_FILE = OUTPUT_DIR .. "sprite_rom_finder.log"

local ROM_HEADER = 0  -- Set to 0x200 if your .sfc has a copier header

local log_handle = nil
local frame_count = 0

local function log(msg)
    if not log_handle then
        log_handle = io.open(LOG_FILE, "w")
    end
    if log_handle then
        log_handle:write(msg .. "\n")
        log_handle:flush()
    end
    emu.log(msg)
end

local function fmt_addr(addr)
    local bank = (addr >> 16) & 0xFF
    local offset = addr & 0xFFFF
    return string.format("%02X:%04X", bank, offset)
end

-- FIX #1: Correct SA-1 full-bank mapping for Kirby Super Star
-- ROM banks C0-FF map full 64KB per bank: file_offset = (bank-0xC0)*0x10000 + addr
-- This handles proven pointers like E9:3AEB, E9:4D0A (addr < 0x8000)
local function cpu_to_file_offset(ptr)
    local bank = (ptr >> 16) & 0xFF
    local addr = ptr & 0xFFFF

    -- SA-1: ROM window is C0-FF (no addr restriction - full 64KB banks)
    if bank < 0xC0 or bank > 0xFF then return nil end

    local file_off = (bank - 0xC0) * 0x10000 + addr + ROM_HEADER
    return file_off
end

--------------------------------------------------------------------------------
-- DEBUG: Pipeline counters to diagnose where attribution fails
--------------------------------------------------------------------------------

local stats = {
    table_reads = 0,
    dp_ptr_complete = 0,
    sessions_started = 0,
    staging_dmas = 0,
    staging_attrib = 0,
    lookback_attrib = 0,  -- v11: attributions from look-back
}

--------------------------------------------------------------------------------
-- OAM / Sprite handling
--------------------------------------------------------------------------------

local oam_sizes = {
    [0] = {{8,8}, {16,16}},
    [1] = {{8,8}, {32,32}},
    [2] = {{8,8}, {64,64}},
    [3] = {{16,16}, {32,32}},
    [4] = {{16,16}, {64,64}},
    [5] = {{32,32}, {64,64}},
    [6] = {{16,32}, {32,64}},
    [7] = {{16,32}, {32,32}}
}

local function get_sprite_info(index)
    local base = index * 4

    local x_low = emu.read(base, emu.memType.snesSpriteRam)
    local y = emu.read(base + 1, emu.memType.snesSpriteRam)
    local tile = emu.read(base + 2, emu.memType.snesSpriteRam)
    local attr = emu.read(base + 3, emu.memType.snesSpriteRam)

    local high_offset = 0x200 + math.floor(index / 4)
    local high_byte = emu.read(high_offset, emu.memType.snesSpriteRam)
    local shift = (index % 4) * 2
    local x_high = (high_byte >> shift) & 1
    local large = ((high_byte >> shift) >> 1) & 1

    local x = x_low + (x_high * 256)
    if x >= 256 then x = x - 512 end

    local state = emu.getState()
    -- v19 FIX: Capital letters (Mesen2 serializes OamMode, not oamMode)
    local oam_mode = state["snes.ppu.OamMode"] or 0
    local size_table = oam_sizes[oam_mode] or oam_sizes[0]
    local size = size_table[large + 1]

    local oam_base = state["snes.ppu.OamBaseAddress"] or 0
    local oam_offset = state["snes.ppu.OamAddressOffset"] or 0

    -- Bit 0 of attr = name table select (second tile page)
    local use_second_table = (attr & 1) == 1
    local tile_addr = oam_base + (tile * 16)  -- 16 words per tile
    if use_second_table then
        tile_addr = tile_addr + oam_offset
    end
    tile_addr = tile_addr & 0x7FFF

    return {
        index = index,
        x = x, y = y,
        tile = tile,
        tile_index = tile,
        use_second_table = use_second_table,
        hflip = (attr & 0x40) ~= 0,
        vflip = (attr & 0x80) ~= 0,
        palette = (attr >> 1) & 7,
        priority = (attr >> 4) & 3,
        width = size[1], height = size[2],
        vram_addr = tile_addr,
        oam_base = oam_base,
        oam_offset = oam_offset,
    }
end

local function is_visible(spr)
    -- v19 FIX: Read OverscanMode instead of hardcoding 224
    local state = emu.getState()
    local overscan = state["snes.ppu.OverscanMode"]
    local screen_height = overscan and 239 or 224
    local x_visible = (spr.x + spr.width > 0) and (spr.x < 256)
    local y_visible = (spr.y < screen_height) and (spr.y + spr.height > 0)
    return x_visible and y_visible
end

local function point_in_sprite(spr, mx, my)
    -- v22: Handle Y (no wrap on SNES - sprites can go offscreen but don't wrap)
    local y_hit = my >= spr.y and my < spr.y + spr.height
    if not y_hit then return false end

    -- v22: Handle X with wrap (sprites at x=250 with width=16 cover 250-255 and 0-9)
    local x_end = spr.x + spr.width
    if x_end <= 256 then
        -- Normal case: no wrap
        return mx >= spr.x and mx < x_end
    else
        -- Wrapped: sprite covers [x..255] and [0..(x_end-256)]
        return mx >= spr.x or mx < (x_end - 256)
    end
end

--------------------------------------------------------------------------------
-- Session/idx tracking
--------------------------------------------------------------------------------

local TABLE_CPU_BASE = 0x01FE52
local TABLE_CPU_END = 0x01FFFF
local ENTRY_SIZE = 3
local DP_PTR_BASE = 0x0002

-- v11 FIX: Remove 0x7E from valid banks - WRAM pointers would pollute attribution
-- v18 FIX: Expand to full C0-FF range (was missing C4-CF, D0-DF, F0-FF)
local VALID_BANKS = {}
for bank = 0xC0, 0xFF do
    VALID_BANKS[bank] = true
end

local idx_database = {}
local ptr_to_idx = {}   -- v23: Reverse lookup from ptr -> idx for fast resolution
local pending_tbl = {}
local pending_dp = {}

--------------------------------------------------------------------------------
-- v19: TUNEABLE PARAMETERS
-- Adjust these if attribution fails for long-loading sprites or non-Kirby games
--------------------------------------------------------------------------------
local RECENT_SESSIONS_MAX = 64   -- Max sessions in queue (increase for busy games)
local SESSION_MATCH_WINDOW = 45  -- Frames to match DMA to session (increase for slow decode)
local ALLOW_UNMATCHED_DP_PTR = false         -- Start sessions for DP ptrs not in idx table
local UNMATCHED_SESSION_LOOKBACK = false     -- Avoid mass attribution for unmatched sessions
local CLICK_PREFER_CLOSEST_SESSION = false   -- v23: Use only direct vram_owner_map attribution
local CLICK_SESSION_WINDOW = 60              -- Frames around DMA to search for nearest session
local PREFER_IDX_KNOWN_SESSIONS = true       -- Prefer idx-known sessions over unmatched
local CLICK_SESSION_ONLY_BEFORE_DMA = true   -- Do not override with sessions after DMA
local MAX_DMA_AGE = 0                        -- Max age (frames) for click attribution; 0 disables
local RECENT_STAGING_MAX = 128   -- Max staging DMAs to track (increase if queue overflows)
local LOOKBACK_WINDOW = 300      -- Frames to look back at session start (increase for preloaded tiles)

-- Staging WRAM buffer range for Kirby Super Star
-- Adjust for other SA-1 games if they use a different decompression buffer
local STAGING_START = 0x7E2000
local STAGING_END = 0x7E2FFF

--------------------------------------------------------------------------------
-- Session/DMA tracking state (forward-declared for Lua scoping)
--------------------------------------------------------------------------------
local session_counter = 0
local recent_sessions = {}
local vram_upload_map = {}       -- Key: vram_word, Value: DMA entry (upload info)
local vram_owner_map = {}        -- Key: vram_word, Value: {idx, ptr, frame, file_offset}
local recent_staging_dmas = {}   -- Recent staging DMAs for look-back attribution

-- v13: Cached counts for draw_debug_info (avoids expensive pairs() every frame)
local cached_counts = { vram = 0, owner = 0, idx = 0, last_frame = -1 }
local COUNT_CACHE_INTERVAL = 30  -- update counts every N frames

local function is_valid_ptr(ptr)
    local bank = (ptr >> 16) & 0xFF
    if not VALID_BANKS[bank] then return false end
    if ptr == 0xFFFFFF or ptr == 0x000000 then return false end
    return true
end

-- v23: Pre-populate idx_database from ROM at init (deterministic, no runtime timing issues)
-- FE52 table format: 3 bytes per entry (lo, hi, bank) -> 24-bit ROM pointer
local function populate_idx_database_from_rom()
    local max_idx = math.floor((TABLE_CPU_END - TABLE_CPU_BASE) / ENTRY_SIZE)
    local count = 0

    for idx = 0, max_idx do
        local entry_addr = TABLE_CPU_BASE + (idx * ENTRY_SIZE)

        -- Read 3 bytes from ROM via CPU address space
        local lo = emu.read(entry_addr, emu.memType.snesMemory)
        local hi = emu.read(entry_addr + 1, emu.memType.snesMemory)
        local bank = emu.read(entry_addr + 2, emu.memType.snesMemory)

        if lo and hi and bank then
            local ptr = lo + (hi * 256) + (bank * 65536)
            if is_valid_ptr(ptr) then
                idx_database[idx] = { ptr = ptr, frame = 0 }
                ptr_to_idx[ptr] = idx
                count = count + 1
            end
        end
    end

    log(string.format("v23: Pre-populated idx_database with %d entries from FE52 table", count))
end

-- v11: Helper to write attribution to vram_owner_map for a DMA entry
local function write_vram_attribution(entry, idx, ptr, file_off)
    for w = entry.vram_start, entry.vram_end - 1 do
        vram_owner_map[w] = {
            idx = idx,
            ptr = ptr,
            file_offset = file_off,
            owner_frame = frame_count,
            dma_frame = entry.frame,
            source = entry.source,
            attrib_mode = entry.attrib_mode,
            session_frame = entry.session_frame,
        }
    end
end

local function start_session(ptr, idx, enable_lookback)
    session_counter = session_counter + 1
    stats.sessions_started = stats.sessions_started + 1
    local idx_str = idx ~= nil and tostring(idx) or "?"
    log(string.format("DBG START_SESSION idx=%s ptr=%s frame=%d", idx_str, fmt_addr(ptr), frame_count))
    table.insert(recent_sessions, {
        id = session_counter,
        ptr = ptr,
        idx = idx,
        frame = frame_count,
        idx_known = (idx ~= nil),
    })
    if #recent_sessions > RECENT_SESSIONS_MAX then
        table.remove(recent_sessions, 1)
    end

    -- v11: Look-back attribution - attribute recent staging DMAs to this session
    -- Only looks backward: at session start, all DMAs in recent_staging_dmas are in the past
    if enable_lookback == false then
        return
    end
    local file_off = cpu_to_file_offset(ptr)
    local lookback_count = 0
    for i, dma in ipairs(recent_staging_dmas) do
        local age = frame_count - dma.frame
        if age >= 0 and age <= LOOKBACK_WINDOW then
            -- Only attribute if not already attributed
            if not dma.attributed then
                dma.attributed = true
                dma.idx = idx
                dma.ptr = ptr
                dma.file_offset = file_off
                dma.attrib_mode = "lookback"
                dma.session_frame = frame_count
                -- v14: Removed vram_upload_map rewrite - dma IS the entry we inserted,
                -- so dma.idx/ptr/file_offset are already set above. Rewriting via
                -- vram_upload_map[dma.vram_start] risks tagging a *different* DMA
                -- if a later upload overwrote that VRAM word.
                -- Write to persistent owner map
                write_vram_attribution(dma, idx, ptr, file_off)
                lookback_count = lookback_count + 1
                stats.lookback_attrib = stats.lookback_attrib + 1
            end
        end
    end
    if lookback_count > 0 then
        log(string.format("DBG LOOKBACK: attributed %d staging DMAs to idx=%s", lookback_count, idx_str))
    end
end

-- Pick most recent session within window (iterate backwards, break early)
local function match_recent_session()
    local fallback = nil
    for i = #recent_sessions, 1, -1 do
        local s = recent_sessions[i]
        if (frame_count - s.frame) <= SESSION_MATCH_WINDOW then
            if PREFER_IDX_KNOWN_SESSIONS and s.idx_known then
                return s
            end
            if not fallback then
                fallback = s
            end
        else
            -- older than window; list is chronological, stop early
            break
        end
    end
    return fallback
end

local function find_closest_session(dma_frame)
    local best = nil
    local best_age = nil
    local require_idx = PREFER_IDX_KNOWN_SESSIONS
    for pass = 1, (require_idx and 2 or 1) do
        for i = #recent_sessions, 1, -1 do
            local s = recent_sessions[i]
            if (not require_idx) or s.idx_known then
                local age = dma_frame - s.frame
                if not CLICK_SESSION_ONLY_BEFORE_DMA then
                    age = math.abs(age)
                end
                if age >= 0 and age <= CLICK_SESSION_WINDOW then
                    if not best or age < best_age then
                        best = s
                        best_age = age
                    end
                end
            end
        end
        if best or not require_idx then
            break
        end
        -- No idx-known session found; allow unmatched in second pass
        require_idx = false
    end
    return best, best_age
end

-- v13 FIX: Factory function to create CPU-specific table_read callbacks
-- This prevents interleaving if both CPUs read the same idx (keys by cpu:idx)
local function make_on_table_read(cpu_name)
    return function(addr, value)
        -- DEBUG: Count every table read
        stats.table_reads = stats.table_reads + 1
        if (stats.table_reads % 2000) == 0 then
            local c = 0
            for _ in pairs(idx_database) do c = c + 1 end
            log(string.format("DBG table_reads=%d idx_db=%d", stats.table_reads, c))
        end

        local offset_from_base = addr - TABLE_CPU_BASE
        local idx = math.floor(offset_from_base / ENTRY_SIZE)
        local byte_pos = offset_from_base % ENTRY_SIZE

        -- v13: Key by cpu_name:idx to prevent cross-CPU contamination
        local key = cpu_name .. ":" .. idx

        if not pending_tbl[key] then
            pending_tbl[key] = {lo = nil, hi = nil, bank = nil, frame = frame_count}
        end

        local entry = pending_tbl[key]
        if byte_pos == 0 then entry.lo = value
        elseif byte_pos == 1 then entry.hi = value
        elseif byte_pos == 2 then entry.bank = value
        end

        if entry.lo and entry.hi and entry.bank then
            local ptr = entry.lo + (entry.hi * 256) + (entry.bank * 65536)
            if is_valid_ptr(ptr) then
                idx_database[idx] = { ptr = ptr, frame = frame_count }
            end
            pending_tbl[key] = nil
        end
        return nil
    end
end

-- FIX #2: Only match bank 00, address < 0x100 for DP writes
local function make_on_dp_write(cpu_name)
    return function(addr, value)
        local bank = (addr >> 16) & 0xFF
        local lo = addr & 0xFFFF

        -- Must be bank 00 and in direct page range
        if bank ~= 0x00 then return nil end
        if lo > 0x00FF then return nil end

        local offset = lo
        if offset < DP_PTR_BASE or offset > DP_PTR_BASE + 2 then return nil end

        if not pending_dp[cpu_name] then pending_dp[cpu_name] = {} end
        local pending = pending_dp[cpu_name]
        local byte_pos = offset - DP_PTR_BASE

        if byte_pos == 0 then pending.lo = value; pending.lo_frame = frame_count
        elseif byte_pos == 1 then pending.hi = value; pending.hi_frame = frame_count
        elseif byte_pos == 2 then pending.bank = value; pending.bank_frame = frame_count
        end

        if pending.lo and pending.hi and pending.bank then
            local max_f = math.max(pending.lo_frame or 0, pending.hi_frame or 0, pending.bank_frame or 0)
            local min_f = math.min(pending.lo_frame or 0, pending.hi_frame or 0, pending.bank_frame or 0)

            if max_f - min_f <= 1 then
                local ptr = pending.lo + (pending.hi * 256) + (pending.bank * 65536)
                -- DEBUG: Log every completed DP pointer write
                stats.dp_ptr_complete = stats.dp_ptr_complete + 1
                log(string.format("DBG DP ptr complete: %02X:%04X frame=%d",
                    pending.bank, pending.hi * 256 + pending.lo, frame_count))

                if is_valid_ptr(ptr) then
                    local matched_idx = ptr_to_idx[ptr]  -- v23: O(1) lookup
                    if matched_idx then
                        start_session(ptr, matched_idx, true)
                    else
                        log(string.format("DBG DP ptr %s valid but no idx match", fmt_addr(ptr)))
                        if ALLOW_UNMATCHED_DP_PTR then
                            start_session(ptr, nil, UNMATCHED_SESSION_LOOKBACK)
                        end
                    end
                else
                    log(string.format("DBG DP ptr %s rejected as invalid", fmt_addr(ptr)))
                end
                pending_dp[cpu_name] = {}
            end
        end
        return nil
    end
end

--------------------------------------------------------------------------------
-- VRAM DMA tracking
-- (Tables/constants forward-declared above to fix Lua scoping)
--------------------------------------------------------------------------------

local DMA_ENABLE_REG = 0x420B

-- FIX #6: Shadow VMADD from writes (don't read back $2116/$2117 which can return open-bus)
local vmadd_lo, vmadd_hi = 0, 0
local vram_addr_shadow = 0

local function on_vram_addr_write(address, value)
    -- Capture the WRITTEN value, not a readback
    if address == 0x2116 then
        vmadd_lo = value & 0xFF
    else -- 0x2117
        vmadd_hi = value & 0xFF
    end
    -- Mask to 15-bit VRAM address space (0x0000-0x7FFF)
    vram_addr_shadow = (vmadd_lo + (vmadd_hi * 256)) & 0x7FFF
end

-- FIX #8: Shadow DMA channel registers (post-DMA reads return garbage)
local dma_shadow = {}
for ch = 0, 7 do
    dma_shadow[ch] = { dmap=0, bbad=0, a1tl=0, a1th=0, a1tb=0, dasl=0, dash=0 }
end

local function on_dma_reg_write(address, value)
    local offset = address - 0x4300
    local ch = math.floor(offset / 16)
    local reg = offset % 16
    if ch < 0 or ch > 7 then return end
    local s = dma_shadow[ch]
    if     reg == 0 then s.dmap = value
    elseif reg == 1 then s.bbad = value
    elseif reg == 2 then s.a1tl = value
    elseif reg == 3 then s.a1th = value
    elseif reg == 4 then s.a1tb = value
    elseif reg == 5 then s.dasl = value
    elseif reg == 6 then s.dash = value
    end
end

local function on_dma_enable(addr, value)
    -- FIX #8: Handle nil value (Mesen may pass nil sometimes)
    local enable = value
    if enable == nil then
        enable = emu.read(0x420B, emu.memType.snesMemory) or 0
    end
    enable = enable & 0xFF
    if enable == 0 then return nil end

    -- v16: Count VRAM-targeting channels to handle multi-channel DMA correctly
    -- When multiple channels target VRAM in one $420B write, VMADD advances between them
    local vram_channels = {}
    for ch = 0, 7 do
        if (enable & (1 << ch)) ~= 0 then
            local s = dma_shadow[ch]
            local dmap = s.dmap or 0
            local bbad = s.bbad or 0
            local direction = (dmap & 0x80) >> 7
            if direction == 0 and (bbad == 0x18 or bbad == 0x19) then
                table.insert(vram_channels, ch)
            end
        end
    end

    -- v16: Track local VRAM destination that advances per channel
    local local_vram_dest = vram_addr_shadow

    for ch = 0, 7 do
        if (enable & (1 << ch)) ~= 0 then
            -- Use shadowed registers (post-DMA reads return garbage)
            local s = dma_shadow[ch]
            local dmap = s.dmap or 0
            local bbad = s.bbad or 0
            local src_addr = (s.a1tl or 0) + ((s.a1th or 0) * 256) + ((s.a1tb or 0) * 65536)
            local dma_size = (s.dasl or 0) + ((s.dash or 0) * 256)
            if dma_size == 0 then dma_size = 0x10000 end

            local direction = (dmap & 0x80) >> 7

            -- Only track A→B transfers to VRAM ($2118/$2119)
            if direction == 0 and (bbad == 0x18 or bbad == 0x19) then
                -- v16: Use local_vram_dest which advances for multi-channel DMAs
                local vram_dest = local_vram_dest

                -- FIX #4: Only attribute staging DMAs
                local is_staging = (src_addr >= STAGING_START and src_addr <= STAGING_END)

                -- DEBUG: Count staging DMAs
                if is_staging then
                    stats.staging_dmas = stats.staging_dmas + 1
                end

                -- FIX #9: Use session queue - match most recent session within window
                local session_idx, session_ptr, file_off = nil, nil, nil
                local session_frame = nil
                local attrib_mode = nil
                if is_staging then
                    local sess = match_recent_session()
                    if sess then
                        session_idx = sess.idx
                        session_ptr = sess.ptr
                        session_frame = sess.frame
                        if session_ptr then file_off = cpu_to_file_offset(session_ptr) end
                        stats.staging_attrib = stats.staging_attrib + 1
                        attrib_mode = "forward"
                    end
                end

                local entry = {
                    frame = frame_count,
                    vram_start = vram_dest,
                    vram_end = vram_dest + math.ceil(dma_size / 2),  -- ceil for odd byte counts
                    source = src_addr,
                    size = dma_size,
                    is_staging = is_staging,
                    idx = session_idx,
                    ptr = session_ptr,
                    file_offset = file_off,
                    attributed = (session_ptr ~= nil),  -- v11: track if attributed
                    attrib_mode = attrib_mode,
                    session_frame = session_frame,
                }

                for w = entry.vram_start, entry.vram_end - 1 do
                    vram_upload_map[w] = entry
                end

                -- v11: If attributed now, also write to persistent owner map
                if session_idx then
                    write_vram_attribution(entry, session_idx, session_ptr, file_off)
                end

                -- v11: Record staging DMAs for look-back attribution
                if is_staging then
                    table.insert(recent_staging_dmas, entry)
                    if #recent_staging_dmas > RECENT_STAGING_MAX then
                        table.remove(recent_staging_dmas, 1)
                    end
                end

                -- v16: Advance local VRAM dest for next channel in multi-channel DMA
                -- VMADD advances by transfer size (in words) after each channel completes
                local words_transferred = math.ceil(dma_size / 2)
                local_vram_dest = local_vram_dest + words_transferred
            end
        end
    end
    return nil
end

local function lookup_vram_source(vram_word)
    local v = vram_word
    local entry = vram_upload_map[v]
    local actual_key = v

    -- v14: Removed unit-mismatch fallback (v>>1, v<<1). OAM tile math and VMADD
    -- shadow are both word-based, so mismatched lookups would find wrong DMAs.

    if entry then
        -- v11: If entry has no attribution, check vram_owner_map
        -- v13 FIX: Only use owner fallback for staging entries - non-staging
        -- DMAs (BG/font) may have overwritten the sprite data
        local idx, ptr, file_offset = entry.idx, entry.ptr, entry.file_offset
        local attrib_mode = entry.attrib_mode
        local session_frame = entry.session_frame
        if entry.ptr == nil and entry.is_staging then
            local owner = vram_owner_map[actual_key]
            if owner then
                idx = owner.idx
                ptr = owner.ptr
                file_offset = owner.file_offset
                attrib_mode = owner.attrib_mode
                session_frame = owner.session_frame
            end
        end

        return {
            found = true,
            vram_word = actual_key,
            vram_addr_original = v,
            upload_frame = entry.frame,
            session_frame = session_frame,
            attrib_mode = attrib_mode,
            source_addr = entry.source,
            is_staging = entry.is_staging,
            idx = idx,
            ptr = ptr,
            file_offset = file_offset,
        }
    end
    return { found = false, vram_word = v }
end

local function lookup_sprite_source(spr)
    return lookup_vram_source(spr.vram_addr)
end

--------------------------------------------------------------------------------
-- UI: Click-to-lookup with debug info
--------------------------------------------------------------------------------

local selected_result = nil
local prev_left = false
local prev_right = false
local last_click_info = nil  -- Debug: store last click attempt

-- v15: Multi-candidate selection
local candidates_under_cursor = {}    -- List of sprites under cursor
local selected_candidate_idx = 1      -- Which candidate is selected (1-based)
local prev_scroll = 0                 -- For scroll wheel delta detection

-- v15: HUD ignore toggle
local hud_ignore_enabled = true
local HUD_Y_THRESHOLD = 32            -- Ignore sprites with y < this

-- v15: Bounding box debug overlay
local show_oam_boxes = false

local function get_sprite_vram_word_at_point(spr, mx, my)
    local cols = math.max(1, math.floor(spr.width / 8))
    local rows = math.max(1, math.floor(spr.height / 8))

    local rel_x = mx - spr.x
    local rel_y = my - spr.y
    local tile_x = math.floor(rel_x / 8)
    local tile_y = math.floor(rel_y / 8)

    if tile_x < 0 then tile_x = 0 end
    if tile_y < 0 then tile_y = 0 end
    if tile_x >= cols then tile_x = cols - 1 end
    if tile_y >= rows then tile_y = rows - 1 end

    if spr.hflip then
        tile_x = cols - 1 - tile_x
    end
    if spr.vflip then
        tile_y = rows - 1 - tile_y
    end

    local base_row = (spr.tile_index >> 4) & 0x0F
    local base_col = spr.tile_index & 0x0F
    local row = (base_row + tile_y) & 0x0F
    local col = (base_col + tile_x) & 0x0F
    local tile_index = row * 16 + col

    local tile_addr = spr.oam_base + (tile_index * 16)
    if spr.use_second_table then
        tile_addr = tile_addr + spr.oam_offset
    end
    tile_addr = tile_addr & 0x7FFF

    return tile_addr, {
        tile_x = tile_x,
        tile_y = tile_y,
        cols = cols,
        rows = rows,
    }
end

local function draw_crosshair(mouse)
    if mouse.x >= 0 and mouse.x < 256 and mouse.y >= 0 and mouse.y < 224 then
        emu.drawLine(mouse.x - 5, mouse.y, mouse.x + 5, mouse.y, 0xFFFFFFFF)
        emu.drawLine(mouse.x, mouse.y - 5, mouse.x, mouse.y + 5, 0xFFFFFFFF)
    end
end

-- v22: Convert mouse coords to PPU space using normalized relativeX/relativeY
-- This bypasses any overscan offset issues with mouse.x/y
local function get_ppu_coords(mouse)
    if mouse.relativeX and mouse.relativeX >= 0 then
        local state = emu.getState()
        local overscan = state["snes.ppu.OverscanMode"]
        local ppu_height = overscan and 239 or 224
        local ppu_width = 256

        local ppu_x = math.floor(mouse.relativeX * ppu_width)
        local ppu_y = math.floor(mouse.relativeY * ppu_height)

        return ppu_x, ppu_y, {
            raw_x = mouse.x, raw_y = mouse.y,
            rel_x = mouse.relativeX, rel_y = mouse.relativeY,
            ppu_width = ppu_width, ppu_height = ppu_height,
        }
    end

    -- Fallback: use direct coords (may have overscan offset)
    return mouse.x, mouse.y, { fallback = true }
end

-- v22: Track last OAM snapshot frame for timing debug
local last_oam_frame = 0

-- v19: Get OAM draw order accounting for EnableOamPriority
-- Returns higher value for sprites drawn later (on top)
local function get_oam_draw_order(index)
    local state = emu.getState()
    local priority_enabled = state["snes.ppu.EnableOamPriority"]
    if priority_enabled then
        -- When priority is enabled, evaluation starts from InternalOamAddress >> 2
        -- Sprites evaluated later are drawn on top
        local start_idx = ((state["snes.ppu.InternalOamAddress"] or 0) >> 2) & 0x7F
        -- N-1 is last (topmost) when starting from N
        return (index - start_idx + 128) % 128
    end
    -- Normal mode: higher index = later in evaluation = on top
    return index
end

-- v15: Collect all sprites under cursor, sorted by draw order (topmost first)
local function collect_candidates(mouse)
    local result = {}
    for i = 0, 127 do
        local spr = get_sprite_info(i)
        if is_visible(spr) and point_in_sprite(spr, mouse.x, mouse.y) then
            -- v15: Apply HUD filter if enabled
            if not hud_ignore_enabled or spr.y >= HUD_Y_THRESHOLD then
                table.insert(result, spr)
            end
        end
    end
    -- v19: Sort by draw order descending (topmost = highest draw_order = first in list)
    table.sort(result, function(a, b)
        return get_oam_draw_order(a.index) > get_oam_draw_order(b.index)
    end)
    return result
end

-- v15: Draw bounding boxes for all visible sprites (debug overlay)
local function draw_oam_boxes()
    if not show_oam_boxes then return end
    for i = 0, 127 do
        local spr = get_sprite_info(i)
        if is_visible(spr) then
            -- Color code: cyan for normal, gray for HUD-filtered
            local color = 0x80FFFF00  -- Semi-transparent cyan
            if hud_ignore_enabled and spr.y < HUD_Y_THRESHOLD then
                color = 0x40808080    -- Dimmed gray for ignored HUD sprites
            end
            emu.drawRectangle(spr.x, spr.y, spr.width, spr.height, color, false)
            emu.drawString(spr.x + 1, spr.y + 1, tostring(spr.index), 0xFFFFFF, 0x80000000)
        end
    end
end

-- v15: Draw candidate list under cursor
local function draw_candidate_list(mouse)
    if #candidates_under_cursor == 0 then return end

    -- Show small list of candidates
    local x, y = 4, 110
    emu.drawString(x, y, string.format("Under cursor: %d", #candidates_under_cursor), 0xFFFF00, 0x80000000)
    for i, spr in ipairs(candidates_under_cursor) do
        local marker = (i == selected_candidate_idx) and ">" or " "
        local color = (i == selected_candidate_idx) and 0x00FF00 or 0xAAAAAA
        emu.drawString(x, y + i * 9, string.format("%s#%d y=%d", marker, spr.index, spr.y), color, 0x80000000)
        if i >= 4 then break end  -- Show max 4
    end
    if #candidates_under_cursor > 4 then
        emu.drawString(x, y + 5 * 9, string.format("  ...+%d more", #candidates_under_cursor - 4), 0x888888, 0x80000000)
    end
end

local function draw_hover_hint(mouse)
    -- v22: Candidates already collected in on_frame() BEFORE click handling
    -- This function now only does drawing

    -- Highlight current selection
    if #candidates_under_cursor > 0 then
        local spr = candidates_under_cursor[selected_candidate_idx]
        if spr then
            emu.drawRectangle(spr.x, spr.y, spr.width, spr.height, 0xFFFFFF00, false)
            emu.drawString(spr.x, spr.y - 8, string.format("#%d", spr.index), 0xFFFFFF, 0x80000000)
        end
        return true
    end
    return false
end

local function draw_result_panel()
    if not selected_result then return end

    local r = selected_result
    local x, y = 4, 4
    local w, h = 140, 100

    emu.drawRectangle(x, y, w, h, 0xE0000000, true)
    emu.drawRectangle(x, y, w, h, 0xFFFFFF, false)

    local line = y + 2
    local function text(s, color)
        emu.drawString(x + 3, line, s, color or 0xFFFFFF, 0x00000000)
        line = line + 9
    end

    text(string.format("OAM #%d", r.sprite_index), 0x00FFFF)
    text(string.format("VRAM w=$%04X b=$%04X", r.vram_word, r.vram_word * 2), 0xFFFF00)
    if r.tile_cols and r.tile_rows then
        text(string.format("tile %d,%d of %dx%d", r.tile_x, r.tile_y, r.tile_cols, r.tile_rows), 0x888888)
    end
    if r.used_base_tile then
        text("fallback: base tile", 0xFF8800)
    end
    if r.upload_age then
        local age_color = (r.stale and 0xFF8800) or 0x888888
        text(string.format("age=%d", r.upload_age), age_color)
    end
    if r.stale then
        text("stale: wait respawn", 0xFF8800)
    end

    if r.found then
        text(string.format("key=$%04X f=%d", r.vram_word, r.upload_frame), 0x888888)
        if r.display_ptr then
            if r.display_idx ~= nil then
                text(string.format("idx=%d", r.display_idx), 0x00FF00)
            else
                text("idx=(unmatched)", 0xFF8800)
            end
            text(fmt_addr(r.display_ptr), 0x00FF00)
            if r.display_file_offset then
                text(string.format("FILE: 0x%06X", r.display_file_offset), 0xFF00FF)
            end
            if r.display_override then
                text("override: nearest", 0xFF8800)
            end
        else
            text("(no idx attrib)", 0xFF8800)
        end
    else
        text("Not in map", 0xFF0000)
        text("Wait for anim", 0x888888)
    end
end

-- Debug: show mouse coords, sprite count, and session diagnostics
local function draw_debug_info(mouse)
    local visible_count = 0
    for i = 0, 127 do
        local spr = get_sprite_info(i)
        if is_visible(spr) then visible_count = visible_count + 1 end
    end

    -- v13: Use cached counts, refresh periodically (avoids expensive pairs() every frame)
    if frame_count - cached_counts.last_frame >= COUNT_CACHE_INTERVAL then
        local vram_count = 0
        for _ in pairs(vram_upload_map) do vram_count = vram_count + 1 end
        local owner_count = 0
        for _ in pairs(vram_owner_map) do owner_count = owner_count + 1 end
        local idx_count = 0
        for _ in pairs(idx_database) do idx_count = idx_count + 1 end

        cached_counts.vram = vram_count
        cached_counts.owner = owner_count
        cached_counts.idx = idx_count
        cached_counts.last_frame = frame_count
    end

    emu.drawString(170, 4, string.format("(%d,%d)", mouse.x, mouse.y), 0x888888, 0x00000000)
    emu.drawString(170, 13, string.format("spr:%d", visible_count), 0x888888, 0x00000000)
    emu.drawString(170, 22, string.format("vram:%d", cached_counts.vram), 0x888888, 0x00000000)
    emu.drawString(170, 31, string.format("f:%d", frame_count), 0x888888, 0x00000000)
    -- Diagnostic: idx_database entries and session count
    emu.drawString(170, 40, string.format("idx:%d", cached_counts.idx), 0x00FF00, 0x00000000)
    emu.drawString(170, 49, string.format("ses:%d", #recent_sessions), 0x00FF00, 0x00000000)
    emu.drawString(170, 58, string.format("own:%d", cached_counts.owner), 0xFF00FF, 0x00000000)
end

local function on_left_click(mouse, coord_debug)
    -- v22: Enhanced debug output for click targeting diagnosis
    coord_debug = coord_debug or {}
    log("========================================")
    log(string.format("CLICK at ppu=(%d,%d) frame=%d oam_frame=%d",
        mouse.x, mouse.y, frame_count, last_oam_frame))
    if coord_debug.rel_x then
        log(string.format("  raw=(%d,%d) rel=(%.4f,%.4f)",
            coord_debug.raw_x or -1, coord_debug.raw_y or -1,
            coord_debug.rel_x or 0, coord_debug.rel_y or 0))
    elseif coord_debug.fallback then
        log("  (using fallback coords - relativeX not available)")
    end
    log(string.format("  Candidates: %d", #candidates_under_cursor))
    for i, c in ipairs(candidates_under_cursor) do
        local marker = i == selected_candidate_idx and ">" or " "
        log(string.format("    %s#%d (%d,%d) %dx%d tile=$%02X",
            marker, c.index, c.x, c.y, c.width, c.height, c.tile or 0))
    end

    -- v15: Use pre-collected candidates (already sorted by OAM index descending)
    if #candidates_under_cursor == 0 then
        log("No sprite at click position")
        log("========================================")
        return
    end

    -- v15: Use selected candidate (default is topmost = first in list)
    local spr = candidates_under_cursor[selected_candidate_idx]
    if not spr then
        log("No valid candidate selected")
        log("========================================")
        return
    end

    local selected_vram_word, tile_info = get_sprite_vram_word_at_point(spr, mouse.x, mouse.y)
    local base_vram_word = spr.vram_addr

    local source = lookup_vram_source(selected_vram_word)
    local used_base_tile = false
    if not source.found and selected_vram_word ~= base_vram_word then
        local base_source = lookup_vram_source(base_vram_word)
        if base_source.found then
            source = base_source
            used_base_tile = true
        end
    end

    local display_idx = source.idx
    local display_ptr = source.ptr
    local display_file_offset = source.file_offset
    local display_override = false
    local override_age = nil
    local upload_age = nil
    local stale = false
    if source.found and source.upload_frame then
        upload_age = frame_count - source.upload_frame
        if MAX_DMA_AGE > 0 and upload_age > MAX_DMA_AGE then
            stale = true
        end
    end
    if CLICK_PREFER_CLOSEST_SESSION and source.found and source.upload_frame then
        local sess, age = find_closest_session(source.upload_frame)
        if sess and sess.ptr and (display_ptr ~= sess.ptr or display_idx == nil) then
            display_idx = sess.idx
            display_ptr = sess.ptr
            display_file_offset = cpu_to_file_offset(sess.ptr)
            display_override = true
            override_age = age
        end
    end
    if stale then
        -- Keep the raw attribution in the log/panel but avoid emitting an offset by default
        display_ptr = nil
        display_file_offset = nil
    end

    selected_result = {
        sprite_index = spr.index,
        vram_word = source.vram_word,
        vram_word_requested = selected_vram_word,
        base_vram_word = base_vram_word,
        used_base_tile = used_base_tile,
        tile_x = tile_info and tile_info.tile_x or nil,
        tile_y = tile_info and tile_info.tile_y or nil,
        tile_cols = tile_info and tile_info.cols or nil,
        tile_rows = tile_info and tile_info.rows or nil,
        found = source.found,
        upload_frame = source.upload_frame,
        session_frame = source.session_frame,
        attrib_mode = source.attrib_mode,
        source_addr = source.source_addr,
        is_staging = source.is_staging,
        idx = source.idx,
        ptr = source.ptr,
        file_offset = source.file_offset,
        display_idx = display_idx,
        display_ptr = display_ptr,
        display_file_offset = display_file_offset,
        display_override = display_override,
        override_age = override_age,
        upload_age = upload_age,
        stale = stale,
    }

    log(string.format("SELECTED: SPRITE #%d at (%d,%d) size=%dx%d [%d of %d candidates]",
        spr.index, spr.x, spr.y, spr.width, spr.height,
        selected_candidate_idx, #candidates_under_cursor))
    if spr.width > 8 or spr.height > 8 then
        if tile_info then
            log(string.format("Tile under cursor: %d,%d of %dx%d",
                tile_info.tile_x, tile_info.tile_y, tile_info.cols, tile_info.rows))
        end
    end
    log(string.format("VRAM word=$%04X  byte=$%04X", selected_vram_word, selected_vram_word * 2))
    if selected_vram_word ~= base_vram_word then
        log(string.format("Base tile VRAM word=$%04X", base_vram_word))
    end
    if source.found then
        log(string.format("FOUND at key=$%04X (frame %d)", source.vram_word, source.upload_frame))
        log(string.format("DMA staging: %s", source.is_staging and "YES" or "no"))
        if source.attrib_mode then
            log(string.format("attrib: %s (session f=%s)", source.attrib_mode, tostring(source.session_frame)))
        end
        if source.upload_frame then
            log(string.format("upload age=%d frames", frame_count - source.upload_frame))
        end
        if stale then
            log(string.format("STALE: upload age exceeds MAX_DMA_AGE (%d)", MAX_DMA_AGE))
        end
        if display_ptr then
            if display_idx ~= nil then
                log(string.format("idx: %d", display_idx))
            else
                log("idx: (unmatched)")
            end
            log(string.format("ptr: %s", fmt_addr(display_ptr)))
            if display_file_offset then
                log(string.format("FILE OFFSET: 0x%06X", display_file_offset))
                log("")
                log(string.format(">>> --offset 0x%06X <<<", display_file_offset))
            end
            if display_override then
                log(string.format("OVERRIDE: closest session (age=%d)", override_age or -1))
            end
            if used_base_tile then
                log("NOTE: Using base tile attribution (cursor tile not found)")
            end
        else
            log("(No attribution - VRAM range never matched a session)")
            log(string.format("DMA source: %s", fmt_addr(source.source_addr)))
            log(string.format("Uploaded at frame %d, current frame %d", source.upload_frame, frame_count))
        end
    else
        log("NOT FOUND in vram_upload_map")
        -- Diagnostic: show nearby keys
        local nearby = {}
        for k, _ in pairs(vram_upload_map) do
            if math.abs(k - selected_vram_word) < 0x100 then
                table.insert(nearby, k)
            end
        end
        if #nearby > 0 then
            table.sort(nearby)
            local s = {}
            for j = 1, math.min(5, #nearby) do
                table.insert(s, string.format("$%04X", nearby[j]))
            end
            log("Nearby keys: " .. table.concat(s, ", "))
        else
            log("(no nearby keys in map)")
        end
    end
    log("========================================")
end

-- v15: Key state tracking for toggles
local prev_key_h = false
local prev_key_b = false
local prev_key_up = false
local prev_key_down = false

local function on_frame()
    frame_count = frame_count + 1

    -- FIX #7: No history purge - tiles may be loaded once and reused for minutes
    -- (Uncomment to limit memory if needed, but defeats long-lived tile lookup)
    -- if frame_count % 60 == 0 then
    --     local cutoff = frame_count - 120
    --     for addr, entry in pairs(vram_upload_map) do
    --         if entry.frame < cutoff then vram_upload_map[addr] = nil end
    --     end
    -- end

    -- Session cleanup handled by size cap in start_session()

    -- DEBUG: Periodic stats dump every 60 frames
    if (frame_count % 60) == 0 then
        log(string.format("DBG f=%d reads=%d dp=%d ses=%d stg=%d attr=%d lkbk=%d",
            frame_count, stats.table_reads, stats.dp_ptr_complete, stats.sessions_started,
            stats.staging_dmas, stats.staging_attrib, stats.lookback_attrib))
    end

    local mouse = emu.getMouseState()

    -- v22: Convert to PPU coordinates FIRST (using normalized relativeX/relativeY)
    local ppu_x, ppu_y, coord_debug = get_ppu_coords(mouse)
    local ppu_mouse = {
        x = ppu_x, y = ppu_y,
        left = mouse.left, right = mouse.right,
        scrollY = mouse.scrollY,
        relativeX = mouse.relativeX, relativeY = mouse.relativeY,
    }

    -- v22: Collect candidates BEFORE click handling (fixes stale OAM snapshot bug)
    candidates_under_cursor = collect_candidates(ppu_mouse)
    last_oam_frame = frame_count
    selected_candidate_idx = math.min(selected_candidate_idx, math.max(1, #candidates_under_cursor))

    -- Handle clicks (now uses THIS frame's candidates)
    if ppu_mouse.left and not prev_left then
        on_left_click(ppu_mouse, coord_debug)
    end
    if ppu_mouse.right and not prev_right then
        selected_result = nil
    end
    prev_left = ppu_mouse.left
    prev_right = ppu_mouse.right

    -- v15: Scroll wheel cycling through candidates (if available)
    if mouse.scrollY then
        local scroll_delta = mouse.scrollY - prev_scroll
        if scroll_delta ~= 0 and #candidates_under_cursor > 0 then
            if scroll_delta > 0 then
                -- Scroll up = previous candidate
                selected_candidate_idx = selected_candidate_idx - 1
                if selected_candidate_idx < 1 then
                    selected_candidate_idx = #candidates_under_cursor
                end
            else
                -- Scroll down = next candidate
                selected_candidate_idx = selected_candidate_idx + 1
                if selected_candidate_idx > #candidates_under_cursor then
                    selected_candidate_idx = 1
                end
            end
        end
        prev_scroll = mouse.scrollY
    end

    -- v15: Keyboard controls for toggles and cycling
    local input = emu.getInput(0) or {}

    -- Up/Down arrow cycling (fallback if scroll wheel not available)
    local key_up = input.up or false
    local key_down = input.down or false
    if key_up and not prev_key_up and #candidates_under_cursor > 0 then
        selected_candidate_idx = selected_candidate_idx - 1
        if selected_candidate_idx < 1 then
            selected_candidate_idx = #candidates_under_cursor
        end
    end
    if key_down and not prev_key_down and #candidates_under_cursor > 0 then
        selected_candidate_idx = selected_candidate_idx + 1
        if selected_candidate_idx > #candidates_under_cursor then
            selected_candidate_idx = 1
        end
    end
    prev_key_up = key_up
    prev_key_down = key_down

    -- H key toggles HUD ignore
    local key_h = input.select or false  -- Map to Select button as "H" key proxy
    if key_h and not prev_key_h then
        hud_ignore_enabled = not hud_ignore_enabled
        log(string.format("HUD ignore: %s (y < %d)", hud_ignore_enabled and "ON" or "OFF", HUD_Y_THRESHOLD))
    end
    prev_key_h = key_h

    -- B key toggles bounding box overlay
    local key_b = input.start or false  -- Map to Start button as "B" key proxy
    if key_b and not prev_key_b then
        show_oam_boxes = not show_oam_boxes
        log(string.format("OAM boxes: %s", show_oam_boxes and "ON" or "OFF"))
    end
    prev_key_b = key_b

    -- Draw (v22: use ppu_mouse for consistent coordinate space)
    draw_oam_boxes()            -- v15: Debug overlay first (behind other UI)
    draw_crosshair(ppu_mouse)
    draw_hover_hint(ppu_mouse)  -- v22: now just draws, doesn't re-collect
    draw_candidate_list(ppu_mouse)  -- v15: Show candidates list
    draw_result_panel()
    draw_debug_info(ppu_mouse)

    -- v15: Show toggle states in corner
    if hud_ignore_enabled or show_oam_boxes then
        local status = ""
        if hud_ignore_enabled then status = status .. "HUD:OFF " end
        if show_oam_boxes then status = status .. "BBOX:ON" end
        emu.drawString(170, 67, status, 0xFFFF00, 0x80000000)
    end
end

--------------------------------------------------------------------------------
-- Initialize
--------------------------------------------------------------------------------

log("========================================")
log("SPRITE ROM FINDER v23")
log("========================================")
log("v23: Strict causal attribution")
log("  - Pre-populated FE52 table at init (no runtime timing issues)")
log("  - Disabled closest-session override (pure vram_owner_map)")
log("  - O(1) ptr->idx lookup via reverse map")
log("  - Cursor-tile attribution (flip-aware), base-tile fallback")
log("  - Scroll/arrows cycle through candidates")
log("  - HUD ignore toggle (Select button)")
log("  - Bounding box overlay (Start button)")
log("")
log("LEFT-CLICK = lookup ROM offset for selected sprite")
log("SCROLL/ARROWS = cycle through candidates under cursor")
log("SELECT = toggle HUD ignore (y < 32)")
log("START = toggle bounding box overlay")
log("RIGHT-CLICK = clear panel")
log("========================================")

-- v23: Pre-populate FE52 table from ROM (must be after ROM is loaded)
populate_idx_database_from_rom()

local snes_cpu = emu.cpuType and emu.cpuType.snes or nil
local sa1_cpu = emu.cpuType and emu.cpuType.sa1 or nil

log(string.format("DEBUG: snes_cpu=%s, sa1_cpu=%s", tostring(snes_cpu), tostring(sa1_cpu)))

-- v18 FIX: SA-1 CPU uses sa1Memory, not snesMemory (per DebugUtilities.h:16)
for _, cpu in ipairs({snes_cpu, sa1_cpu}) do
    if cpu then
        local cpu_name = (cpu == snes_cpu) and "snes" or "sa1"
        local mem_type = (cpu == snes_cpu) and emu.memType.snesMemory or emu.memType.sa1Memory

        local ok1, err1 = pcall(function()
            emu.addMemoryCallback(make_on_table_read(cpu_name), emu.callbackType.read,
                TABLE_CPU_BASE, TABLE_CPU_END, cpu, mem_type)
        end)
        log(string.format("DEBUG: table_read callback (%s, mem=%s): %s %s",
            cpu_name, (cpu == snes_cpu) and "snesMemory" or "sa1Memory",
            ok1 and "OK" or "FAIL", err1 or ""))

        local ok2, err2 = pcall(function()
            emu.addMemoryCallback(make_on_dp_write(cpu_name), emu.callbackType.write,
                0x000000, 0x0000FF, cpu, mem_type)
        end)
        log(string.format("DEBUG: dp_write callback (%s, mem=%s): %s %s",
            cpu_name, (cpu == snes_cpu) and "snesMemory" or "sa1Memory",
            ok2 and "OK" or "FAIL", err2 or ""))
    end
end

-- FIX #5: Use snesMemory (not snesRegister) for $420B callback
local ok3, err3 = pcall(function()
    emu.addMemoryCallback(on_dma_enable, emu.callbackType.write,
        DMA_ENABLE_REG, DMA_ENABLE_REG, snes_cpu, emu.memType.snesMemory)
end)
log(string.format("DEBUG: dma_enable callback: %s %s", ok3 and "OK" or "FAIL", err3 or ""))

-- FIX #6: Shadow VMADD by capturing writes to $2116/$2117
local ok4, err4 = pcall(function()
    emu.addMemoryCallback(on_vram_addr_write, emu.callbackType.write,
        0x2116, 0x2117, snes_cpu, emu.memType.snesMemory)
end)
log(string.format("DEBUG: vram_addr callback: %s %s", ok4 and "OK" or "FAIL", err4 or ""))

-- FIX #8: Shadow DMA channel registers $4300-$437F
local ok5, err5 = pcall(function()
    emu.addMemoryCallback(on_dma_reg_write, emu.callbackType.write,
        0x4300, 0x437F, snes_cpu, emu.memType.snesMemory)
end)
log(string.format("DEBUG: dma_reg callback: %s %s", ok5 and "OK" or "FAIL", err5 or ""))

emu.addEventCallback(on_frame, emu.eventType.endFrame)

log("")
log("Ready. Click on sprites!")
