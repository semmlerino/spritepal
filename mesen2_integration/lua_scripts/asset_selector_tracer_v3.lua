-- Asset Selector Tracer v3
-- Full idx→DMA payload attribution join
--
-- Key improvements over v2:
--   1) Fixed linkage metric: table_path_streams denominator (not all PRG streams)
--   2) Session tracking tied to DP_PTR_SET with record_type
--   3) DMA capture and attribution to sessions
--   4) Payload hash for DMA data
--   5) Per-idx database report
--
-- Pipeline: idx → ROM[01:FE52 + idx*3] → DP[00:0002-0004] → PRG stream → staging DMA

local OUTPUT_DIR = os.getenv("OUTPUT_DIR") or "C:\\CustomScripts\\KirbyMax\\workshop\\exhal-master\\spritepal\\mesen2_exchange\\"
local LOG_FILE = OUTPUT_DIR .. "asset_selector_v3.log"
local MAX_FRAMES = 3000

local log_handle = nil
local frame_count = 0
local script_stopping = false

-- ROM pointer table
local TABLE_CPU_BASE = 0x01FE52
local TABLE_CPU_END = 0x01FFFF
local ENTRY_SIZE = 3

-- DP pointer slot (primary)
local DP_PTR_BASE = 0x0002  -- 00:0002-0004

-- WRAM staging range
local STAGING_START = 0x7E2000
local STAGING_END = 0x7E2FFF

-- VRAM sprite region (word addresses)
local VRAM_SPRITE_START = 0x4000
local VRAM_SPRITE_END = 0x5FFF

-- Valid asset banks
local VALID_BANKS = {
    [0xC0] = true, [0xC1] = true, [0xC2] = true, [0xC3] = true,
    [0xE0] = true, [0xE1] = true, [0xE2] = true, [0xE3] = true,
    [0xE4] = true, [0xE5] = true, [0xE6] = true, [0xE7] = true,
    [0xE8] = true, [0xE9] = true, [0xEA] = true, [0xEB] = true,
    [0xEC] = true, [0xED] = true, [0xEE] = true, [0xEF] = true,
    [0x7E] = true,  -- WRAM staging (idx 87 case)
}

-- State tracking
local pending_tbl = {}       -- Per-idx pending table reads
local pending_dp = {}        -- Per-CPU pending DP writes
local current_ptr = {}       -- Per-CPU current pointer cache
local committed_ptrs = {}    -- Set of all committed pointers (for linkage check)

-- Session tracking
local active_session = nil   -- Current decode session
local completed_sessions = {} -- Completed sessions with DMA attribution
local session_counter = 0
local SESSION_TIMEOUT = 4    -- Frames before session timeout

-- DMA tracking
local pending_dma = {}       -- Pending DMA info from register writes
local dma_in_progress = false

-- Per-idx database
local idx_database = {}      -- {idx: {ptr, record_types, sessions, dmas, hashes}}

-- Statistics
local stats = {
    raw_tbl_reads = 0,
    tbl_ptr_decoded = 0,
    raw_dp_writes = 0,
    dp_ptr_commits = 0,
    prg_starts_total = 0,
    prg_starts_table_path = 0,  -- Starts at a committed ptr
    prg_linked = 0,
    sessions_created = 0,
    sessions_with_dma = 0,
    staging_dmas = 0,
}

local function log(msg)
    if not log_handle then
        log_handle = io.open(LOG_FILE, "w")
    end
    if log_handle then
        log_handle:write(msg .. "\n")
        log_handle:flush()
    end
end

local function fmt_addr(addr)
    local bank = math.floor(addr / 65536)
    local offset = addr % 65536
    return string.format("%02X:%04X", bank, offset)
end

local function fmt_cpu(cpu_type)
    if cpu_type == 0 then return "SNES"
    elseif cpu_type == 3 then return "SA1"
    else return string.format("CPU%d", cpu_type)
    end
end

-- Simple hash for payload identification (Lua 5.4 native bitwise ops)
local function compute_hash(data, len)
    local hash = 0x811c9dc5  -- FNV-1a offset basis
    for i = 1, math.min(len, 64) do  -- Hash first 64 bytes
        local byte = data[i] or 0
        hash = hash ~ byte  -- XOR
        hash = (hash * 0x01000193) & 0xFFFFFFFF  -- AND mask to 32 bits
    end
    return string.format("%08X", hash)
end

-- Validate pointer
local function is_valid_ptr(ptr)
    local bank = math.floor(ptr / 65536)
    local offset = ptr % 65536

    if not VALID_BANKS[bank] then return false end
    if ptr == 0xFFFFFF or ptr == 0x000000 then return false end
    if bank == 0xFF then return false end

    -- SA-1 banks E0-EF: full 64KB addressable
    if bank >= 0xC0 and bank <= 0xDF then
        if offset < 0x8000 then return false end
    end

    -- WRAM staging range
    if bank == 0x7E then
        if offset < 0x2000 or offset > 0x7FFF then return false end
    end

    return true
end

-- Read byte from memory (for record type detection)
local function read_byte(addr)
    local ok, val = pcall(function()
        return emu.read(addr, emu.memType.snesMemory)
    end)
    if ok then return val end
    return nil
end

-- Read bytes for hash
local function read_bytes(addr, count)
    local data = {}
    for i = 0, count - 1 do
        local ok, val = pcall(function()
            return emu.read(addr + i, emu.memType.snesMemory)
        end)
        if ok then
            data[i + 1] = val
        else
            data[i + 1] = 0
        end
    end
    return data
end

-- Close current session with optional staging attribution
local function close_session(reason, staging_info)
    if not active_session then return end

    active_session.close_reason = reason
    active_session.close_frame = frame_count

    if staging_info then
        active_session.staging = staging_info
        stats.sessions_with_dma = stats.sessions_with_dma + 1

        -- Update idx database with staging info
        local idx = active_session.idx
        if idx and idx_database[idx] then
            local db = idx_database[idx]
            db.dma_count = (db.dma_count or 0) + 1

            -- Track unique staging identities (wram range + hash)
            local staging_key = string.format("%06X_%04X_%s",
                staging_info.wram_start or 0, staging_info.size or 0, staging_info.hash or "")
            if not db.dma_identities then db.dma_identities = {} end
            if not db.dma_identities[staging_key] then
                db.dma_identities[staging_key] = {
                    wram_start = staging_info.wram_start,
                    wram_end = staging_info.wram_end,
                    size = staging_info.size,
                    hash = staging_info.hash,
                    count = 0,
                }
            end
            db.dma_identities[staging_key].count = db.dma_identities[staging_key].count + 1

            -- Track hash stability
            if not db.hashes then db.hashes = {} end
            if staging_info.hash then
                db.hashes[staging_info.hash] = (db.hashes[staging_info.hash] or 0) + 1
            end
        end
    end

    table.insert(completed_sessions, active_session)

    -- Log session close (first 50)
    if #completed_sessions <= 50 then
        local staging_str = ""
        if staging_info then
            staging_str = string.format(" STAGING wram=%06X size=%d hash=%s",
                staging_info.wram_start or 0, staging_info.size or 0, staging_info.hash or "?")
        end
        log(string.format("SESSION_CLOSE: id=%d idx=%s ptr=%s reason=%s%s",
            active_session.id, active_session.idx or "?",
            fmt_addr(active_session.ptr), reason, staging_str))
    end

    active_session = nil
end

-- Start new session from DP_PTR_SET
local function start_session(ptr, idx)
    -- Close any existing session first
    if active_session then
        close_session("new_ptr")
    end

    session_counter = session_counter + 1
    stats.sessions_created = stats.sessions_created + 1

    -- Get record type (first byte at pointer)
    local record_type = nil
    local bank = math.floor(ptr / 65536)
    if bank ~= 0x7E then  -- Don't read record type for WRAM pointers
        record_type = read_byte(ptr)
    end

    active_session = {
        id = session_counter,
        ptr = ptr,
        idx = idx,
        frame_start = frame_count,
        record_type = record_type,
        prg_reads = 0,
        dma = nil,
    }

    -- Update idx database
    if idx then
        if not idx_database[idx] then
            idx_database[idx] = {
                ptr = ptr,
                record_types = {},
                session_count = 0,
                dma_count = 0,
                dma_identities = {},
                hashes = {},
            }
        end
        local db = idx_database[idx]
        db.session_count = db.session_count + 1
        if record_type then
            db.record_types[record_type] = (db.record_types[record_type] or 0) + 1
        end
    end

    -- Log session start (first 50)
    if session_counter <= 50 then
        log(string.format("SESSION_START: id=%d idx=%s ptr=%s record=0x%02X frame=%d",
            session_counter, idx or "?", fmt_addr(ptr), record_type or 0, frame_count))
    end
end

-- A) ROM table read - collect into entry-level events
local function on_table_read(addr, value)
    if script_stopping then return nil end

    stats.raw_tbl_reads = stats.raw_tbl_reads + 1

    local offset_from_base = addr - TABLE_CPU_BASE
    local idx = math.floor(offset_from_base / ENTRY_SIZE)
    local byte_pos = offset_from_base % ENTRY_SIZE

    if not pending_tbl[idx] then
        pending_tbl[idx] = {lo = nil, hi = nil, bank = nil, frame = frame_count}
    end

    local entry = pending_tbl[idx]
    if byte_pos == 0 then entry.lo = value
    elseif byte_pos == 1 then entry.hi = value
    elseif byte_pos == 2 then entry.bank = value
    end
    entry.frame = frame_count

    -- Complete 3-byte entry
    if entry.lo and entry.hi and entry.bank then
        local ptr = entry.lo + (entry.hi * 256) + (entry.bank * 65536)
        stats.tbl_ptr_decoded = stats.tbl_ptr_decoded + 1

        if is_valid_ptr(ptr) then
            -- Track for linkage checking
            committed_ptrs[ptr] = true

            -- Populate idx_database immediately
            if not idx_database[idx] then
                idx_database[idx] = {
                    ptr = ptr,
                    record_types = {},
                    session_count = 0,
                    dma_count = 0,
                    dma_identities = {},
                    hashes = {},
                    first_frame = frame_count,
                }
            end

            if stats.tbl_ptr_decoded <= 100 then
                log(string.format("TBL_PTR: frame=%d idx=%d ptr=%s",
                    frame_count, idx, fmt_addr(ptr)))
            end
        end

        pending_tbl[idx] = nil
    end

    return nil
end

-- B) DP write - commit when 3-byte pointer complete
local function on_dp_write(addr, value)
    if script_stopping then return nil end

    local offset = addr % 256
    if offset < DP_PTR_BASE or offset > DP_PTR_BASE + 2 then
        return nil
    end

    stats.raw_dp_writes = stats.raw_dp_writes + 1

    local cpu_id = 0
    if not pending_dp[cpu_id] then
        pending_dp[cpu_id] = {lo = nil, hi = nil, bank = nil}
    end

    local pending = pending_dp[cpu_id]
    local byte_pos = offset - DP_PTR_BASE

    if byte_pos == 0 then
        pending.lo = value
        pending.lo_frame = frame_count
    elseif byte_pos == 1 then
        pending.hi = value
        pending.hi_frame = frame_count
    elseif byte_pos == 2 then
        pending.bank = value
        pending.bank_frame = frame_count
    end

    -- Complete and same-frame check
    if pending.lo and pending.hi and pending.bank then
        local max_frame = math.max(pending.lo_frame or 0, pending.hi_frame or 0, pending.bank_frame or 0)
        local min_frame = math.min(pending.lo_frame or 0, pending.hi_frame or 0, pending.bank_frame or 0)

        if max_frame - min_frame <= 1 then
            local ptr = pending.lo + (pending.hi * 256) + (pending.bank * 65536)

            if is_valid_ptr(ptr) then
                stats.dp_ptr_commits = stats.dp_ptr_commits + 1
                committed_ptrs[ptr] = true

                -- Find matching table index
                local matched_idx = nil
                for idx, db in pairs(idx_database) do
                    if db.ptr == ptr then
                        matched_idx = idx
                        break
                    end
                end

                -- Also check recent TBL_PTR events
                if not matched_idx then
                    -- Check if pointer matches known table entries
                    -- (simplified - in practice would track recent TBL_PTR events)
                end

                log(string.format("DP_PTR_SET: frame=%d ptr=%s idx=%s",
                    frame_count, fmt_addr(ptr), matched_idx or "?"))

                -- Update current_ptr cache
                current_ptr[cpu_id] = {
                    ptr = ptr,
                    frame = frame_count,
                    idx = matched_idx,
                }

                -- Start new session
                start_session(ptr, matched_idx)
            end

            pending_dp[cpu_id] = {lo = nil, hi = nil, bank = nil}
        end
    end

    return nil
end

-- C) PRG stream start detection
local prg_stream_active = nil
local prg_last_addr = nil

local function on_prg_read(addr, value)
    if script_stopping then return nil end

    local bank = math.floor(addr / 65536)
    if bank < 0xC0 then return nil end

    -- Detect stream start
    local is_new_stream = false
    if not prg_stream_active then
        is_new_stream = true
    elseif prg_last_addr and (addr ~= prg_last_addr + 1) and (addr ~= prg_last_addr) then
        if math.abs(addr - prg_last_addr) > 16 then
            is_new_stream = true
        end
    end

    if is_new_stream and bank >= 0xE0 then
        stats.prg_starts_total = stats.prg_starts_total + 1

        -- Check if this is a table-path stream (starts at committed ptr)
        local is_table_path = committed_ptrs[addr] ~= nil
        if is_table_path then
            stats.prg_starts_table_path = stats.prg_starts_table_path + 1
        end

        -- Check linkage against current_ptr
        local linked = false
        for cpu_id, cache in pairs(current_ptr) do
            if cache.ptr == addr then
                linked = true
                stats.prg_linked = stats.prg_linked + 1
                break
            end
        end

        -- Track reads in active session
        if active_session and active_session.ptr == addr then
            active_session.prg_reads = active_session.prg_reads + 1
        end

        prg_stream_active = addr
    end

    prg_last_addr = addr

    -- Track reads in active session
    if active_session then
        active_session.prg_reads = (active_session.prg_reads or 0) + 1
    end

    return nil
end

-- D) Staging buffer detection via WRAM writes
-- Watch writes to WRAM staging area (7E:2000-7E:2FFF)
-- This is where decoded asset data lands before VRAM transfer
--
-- Strategy: Track batches of writes to staging. When a batch completes
-- (no writes for N frames or new batch starts), capture the payload hash.

local staging_writes = {}       -- Current batch of writes {addr, value, frame}
local staging_write_count = 0   -- Total staging writes (debug)
local staging_batches = {}      -- Captured batches this frame
local staging_batch_count = 0   -- Total batches captured

-- Called when staging WRAM is written
local function on_staging_write(addr, value)
    if script_stopping then return nil end

    staging_write_count = staging_write_count + 1

    -- Track write
    table.insert(staging_writes, {
        addr = addr,
        value = value,
        frame = frame_count,
    })

    return nil
end

-- Process staging writes at end of frame
local function process_staging_writes()
    if #staging_writes == 0 then return end

    -- Group writes by frame
    local frames = {}
    for _, w in ipairs(staging_writes) do
        if not frames[w.frame] then
            frames[w.frame] = {}
        end
        table.insert(frames[w.frame], w)
    end

    -- Process each frame's writes
    for f, writes in pairs(frames) do
        -- Only consider significant batches (>=16 bytes, likely tile data)
        if #writes >= 16 then
            staging_batch_count = staging_batch_count + 1
            stats.staging_dmas = stats.staging_dmas + 1

            -- Sort by address
            table.sort(writes, function(a, b) return a.addr < b.addr end)

            local min_addr = writes[1].addr
            local max_addr = writes[#writes].addr
            local size = max_addr - min_addr + 1

            -- Compute hash from values
            local sample_data = {}
            for i = 1, math.min(64, #writes) do
                sample_data[i] = writes[i].value
            end
            local hash = compute_hash(sample_data, #sample_data)

            local batch_info = {
                frame = f,
                wram_start = min_addr,
                wram_end = max_addr,
                size = size,
                write_count = #writes,
                hash = hash,
            }

            -- Log first 50 batches
            if staging_batch_count <= 50 then
                log(string.format("STAGING: frame=%d wram=%06X-%06X size=%d writes=%d hash=%s",
                    f, min_addr, max_addr, size, #writes, hash))
            end

            table.insert(staging_batches, batch_info)
        end
    end

    staging_writes = {}
end

-- Attribute staging batches to sessions
local function process_staging_batches()
    for _, batch_info in ipairs(staging_batches) do
        -- Attribute to active session if same frame or within 2 frames
        if active_session and
           (batch_info.frame >= active_session.frame_start and
            batch_info.frame <= active_session.frame_start + 2) then
            close_session("staging_captured", batch_info)
        end
    end
    staging_batches = {}
end

-- Frame handler
local function on_frame()
    if script_stopping then return end
    frame_count = frame_count + 1

    -- Process staging writes from this frame
    process_staging_writes()

    -- Attribute staging batches to sessions
    process_staging_batches()

    -- Timeout active session
    if active_session and (frame_count - active_session.frame_start) >= SESSION_TIMEOUT then
        close_session("timeout")
    end

    -- Progress every 500 frames
    if frame_count % 500 == 0 then
        local linkage_rate = 0
        if stats.prg_starts_table_path > 0 then
            linkage_rate = stats.prg_linked / stats.prg_starts_table_path * 100
        end
        log(string.format("Frame %d: tbl=%d dp=%d prg_total=%d prg_table=%d linked=%d (%.1f%%) sessions=%d staging=%d writes=%d",
            frame_count, stats.tbl_ptr_decoded, stats.dp_ptr_commits,
            stats.prg_starts_total, stats.prg_starts_table_path, stats.prg_linked,
            linkage_rate, stats.sessions_created, stats.staging_dmas, staging_write_count))
    end

    if frame_count >= MAX_FRAMES then
        -- Process any remaining staging writes
        process_staging_writes()
        process_staging_batches()
        generate_summary()
        script_stopping = true
        emu.stop()
    end
end

function generate_summary()
    -- Close any remaining session
    if active_session then
        close_session("end_of_run")
    end

    log("")
    log(string.rep("=", 70))
    log("ASSET SELECTOR V3 SUMMARY")
    log(string.rep("=", 70))
    log(string.format("Frames analyzed: %d", frame_count))
    log("")

    -- Corrected linkage metric
    local linkage_rate = 0
    if stats.prg_starts_table_path > 0 then
        linkage_rate = stats.prg_linked / stats.prg_starts_table_path * 100
    end

    log("=== STATISTICS ===")
    log(string.format("  Table reads: %d raw → %d decoded", stats.raw_tbl_reads, stats.tbl_ptr_decoded))
    log(string.format("  DP commits: %d raw → %d valid", stats.raw_dp_writes, stats.dp_ptr_commits))
    log(string.format("  PRG streams: %d total, %d table-path", stats.prg_starts_total, stats.prg_starts_table_path))
    log(string.format("  Linked (table-path): %d / %d (%.1f%%)", stats.prg_linked, stats.prg_starts_table_path, linkage_rate))
    log(string.format("  Sessions: %d created, %d with staging", stats.sessions_created, stats.sessions_with_dma))
    log(string.format("  Staging WRAM writes: %d total", staging_write_count))
    log(string.format("  Staging batches captured: %d (>=16 bytes)", stats.staging_dmas))
    log("")

    -- Per-idx database report
    log("=== PER-INDEX DATABASE ===")
    local sorted_indices = {}
    for idx, _ in pairs(idx_database) do
        table.insert(sorted_indices, idx)
    end
    table.sort(sorted_indices)

    for _, idx in ipairs(sorted_indices) do
        local db = idx_database[idx]

        -- Get primary record type
        local primary_record = "?"
        local max_count = 0
        for rt, count in pairs(db.record_types) do
            if count > max_count then
                max_count = count
                primary_record = string.format("0x%02X", rt)
            end
        end

        -- Count unique hashes
        local hash_count = 0
        for _, _ in pairs(db.hashes or {}) do
            hash_count = hash_count + 1
        end
        local hash_stable = hash_count <= 1 and "STABLE" or string.format("%d variants", hash_count)

        -- Get top DMA identities
        local dma_list = {}
        for _, dma in pairs(db.dma_identities or {}) do
            table.insert(dma_list, dma)
        end
        table.sort(dma_list, function(a, b) return a.count > b.count end)

        log(string.format("  idx=%3d ptr=%s record=%s sessions=%d staging=%d hashes=%s",
            idx, fmt_addr(db.ptr), primary_record, db.session_count, db.dma_count, hash_stable))

        -- Show top 3 staging identities
        for i = 1, math.min(3, #dma_list) do
            local stg = dma_list[i]
            log(string.format("           STAGING: wram=%06X size=%d hash=%s (x%d)",
                stg.wram_start or 0, stg.size or 0, stg.hash or "?", stg.count))
        end
    end
    log("")

    -- Session summary
    log("=== SESSION SUMMARY ===")
    local sessions_by_reason = {}
    for _, sess in ipairs(completed_sessions) do
        local reason = sess.close_reason or "unknown"
        sessions_by_reason[reason] = (sessions_by_reason[reason] or 0) + 1
    end
    for reason, count in pairs(sessions_by_reason) do
        log(string.format("  %s: %d", reason, count))
    end
    log("")

    -- Committed pointers not in idx_database (unattributed)
    log("=== COMMITTED POINTERS (not via table reads) ===")
    local unattributed = {}
    for ptr, _ in pairs(committed_ptrs) do
        local found = false
        for idx, db in pairs(idx_database) do
            if db.ptr == ptr then
                found = true
                break
            end
        end
        if not found then
            table.insert(unattributed, ptr)
        end
    end
    table.sort(unattributed)
    log(string.format("  Count: %d", #unattributed))
    for i, ptr in ipairs(unattributed) do
        if i <= 20 then
            log(string.format("    %s", fmt_addr(ptr)))
        end
    end
    if #unattributed > 20 then
        log(string.format("    ... and %d more", #unattributed - 20))
    end
    log("")

    log(string.rep("=", 70))
    log("END SUMMARY")
    log(string.rep("=", 70))
end

-- Initialize
log("Asset Selector Tracer v3")
log(string.format("Started: %s", os.date()))
log(string.format("ROM table: %s - %s", fmt_addr(TABLE_CPU_BASE), fmt_addr(TABLE_CPU_END)))
log(string.format("DP pointer slot: 00:%04X-00:%04X", DP_PTR_BASE, DP_PTR_BASE + 2))
log(string.format("Staging WRAM (watch range): %s - %s", fmt_addr(STAGING_START), fmt_addr(STAGING_END)))
log(string.format("Session timeout: %d frames", SESSION_TIMEOUT))
log("Capturing staging buffer writes (>=16 bytes) for idx→payload attribution")
log("")

local snes_cpu = emu.cpuType and emu.cpuType.snes or nil
local sa1_cpu = emu.cpuType and emu.cpuType.sa1 or nil

-- Register callbacks
for _, cpu in ipairs({snes_cpu, sa1_cpu}) do
    if cpu then
        local cpu_name = fmt_cpu(cpu)

        pcall(function()
            emu.addMemoryCallback(on_table_read, emu.callbackType.read,
                TABLE_CPU_BASE, TABLE_CPU_END, cpu, emu.memType.snesMemory)
            log(string.format("%s: Table read callback registered", cpu_name))
        end)

        pcall(function()
            emu.addMemoryCallback(on_dp_write, emu.callbackType.write,
                0x000000, 0x0000FF, cpu, emu.memType.snesMemory)
            log(string.format("%s: DP write callback registered", cpu_name))
        end)

        pcall(function()
            emu.addMemoryCallback(on_prg_read, emu.callbackType.read,
                0, 0x3FFFFF, cpu, emu.memType.snesPrgRom)
            log(string.format("%s: PRG read callback registered", cpu_name))
        end)
    end
end

-- Staging WRAM write callback (7E:2000-7E:2FFF)
-- This fires when decoded asset data is written to staging buffer
for _, cpu in ipairs({snes_cpu, sa1_cpu}) do
    if cpu then
        pcall(function()
            emu.addMemoryCallback(on_staging_write, emu.callbackType.write,
                STAGING_START, STAGING_END, cpu, emu.memType.snesMemory)
            log(string.format("%s: Staging WRAM write callback registered (7E:2000-7E:2FFF)", fmt_cpu(cpu)))
        end)
    end
end

emu.addEventCallback(on_frame, emu.eventType.endFrame)
log("Frame callback registered")
log("")
log("Tracing with idx→DMA attribution...")
log("")
