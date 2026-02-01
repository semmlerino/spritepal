-- sprite_capture_with_attribution.lua v1
-- Combined script: SA-1 attribution tracking + full sprite capture
--
-- Merges functionality from:
--   - sprite_rom_finder.lua (accurate ROM offset attribution via SA-1 bank tracking)
--   - full_sprite_dump.lua (complete OAM/VRAM/CGRAM capture)
--
-- Output: JSON capture with per-tile rom_offset for direct import into SpritePal Frame Mapping
--
-- Press F9 to capture full dump with ROM offsets to JSON
-- Press F10 to capture raw binary dumps (OAM.dmp, VRAM.dmp, CGRAM.dmp)
-- Press E to export VRAM attribution map (vram_attribution.json)
--
-- Workflow: Just run this script, play game until sprites appear, press F9.
-- Each tile in the capture JSON will have rom_offset if attribution was tracked.

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

--------------------------------------------------------------------------------
-- Configuration
--------------------------------------------------------------------------------
local OUTPUT_DIR = os.getenv("OUTPUT_DIR") or "C:\\CustomScripts\\KirbyMax\\workshop\\exhal-master\\spritepal\\mesen2_exchange\\"
local LOG_FILE = OUTPUT_DIR .. "capture_attribution.log"
local ATTRIBUTION_FILE = OUTPUT_DIR .. "vram_attribution.json"

-- SMC header offset: Keep at 0 for SpritePal (handles headers automatically)
local ROM_HEADER = 0

-- Memory type references
local MEM = {
    oam = emu.memType.snesSpriteRam,
    vram = emu.memType.snesVideoRam,
    cgram = emu.memType.snesCgRam,
}

os.execute('mkdir "' .. OUTPUT_DIR:gsub("\\", "\\\\") .. '" 2>NUL')

--------------------------------------------------------------------------------
-- Logging
--------------------------------------------------------------------------------
local log_handle = nil
local frame_count = 0
local fatal_error = nil

local function log(msg)
    if not log_handle then
        log_handle = io.open(LOG_FILE, "a")
    end
    if log_handle then
        log_handle:write(msg .. "\n")
        log_handle:flush()
    end
    emu.log(msg)
end

local function log_fatal(context, err)
    if fatal_error then return end
    fatal_error = err or "unknown error"
    log(string.format("FATAL(%s): %s", context, tostring(fatal_error)))
end

--------------------------------------------------------------------------------
-- Safe callback wrapper
--------------------------------------------------------------------------------
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

--------------------------------------------------------------------------------
-- SA-1 Bank Register Shadowing ($2220-$2223)
-- Critical for accurate ROM offset calculation - these are write-only registers
--------------------------------------------------------------------------------
local sa1_cxb_shadow = 0x00  -- $2220: C0-CF bank mapping (default=0)
local sa1_dxb_shadow = 0x01  -- $2221: D0-DF bank mapping (default=1)
local sa1_exb_shadow = 0x02  -- $2222: E0-EF bank mapping (default=2)
local sa1_fxb_shadow = 0x03  -- $2223: F0-FF bank mapping (default=3)

local function on_sa1_bank_write(address, value)
    local lo = address & 0xFFFF
    local reg_value = value & 0x07
    if lo == 0x2220 then
        sa1_cxb_shadow = reg_value
    elseif lo == 0x2221 then
        sa1_dxb_shadow = reg_value
    elseif lo == 0x2222 then
        sa1_exb_shadow = reg_value
    elseif lo == 0x2223 then
        sa1_fxb_shadow = reg_value
    end
end

-- Convert CPU address to ROM file offset using SA-1 bank mapping
local function cpu_to_file_offset(ptr)
    local bank = (ptr >> 16) & 0xFF
    local addr = ptr & 0xFFFF

    -- SA-1 HiROM-style: Full 64KB banks at C0-FF
    if bank >= 0xC0 and bank <= 0xFF then
        local bank_base, bank_reg
        if bank >= 0xC0 and bank <= 0xCF then
            bank_base, bank_reg = 0xC0, sa1_cxb_shadow
        elseif bank >= 0xD0 and bank <= 0xDF then
            bank_base, bank_reg = 0xD0, sa1_dxb_shadow
        elseif bank >= 0xE0 and bank <= 0xEF then
            bank_base, bank_reg = 0xE0, sa1_exb_shadow
        else  -- F0-FF
            bank_base, bank_reg = 0xF0, sa1_fxb_shadow
        end
        return (bank_reg * 0x100000) + ((bank - bank_base) * 0x10000) + addr + ROM_HEADER
    end

    -- SA-1 LoROM-style: Banks $00-$3F and $80-$BF at $8000-$FFFF
    if addr >= 0x8000 then
        local effective_bank = bank & 0x3F
        if effective_bank <= 0x3F then
            local bank_reg
            if effective_bank <= 0x1F then
                bank_reg = sa1_cxb_shadow
            else
                bank_reg = sa1_dxb_shadow
                effective_bank = effective_bank - 0x20
            end
            return (bank_reg * 0x100000) + (effective_bank * 0x8000) + (addr - 0x8000) + ROM_HEADER
        end
    end

    return nil
end

--------------------------------------------------------------------------------
-- VRAM Attribution Tracking
--------------------------------------------------------------------------------
local vram_owner_map = {}        -- Key: vram_word, Value: {idx, ptr, frame, file_offset}
local vram_upload_map = {}       -- Key: vram_word, Value: DMA entry
local staging_owner_map = {}     -- Key: chunk_idx, Value: attribution info

-- Staging buffer ranges for Kirby Super Star
local STAGING_START = 0x7E2000
local STAGING_END = 0x7E2FFF
local STAGING2_START = 0x7F8000
local STAGING2_END = 0x7FFFFF
local STAGING_CHUNK_SIZE = 32

-- Session tracking
local SESSION_MATCH_WINDOW = 1000
local RECENT_SESSIONS_MAX = 128
local session_counter = 0
local recent_sessions = {}

-- FE52 pointer table (graphics pointers)
local TABLE_CPU_BASE = 0x01FE52
local TABLE_CPU_END = 0x01FFFF
local ENTRY_SIZE = 3
local idx_database = {}
local ptr_to_idx = {}

local VALID_BANKS = {}
for bank = 0xC0, 0xFF do
    VALID_BANKS[bank] = true
end

local function is_valid_ptr(ptr)
    local bank = (ptr >> 16) & 0xFF
    if not VALID_BANKS[bank] then return false end
    if ptr == 0xFFFFFF or ptr == 0x000000 then return false end
    return true
end

local function fmt_addr(addr)
    local bank = (addr >> 16) & 0xFF
    local offset = addr & 0xFFFF
    return string.format("%02X:%04X", bank, offset)
end

--------------------------------------------------------------------------------
-- Session Management
--------------------------------------------------------------------------------
local function is_fe52_session(s)
    return s.cpu and string.find(s.cpu, "fe52") ~= nil
end

local function match_recent_session()
    local best = nil
    local best_rank = 999
    local SLOT_RANK = { [0x0002] = 1, [0x0005] = 2, [0x0008] = 3 }

    for i = #recent_sessions, 1, -1 do
        local s = recent_sessions[i]
        local age = frame_count - s.frame
        if age > SESSION_MATCH_WINDOW then
            break
        end

        local rank
        if is_fe52_session(s) and s.idx_known then
            rank = 0
        elseif is_fe52_session(s) then
            rank = 500
        else
            rank = SLOT_RANK[s.slot] or 999
        end

        if s.idx_known and rank < best_rank then
            best = s
            best_rank = rank
        elseif not best then
            best = s
        end
    end

    return best
end

local function start_session(ptr, idx, slot_base, cpu_name)
    session_counter = session_counter + 1
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
end

--------------------------------------------------------------------------------
-- VRAM Attribution Write
-- For direct ROM transfers: each tile gets its own sequential ROM offset
-- For staged (compressed) transfers: all tiles share the base offset, but we track tile_index
-- A 4bpp tile = 16 VRAM words = 32 ROM bytes
--------------------------------------------------------------------------------
local VRAM_WORDS_PER_TILE = 16  -- 16 VRAM words (32 bytes) per 4bpp tile
local ROM_BYTES_PER_TILE = 32

local function write_vram_attribution(entry, idx, ptr, file_off)
    local is_direct = (entry.attrib_mode == "direct_rom" or entry.attrib_mode == "direct_lorom")
    local words = entry.vram_words

    if words then
        -- vram_words is indexed by position in DMA transfer (1-based)
        for i, w in ipairs(words) do
            local existing = vram_owner_map[w]
            if not (existing and existing.attrib_mode == "direct_rom" and entry.attrib_mode ~= "direct_rom") then
                local tile_index = math.floor((i - 1) / VRAM_WORDS_PER_TILE)
                local tile_rom_offset
                if is_direct and file_off then
                    -- Direct ROM: sequential offsets for each tile
                    tile_rom_offset = file_off + tile_index * ROM_BYTES_PER_TILE
                else
                    -- Staged/compressed: all tiles share the compressed block offset
                    tile_rom_offset = file_off
                end
                vram_owner_map[w] = {
                    idx = idx,
                    ptr = ptr,
                    file_offset = tile_rom_offset,
                    tile_index_in_block = tile_index,  -- Position within the block
                    owner_frame = frame_count,
                    dma_frame = entry.frame,
                    attrib_mode = entry.attrib_mode,
                }
            end
        end
        return
    end

    -- Fallback path using vram_start/vram_end range
    local word_index = 0
    for w = entry.vram_start, entry.vram_end - 1 do
        local existing = vram_owner_map[w]
        if not (existing and existing.attrib_mode == "direct_rom" and entry.attrib_mode ~= "direct_rom") then
            local tile_index = math.floor(word_index / VRAM_WORDS_PER_TILE)
            local tile_rom_offset
            if is_direct and file_off then
                tile_rom_offset = file_off + tile_index * ROM_BYTES_PER_TILE
            else
                tile_rom_offset = file_off
            end
            vram_owner_map[w] = {
                idx = idx,
                ptr = ptr,
                file_offset = tile_rom_offset,
                tile_index_in_block = tile_index,
                owner_frame = frame_count,
                dma_frame = entry.frame,
                attrib_mode = entry.attrib_mode,
            }
        end
        word_index = word_index + 1
    end
end

--------------------------------------------------------------------------------
-- FE52 Table Read Callback
--------------------------------------------------------------------------------
local pending_tbl = {}

local function make_on_table_read(cpu_name)
    return function(addr, value)
        local offset_from_base = addr - TABLE_CPU_BASE
        local idx = math.floor(offset_from_base / ENTRY_SIZE)
        local byte_pos = offset_from_base % ENTRY_SIZE
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
                ptr_to_idx[ptr] = idx
                start_session(ptr, idx, nil, cpu_name .. "_fe52")
            end
            pending_tbl[key] = nil
        end
        return nil
    end
end

--------------------------------------------------------------------------------
-- DP Pointer Write Callback
--------------------------------------------------------------------------------
local DP_PTR_SLOTS = {0x0002, 0x0005, 0x0008}
local DP_PTR_SLOT_SIZE = 3
local DP_PTR_SLOT_BY_OFFSET = {}
for _, base in ipairs(DP_PTR_SLOTS) do
    for i = 0, DP_PTR_SLOT_SIZE - 1 do
        DP_PTR_SLOT_BY_OFFSET[base + i] = base
    end
end

local pending_dp = {}

local function make_on_dp_write(cpu_name)
    return function(addr, value)
        local bank = (addr >> 16) & 0xFF
        local lo = addr & 0xFFFF
        if bank ~= 0x00 or lo > 0x00FF then return nil end

        local slot_base = DP_PTR_SLOT_BY_OFFSET[lo]
        if not slot_base then return nil end

        if not pending_dp[cpu_name] then pending_dp[cpu_name] = {} end
        local pending_slots = pending_dp[cpu_name]
        if not pending_slots[slot_base] then pending_slots[slot_base] = {} end
        local pending = pending_slots[slot_base]
        local byte_pos = lo - slot_base

        if byte_pos == 0 then pending.lo = value; pending.lo_frame = frame_count
        elseif byte_pos == 1 then pending.hi = value; pending.hi_frame = frame_count
        elseif byte_pos == 2 then pending.bank = value; pending.bank_frame = frame_count
        end

        if pending.lo and pending.hi and pending.bank then
            local max_f = math.max(pending.lo_frame or 0, pending.hi_frame or 0, pending.bank_frame or 0)
            local min_f = math.min(pending.lo_frame or 0, pending.hi_frame or 0, pending.bank_frame or 0)

            if max_f - min_f <= 1 then
                local ptr = pending.lo + (pending.hi * 256) + (pending.bank * 65536)
                if is_valid_ptr(ptr) then
                    local matched_idx = ptr_to_idx[ptr]
                    start_session(ptr, matched_idx, slot_base, cpu_name)
                end
                pending_slots[slot_base] = {}
            end
        end
        return nil
    end
end

--------------------------------------------------------------------------------
-- Staging Buffer Write Callback
--------------------------------------------------------------------------------
local function on_staging_write(address, value)
    local addr_lo = address & 0xFFFFFF
    local staging_offset = nil

    if addr_lo >= STAGING_START and addr_lo <= STAGING_END then
        staging_offset = addr_lo - STAGING_START
    elseif addr_lo >= STAGING2_START and addr_lo <= STAGING2_END then
        staging_offset = (STAGING_END - STAGING_START + 1) + (addr_lo - STAGING2_START)
    else
        return
    end

    local chunk_idx = math.floor(staging_offset / STAGING_CHUNK_SIZE)
    local existing = staging_owner_map[chunk_idx]
    if existing and existing.frame == frame_count then
        return
    end

    local sess = match_recent_session()
    if sess then
        staging_owner_map[chunk_idx] = {
            idx = sess.idx,
            ptr = sess.ptr,
            frame = frame_count,
            file_offset = sess.ptr and cpu_to_file_offset(sess.ptr) or nil
        }
    elseif existing then
        staging_owner_map[chunk_idx] = nil
    end
end

--------------------------------------------------------------------------------
-- VRAM/DMA Tracking
--------------------------------------------------------------------------------
local DMA_ENABLE_REG = 0x420B
local vmadd_lo, vmadd_hi = 0, 0
local vram_addr_logical = 0
local vram_addr_shadow = 0
local vmain_shadow = 0x00
local vram_increment_value = 1
local vram_remap_mode = 0

local dma_shadow = {}
for ch = 0, 7 do
    dma_shadow[ch] = { dmap=0, bbad=0, a1tl=0, a1th=0, a1tb=0, dasl=0, dash=0 }
end

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
end

local function apply_vram_remap(addr)
    addr = addr & 0x7FFF
    if vram_remap_mode == 0 then return addr end
    if vram_remap_mode == 1 then
        return (addr & 0xFF00) | ((addr & 0xE0) >> 5) | ((addr & 0x1F) << 3)
    end
    if vram_remap_mode == 2 then
        return (addr & 0xFE00) | ((addr & 0x1C0) >> 6) | ((addr & 0x3F) << 3)
    end
    return (addr & 0xFC00) | ((addr & 0x380) >> 7) | ((addr & 0x7F) << 3)
end

local function on_vmain_write(address, value)
    update_vmain_shadow(value)
    vram_addr_shadow = apply_vram_remap(vram_addr_logical)
end

local function on_vram_addr_write(address, value)
    if address == 0x2116 then
        vmadd_lo = value & 0xFF
    else
        vmadd_hi = value & 0xFF
    end
    vram_addr_logical = (vmadd_lo + (vmadd_hi * 256)) & 0x7FFF
    vram_addr_shadow = apply_vram_remap(vram_addr_logical)
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

local function map_dma_vram_words(entry, start_logical, word_count, increment)
    local inc = increment or 1
    if inc == 0 then inc = 1 end

    entry.vram_words = {}
    local logical = start_logical
    for i = 1, word_count do
        local physical = apply_vram_remap(logical)
        entry.vram_words[i] = physical
        vram_upload_map[physical] = entry
        logical = (logical + inc) & 0x7FFF
    end
    entry.vram_start = start_logical
    entry.vram_end = (start_logical + word_count) & 0x7FFF
    return logical
end

local function on_dma_enable(addr, value)
    local enable = value
    if enable == nil then
        enable = emu.read(0x420B, emu.memType.snesMemory) or 0
    end
    enable = enable & 0xFF
    if enable == 0 then return nil end

    local local_vram_logical = vram_addr_logical
    local vram_increment = vram_increment_value
    if not vram_increment or vram_increment == 0 then vram_increment = 1 end

    for ch = 0, 7 do
        if (enable & (1 << ch)) ~= 0 then
            local s = dma_shadow[ch]
            local dmap = s.dmap or 0
            local bbad = s.bbad or 0
            local src_addr = (s.a1tl or 0) + ((s.a1th or 0) * 256) + ((s.a1tb or 0) * 65536)
            local dma_size = (s.dasl or 0) + ((s.dash or 0) * 256)
            if dma_size == 0 then dma_size = 0x10000 end

            local direction = (dmap & 0x80) >> 7

            if direction == 0 and (bbad == 0x18 or bbad == 0x19) then
                local is_staging = (src_addr >= STAGING_START and src_addr <= STAGING_END)
                    or (src_addr >= STAGING2_START and src_addr <= STAGING2_END)

                local session_idx, session_ptr, file_off = nil, nil, nil
                local attrib_mode = nil

                if is_staging then
                    local staging_offset
                    if src_addr >= STAGING_START and src_addr <= STAGING_END then
                        staging_offset = src_addr - STAGING_START
                    else
                        staging_offset = (STAGING_END - STAGING_START + 1) + (src_addr - STAGING2_START)
                    end
                    local chunk_idx = math.floor(staging_offset / STAGING_CHUNK_SIZE)
                    local owner = staging_owner_map[chunk_idx]

                    if owner and (frame_count - owner.frame) > SESSION_MATCH_WINDOW then
                        owner = nil
                        staging_owner_map[chunk_idx] = nil
                    end

                    if owner and owner.ptr then
                        session_idx = owner.idx
                        session_ptr = owner.ptr
                        file_off = owner.file_offset
                        attrib_mode = "staging_map"
                    else
                        local sess = match_recent_session()
                        if sess then
                            session_idx = sess.idx
                            session_ptr = sess.ptr
                            if session_ptr then file_off = cpu_to_file_offset(session_ptr) end
                            attrib_mode = "forward"
                        end
                    end
                else
                    -- Direct ROM->VRAM DMA
                    local src_bank = (src_addr >> 16) & 0xFF
                    local src_addr_low = src_addr & 0xFFFF
                    local is_hirom = (src_bank >= 0xC0 and src_bank <= 0xFF)
                    local is_lorom = (src_addr_low >= 0x8000 and
                                      ((src_bank >= 0x00 and src_bank <= 0x3F) or
                                       (src_bank >= 0x80 and src_bank <= 0xBF)))
                    if is_hirom or is_lorom then
                        session_ptr = src_addr
                        file_off = cpu_to_file_offset(src_addr)
                        session_idx = ptr_to_idx[src_addr]
                        attrib_mode = is_lorom and "direct_lorom" or "direct_rom"
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
                    attrib_mode = attrib_mode,
                }

                local words_transferred = math.ceil(dma_size / 2)
                local_vram_logical = map_dma_vram_words(entry, local_vram_logical, words_transferred, vram_increment)

                if session_idx or file_off then
                    write_vram_attribution(entry, session_idx, session_ptr, file_off)
                end
            end
        end
    end
    return nil
end

--------------------------------------------------------------------------------
-- OBSEL Tracking
--------------------------------------------------------------------------------
local LAST_OBSEL = nil

local function on_obsel_write(address, value)
    LAST_OBSEL = value & 0xFF
end

--------------------------------------------------------------------------------
-- SNES Constants for OAM
--------------------------------------------------------------------------------
local SIZE_TABLE = {
    [0] = {8, 8, 16, 16},
    [1] = {8, 8, 32, 32},
    [2] = {8, 8, 64, 64},
    [3] = {16, 16, 32, 32},  -- Kirby Super Star
    [4] = {16, 16, 64, 64},
    [5] = {32, 32, 64, 64},
    [6] = {16, 32, 32, 64},
    [7] = {16, 32, 32, 32},
}

--------------------------------------------------------------------------------
-- Helper Functions
--------------------------------------------------------------------------------
local function get_obsel()
    local obsel
    if LAST_OBSEL ~= nil then
        obsel = LAST_OBSEL
    else
        obsel = emu.read(0x2101, emu.memType.snesMemory) or 0x63
    end

    local name_base = obsel & 0x07
    local name_sel = (obsel >> 3) & 0x03
    local size_sel = (obsel >> 5) & 0x07

    return {
        raw = obsel,
        name_base = name_base,
        name_select = name_sel,
        size_select = size_sel,
        tile_base_addr = name_base << 14,
        second_table_offset = (name_sel + 1) << 13,
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

-- Get ROM attribution info for a VRAM word address
-- Returns: rom_offset, tile_index_in_block (or nil, nil if not found)
local function get_rom_offset_for_vram(vram_word)
    local owner = vram_owner_map[vram_word]
    if owner and owner.file_offset then
        return owner.file_offset, owner.tile_index_in_block
    end
    return nil, nil
end

--------------------------------------------------------------------------------
-- Read Complete OAM with ROM Attribution
--------------------------------------------------------------------------------
local function read_full_oam_with_attribution(obsel)
    local entries = {}
    local size_info = SIZE_TABLE[obsel.size_select] or SIZE_TABLE[3]
    local small_w, small_h = size_info[1], size_info[2]
    local large_w, large_h = size_info[3], size_info[4]

    for i = 0, 127 do
        local base = i * 4

        local x_low = emu.read(base, MEM.oam)
        local y = emu.read(base + 1, MEM.oam)
        local tile = emu.read(base + 2, MEM.oam)
        local attr = emu.read(base + 3, MEM.oam)

        local high_byte_idx = math.floor(i / 4)
        local high_bit_pos = (i % 4) * 2
        local high_byte = emu.read(0x200 + high_byte_idx, MEM.oam)
        local high_bits = (high_byte >> high_bit_pos) & 0x03

        local x_high = high_bits & 0x01
        local size_bit = (high_bits >> 1) & 0x01

        local x = x_low | (x_high << 8)
        if x >= 256 then
            x = x - 512
        end

        local width, height
        if size_bit == 1 then
            width, height = large_w, large_h
        else
            width, height = small_w, small_h
        end

        local name_table = attr & 0x01
        local palette = (attr >> 1) & 0x07
        local priority = (attr >> 4) & 0x03
        local flip_h = ((attr >> 6) & 0x01) == 1
        local flip_v = ((attr >> 7) & 0x01) == 1

        -- Read tile data with ROM attribution
        local tiles_x = width // 8
        local tiles_y = height // 8
        local tile_data_list = {}

        local base_tile_x = tile & 0x0F
        local base_tile_y = (tile >> 4) & 0x0F

        -- Track first tile's ROM offset for entry-level attribution
        local first_tile_rom_offset = nil

        for ty = 0, tiles_y - 1 do
            for tx = 0, tiles_x - 1 do
                local tile_x = (base_tile_x + tx) & 0x0F
                local tile_y = (base_tile_y + ty) & 0x0F
                local tile_idx = (tile_y << 4) | tile_x

                -- Calculate VRAM word address
                local word_addr = (obsel.name_base << 13) + (tile_idx << 4)
                if name_table == 1 then
                    word_addr = word_addr + ((obsel.name_select + 1) << 12)
                end
                word_addr = word_addr & 0x7FFF
                local byte_addr = word_addr << 1

                -- Read 32 bytes of 4bpp tile data
                local tile_bytes = {}
                for b = 0, 31 do
                    tile_bytes[b + 1] = emu.read(byte_addr + b, MEM.vram)
                end

                -- Look up ROM offset and tile index from attribution map
                local rom_offset, tile_index_in_block = get_rom_offset_for_vram(word_addr)

                -- Track first tile's offset for entry-level attribution
                if ty == 0 and tx == 0 and rom_offset then
                    first_tile_rom_offset = rom_offset
                end

                table.insert(tile_data_list, {
                    tile_index = tile_idx,
                    vram_addr = byte_addr,
                    pos_x = tx,
                    pos_y = ty,
                    data_hex = bytes_to_hex(tile_bytes),
                    rom_offset = rom_offset,  -- ROM offset for this tile
                    tile_index_in_block = tile_index_in_block,  -- Position within compressed block
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
            rom_offset = first_tile_rom_offset,  -- Entry-level ROM offset from first tile
        }
    end

    return entries
end

--------------------------------------------------------------------------------
-- Read All Sprite Palettes from CGRAM
--------------------------------------------------------------------------------
local function read_sprite_palettes()
    local palettes = {}

    for pal = 0, 7 do
        local colors = {}
        local base = 0x100 + (pal * 32)

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

--------------------------------------------------------------------------------
-- Export VRAM Attribution Map (E key)
--------------------------------------------------------------------------------
local function export_vram_attribution()
    local f = io.open(ATTRIBUTION_FILE, "w")
    if not f then
        log("ERROR: Cannot open attribution file for writing")
        return 0
    end

    local entries = {}
    local count = 0
    for vram_word, owner in pairs(vram_owner_map) do
        if owner and (owner.idx or owner.file_offset) then
            table.insert(entries, {
                vram_word = vram_word,
                vram_byte = vram_word * 2,
                idx = owner.idx,
                ptr = owner.ptr,
                file_offset = owner.file_offset,
            })
            count = count + 1
        end
    end

    table.sort(entries, function(a, b) return a.vram_word < b.vram_word end)

    f:write("{\n")
    f:write(string.format('  "export_frame": %d,\n', frame_count))
    f:write(string.format('  "export_time": "%s",\n', os.date("%Y-%m-%d %H:%M:%S")))
    f:write(string.format('  "entry_count": %d,\n', count))
    f:write('  "entries": [\n')

    for i, entry in ipairs(entries) do
        f:write(string.format(
            '    {"vram_word":%d,"vram_byte":%d,"idx":%s,"ptr":%s,"file_offset":%s}',
            entry.vram_word,
            entry.vram_byte,
            entry.idx and tostring(entry.idx) or "null",
            entry.ptr and tostring(entry.ptr) or "null",
            entry.file_offset and tostring(entry.file_offset) or "null"
        ))
        if i < #entries then f:write(",") end
        f:write("\n")
    end

    f:write("  ]\n")
    f:write("}\n")
    f:close()

    log(string.format("EXPORT: Wrote %d VRAM->ROM attributions to %s", count, ATTRIBUTION_FILE))
    emu.displayMessage("Attribution", string.format("Exported %d VRAM->ROM mappings", count))
    return count
end

--------------------------------------------------------------------------------
-- Capture to JSON (F9) - Main capture function with ROM offsets
--------------------------------------------------------------------------------
local function capture_full_json()
    local obsel = get_obsel()
    local timestamp = os.time()
    local filename = OUTPUT_DIR .. "capture_" .. timestamp .. ".json"

    log(string.format("Capturing full dump with attribution (OBSEL=0x%02X, frame=%d)", obsel.raw, frame_count))

    local entries = read_full_oam_with_attribution(obsel)
    local palettes = read_sprite_palettes()

    -- Count visible sprites and tiles with attribution
    local visible_count = 0
    local tiles_with_offset = 0
    local total_tiles = 0
    for _, e in ipairs(entries) do
        if e.y < 224 or e.y >= 240 then
            visible_count = visible_count + 1
        end
        for _, t in ipairs(e.tiles) do
            total_tiles = total_tiles + 1
            if t.rom_offset then
                tiles_with_offset = tiles_with_offset + 1
            end
        end
    end

    local f = io.open(filename, "w")
    if not f then
        log("ERROR: Could not open " .. filename)
        return
    end

    f:write('{\n')
    f:write('  "schema_version": "2.1",\n')
    f:write('  "capture_type": "full_dump_with_attribution",\n')
    f:write(string.format('  "timestamp": %d,\n', timestamp))
    f:write(string.format('  "capture_time": "%s",\n', os.date("%Y-%m-%d %H:%M:%S")))
    f:write(string.format('  "frame": %d,\n', frame_count))
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
    f:write(string.format('  "tiles_with_attribution": %d,\n', tiles_with_offset))
    f:write(string.format('  "total_tiles": %d,\n', total_tiles))

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
        -- Entry-level ROM offset (from first tile)
        if e.rom_offset then
            f:write(string.format('      "rom_offset": %d,\n', e.rom_offset))
        end

        -- Write tiles array with per-tile rom_offset
        f:write('      "tiles": [\n')
        for j, t in ipairs(e.tiles) do
            f:write('        {\n')
            f:write(string.format('          "tile_index": %d,\n', t.tile_index))
            f:write(string.format('          "vram_addr": %d,\n', t.vram_addr))
            f:write(string.format('          "pos_x": %d,\n', t.pos_x))
            f:write(string.format('          "pos_y": %d,\n', t.pos_y))
            if t.rom_offset then
                f:write(string.format('          "rom_offset": %d,\n', t.rom_offset))
            end
            if t.tile_index_in_block then
                f:write(string.format('          "tile_index_in_block": %d,\n', t.tile_index_in_block))
            end
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

    log(string.format("Saved capture to %s (%d entries, %d/%d tiles with ROM offsets)",
        filename, 128, tiles_with_offset, total_tiles))
    emu.displayMessage("Capture", string.format("Saved %d entries, %d/%d tiles attributed",
        128, tiles_with_offset, total_tiles))
end

--------------------------------------------------------------------------------
-- Capture Raw Binary Dumps (F10)
--------------------------------------------------------------------------------
local function capture_binary_dumps()
    local timestamp = os.time()
    local prefix = OUTPUT_DIR .. "dump_F" .. frame_count .. "_"

    log(string.format("Capturing binary dumps (frame=%d)", frame_count))

    -- OAM dump (544 bytes)
    local oam_file = prefix .. "OAM.dmp"
    local f = io.open(oam_file, "wb")
    if f then
        for i = 0, 543 do
            f:write(string.char(emu.read(i, MEM.oam)))
        end
        f:close()
    end

    -- VRAM dump (64KB)
    local vram_file = prefix .. "VRAM.dmp"
    f = io.open(vram_file, "wb")
    if f then
        for i = 0, 65535 do
            f:write(string.char(emu.read(i, MEM.vram)))
        end
        f:close()
    end

    -- CGRAM dump (512 bytes)
    local cgram_file = prefix .. "CGRAM.dmp"
    f = io.open(cgram_file, "wb")
    if f then
        for i = 0, 511 do
            f:write(string.char(emu.read(i, MEM.cgram)))
        end
        f:close()
    end

    local obsel = get_obsel()
    local obsel_file = prefix .. "OBSEL.txt"
    f = io.open(obsel_file, "w")
    if f then
        f:write(string.format("OBSEL: 0x%02X\n", obsel.raw))
        f:write(string.format("name_base: %d\n", obsel.name_base))
        f:write(string.format("name_select: %d\n", obsel.name_select))
        f:write(string.format("size_select: %d\n", obsel.size_select))
        f:write(string.format("Frame: %d\n", frame_count))
        f:close()
    end

    emu.displayMessage("Binary Dumps", string.format("Saved OAM/VRAM/CGRAM to %s*", prefix:match("[^\\]+$")))
end

--------------------------------------------------------------------------------
-- Frame Handler
--------------------------------------------------------------------------------
local lastF9State = false
local lastF10State = false
local lastEState = false

local function on_frame()
    frame_count = frame_count + 1

    -- Count attribution stats
    local attr_count = 0
    for _ in pairs(vram_owner_map) do attr_count = attr_count + 1 end

    -- Draw on-screen status
    emu.drawString(8, 8, "SpritePal Capture+Attribution: F9=JSON, F10=Binary, E=Export",
        0xFFFFFF, 0x80000000)
    emu.drawString(8, 20, string.format("Frame: %d  VRAM attrs: %d",
        frame_count, attr_count), 0xFFFFFF, 0x80000000)

    -- F9 = Capture JSON with attribution
    local f9Pressed = emu.isKeyPressed("F9")
    if f9Pressed and not lastF9State then
        emu.drawString(8, 32, "CAPTURING JSON...", 0x00FF00, 0x80000000)
        capture_full_json()
    end
    lastF9State = f9Pressed

    -- F10 = Binary dumps
    local f10Pressed = emu.isKeyPressed("F10")
    if f10Pressed and not lastF10State then
        emu.drawString(8, 32, "CAPTURING BINARY...", 0xFFFF00, 0x80000000)
        capture_binary_dumps()
    end
    lastF10State = f10Pressed

    -- E = Export VRAM attribution map
    local ePressed = emu.isKeyPressed("E")
    if ePressed and not lastEState then
        emu.drawString(8, 32, "EXPORTING ATTRIBUTION...", 0x00FFFF, 0x80000000)
        export_vram_attribution()
    end
    lastEState = ePressed
end

local safe_on_frame = make_safe_callback(on_frame, "on_frame")

--------------------------------------------------------------------------------
-- Callback Registration
--------------------------------------------------------------------------------
log("========================================")
log("sprite_capture_with_attribution.lua v1")
log("Combined SA-1 attribution + full capture")
log("F9 = Capture JSON with per-tile ROM offsets")
log("F10 = Binary dumps (OAM/VRAM/CGRAM)")
log("E = Export VRAM attribution map")
log("========================================")

emu.addEventCallback(safe_on_frame, emu.eventType.endFrame)

do
    local snes_cpu = emu.cpuType.snes
    local sa1_cpu = emu.cpuType.sa1

    local function reg_cb(name, cb, cb_type, start_addr, end_addr, cpu, mem_type)
        local ok, err = pcall(function()
            emu.addMemoryCallback(make_safe_callback(cb, name), cb_type, start_addr, end_addr, cpu, mem_type)
        end)
        log(string.format("%s: %s %s", name, ok and "OK" or "FAIL", err or ""))
    end

    -- SA-1 bank registers ($2220-$2223) - CRITICAL for accurate ROM offsets
    reg_cb("SA-1 bank (SNES)", on_sa1_bank_write, emu.callbackType.write, 0x2220, 0x2223, snes_cpu, emu.memType.snesMemory)
    reg_cb("SA-1 bank (SA-1)", on_sa1_bank_write, emu.callbackType.write, 0x2220, 0x2223, sa1_cpu, emu.memType.sa1Memory)

    -- Staging buffers for decompressed sprite data
    reg_cb("Staging1 (SA-1)", on_staging_write, emu.callbackType.write, STAGING_START, STAGING_END, sa1_cpu, emu.memType.sa1Memory)
    reg_cb("Staging1 (SNES)", on_staging_write, emu.callbackType.write, STAGING_START, STAGING_END, snes_cpu, emu.memType.snesMemory)
    reg_cb("Staging2 (SA-1)", on_staging_write, emu.callbackType.write, STAGING2_START, STAGING2_END, sa1_cpu, emu.memType.sa1Memory)
    reg_cb("Staging2 (SNES)", on_staging_write, emu.callbackType.write, STAGING2_START, STAGING2_END, snes_cpu, emu.memType.snesMemory)

    -- FE52 table reads (graphics pointers)
    reg_cb("FE52 read (SNES)", make_on_table_read("snes"), emu.callbackType.read, TABLE_CPU_BASE, TABLE_CPU_END, snes_cpu, emu.memType.snesMemory)
    reg_cb("FE52 read (SA-1)", make_on_table_read("sa1"), emu.callbackType.read, TABLE_CPU_BASE, TABLE_CPU_END, sa1_cpu, emu.memType.sa1Memory)

    -- DMA tracking
    reg_cb("DMA enable", on_dma_enable, emu.callbackType.write, DMA_ENABLE_REG, DMA_ENABLE_REG, snes_cpu, emu.memType.snesMemory)
    reg_cb("VRAM addr", on_vram_addr_write, emu.callbackType.write, 0x2116, 0x2117, snes_cpu, emu.memType.snesMemory)
    reg_cb("VMAIN", on_vmain_write, emu.callbackType.write, 0x2115, 0x2115, snes_cpu, emu.memType.snesMemory)
    reg_cb("DMA regs", on_dma_reg_write, emu.callbackType.write, 0x4300, 0x437F, snes_cpu, emu.memType.snesMemory)

    -- OBSEL tracking
    reg_cb("OBSEL", on_obsel_write, emu.callbackType.write, 0x2101, 0x2101, snes_cpu, emu.memType.snesMemory)

    -- DP pointer writes
    reg_cb("DP write (snes)", make_on_dp_write("snes"), emu.callbackType.write, 0x000000, 0x0000FF, snes_cpu, emu.memType.snesMemory)
    reg_cb("DP write (sa1)", make_on_dp_write("sa1"), emu.callbackType.write, 0x000000, 0x0000FF, sa1_cpu, emu.memType.sa1Memory)
end

log("Ready! Press F9 for full JSON capture with ROM offsets")
emu.displayMessage("Capture+Attribution", "F9=JSON (with ROM offsets), F10=Binary, E=Export")
