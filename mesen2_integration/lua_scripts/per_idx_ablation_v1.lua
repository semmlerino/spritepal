-- Per-idx Ablation Tracer v1
-- Proves idx→ptr→staging payload causal chain via surgical ablation
--
-- Protocol:
--   1) Run BASELINE (ABLATION_ENABLED=false): capture staging identities per idx
--   2) Run ABLATION (ABLATION_ENABLED=true): corrupt ptr target, capture same DMA identities
--   3) Compare: same DMA identity (wram+size) should have different hash
--
-- Usage:
--   Configure ABLATION_TARGET_IDX below
--   Run twice: once baseline, once with ABLATION_ENABLED=true
--   Compare output files

-- ============================================================
-- ABLATION CONFIGURATION - EDIT THESE VALUES
-- ============================================================
local ABLATION_ENABLED = false      -- Set to true for ablation run
local ABLATION_TARGET_IDX = 6       -- Which idx to ablate
local ABLATION_MODE = "B"           -- "A" = 1 byte at ptr, "B" = at ptr+0x10

-- Target pointers from v3 results:
local IDX_TARGETS = {
    [5]  = {ptr = 0xE94D0A, record = 0x25, baseline_hash = "5F0BB905"},
    [6]  = {ptr = 0xE93AEB, record = 0xE0, baseline_hash = "B5143253"},
    [19] = {ptr = 0xE98DDF, record = 0x03, baseline_hash = "B254A8E4"},
    [40] = {ptr = 0xE9E667, record = 0xE0, baseline_hash = "EC8FF37F"},
    [43] = {ptr = 0xE9FB06, record = 0x00, baseline_hash = "232EE368"},
    [72] = {ptr = 0xE9677F, record = 0x1F, baseline_hash = "42AEE372"},  -- has 2 variants
}
-- ============================================================

local OUTPUT_DIR = os.getenv("OUTPUT_DIR") or "C:\\CustomScripts\\KirbyMax\\workshop\\exhal-master\\spritepal\\mesen2_exchange\\"
local MODE_STR = ABLATION_ENABLED and "ablation" or "baseline"
local LOG_FILE = OUTPUT_DIR .. string.format("ablation_idx%d_%s.log", ABLATION_TARGET_IDX, MODE_STR)
local MAX_FRAMES = 3000

local log_handle = nil
local frame_count = 0
local script_stopping = false

-- ROM pointer table
local TABLE_CPU_BASE = 0x01FE52
local TABLE_CPU_END = 0x01FFFF
local ENTRY_SIZE = 3

-- DP pointer slot
local DP_PTR_BASE = 0x0002

-- WRAM staging range
local STAGING_START = 0x7E2000
local STAGING_END = 0x7E2FFF

-- Ablation state
local ablation_applied = false
local original_bytes = {}

-- Valid asset banks
local VALID_BANKS = {
    [0xC0] = true, [0xC1] = true, [0xC2] = true, [0xC3] = true,
    [0xE0] = true, [0xE1] = true, [0xE2] = true, [0xE3] = true,
    [0xE4] = true, [0xE5] = true, [0xE6] = true, [0xE7] = true,
    [0xE8] = true, [0xE9] = true, [0xEA] = true, [0xEB] = true,
    [0xEC] = true, [0xED] = true, [0xEE] = true, [0xEF] = true,
    [0x7E] = true,
}

-- State tracking
local pending_tbl = {}
local pending_dp = {}
local current_ptr = {}
local committed_ptrs = {}

-- Session tracking
local active_session = nil
local completed_sessions = {}
local session_counter = 0
local SESSION_TIMEOUT = 4

-- Per-idx database
local idx_database = {}

-- DMA identity capture: key = "wram_size" → {hash_baseline, hash_ablation}
local dma_identities = {}

-- Statistics
local stats = {
    tbl_ptr_decoded = 0,
    dp_ptr_commits = 0,
    sessions_created = 0,
    sessions_with_staging = 0,
    target_sessions = 0,
    target_staging = 0,
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

-- FNV-1a hash (Lua 5.4 native bitwise ops)
local function compute_hash(data, len)
    local hash = 0x811c9dc5
    for i = 1, math.min(len, 64) do
        local byte = data[i] or 0
        hash = hash ~ byte
        hash = (hash * 0x01000193) & 0xFFFFFFFF
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
    if bank >= 0xC0 and bank <= 0xDF then
        if offset < 0x8000 then return false end
    end
    if bank == 0x7E then
        if offset < 0x2000 or offset > 0x7FFF then return false end
    end
    return true
end

-- Read from PRG ROM
local function read_prg_byte(cpu_addr)
    local ok, val = pcall(function()
        return emu.read(cpu_addr, emu.memType.snesMemory)
    end)
    if ok then return val end
    return nil
end

-- Write to PRG ROM (for ablation)
local function write_prg_byte(cpu_addr, value)
    local ok = pcall(function()
        emu.write(cpu_addr, value, emu.memType.snesMemory)
    end)
    return ok
end

-- Convert CPU address to PRG ROM offset
-- Kirby Super Star uses HiROM mapping with SA-1
-- Banks E0-EF map to PRG ROM with bank = (cpu_bank - 0xC0) for HiROM
local function cpu_to_prg_offset(cpu_addr)
    local bank = math.floor(cpu_addr / 65536)
    local offset = cpu_addr % 65536

    -- HiROM: banks C0-FF map directly
    -- PRG offset = ((bank & 0x3F) * 0x10000) + offset
    if bank >= 0xC0 then
        local prg_bank = bank - 0xC0
        return (prg_bank * 0x10000) + offset
    elseif bank >= 0x40 and bank < 0x80 then
        -- HiROM: 40-7D:0000-FFFF
        return ((bank - 0x40) * 0x10000) + offset
    else
        return nil
    end
end

-- Write to PRG ROM directly
local function write_prg_rom(cpu_addr, value)
    local prg_offset = cpu_to_prg_offset(cpu_addr)
    if not prg_offset then
        log(string.format("  Cannot convert %s to PRG offset", fmt_addr(cpu_addr)))
        return false
    end

    local ok = pcall(function()
        emu.write(prg_offset, value, emu.memType.snesPrgRom)
    end)
    return ok
end

-- Read from PRG ROM directly
local function read_prg_rom(cpu_addr)
    local prg_offset = cpu_to_prg_offset(cpu_addr)
    if not prg_offset then return nil end

    local ok, val = pcall(function()
        return emu.read(prg_offset, emu.memType.snesPrgRom)
    end)
    if ok then return val end
    return nil
end

-- Apply ablation to target idx
local function apply_ablation()
    if ablation_applied then return end
    if not ABLATION_ENABLED then return end

    local target = IDX_TARGETS[ABLATION_TARGET_IDX]
    if not target then
        log(string.format("ERROR: No target defined for idx=%d", ABLATION_TARGET_IDX))
        return
    end

    local ablation_addr = target.ptr
    local ablation_len = 1

    if ABLATION_MODE == "B" then
        ablation_addr = target.ptr + 0x10
    end

    local prg_offset = cpu_to_prg_offset(ablation_addr)
    log(string.format("ABLATION: Corrupting idx=%d at %s (PRG offset 0x%06X, mode %s)",
        ABLATION_TARGET_IDX, fmt_addr(ablation_addr), prg_offset or 0, ABLATION_MODE))

    -- Read original bytes via CPU address (for comparison)
    local orig_cpu = read_prg_byte(ablation_addr)
    local orig_prg = read_prg_rom(ablation_addr)
    log(string.format("  Before: CPU read=0x%02X, PRG read=0x%02X",
        orig_cpu or 0xFF, orig_prg or 0xFF))
    original_bytes[0] = orig_prg or orig_cpu

    -- Write corruption via PRG ROM memory type
    local success = write_prg_rom(ablation_addr, 0xFF)
    if success then
        log(string.format("  Wrote 0xFF to PRG offset 0x%06X", prg_offset or 0))
    else
        log(string.format("  FAILED to write via PRG ROM"))
        -- Fallback: try CPU address write
        success = write_prg_byte(ablation_addr, 0xFF)
        if success then
            log(string.format("  Fallback: wrote 0xFF via CPU address"))
        else
            log(string.format("  Fallback also FAILED"))
        end
    end

    -- Verify corruption took effect
    local verify_cpu = read_prg_byte(ablation_addr)
    local verify_prg = read_prg_rom(ablation_addr)
    log(string.format("  After: CPU read=0x%02X, PRG read=0x%02X",
        verify_cpu or 0xFF, verify_prg or 0xFF))

    if verify_cpu == 0xFF or verify_prg == 0xFF then
        log("  VERIFIED: Corruption applied successfully!")
    else
        log("  WARNING: Corruption may not have taken effect!")
        log("  (ROM may be read-only in this emulator build)")
    end

    ablation_applied = true
end

-- Close session with staging attribution
local function close_session(reason, staging_info)
    if not active_session then return end

    active_session.close_reason = reason
    active_session.close_frame = frame_count

    if staging_info then
        active_session.staging = staging_info
        stats.sessions_with_staging = stats.sessions_with_staging + 1

        -- Track if this is our target idx
        if active_session.idx == ABLATION_TARGET_IDX then
            stats.target_staging = stats.target_staging + 1
        end

        -- Capture DMA identity for comparison
        -- Key includes idx so each index tracks its own identities
        local idx_val = active_session.idx or 0
        local identity_key = string.format("%d_%06X_%04X",
            idx_val, staging_info.wram_start or 0, staging_info.size or 0)

        if not dma_identities[identity_key] then
            dma_identities[identity_key] = {
                wram_start = staging_info.wram_start,
                size = staging_info.size,
                hashes = {},
                idx = idx_val,
            }
        end

        table.insert(dma_identities[identity_key].hashes, {
            hash = staging_info.hash,
            frame = staging_info.frame,
            mode = MODE_STR,
        })

        -- Also update idx_database staging count
        if active_session.idx and idx_database[active_session.idx] then
            idx_database[active_session.idx].staging_count =
                (idx_database[active_session.idx].staging_count or 0) + 1
        end

        -- Log for target idx
        if active_session.idx == ABLATION_TARGET_IDX then
            log(string.format("[TARGET] SESSION_CLOSE: id=%d idx=%d ptr=%s",
                active_session.id, active_session.idx, fmt_addr(active_session.ptr)))
            log(string.format("[TARGET]   STAGING: wram=%06X size=%d hash=%s",
                staging_info.wram_start or 0, staging_info.size or 0, staging_info.hash or "?"))
        end
    end

    table.insert(completed_sessions, active_session)
    active_session = nil
end

-- Start new session
local function start_session(ptr, idx)
    if active_session then
        close_session("new_ptr")
    end

    session_counter = session_counter + 1
    stats.sessions_created = stats.sessions_created + 1

    local record_type = nil
    local bank = math.floor(ptr / 65536)
    if bank ~= 0x7E then
        record_type = read_prg_byte(ptr)
    end

    active_session = {
        id = session_counter,
        ptr = ptr,
        idx = idx,
        frame_start = frame_count,
        record_type = record_type,
    }

    if idx == ABLATION_TARGET_IDX then
        stats.target_sessions = stats.target_sessions + 1
        log(string.format("[TARGET] SESSION_START: id=%d idx=%d ptr=%s record=0x%02X frame=%d",
            session_counter, idx, fmt_addr(ptr), record_type or 0, frame_count))
    end

    -- Update idx database
    if idx then
        if not idx_database[idx] then
            idx_database[idx] = {
                ptr = ptr,
                session_count = 0,
                staging_count = 0,
                hashes = {},
            }
        end
        idx_database[idx].session_count = idx_database[idx].session_count + 1
    end
end

-- Table read callback
local function on_table_read(addr, value)
    if script_stopping then return nil end

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

    if entry.lo and entry.hi and entry.bank then
        local ptr = entry.lo + (entry.hi * 256) + (entry.bank * 65536)
        stats.tbl_ptr_decoded = stats.tbl_ptr_decoded + 1

        if is_valid_ptr(ptr) then
            committed_ptrs[ptr] = true

            if not idx_database[idx] then
                idx_database[idx] = {
                    ptr = ptr,
                    session_count = 0,
                    staging_count = 0,
                    hashes = {},
                    first_frame = frame_count,
                }
            end

            if idx == ABLATION_TARGET_IDX then
                log(string.format("[TARGET] TBL_PTR: frame=%d idx=%d ptr=%s",
                    frame_count, idx, fmt_addr(ptr)))
            end
        end

        pending_tbl[idx] = nil
    end

    return nil
end

-- DP write callback
local function on_dp_write(addr, value)
    if script_stopping then return nil end

    local offset = addr % 256
    if offset < DP_PTR_BASE or offset > DP_PTR_BASE + 2 then
        return nil
    end

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

    if pending.lo and pending.hi and pending.bank then
        local max_frame = math.max(pending.lo_frame or 0, pending.hi_frame or 0, pending.bank_frame or 0)
        local min_frame = math.min(pending.lo_frame or 0, pending.hi_frame or 0, pending.bank_frame or 0)

        if max_frame - min_frame <= 1 then
            local ptr = pending.lo + (pending.hi * 256) + (pending.bank * 65536)

            if is_valid_ptr(ptr) then
                stats.dp_ptr_commits = stats.dp_ptr_commits + 1
                committed_ptrs[ptr] = true

                -- Find matching idx
                local matched_idx = nil
                for idx, db in pairs(idx_database) do
                    if db.ptr == ptr then
                        matched_idx = idx
                        break
                    end
                end

                current_ptr[cpu_id] = {
                    ptr = ptr,
                    frame = frame_count,
                    idx = matched_idx,
                }

                if matched_idx == ABLATION_TARGET_IDX then
                    log(string.format("[TARGET] DP_PTR_SET: frame=%d ptr=%s idx=%d",
                        frame_count, fmt_addr(ptr), matched_idx))
                end

                start_session(ptr, matched_idx)
            end

            pending_dp[cpu_id] = {lo = nil, hi = nil, bank = nil}
        end
    end

    return nil
end

-- Staging write tracking
local staging_writes = {}
local staging_write_count = 0
local staging_batches = {}

local function on_staging_write(addr, value)
    if script_stopping then return nil end

    staging_write_count = staging_write_count + 1
    table.insert(staging_writes, {
        addr = addr,
        value = value,
        frame = frame_count,
    })

    return nil
end

local function process_staging_writes()
    if #staging_writes == 0 then return end

    local frames = {}
    for _, w in ipairs(staging_writes) do
        if not frames[w.frame] then
            frames[w.frame] = {}
        end
        table.insert(frames[w.frame], w)
    end

    for f, writes in pairs(frames) do
        if #writes >= 16 then
            table.sort(writes, function(a, b) return a.addr < b.addr end)

            local min_addr = writes[1].addr
            local max_addr = writes[#writes].addr
            local size = max_addr - min_addr + 1

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

            table.insert(staging_batches, batch_info)
        end
    end

    staging_writes = {}
end

local function process_staging_batches()
    for _, batch_info in ipairs(staging_batches) do
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

    -- Apply ablation on first frame
    if frame_count == 1 and ABLATION_ENABLED then
        apply_ablation()
    end

    process_staging_writes()
    process_staging_batches()

    if active_session and (frame_count - active_session.frame_start) >= SESSION_TIMEOUT then
        close_session("timeout")
    end

    if frame_count % 1000 == 0 then
        log(string.format("Frame %d: target_sessions=%d target_staging=%d total_sessions=%d",
            frame_count, stats.target_sessions, stats.target_staging, stats.sessions_created))
    end

    if frame_count >= MAX_FRAMES then
        process_staging_writes()
        process_staging_batches()
        generate_summary()
        script_stopping = true
        emu.stop()
    end
end

function generate_summary()
    if active_session then
        close_session("end_of_run")
    end

    log("")
    log(string.rep("=", 70))
    log(string.format("PER-IDX ABLATION %s: idx=%d", string.upper(MODE_STR), ABLATION_TARGET_IDX))
    log(string.rep("=", 70))
    log(string.format("Mode: %s", ABLATION_ENABLED and "ABLATION" or "BASELINE"))
    log(string.format("Target idx: %d", ABLATION_TARGET_IDX))

    local target = IDX_TARGETS[ABLATION_TARGET_IDX]
    if target then
        log(string.format("Target ptr: %s", fmt_addr(target.ptr)))
        log(string.format("Expected record type: 0x%02X", target.record))
        log(string.format("Expected baseline hash: %s", target.baseline_hash))
    end
    log("")

    if ABLATION_ENABLED then
        log("ABLATION APPLIED:")
        if ABLATION_MODE == "A" then
            log(string.format("  Corrupted 1 byte at ptr (%s)", fmt_addr(target.ptr)))
        else
            log(string.format("  Corrupted 1 byte at ptr+0x10 (%s)", fmt_addr(target.ptr + 0x10)))
        end
        for i, orig in pairs(original_bytes) do
            log(string.format("  Original[%d]: 0x%02X → 0xFF", i, orig))
        end
        log("")
    end

    log("=== STATISTICS ===")
    log(string.format("  Frames analyzed: %d", frame_count))
    log(string.format("  Total sessions: %d", stats.sessions_created))
    log(string.format("  Sessions with staging: %d", stats.sessions_with_staging))
    log(string.format("  TARGET idx=%d sessions: %d", ABLATION_TARGET_IDX, stats.target_sessions))
    log(string.format("  TARGET idx=%d staging captures: %d", ABLATION_TARGET_IDX, stats.target_staging))
    log("")

    log("=== DMA IDENTITIES FOR TARGET IDX ===")
    local target_identities = {}
    for key, identity in pairs(dma_identities) do
        if identity.idx == ABLATION_TARGET_IDX then
            table.insert(target_identities, identity)
        end
    end

    if #target_identities == 0 then
        log("  No staging captures for target idx!")
        log("  (Possible: decode bailed, different path taken, or no session matched)")
    else
        for _, identity in ipairs(target_identities) do
            log(string.format("  Identity: wram=%06X size=%d", identity.wram_start, identity.size))
            for _, h in ipairs(identity.hashes) do
                log(string.format("    frame=%d hash=%s mode=%s", h.frame, h.hash, h.mode))
            end
        end
    end
    log("")

    -- Summary table for all captured identities (for diffing)
    log("=== PROOF DATA (for diff) ===")
    log(string.format("MODE=%s IDX=%d", MODE_STR, ABLATION_TARGET_IDX))
    for _, identity in ipairs(target_identities) do
        for _, h in ipairs(identity.hashes) do
            log(string.format("DMA wram=%06X size=%04X hash=%s",
                identity.wram_start, identity.size, h.hash))
        end
    end
    log("")

    -- idx database summary
    log("=== ALL INDICES WITH STAGING ===")
    local sorted_indices = {}
    for idx, _ in pairs(idx_database) do
        table.insert(sorted_indices, idx)
    end
    table.sort(sorted_indices)

    for _, idx in ipairs(sorted_indices) do
        local db = idx_database[idx]
        if db.session_count > 0 then
            local hash_count = 0
            local hash_list = {}
            for key, identity in pairs(dma_identities) do
                if identity.idx == idx then
                    for _, h in ipairs(identity.hashes) do
                        hash_count = hash_count + 1
                        hash_list[h.hash] = (hash_list[h.hash] or 0) + 1
                    end
                end
            end

            local unique_hashes = 0
            local hash_str = ""
            for h, count in pairs(hash_list) do
                unique_hashes = unique_hashes + 1
                if hash_str == "" then
                    hash_str = string.format("%s(x%d)", h, count)
                else
                    hash_str = hash_str .. ", " .. string.format("%s(x%d)", h, count)
                end
            end

            local marker = ""
            if idx == ABLATION_TARGET_IDX then
                marker = " <<<TARGET"
            end

            log(string.format("  idx=%3d ptr=%s sessions=%d staging=%d hashes=%s%s",
                idx, fmt_addr(db.ptr), db.session_count, hash_count,
                hash_str ~= "" and hash_str or "none", marker))
        end
    end

    log("")
    log(string.rep("=", 70))
    log("END ABLATION REPORT")
    log(string.rep("=", 70))
end

-- Initialize
log("Per-idx Ablation Tracer v1")
log(string.format("Started: %s", os.date()))
log(string.format("Mode: %s", MODE_STR))
log(string.format("Target idx: %d", ABLATION_TARGET_IDX))
log(string.format("Ablation mode: %s", ABLATION_MODE))
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
            emu.addMemoryCallback(on_staging_write, emu.callbackType.write,
                STAGING_START, STAGING_END, cpu, emu.memType.snesMemory)
            log(string.format("%s: Staging WRAM write callback registered", cpu_name))
        end)
    end
end

emu.addEventCallback(on_frame, emu.eventType.endFrame)
log("Frame callback registered")
log("")
log(string.format("Tracing %s for idx=%d...", MODE_STR, ABLATION_TARGET_IDX))
log("")
