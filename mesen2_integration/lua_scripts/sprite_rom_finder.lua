-- sprite_rom_finder.lua v34
-- Click on any sprite to get its ROM source offset
-- v33: Always-on automatic attribution mode
--
-- LEFT-CLICK on sprite = lookup ROM offset (topmost wins)
-- SCROLL UP/DOWN = cycle through candidates under cursor
-- RIGHT-CLICK = clear panel
-- SELECT = toggle HUD ignore (sprites with y < 32)
-- START = toggle bounding box debug overlay
-- R = toggle always-on sprite labels
-- X = cycle filter mode (ALL/NO_HUD/LARGE/MOVING)
-- LEFT/RIGHT = navigate sprites (logs attribution to console)
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
-- v23: pre-populate FE52 table at init, disable closest-session override, O(1) ptr->idx lookup
-- v24: hard enforcement - delete unmatched session path, sync ptr_to_idx in runtime, remove stale blanking
-- v25: DP slot tracking, slot-preference attribution, FE52 off-by-one fix, PPU edge clamp
-- v26: delayed activation (start after N frames), safe getState fallback
-- v27: crash guards for callbacks and on_frame (logs stack trace and disables tracking)
-- v28: safe vararg forwarding for crash-guard wrapper
-- v29: wider lookback + larger staging queue + last-session boundary
-- v31: optional unmatched sessions + session dedup
-- v32: reset hotkey + disable lookback for unmatched sessions
-- v33: always-on automatic attribution (R=labels, X=filter, LEFT/RIGHT=nav, auto-watch)

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
local OFFSET_FILE = OUTPUT_DIR .. "last_offset.txt"  -- Simple file for SpritePal to watch

local ROM_HEADER = 0  -- Set to 0x200 if your .sfc has a copier header

local log_handle = nil
local frame_count = 0
local tracking_active = false
local callbacks_registered = false
local fatal_error = nil

local function log(msg)
    if not log_handle then
        log_handle = io.open(LOG_FILE, "a")  -- Append mode to preserve history
    end
    if log_handle then
        log_handle:write(msg .. "\n")
        log_handle:flush()
    end
    emu.log(msg)
end

-- Write offset to a simple file for SpritePal integration
local function write_offset_file(offset, frame)
    local f = io.open(OFFSET_FILE, "w")
    if f then
        f:write(string.format("FILE OFFSET: 0x%06X\n", offset))
        f:write(string.format("frame=%d\n", frame or 0))
        f:write(string.format("timestamp=%d\n", os.time()))
        f:close()
    end
end

local function log_fatal(context, err)
    if fatal_error then return end
    fatal_error = err or "unknown error"
    tracking_active = false
    log(string.format("FATAL(%s): %s", context, tostring(fatal_error)))
end

local function unpack_args(args, i, n)
    if i > n then return end
    return args[i], unpack_args(args, i + 1, n)
end

local function call_with_args(cb, args, n)
    if table.unpack then
        return cb(table.unpack(args, 1, n))
    end
    return cb(unpack_args(args, 1, n))
end

local function make_safe_callback(cb, name)
    return function(...)
        if fatal_error then return nil end
        local args = { ... }
        local argc = select("#", ...)
        local ok, err = xpcall(function() return call_with_args(cb, args, argc) end, debug.traceback)
        if not ok then
            log_fatal(name, err)
        end
        return nil
    end
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

-- v34 FIX: Shadow OBSEL ($2101) - declared early so get_sprite_info() can access it
-- Default to $03 (name base=$6000) which is common for Kirby sprite VRAM
local obsel_shadow = 0x03
local oam_base_shadow = 0
local oam_offset_shadow = 0

local function update_oam_from_obsel(value)
    obsel_shadow = value & 0xFF
    local name_base_bits = obsel_shadow & 7
    oam_base_shadow = name_base_bits * 0x2000
    local name_select_bits = (obsel_shadow >> 3) & 3
    oam_offset_shadow = (name_select_bits + 1) * 0x1000
end

update_oam_from_obsel(obsel_shadow)

local function resolve_oam_tables(state)
    local oam_base = state and state["snes.ppu.OamBaseAddress"]
    local oam_offset = state and state["snes.ppu.OamAddressOffset"]
    if oam_base ~= nil and oam_offset ~= nil and oam_offset ~= 0 then
        return oam_base, oam_offset, "state"
    end
    return oam_base_shadow, oam_offset_shadow, "shadow"
end

local function sync_oam_from_state(state)
    local oam_base = state and state["snes.ppu.OamBaseAddress"]
    local oam_offset = state and state["snes.ppu.OamAddressOffset"]
    if oam_base ~= nil and oam_offset ~= nil and oam_offset ~= 0 then
        oam_base_shadow = oam_base
        oam_offset_shadow = oam_offset
        return true
    end
    return false
end

local function get_sprite_info(index)
    local base = index * 4

    local x_low = emu.read(base, emu.memType.snesSpriteRam)
    local y = emu.read(base + 1, emu.memType.snesSpriteRam)
    local tile = emu.read(base + 2, emu.memType.snesSpriteRam)
    local attr = emu.read(base + 3, emu.memType.snesSpriteRam)

    local high_offset = 0x200 + math.floor(index / 4)
    local high_byte = emu.read(high_offset, emu.memType.snesSpriteRam)
    if x_low == nil or y == nil or tile == nil or attr == nil or high_byte == nil then
        return nil
    end
    local shift = (index % 4) * 2
    local x_high = (high_byte >> shift) & 1
    local large = ((high_byte >> shift) >> 1) & 1

    local x = x_low + (x_high * 256)
    if x >= 256 then x = x - 512 end

    local state = emu.getState() or {}
    -- v19 FIX: Capital letters (Mesen2 serializes OamMode, not oamMode)
    local oam_mode = state["snes.ppu.OamMode"] or 0
    local size_table = oam_sizes[oam_mode] or oam_sizes[0]
    local size = size_table[large + 1]

    -- Prefer PPU state (captures pre-activation writes); fall back to OBSEL shadow.
    local oam_base, oam_offset = resolve_oam_tables(state)

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
    local state = emu.getState() or {}
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
-- DP pointer cache slots (lo/hi/bank), see docs/mesen2/03_GAME_MAPPING_KIRBY_SA1.md
local DP_PTR_SLOTS = {0x0002, 0x0005, 0x0008}
local DP_PTR_SLOT_SIZE = 3

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

local DP_PTR_SLOT_BY_OFFSET = {}
for _, base in ipairs(DP_PTR_SLOTS) do
    for i = 0, DP_PTR_SLOT_SIZE - 1 do
        DP_PTR_SLOT_BY_OFFSET[base + i] = base
    end
end

--------------------------------------------------------------------------------
-- v19: TUNEABLE PARAMETERS
-- Adjust these if attribution fails for long-loading sprites or non-Kirby games
--------------------------------------------------------------------------------
local RECENT_SESSIONS_MAX = 64   -- Max sessions in queue (increase for busy games)
local SESSION_MATCH_WINDOW = 45  -- Frames to match DMA to session (increase for slow decode)
local ALLOW_UNMATCHED_DP_PTR = true  -- Allow sessions for valid DP ptrs not in FE52 table
local CLICK_PREFER_CLOSEST_SESSION = false   -- v23: Use only direct vram_owner_map attribution
local CLICK_SESSION_WINDOW = 60              -- Frames around DMA to search for nearest session
local PREFER_IDX_KNOWN_SESSIONS = true       -- Prefer idx-known sessions over unmatched
local CLICK_SESSION_ONLY_BEFORE_DMA = true   -- Do not override with sessions after DMA
local MAX_DMA_AGE = 0                        -- Max age (frames) for click attribution; 0 disables
local RECENT_STAGING_MAX = 512   -- Max staging DMAs to track (increase if queue overflows)
local LOOKBACK_WINDOW = 90       -- Frames to look back at session start (raise for slow decode)
local LOOKBACK_REQUIRE_SINCE_LAST_SESSION = true  -- Avoid attributing DMAs from earlier sessions
local LOOKBACK_ALLOW_UNMATCHED = false  -- If false, unmatched sessions won't claim lookback DMAs
local SESSION_DEDUP_WINDOW = 4   -- Skip duplicate ptr sessions within N frames (0 disables)
local ACTIVATE_AT_FRAME = 500    -- Delay tracking/UI until this frame (0 = immediate)

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
local vram_watch_set = {}        -- v33: Key: vram_word, Value: {first_seen, count} - for auto-watch
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
    -- v25: Fix off-by-one - last valid entry must fit entirely within table bounds
    local bytes = (TABLE_CPU_END - TABLE_CPU_BASE + 1)
    local max_idx = math.floor(bytes / ENTRY_SIZE) - 1
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

-- v33: Register a VRAM word for auto-watch (when unresolved sprite uses it)
local function register_vram_watch(vram_word)
    if not vram_watch_set[vram_word] then
        vram_watch_set[vram_word] = {
            first_seen = frame_count,
            count = 1,
        }
    else
        vram_watch_set[vram_word].count = vram_watch_set[vram_word].count + 1
    end
end

-- v11: Helper to write attribution to vram_owner_map for a DMA entry
-- v33: Also checks vram_watch_set and logs when watched VRAM is resolved
local function write_vram_attribution(entry, idx, ptr, file_off)
    local words = entry.vram_words
    if words then
        for _, w in ipairs(words) do
            -- v33: Check if this VRAM word was being watched
            if vram_watch_set[w] then
                local watch = vram_watch_set[w]
                log(string.format("WATCH RESOLVED: VRAM $%04X -> idx=%s ptr=%s FILE=0x%06X (watched since f%d, seen %dx)",
                    w, idx ~= nil and tostring(idx) or "?", fmt_addr(ptr), file_off or 0,
                    watch.first_seen, watch.count))
                vram_watch_set[w] = nil  -- Clear watch
            end

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
        return
    end

    for w = entry.vram_start, entry.vram_end - 1 do
        -- v33: Check if this VRAM word was being watched
        if vram_watch_set[w] then
            local watch = vram_watch_set[w]
            log(string.format("WATCH RESOLVED: VRAM $%04X -> idx=%s ptr=%s FILE=0x%06X (watched since f%d, seen %dx)",
                w, idx ~= nil and tostring(idx) or "?", fmt_addr(ptr), file_off or 0,
                watch.first_seen, watch.count))
            vram_watch_set[w] = nil  -- Clear watch
        end

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

local function start_session(ptr, idx, enable_lookback, slot_base, cpu_name)
    if idx == nil and not LOOKBACK_ALLOW_UNMATCHED then
        enable_lookback = false
    end
    if SESSION_DEDUP_WINDOW > 0 then
        local last = recent_sessions[#recent_sessions]
        if last and last.ptr == ptr and (frame_count - last.frame) <= SESSION_DEDUP_WINDOW then
            return
        end
    end
    session_counter = session_counter + 1
    stats.sessions_started = stats.sessions_started + 1
    local idx_str = idx ~= nil and tostring(idx) or "?"
    local slot_str = slot_base and string.format(" slot=%04X", slot_base) or ""
    local cpu_str = cpu_name and string.format(" cpu=%s", cpu_name) or ""
    log(string.format("DBG START_SESSION idx=%s ptr=%s frame=%d%s%s",
        idx_str, fmt_addr(ptr), frame_count, slot_str, cpu_str))
    table.insert(recent_sessions, {
        id = session_counter,
        ptr = ptr,
        idx = idx,
        frame = frame_count,
        idx_known = (idx ~= nil),
        slot = slot_base,
        cpu = cpu_name,
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
    local prev_session_frame = nil
    if LOOKBACK_REQUIRE_SINCE_LAST_SESSION and #recent_sessions >= 2 then
        prev_session_frame = recent_sessions[#recent_sessions - 1].frame
    end
    for i, dma in ipairs(recent_staging_dmas) do
        local age = frame_count - dma.frame
        if age >= 0 and age <= LOOKBACK_WINDOW then
            -- Only attribute if not already attributed
            if not dma.attributed and (not prev_session_frame or dma.frame > prev_session_frame) then
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

-- v25: Slot preference for forward attribution (0x0002 = canonical DP cache, beats 0x0005/0x0008)
-- When multiple pointers complete near each other, prefer the primary slot
local SLOT_RANK = { [0x0002] = 1, [0x0005] = 2, [0x0008] = 3 }

-- Pick best session within window (prefer primary slot, then idx_known, then most recent)
local function match_recent_session()
    local best = nil
    local best_rank = 999
    for i = #recent_sessions, 1, -1 do
        local s = recent_sessions[i]
        local age = frame_count - s.frame
        if age > SESSION_MATCH_WINDOW then
            -- older than window; list is chronological, stop early
            break
        end

        -- v25: Rank by slot preference (lower = better)
        local rank = SLOT_RANK[s.slot] or 999
        if s.idx_known and rank < best_rank then
            best = s
            best_rank = rank
            -- Short-circuit: if we found primary slot with known idx, can't do better
            if best_rank == 1 then return best end
        elseif not best then
            -- Fallback to any session if none with known idx yet
            best = s
        end
    end
    return best
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
        if not tracking_active then return nil end
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
                ptr_to_idx[ptr] = idx  -- v24: Keep reverse map in sync
            end
            pending_tbl[key] = nil
        end
        return nil
    end
end

-- FIX #2: Only match bank 00, address < 0x100 for DP writes
local function make_on_dp_write(cpu_name)
    return function(addr, value)
        if not tracking_active then return nil end
        local bank = (addr >> 16) & 0xFF
        local lo = addr & 0xFFFF

        -- Must be bank 00 and in direct page range
        if bank ~= 0x00 then return nil end
        if lo > 0x00FF then return nil end

        local offset = lo
        local slot_base = DP_PTR_SLOT_BY_OFFSET[offset]
        if not slot_base then return nil end

        if not pending_dp[cpu_name] then pending_dp[cpu_name] = {} end
        local pending_slots = pending_dp[cpu_name]
        if not pending_slots[slot_base] then pending_slots[slot_base] = {} end
        local pending = pending_slots[slot_base]
        local byte_pos = offset - slot_base

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
                log(string.format("DBG DP ptr complete: slot=%04X %02X:%04X frame=%d cpu=%s",
                    slot_base, pending.bank, pending.hi * 256 + pending.lo, frame_count, cpu_name))

                if is_valid_ptr(ptr) then
                    local matched_idx = ptr_to_idx[ptr]  -- v23: O(1) lookup
                    if matched_idx then
                        start_session(ptr, matched_idx, true, slot_base, cpu_name)
                    elseif ALLOW_UNMATCHED_DP_PTR then
                        start_session(ptr, nil, true, slot_base, cpu_name)
                    else
                        -- v24: Log-only, never start session for unmatched pointers
                        log(string.format("DBG DP ptr %s valid but no idx match", fmt_addr(ptr)))
                    end
                else
                    log(string.format("DBG DP ptr %s rejected as invalid", fmt_addr(ptr)))
                end
                pending_slots[slot_base] = {}
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
local vram_addr_logical = 0
local vram_addr_shadow = 0

-- v34 FIX: Callback to shadow OBSEL ($2101) writes - register is write-only
-- (obsel_shadow variable declared earlier near get_sprite_info)
local function on_obsel_write(address, value)
    if not tracking_active then return end
    update_oam_from_obsel(value)
    -- Log only on changes (uncomment for debug)
    -- log(string.format("OBSEL write: $%02X -> base=$%04X", obsel_shadow, (obsel_shadow & 7) * 0x2000))
end

-- VMAIN ($2115) controls VRAM increment and address remapping (matches SnesPpu::GetVramAddress)
local vmain_shadow = 0x00
local vram_increment_value = 1
local vram_remap_mode = 0
local vram_increment_on_second = false

local function update_vmain_shadow(value)
    vmain_shadow = value & 0xFF
    local step = vmain_shadow & 0x03
    if step == 0 then
        vram_increment_value = 1
    elseif step == 1 then
        vram_increment_value = 32
    else
        vram_increment_value = 128
    end
    vram_remap_mode = (vmain_shadow >> 2) & 0x03
    vram_increment_on_second = (vmain_shadow & 0x80) ~= 0
end

local function apply_vram_remap(addr)
    addr = addr & 0x7FFF
    if vram_remap_mode == 0 then
        return addr
    end
    if vram_remap_mode == 1 then
        return (addr & 0xFF00) | ((addr & 0xE0) >> 5) | ((addr & 0x1F) << 3)
    end
    if vram_remap_mode == 2 then
        return (addr & 0xFE00) | ((addr & 0x1C0) >> 6) | ((addr & 0x3F) << 3)
    end
    return (addr & 0xFC00) | ((addr & 0x380) >> 7) | ((addr & 0x7F) << 3)
end

local function on_vmain_write(address, value)
    if not tracking_active then return end
    update_vmain_shadow(value)
    -- Remap current VMADD after VMAIN changes.
    vram_addr_shadow = apply_vram_remap(vram_addr_logical)
end

local function on_vram_addr_write(address, value)
    if not tracking_active then return end
    -- Capture the WRITTEN value, not a readback
    if address == 0x2116 then
        vmadd_lo = value & 0xFF
    else -- 0x2117
        vmadd_hi = value & 0xFF
    end
    -- Mask to 15-bit VRAM address space (0x0000-0x7FFF)
    vram_addr_logical = (vmadd_lo + (vmadd_hi * 256)) & 0x7FFF
    vram_addr_shadow = apply_vram_remap(vram_addr_logical)
end

local function sync_ppu_vram_state(state)
    if not state then return end
    local addr = state["snes.ppu.VramAddress"]
    if addr ~= nil then
        vram_addr_logical = addr & 0x7FFF
    end
    local inc = state["snes.ppu.VramIncrementValue"]
    if inc ~= nil and inc ~= 0 then
        vram_increment_value = inc
    end
    local remap = state["snes.ppu.VramAddressRemapping"]
    if remap ~= nil then
        vram_remap_mode = remap & 0x03
    end
    local inc_second = state["snes.ppu.VramAddrIncrementOnSecondReg"]
    if inc_second ~= nil then
        vram_increment_on_second = inc_second
    end
    vram_addr_shadow = apply_vram_remap(vram_addr_logical)
end

-- FIX #8: Shadow DMA channel registers (post-DMA reads return garbage)
local dma_shadow = {}
for ch = 0, 7 do
    dma_shadow[ch] = { dmap=0, bbad=0, a1tl=0, a1th=0, a1tb=0, dasl=0, dash=0 }
end

local function on_dma_reg_write(address, value)
    if not tracking_active then return end
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

local function map_dma_vram_words(entry, start_logical, word_count, increment)
    local inc = increment or 1
    if inc == 0 then inc = 1 end
    entry.vram_logical_start = start_logical
    entry.vram_logical_end = (start_logical + (word_count * inc)) & 0x7FFF

    if vram_remap_mode == 0 and inc == 1 then
        entry.vram_start = start_logical
        entry.vram_end = start_logical + word_count
        for w = entry.vram_start, entry.vram_end - 1 do
            vram_upload_map[w] = entry
        end
        return entry.vram_logical_end
    end

    entry.vram_words = {}
    local min_addr = 0x7FFF
    local max_addr = 0
    local logical = start_logical
    for i = 1, word_count do
        local physical = apply_vram_remap(logical)
        entry.vram_words[i] = physical
        if physical < min_addr then min_addr = physical end
        if physical > max_addr then max_addr = physical end
        vram_upload_map[physical] = entry
        logical = (logical + inc) & 0x7FFF
    end
    entry.vram_start = min_addr
    entry.vram_end = max_addr + 1
    return entry.vram_logical_end
end

local function on_dma_enable(addr, value)
    if not tracking_active then return nil end
    -- FIX #8: Handle nil value (Mesen may pass nil sometimes)
    local enable = value
    if enable == nil then
        enable = emu.read(0x420B, emu.memType.snesMemory) or 0
    end
    enable = enable & 0xFF
    if enable == 0 then return nil end

    -- Ensure VMAIN/VMADD shadow matches current PPU state before DMA starts.
    sync_ppu_vram_state(emu.getState() or {})

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
    local local_vram_logical = vram_addr_logical
    local vram_increment = vram_increment_value
    if not vram_increment or vram_increment == 0 then vram_increment = 1 end

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

                local words_transferred = math.ceil(dma_size / 2)
                local_vram_logical = map_dma_vram_words(entry, local_vram_logical, words_transferred, vram_increment)

                -- DEBUG: Log ALL DMAs (every 60 frames) to see what VRAM ranges are being written
                if frame_count % 60 == 0 then
                    log(string.format("DEBUG DMA: VRAM $%04X-$%04X src=%06X stg=%s idx=%s",
                        entry.vram_start, entry.vram_end - 1, src_addr,
                        is_staging and "Y" or "N", session_idx or "?"))
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

                -- v16: local_vram_logical already advanced by map_dma_vram_words()
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
local prev_key_l = false              -- Reset tracking hotkey (L)

-- v15: HUD ignore toggle
local hud_ignore_enabled = true
local HUD_Y_THRESHOLD = 32            -- Ignore sprites with y < this

-- v15: Bounding box debug overlay
local show_oam_boxes = false
local screen_height = 224

-- v33: Always-on sprite labels
local show_sprite_labels = false
-- Note: vram_watch_set is declared earlier (line 312) for Lua scoping
local labeled_count = 0         -- Sprites with attribution this frame
local unresolved_count = 0      -- Sprites without attribution this frame

-- v34: Sprite clustering with velocity
local CLUSTER_DISTANCE = 24     -- Max pixels between sprites to cluster
local CLUSTER_VEL_TOL = 2       -- Max velocity difference (pixels/frame) to cluster
local CLUSTER_MIN_SIZE = 1      -- Min sprites per cluster (set 2 to hide singletons)
local VELOCITY_HISTORY = 5      -- Frames to smooth velocity calculation
local sprite_clusters = {}      -- Updated each frame when labels enabled
local sprite_history = {}       -- [oam_idx] = { positions = {{x,y,frame},...}, vx=0, vy=0 }

-- v33: Filter modes for labels
local FILTER_MODES = { ALL = 1, NO_HUD = 2, LARGE_ONLY = 3, MOVING = 4 }
local current_filter_mode = FILTER_MODES.NO_HUD

-- v33: Keyboard navigation for sprite selection
local selected_sprite_idx = 0   -- Currently selected sprite for info panel

local function clamp_rect(x, y, w, h)
    local x1 = math.max(0, x)
    local y1 = math.max(0, y)
    local x2 = math.min(255, x + w - 1)
    local y2 = math.min(screen_height - 1, y + h - 1)
    local cw = x2 - x1 + 1
    local ch = y2 - y1 + 1
    if cw <= 0 or ch <= 0 then return nil end
    return x1, y1, cw, ch
end

local function draw_rect_safe(x, y, w, h, color, filled)
    local cx, cy, cw, ch = clamp_rect(x, y, w, h)
    if not cx then return end
    emu.drawRectangle(cx, cy, cw, ch, color, filled)
end

local function draw_text_safe(x, y, text, color, bg)
    if x < 0 or y < 0 or x > 255 or y > (screen_height - 1) then
        return
    end
    emu.drawString(x, y, text, color, bg or 0x00000000)
end

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
    if mouse.x >= 0 and mouse.x < 256 and mouse.y >= 0 and mouse.y < screen_height then
        emu.drawLine(mouse.x - 5, mouse.y, mouse.x + 5, mouse.y, 0xFFFFFFFF)
        emu.drawLine(mouse.x, mouse.y - 5, mouse.x, mouse.y + 5, 0xFFFFFFFF)
    end
end

-- v22: Convert mouse coords to PPU space using normalized relativeX/relativeY
-- This bypasses any overscan offset issues with mouse.x/y
local function get_ppu_coords(mouse)
    if mouse.relativeX and mouse.relativeX >= 0 then
        local state = emu.getState() or {}
        local overscan = state["snes.ppu.OverscanMode"]
        local ppu_height = overscan and 239 or 224
        local ppu_width = 256

        local ppu_x = math.floor(mouse.relativeX * ppu_width)
        local ppu_y = math.floor(mouse.relativeY * ppu_height)

        -- v25: Clamp to valid range (relativeX/Y=1.0 can produce out-of-bounds)
        ppu_x = math.min(ppu_x, ppu_width - 1)
        ppu_y = math.min(ppu_y, ppu_height - 1)

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
    local state = emu.getState() or {}
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
        if spr and is_visible(spr) and point_in_sprite(spr, mouse.x, mouse.y) then
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
        if spr and is_visible(spr) then
            -- Color code: cyan for normal, gray for HUD-filtered
            local color = 0x80FFFF00  -- Semi-transparent cyan
            if hud_ignore_enabled and spr.y < HUD_Y_THRESHOLD then
                color = 0x40808080    -- Dimmed gray for ignored HUD sprites
            end
            draw_rect_safe(spr.x, spr.y, spr.width, spr.height, color, false)
            draw_text_safe(spr.x + 1, spr.y + 1, tostring(spr.index), 0xFFFFFF, 0x80000000)
        end
    end
end

-- v33: Check if sprite is moving (changed position in last 30 frames)
local function is_moving(spr)
    local prev = sprite_positions[spr.index]
    if not prev then
        sprite_positions[spr.index] = {x = spr.x, y = spr.y, last_moved = frame_count}
        return true  -- New sprite counts as moving
    end
    if prev.x ~= spr.x or prev.y ~= spr.y then
        sprite_positions[spr.index] = {x = spr.x, y = spr.y, last_moved = frame_count}
        return true
    end
    return (frame_count - prev.last_moved) < 30
end

-- v33: Check if sprite passes current filter
local function passes_filter(spr)
    if current_filter_mode == FILTER_MODES.ALL then
        return true
    elseif current_filter_mode == FILTER_MODES.NO_HUD then
        return spr.y >= HUD_Y_THRESHOLD
    elseif current_filter_mode == FILTER_MODES.LARGE_ONLY then
        return spr.width > 8 or spr.height > 8
    elseif current_filter_mode == FILTER_MODES.MOVING then
        return is_moving(spr)
    end
    return true
end

-- v34: Update sprite position/velocity history
local function update_sprite_history()
    for i = 0, 127 do
        local spr = get_sprite_info(i)
        if spr and is_visible(spr) then
            local hist = sprite_history[i] or { positions = {}, vx = 0, vy = 0 }

            -- Add current position
            table.insert(hist.positions, { x = spr.x, y = spr.y, frame = frame_count })

            -- Keep last VELOCITY_HISTORY frames
            while #hist.positions > VELOCITY_HISTORY do
                table.remove(hist.positions, 1)
            end

            -- Calculate velocity from oldest to newest
            if #hist.positions >= 2 then
                local oldest = hist.positions[1]
                local newest = hist.positions[#hist.positions]
                local dt = newest.frame - oldest.frame
                if dt > 0 then
                    hist.vx = (newest.x - oldest.x) / dt
                    hist.vy = (newest.y - oldest.y) / dt
                end
            end

            sprite_history[i] = hist
        else
            sprite_history[i] = nil  -- Clear history for invisible sprites
        end
    end
end

-- v34: Build clusters of sprites by proximity AND velocity
local function build_sprite_clusters()
    update_sprite_history()  -- Update velocities first

    local visible = {}
    for i = 0, 127 do
        local spr = get_sprite_info(i)
        if spr and is_visible(spr) and passes_filter(spr) then
            -- Attach velocity to sprite for clustering
            local hist = sprite_history[i] or { vx = 0, vy = 0 }
            spr.vx = hist.vx
            spr.vy = hist.vy
            table.insert(visible, spr)
        end
    end

    -- Proximity + velocity clustering
    local clusters = {}
    local assigned = {}

    for _, spr in ipairs(visible) do
        if not assigned[spr.index] then
            local cluster = {spr}
            assigned[spr.index] = true

            -- Find all unassigned sprites within distance AND similar velocity
            for _, other in ipairs(visible) do
                if not assigned[other.index] then
                    local dx = math.abs(spr.x - other.x)
                    local dy = math.abs(spr.y - other.y)
                    local dvx = math.abs(spr.vx - other.vx)
                    local dvy = math.abs(spr.vy - other.vy)

                    -- Must be close AND moving similarly
                    if dx <= CLUSTER_DISTANCE and dy <= CLUSTER_DISTANCE and
                       dvx <= CLUSTER_VEL_TOL and dvy <= CLUSTER_VEL_TOL then
                        table.insert(cluster, other)
                        assigned[other.index] = true
                    end
                end
            end

            -- Filter by minimum cluster size
            if #cluster >= CLUSTER_MIN_SIZE then
                table.insert(clusters, cluster)
            end
        end
    end

    sprite_clusters = clusters
end

-- v33: Get cluster attribution (best idx from any member)
-- Uses lookup_vram_source() for consistency with click-based lookup
-- Checks multiple tiles per sprite (16x16 = 4 tiles, 32x32 = 16 tiles, etc.)
local function get_cluster_attribution(cluster)
    local best_result = nil
    for _, spr in ipairs(cluster) do
        -- Calculate how many tiles this sprite uses
        local tiles_wide = spr.width / 8
        local tiles_tall = spr.height / 8

        -- Check each tile in the sprite
        for ty = 0, tiles_tall - 1 do
            for tx = 0, tiles_wide - 1 do
                -- SNES OAM tiles are arranged in 16x16 blocks (4 tiles)
                -- Tile index = base + (row * 16) + col
                local tile_offset = (ty * 16 + tx) * 16  -- 16 words per tile
                local tile_vram = (spr.vram_addr + tile_offset) & 0x7FFF

                local result = lookup_vram_source(tile_vram)
                if result.found then
                    local result_has_attrib = result.file_offset ~= nil or result.idx ~= nil
                    local best_has_attrib = best_result and (best_result.file_offset ~= nil or best_result.idx ~= nil)
                    if not best_result then
                        best_result = result
                    elseif result_has_attrib and not best_has_attrib then
                        best_result = result
                    elseif result_has_attrib == best_has_attrib then
                        if result.upload_frame and best_result.upload_frame and result.upload_frame > best_result.upload_frame then
                            best_result = result
                        end
                    end
                end
            end
        end
    end
    return best_result
end

-- v33: Get cluster centroid
local function get_cluster_centroid(cluster)
    local sum_x, sum_y = 0, 0
    for _, spr in ipairs(cluster) do
        sum_x = sum_x + spr.x + spr.width / 2
        sum_y = sum_y + spr.y + spr.height / 2
    end
    return math.floor(sum_x / #cluster), math.floor(sum_y / #cluster)
end

-- v34: Draw bounding boxes around sprite clusters
local function draw_cluster_boxes()
    if not show_sprite_labels then return end

    for _, cluster in ipairs(sprite_clusters) do
        -- Calculate cluster bounding box
        local min_x, min_y = 999, 999
        local max_x, max_y = -999, -999

        for _, spr in ipairs(cluster) do
            min_x = math.min(min_x, spr.x)
            min_y = math.min(min_y, spr.y)
            max_x = math.max(max_x, spr.x + spr.width)
            max_y = math.max(max_y, spr.y + spr.height)
        end

        -- Determine color based on attribution
        local result = get_cluster_attribution(cluster)
        local color = 0xFF0000  -- Red = unresolved
        if result and (result.file_offset ~= nil or result.idx ~= nil) then
            color = 0x00FF00  -- Green = attributed
        elseif result and result.found then
            color = 0xFFFF00  -- Yellow = DMA found but no idx
        end

        -- Draw box (skip if bounds are invalid)
        if min_x < max_x and min_y < max_y then
            draw_rect_safe(min_x, min_y, max_x - min_x, max_y - min_y, color, false)
        end
    end
end

-- v34: Draw always-on sprite labels (FILE offset or ? for unresolved)
local function draw_sprite_labels()
    if not show_sprite_labels then return end

    -- Build clusters first
    build_sprite_clusters()

    labeled_count = 0
    unresolved_count = 0

    -- Draw boxes first (underneath labels)
    draw_cluster_boxes()

    for _, cluster in ipairs(sprite_clusters) do
        local result = get_cluster_attribution(cluster)
        local cx, cy = get_cluster_centroid(cluster)

        if result and (result.file_offset ~= nil or result.idx ~= nil) then
            -- Attributed: show FILE offset in green (or idx if no file_offset)
            local label
            if result.file_offset then
                label = string.format("%X", result.file_offset)  -- e.g., "3C6EF1"
            else
                label = tostring(result.idx)
            end
            draw_text_safe(cx - 4, cy - 12, label, 0x00FF00, 0x80000000)
            labeled_count = labeled_count + 1
        elseif result and result.found then
            -- Found DMA but no idx attribution: show "~" in yellow
            draw_text_safe(cx - 2, cy - 12, "~", 0xFFFF00, 0x80000000)
            unresolved_count = unresolved_count + 1
            for _, spr in ipairs(cluster) do
                register_vram_watch(spr.vram_addr)
            end
        else
            -- No DMA found at all: show "?" in red
            draw_text_safe(cx - 2, cy - 12, "?", 0xFF0000, 0x80000000)
            unresolved_count = unresolved_count + 1
            for _, spr in ipairs(cluster) do
                register_vram_watch(spr.vram_addr)
            end
            -- DEBUG: Log unresolved sprite VRAM addresses (once per cluster per 60 frames)
            if frame_count % 60 == 0 and #cluster > 0 then
                local spr = cluster[1]
                log(string.format("DEBUG unresolved: OAM#%d VRAM=$%04X base=$%04X tile=%d (%d,%d)",
                    spr.index, spr.vram_addr, spr.oam_base or 0,
                    spr.tile or 0, spr.x, spr.y))
            end
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
            draw_rect_safe(spr.x, spr.y, spr.width, spr.height, 0xFFFFFF00, false)
            draw_text_safe(spr.x, spr.y - 8, string.format("#%d", spr.index), 0xFFFFFF, 0x80000000)
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
        if spr and is_visible(spr) then visible_count = visible_count + 1 end
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
    -- v33: Label and watch counters
    if show_sprite_labels then
        local watch_count = 0
        for _ in pairs(vram_watch_set) do watch_count = watch_count + 1 end
        emu.drawString(170, 67, string.format("lbl:%d/%d", labeled_count, labeled_count + unresolved_count), 0xFFFF00, 0x00000000)
        emu.drawString(170, 76, string.format("wtc:%d", watch_count), 0xFF8800, 0x00000000)
    end
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
    -- v24: Removed stale blanking - age is not invalidation (attribution is still causal)

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
            -- v24: Just informational, doesn't affect attribution
            log(string.format("NOTE: upload age (%d) exceeds MAX_DMA_AGE (%d) - tile reused from old upload", upload_age, MAX_DMA_AGE))
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
                -- Write to simple file for SpritePal integration
                write_offset_file(display_file_offset, frame_count)
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
-- v33: New key state for labels, filter, navigation
local prev_key_r = false
local prev_key_x = false
local prev_key_left = false
local prev_key_right = false

local function activate_tracking()
    if tracking_active then return end
    tracking_active = true

    if not callbacks_registered then
        callbacks_registered = true
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
                    emu.addMemoryCallback(make_safe_callback(make_on_table_read(cpu_name), "table_read:" .. cpu_name),
                        emu.callbackType.read,
                        TABLE_CPU_BASE, TABLE_CPU_END, cpu, mem_type)
                end)
                log(string.format("DEBUG: table_read callback (%s, mem=%s): %s %s",
                    cpu_name, (cpu == snes_cpu) and "snesMemory" or "sa1Memory",
                    ok1 and "OK" or "FAIL", err1 or ""))

                local ok2, err2 = pcall(function()
                    emu.addMemoryCallback(make_safe_callback(make_on_dp_write(cpu_name), "dp_write:" .. cpu_name),
                        emu.callbackType.write,
                        0x000000, 0x0000FF, cpu, mem_type)
                end)
                log(string.format("DEBUG: dp_write callback (%s, mem=%s): %s %s",
                    cpu_name, (cpu == snes_cpu) and "snesMemory" or "sa1Memory",
                    ok2 and "OK" or "FAIL", err2 or ""))
            end
        end

        -- FIX #5: Use snesMemory (not snesRegister) for $420B callback
        local ok3, err3 = pcall(function()
            emu.addMemoryCallback(make_safe_callback(on_dma_enable, "dma_enable"), emu.callbackType.write,
                DMA_ENABLE_REG, DMA_ENABLE_REG, snes_cpu, emu.memType.snesMemory)
        end)
        log(string.format("DEBUG: dma_enable callback: %s %s", ok3 and "OK" or "FAIL", err3 or ""))

        -- FIX #6: Shadow VMADD by capturing writes to $2116/$2117
        local ok4, err4 = pcall(function()
            emu.addMemoryCallback(make_safe_callback(on_vram_addr_write, "vram_addr"), emu.callbackType.write,
                0x2116, 0x2117, snes_cpu, emu.memType.snesMemory)
        end)
        log(string.format("DEBUG: vram_addr callback: %s %s", ok4 and "OK" or "FAIL", err4 or ""))

        -- v34: Shadow VMAIN ($2115) to track remap/increment behavior
        local ok5, err5 = pcall(function()
            emu.addMemoryCallback(make_safe_callback(on_vmain_write, "vmain"), emu.callbackType.write,
                0x2115, 0x2115, snes_cpu, emu.memType.snesMemory)
        end)
        log(string.format("DEBUG: vmain callback: %s %s", ok5 and "OK" or "FAIL", err5 or ""))

        -- FIX #8: Shadow DMA channel registers $4300-$437F
        local ok6, err6 = pcall(function()
            emu.addMemoryCallback(make_safe_callback(on_dma_reg_write, "dma_reg"), emu.callbackType.write,
                0x4300, 0x437F, snes_cpu, emu.memType.snesMemory)
        end)
        log(string.format("DEBUG: dma_reg callback: %s %s", ok6 and "OK" or "FAIL", err6 or ""))

        -- v34 FIX: Shadow OBSEL ($2101) writes - register is write-only
        local ok7, err7 = pcall(function()
            emu.addMemoryCallback(make_safe_callback(on_obsel_write, "obsel"), emu.callbackType.write,
                0x2101, 0x2101, snes_cpu, emu.memType.snesMemory)
        end)
        log(string.format("DEBUG: obsel callback: %s %s", ok7 and "OK" or "FAIL", err7 or ""))
    end

    local state = emu.getState() or {}
    local oam_from_state = sync_oam_from_state(state)
    sync_ppu_vram_state(state)

    log(string.format("Activated at frame %d", frame_count))

    local oam_source = oam_from_state and "state" or "shadow"
    log(string.format("OAM tables (%s): base=$%04X offset=$%04X (obsel=$%02X)",
        oam_source, oam_base_shadow, oam_offset_shadow, obsel_shadow))
    log(string.format("VMAIN: remap=%d inc=%d inc_on_second=%s",
        vram_remap_mode, vram_increment_value, tostring(vram_increment_on_second)))

    log("Ready. Click on sprites! Press R to toggle always-on labels.")
end

local function on_frame()
    frame_count = frame_count + 1

    if not tracking_active then
        if ACTIVATE_AT_FRAME <= 0 or frame_count >= ACTIVATE_AT_FRAME then
            activate_tracking()
        elseif (frame_count % 60) == 0 then
            log(string.format("Waiting for activation: frame %d/%d", frame_count, ACTIVATE_AT_FRAME))
        end
        return
    end

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
    if not mouse then
        if (frame_count % 60) == 0 then
            log("WARN: mouse state unavailable")
        end
        mouse = { x = -1, y = -1, left = false, right = false }
    end

    -- v22: Convert to PPU coordinates FIRST (using normalized relativeX/relativeY)
    local ppu_x, ppu_y, coord_debug = get_ppu_coords(mouse)
    if coord_debug and coord_debug.ppu_height then
        screen_height = coord_debug.ppu_height
    end
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

    -- L key clears attribution/session history (forces fresh capture)
    local key_l = input.l or false
    if key_l and not prev_key_l then
        vram_upload_map = {}
        vram_owner_map = {}
        recent_staging_dmas = {}
        recent_sessions = {}
        session_counter = 0
        stats.staging_dmas = 0
        stats.staging_attrib = 0
        stats.lookback_attrib = 0
        selected_result = nil
        -- v33: Also clear watch set and position tracking
        vram_watch_set = {}
        sprite_positions = {}
        log(string.format("RESET: cleared history at frame %d", frame_count))
    end
    prev_key_l = key_l

    -- v33: R key toggles always-on sprite labels (keyboard, not controller)
    local key_r = emu.isKeyPressed("R")
    if key_r and not prev_key_r then
        show_sprite_labels = not show_sprite_labels
        log(string.format("Sprite labels: %s", show_sprite_labels and "ON" or "OFF"))
    end
    prev_key_r = key_r

    -- v33: X key cycles filter mode (keyboard, not controller)
    local key_x = emu.isKeyPressed("X")
    if key_x and not prev_key_x then
        if current_filter_mode == FILTER_MODES.ALL then
            current_filter_mode = FILTER_MODES.NO_HUD
            log("Filter: NO_HUD (skip y < 32)")
        elseif current_filter_mode == FILTER_MODES.NO_HUD then
            current_filter_mode = FILTER_MODES.LARGE_ONLY
            log("Filter: LARGE_ONLY (skip 8x8)")
        elseif current_filter_mode == FILTER_MODES.LARGE_ONLY then
            current_filter_mode = FILTER_MODES.MOVING
            log("Filter: MOVING (only moving sprites)")
        else
            current_filter_mode = FILTER_MODES.ALL
            log("Filter: ALL")
        end
    end
    prev_key_x = key_x

    -- v33: Left/Right d-pad cycle through visible sprites for info panel (controller)
    local key_left = input.left or false
    local key_right = input.right or false
    if (key_left and not prev_key_left) or (key_right and not prev_key_right) then
        -- Build list of visible filtered sprites
        local visible = {}
        for i = 0, 127 do
            local spr = get_sprite_info(i)
            if spr and is_visible(spr) and passes_filter(spr) then
                table.insert(visible, spr)
            end
        end
        if #visible > 0 then
            -- Find current position
            local cur_pos = 1
            for i, spr in ipairs(visible) do
                if spr.index == selected_sprite_idx then
                    cur_pos = i
                    break
                end
            end
            -- Navigate
            if key_left and not prev_key_left then
                cur_pos = cur_pos - 1
                if cur_pos < 1 then cur_pos = #visible end
            elseif key_right and not prev_key_right then
                cur_pos = cur_pos + 1
                if cur_pos > #visible then cur_pos = 1 end
            end
            selected_sprite_idx = visible[cur_pos].index
            -- Log info about selected sprite
            local spr = visible[cur_pos]
            local owner = vram_owner_map[spr.vram_addr]
            if owner and owner.idx then
                log(string.format("Selected: OAM#%d (%d,%d) -> idx=%d FILE=0x%06X",
                    spr.index, spr.x, spr.y, owner.idx, owner.file_offset or 0))
            else
                log(string.format("Selected: OAM#%d (%d,%d) -> (unresolved, VRAM=$%04X)",
                    spr.index, spr.x, spr.y, spr.vram_addr))
            end
        end
    end
    prev_key_left = key_left
    prev_key_right = key_right

    -- Draw (v22: use ppu_mouse for consistent coordinate space)
    draw_oam_boxes()            -- v15: Debug overlay first (behind other UI)
    draw_sprite_labels()        -- v33: Always-on labels (after boxes, before other UI)
    draw_crosshair(ppu_mouse)
    draw_hover_hint(ppu_mouse)  -- v22: now just draws, doesn't re-collect
    draw_candidate_list(ppu_mouse)  -- v15: Show candidates list
    draw_result_panel()
    draw_debug_info(ppu_mouse)

    -- v15/v33: Show toggle states in corner
    local status_y = show_sprite_labels and 85 or 67  -- Offset when labels overlay is active
    local status = ""
    if show_sprite_labels then
        local filter_names = {[1]="ALL", [2]="NO_HUD", [3]="LARGE", [4]="MOVING"}
        status = status .. "LBL:" .. (filter_names[current_filter_mode] or "?") .. " "
    end
    if hud_ignore_enabled then status = status .. "HUD:OFF " end
    if show_oam_boxes then status = status .. "BBOX:ON" end
    if #status > 0 then
        emu.drawString(170, status_y, status, 0xFFFF00, 0x80000000)
    end
end

local function safe_on_frame()
    if fatal_error then return end
    local ok, err = xpcall(on_frame, debug.traceback)
    if not ok then
        log_fatal("on_frame", err)
    end
end

--------------------------------------------------------------------------------
-- Initialize
--------------------------------------------------------------------------------

log("========================================")
log("SPRITE ROM FINDER v34")
log("========================================")
log("v34: OAM/VMAIN fixes + velocity clustering + cluster boxes")
log("  - FIX: Use PPU state/OBSEL shadow for OAM tables (write-only $2101)")
log("  - FIX: Apply VMAIN remap when tracking VMADD/VRAM DMAs")
log("  - Clusters now require proximity AND similar velocity")
log("  - Bounding boxes drawn around sprite clusters")
log("  - Labels show FILE offset (e.g., 3C6EF1) instead of idx")
log("  - Tuneable: CLUSTER_VEL_TOL, VELOCITY_HISTORY, CLUSTER_MIN_SIZE")
log("v33: Always-on automatic attribution")
log("  - R toggles sprite labels (idx or ? for unresolved)")
log("  - X cycles filter mode (ALL/NO_HUD/LARGE/MOVING)")
log("  - LEFT/RIGHT navigates sprites (logs attribution)")
log("  - Auto-watch: unresolved sprites log when they reload")
log("  - Proximity clustering groups multi-OAM sprites")
log("v32: Reset hotkey + lookback guard")
log("  - L clears history (VRAM/owner/session) for fresh capture")
log("  - Unmatched sessions skip lookback attribution by default")
log("v31: Unmatched sessions + session dedup")
log("  - Allow unmatched DP ptr sessions (see ALLOW_UNMATCHED_DP_PTR)")
log("  - Skip duplicate ptr sessions within SESSION_DEDUP_WINDOW")
log("v30: Safe draw clamps for OAM overlay/hover")
log("  - Clamp rectangles/text to screen bounds to avoid crashes")
log("v29: Wider lookback + larger staging queue")
log("  - Lookback window defaults to 90 frames")
log("  - Staging DMA queue increased to 512 entries")
log("  - Optional last-session boundary for lookback")
log("v28: Crash guards (fixed vararg wrapper)")
log("  - Safe vararg forwarding in callback wrapper")
log("v27: Crash guards + stack-trace logging")
log("  - Wraps callbacks/on_frame with xpcall")
log("  - Logs fatal error then disables tracking")
log("v26: Delayed activation + stability tweaks")
log("  - Tracking/UI starts after ACTIVATE_AT_FRAME (configurable)")
log("  - Safe getState() fallback to avoid early-frame nil crashes")
log("  - Guarded OAM reads + mouse fallback to avoid nil access")
log("v25: Slot-preference attribution + correctness fixes")
log("  - Tracks DP pointer slots 00:0002 / 00:0005 / 00:0008")
log("  - Slot-preference in forward attribution (0x0002 beats 0x0005/0x0008)")
log("  - Fixed FE52 prefill off-by-one (last entry could read past table)")
log("  - Clamped PPU coords to prevent edge weirdness")
log("v24: Hard enforcement of causal rules")
log("  - Unmatched idx sessions are optional (ALLOW_UNMATCHED_DP_PTR)")
log("  - Runtime table reads update ptr_to_idx (no sync gaps)")
log("  - Removed stale blanking (age is not invalidation)")
log("  - Pre-populated FE52 table at init (deterministic)")
log("  - Pure vram_owner_map attribution (no session guessing)")
log("  - Cursor-tile attribution (flip-aware), base-tile fallback")
log("  - Bounding box overlay (Start button)")
log("")
do
    local slots = {}
    for _, base in ipairs(DP_PTR_SLOTS) do
        table.insert(slots, string.format("%04X", base))
    end
    log("DP slots: " .. table.concat(slots, ", "))
end
log("LEFT-CLICK = lookup ROM offset for selected sprite")
log("SCROLL/UP/DOWN = cycle through candidates under cursor")
log("SELECT = toggle HUD ignore (y < 32)")
log("START = toggle bounding box overlay")
log("R = toggle always-on sprite labels")
log("X = cycle filter mode (ALL/NO_HUD/LARGE/MOVING)")
log("LEFT/RIGHT = navigate sprites (logs attribution)")
log("L = reset history (fresh capture)")
log("RIGHT-CLICK = clear panel")
log("========================================")

emu.addEventCallback(safe_on_frame, emu.eventType.endFrame)

log("")
if ACTIVATE_AT_FRAME > 0 then
    log(string.format("Activation delayed until frame %d", ACTIVATE_AT_FRAME))
else
    activate_tracking()
end
