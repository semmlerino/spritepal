-- DMA/SA-1 probe for sprite upload diagnostics (headless-safe)
-- =============================================================================
-- INSTRUMENTATION CONTRACT v1.1
--
-- SECTION MAP:
--   1. BOOTSTRAP & CONFIG    - Version, output dirs, env var parsing
--   2. LOGGING SERVICE       - Log file init/close, log() function
--   3. MEMORY TYPE RESOLUTION- MEM table, CPU types
--   4. UTILITIES             - parse_int, get_cpu_state_snapshot, callbacks
--   5. DMA TRACKER           - Shadow registers, VRAM addr, channel logging
--   6. SA-1 TRACKER          - Bank mapping, CCDMA detection
--   7. STAGING BUFFER WATCHER- Ring buffers, causal pairing, summaries
--   8. DMA COMPARISON        - Deferred VRAM verification (at frame end)
--   9. FRAME DETECTION       - Frame counter, endFrame/exec callbacks
--  10. CALLBACK REGISTRATION - Wire up all callbacks
--  11. INITIALIZATION        - Final setup, error handling
-- =============================================================================

-- =============================================================================
-- SECTION 1: BOOTSTRAP & CONFIG
-- Environment variables, output paths, version info
-- =============================================================================
local LOG_VERSION = "1.7"
local RUN_ID = string.format("%d_%04x", os.time(), math.random(0, 0xFFFF))

-- Persistent log file handle (opened once, closed on script end)
local log_file_handle = nil
local cached_rom_info = nil  -- Cached at init to avoid repeated emu.getRomInfo() calls

local DEFAULT_OUTPUT = "C:\\CustomScripts\\KirbyMax\\workshop\\exhal-master\\"
    .. "spritepal\\mesen2_exchange\\"
local OUTPUT_DIR = os.getenv("OUTPUT_DIR") or DEFAULT_OUTPUT
local SAVESTATE_PATH = os.getenv("SAVESTATE_PATH")
local PRELOADED_STATE = os.getenv("PRELOADED_STATE") == "1"
local FRAME_EVENT = os.getenv("FRAME_EVENT")
local MASTER_CLOCK_FALLBACK = os.getenv("MASTER_CLOCK_FALLBACK")
local MASTER_CLOCK_FPS = tonumber(os.getenv("MASTER_CLOCK_FPS"))
local MASTER_CLOCK_MAX_SECONDS = tonumber(os.getenv("MASTER_CLOCK_MAX_SECONDS"))
local MAX_FRAMES = tonumber(os.getenv("MAX_FRAMES")) or 300

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
os.execute('mkdir "' .. OUTPUT_DIR:gsub("\\", "\\\\") .. '" 2>NUL')

local LOG_FILE = OUTPUT_DIR .. "dma_probe_log.txt"

-- =============================================================================
-- SECTION 2: LOGGING SERVICE
-- Log file management and the core log() function
-- =============================================================================

-- Get ROM info for header (best effort - may not have SHA256)
-- Note: MEM may not be defined yet when this is first called, so check for it
local function get_rom_info()
    local info = {}
    local ok, rom_info = pcall(emu.getRomInfo)
    if ok and rom_info then
        info.name = rom_info.name or "unknown"
        info.sha256 = rom_info.sha256 or rom_info.fileSha256 or "N/A"
    else
        info.name = "unknown"
        info.sha256 = "N/A"
    end
    -- Get PRG size if available (MEM defined later in file)
    if MEM and MEM.prg then
        local ok2, size = pcall(emu.getMemorySize, MEM.prg)
        if ok2 then
            info.prg_size = size
        end
    end
    return info
end

-- Open log file once at script start (call after OUTPUT_DIR is set)
local function init_log_file()
    if log_file_handle then return true end
    log_file_handle = io.open(LOG_FILE, "w")  -- "w" to start fresh each run
    return log_file_handle ~= nil
end

-- Close log file (call on script end)
local function close_log_file()
    if log_file_handle then
        log_file_handle:close()
        log_file_handle = nil
    end
end

-- Write header after MEM types are resolved (so we can get PRG size)
local function write_log_header()
    if not log_file_handle then return end
    -- Cache ROM info once (expensive call)
    if not cached_rom_info then
        cached_rom_info = get_rom_info()
    end
    local header = string.format(
        "# LOG_VERSION=%s RUN_ID=%s ROM=%s SHA256=%s PRG_SIZE=%s\n",
        LOG_VERSION,
        RUN_ID,
        cached_rom_info.name or "unknown",
        cached_rom_info.sha256 or "N/A",
        cached_rom_info.prg_size and string.format("0x%X", cached_rom_info.prg_size) or "N/A"
    )
    log_file_handle:write(header)
    log_file_handle:flush()
end

local log_line_count = 0
local LOG_FLUSH_INTERVAL = 100  -- Flush every N lines for crash safety

local function log(msg)
    if not log_file_handle then
        -- Fallback: try to init if not done
        if not init_log_file() then return end
    end
    log_file_handle:write(os.date("%H:%M:%S") .. " " .. msg .. "\n")
    log_line_count = log_line_count + 1
    -- Periodic flush for crash safety (not every line for performance)
    if log_line_count % LOG_FLUSH_INTERVAL == 0 then
        log_file_handle:flush()
    end
end

-- Initialize log file immediately
init_log_file()

-- =============================================================================
-- SECTION 3: MEMORY TYPE RESOLUTION
-- Resolve emu.memType and emu.cpuType constants for callback registration
-- =============================================================================

-- Memory type names verified from Mesen2/Core/Shared/MemoryType.h
-- LuaApi.cpp lowercases the first letter: SnesPrgRom -> snesPrgRom
local MEM = {
    cpu = emu.memType.snesMemory,         -- SnesMemory
    prg = emu.memType.snesPrgRom,         -- SnesPrgRom
    vram = emu.memType.snesVideoRam,      -- SnesVideoRam
    wram = emu.memType.snesWorkRam,       -- SnesWorkRam
    oam = emu.memType.snesSpriteRam,      -- SnesSpriteRam
    cgram = emu.memType.snesCgRam,        -- SnesCgRam
    sa1_iram = emu.memType.sa1InternalRam, -- Sa1InternalRam
}
if not MEM.cpu then
    log("ERROR: could not resolve CPU memory type; aborting")
    emu.stop(2)
    return
end
if not MEM.vram then
    log("WARNING: could not resolve VRAM memory type; VRAM memType writes will not be logged")
end
if not MEM.prg then
    log("WARNING: could not resolve PRG ROM memory type; ROM read tracking will not work")
end
if not MEM.wram then
    log("WARNING: could not resolve WRAM memory type; WRAM source tracking will not work")
end

-- Write log header now that MEM is defined (for PRG size)
write_log_header()

-- Log resolved memory types for debugging
log(string.format("MEM types resolved: cpu=%s prg=%s vram=%s wram=%s oam=%s cgram=%s sa1_iram=%s",
    tostring(MEM.cpu), tostring(MEM.prg), tostring(MEM.vram), tostring(MEM.wram),
    tostring(MEM.oam), tostring(MEM.cgram), tostring(MEM.sa1_iram)))

-- CPU type names verified from Mesen2/Core/Shared/CpuType.h
-- LuaApi.cpp lowercases the first letter: Snes -> snes, Sa1 -> sa1
local cpu_type = emu.cpuType and emu.cpuType.snes or nil
local sa1_cpu_type = emu.cpuType and emu.cpuType.sa1 or nil

log(string.format("CPU types resolved: snes=%s sa1=%s", tostring(cpu_type), tostring(sa1_cpu_type)))

-- =============================================================================
-- SECTION 4: UTILITIES
-- Helper functions: parse_int, get_cpu_state_snapshot, callback registration
-- =============================================================================

local function add_memory_callback_compat(callback, cb_type, start_addr, end_addr, cb_cpu_type, mem_type)
    -- FIXED: Actually use the requested cpuType parameter instead of ignoring it
    local use_cpu_type = cb_cpu_type or cpu_type

    if use_cpu_type ~= nil and mem_type ~= nil then
        local ok, id = pcall(emu.addMemoryCallback, callback, cb_type, start_addr, end_addr, use_cpu_type, mem_type)
        if ok then
            return id
        end
    end
    if use_cpu_type ~= nil then
        local ok, id = pcall(emu.addMemoryCallback, callback, cb_type, start_addr, end_addr, use_cpu_type)
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

local function parse_int(value, default_value)
    if value == nil then
        return default_value
    end
    if type(value) == "number" then
        return value
    end
    local text = tostring(value)
    if text:sub(1, 2) == "0x" or text:sub(1, 2) == "0X" then
        return tonumber(text:sub(3), 16) or default_value
    end
    return tonumber(text) or default_value
end

local vram_inc_mode = 0
local vram_inc_value = 1
local last_master_clock = nil
local last_state_frame = nil
local last_sa1_dma_irq = nil

-- Consolidated configuration table to stay under Lua's 200 local variable limit
local CFG = {
    -- General
    heartbeat_every = tonumber(os.getenv("HEARTBEAT_EVERY")) or 0,
    dma_dump_on_vram = os.getenv("DMA_DUMP_ON_VRAM") ~= "0",
    dma_dump_max = tonumber(os.getenv("DMA_DUMP_MAX")) or 20,
    dma_dump_min_size = tonumber(os.getenv("DMA_DUMP_MIN_SIZE")) or 1,
    dma_dump_max_size = tonumber(os.getenv("DMA_DUMP_MAX_SIZE")) or 16384,  -- 16KB max per dump
    dma_compare_enabled = os.getenv("DMA_COMPARE_ENABLED") ~= "0",
    dma_compare_max = tonumber(os.getenv("DMA_COMPARE_MAX")) or 50,
    dma_compare_sample_bytes = tonumber(os.getenv("DMA_COMPARE_SAMPLE_BYTES")) or 32,
}
-- Dependent config values
CFG.dma_dump_start_frame = tonumber(os.getenv("DMA_DUMP_START_FRAME")) or 0

-- WRAM memory type resolution (used by staging watch)
local wram_mem_type = MEM.wram
local wram_address_mode = "relative"
if not wram_mem_type then
    -- Fallback: use CPU memory with absolute WRAM addresses
    wram_mem_type = MEM.cpu
    wram_address_mode = "absolute"
end
local dma_read_mem = MEM.cpu_debug or MEM.cpu
local dma_dump_count = 0
local dma_compare_count = 0

-- =============================================================================
-- SECTION 5: DMA TRACKER
-- Shadow DMA channel registers, VRAM address tracking, DMA channel logging
-- Hot paths: on_dma_enable (per-DMA), on_dma_reg_write (per-register)
-- =============================================================================

-- DMA register shadowing: capture values AS THEY ARE WRITTEN (before $420B triggers DMA)
-- This avoids reading post-DMA state where DAS=0 and VMADD may have changed
local dma_shadow = {}
for ch = 0, 7 do
    dma_shadow[ch] = {
        dmap = 0,        -- $43x0: DMA control
        bbad = 0,        -- $43x1: B-bus address
        a1t_lo = 0,      -- $43x2: A1T low
        a1t_hi = 0,      -- $43x3: A1T high
        a1b = 0,         -- $43x4: A1B (bank)
        das_lo = 0,      -- $43x5: DAS low
        das_hi = 0,      -- $43x6: DAS high
    }
end
-- Shadow VRAM address at time of last $2116/$2117 write
local vram_addr_shadow = 0

-- Queue for deferred DMA comparisons (executed at frame end, after DMA completes)
local pending_dma_compares = {}

-- Frame counter (moved up to be available for staging watch)
local frame_count = 0

-- Canonical frame source (per Instrumentation Contract v1.1)
-- Use last_state_frame if a savestate was loaded, else use frame_count
local function get_canonical_frame()
    return last_state_frame or frame_count
end

-- Get CPU state snapshot for PC samples
local function get_cpu_state_snapshot()
    local state = emu.getState and emu.getState() or nil
    if not state then
        return nil
    end
    local function pick(candidates)
        for _, key in ipairs(candidates) do
            local value = state[key]
            if value ~= nil then
                return key, value
            end
        end
        return nil, nil
    end
    local pc_key, pc_val = pick({"cpu.pc", "pc", "cpu.PC", "PC"})
    local k_key, k_val = pick({"cpu.k", "k", "cpu.K", "K"})
    local dbr_key, dbr_val = pick({"cpu.dbr", "dbr", "cpu.DBR", "DBR"})
    if pc_val == nil and k_val == nil and dbr_val == nil then
        return nil
    end
    return {
        pc_key = pc_key,
        pc_val = pc_val or 0,
        k_key = k_key,
        k_val = k_val or 0,
        dbr_key = dbr_key,
        dbr_val = dbr_val or 0,
        -- Aliases for downstream code that uses .pc/.k/.dbr
        pc = pc_val or 0,
        k = k_val or 0,
        dbr = dbr_val or 0
    }
end

-- =============================================================================
-- SECTION 7: STAGING BUFFER WATCHER
-- Ring buffers, read→write pairing, summary logging for DMA source analysis
-- Hot paths: on_staging_write (per-write), make_staging_wram_source_reader (per-read)
-- =============================================================================
local STAGING_WATCH_ENABLED = os.getenv("STAGING_WATCH_ENABLED") == "1"
local STAGING_WATCH_START = tonumber(os.getenv("STAGING_WATCH_START") or "0x2000", 16) or 0x2000
local STAGING_WATCH_END = tonumber(os.getenv("STAGING_WATCH_END") or "0x2FFF", 16) or 0x2FFF
local STAGING_WATCH_PC_SAMPLES = tonumber(os.getenv("STAGING_WATCH_PC_SAMPLES")) or 4
local STAGING_HISTORY_FRAMES = tonumber(os.getenv("STAGING_HISTORY_FRAMES")) or 3
local STAGING_START_FRAME = tonumber(os.getenv("STAGING_START_FRAME")) or 0
-- STAGING_CAUSAL disabled: PRG read callbacks are permanently off (timeout risk)
-- Env var STAGING_CAUSAL_ENABLED is ignored. Use STAGING_WRAM_SOURCE instead.
local STAGING_CAUSAL_ENABLED = false

-- WRAM read tracking: detect intermediate buffer pattern (PRG → WRAM → staging)
-- WARNING: DEBUG-ONLY. EXPECT TIMEOUTS. Callbacks fire on every WRAM read (~120KB).
-- Use only for short, controlled runs investigating intermediate buffer patterns.
-- Default OFF - will freeze/timeout the emulator under normal use.
local STAGING_WRAM_TRACKING_ENABLED = os.getenv("STAGING_WRAM_TRACKING") == "1"

-- STAGING_WRAM_SOURCE: Track what WRAM region the staging writer reads FROM
-- This is the KEY feature: reveals the intermediate buffer address range
-- that feeds staging. Once known, we trace who writes to THAT buffer.
-- Default OFF; enable with narrow range first (0x0000-0x1FFF), widen if needed
local STAGING_WRAM_SOURCE_ENABLED = os.getenv("STAGING_WRAM_SOURCE") == "1"
local STAGING_WRAM_SRC_START = parse_int(os.getenv("STAGING_WRAM_SRC_START"), 0x0000)
local STAGING_WRAM_SRC_END = parse_int(os.getenv("STAGING_WRAM_SRC_END"), 0x1FFF)

-- Ring buffer size for read tracking (per CPU)
-- Larger buffer captures more context; 32 is enough for typical copy loops
local RING_BUFFER_SIZE = tonumber(os.getenv("STAGING_RING_SIZE")) or 32

-- Per-frame staging write stats
local staging_frame_stats = {}  -- [frame] = {stats}
local staging_current_frame = nil
local staging_current_stats = nil

-- ROM read tracking during staging fills
local staging_active = false
local staging_first_pc = nil  -- PC that started the fill

-- ============================================================================
-- CAUSAL READ→WRITE TRACKING
-- Track which PRG reads actually feed staging writes (not just correlation)
-- Also track WRAM reads to detect intermediate buffer pattern:
--   PRG → WRAM buffer → staging ($7E:2000) → VRAM
-- ============================================================================
-- Ring buffers for PRG reads (per CPU)
-- Each entry: {addr = prg_offset, frame = frame, seq = sequence_number, read_pc = pc, read_k = bank}
local prg_ring_buffer = {
    snes = {},  -- Ring buffer array
    sa1 = {}
}
local prg_ring_head = {
    snes = 0,  -- Current head index (1-based, wraps at RING_BUFFER_SIZE)
    sa1 = 0
}

-- Ring buffers for WRAM source reads (per CPU)
-- Tracks what WRAM region the staging copy routine reads FROM
local wram_src_ring_buffer = {
    snes = {},
    sa1 = {}
}
local wram_src_ring_head = {
    snes = 0,
    sa1 = 0
}

local read_sequence = 0  -- Global sequence counter for ordering (shared between PRG and WRAM reads)

-- Flag to skip scanning empty ring buffer (reset in reset_staging_tracking)
local wram_src_seen_any = 0  -- Nonzero if we've pushed to WRAM source ring buffer this session

-- Helper: push to ring buffer
local function push_ring(buffer, head_table, cpu_label, entry)
    local head = (head_table[cpu_label] % RING_BUFFER_SIZE) + 1
    head_table[cpu_label] = head
    buffer[cpu_label][head] = entry
end

-- Helper: find best read from ring buffer (most recent with seq >= min_seq)
local function find_best_read_from_rings(ring_buffers, min_seq)
    local best_read = nil
    local best_cpu = nil
    local best_seq = -1

    for cpu_label, buffer in pairs(ring_buffers) do
        for i = 1, RING_BUFFER_SIZE do
            local entry = buffer[i]
            if entry and entry.seq >= min_seq and entry.seq > best_seq then
                best_read = entry
                best_cpu = cpu_label
                best_seq = entry.seq
            end
        end
    end

    return best_read, best_cpu
end

-- Helper: mark a ring buffer entry as consumed (prevent double-pairing)
local function consume_ring_entry(ring_buffers, cpu_label, seq)
    local buffer = ring_buffers[cpu_label]
    for i = 1, RING_BUFFER_SIZE do
        if buffer[i] and buffer[i].seq == seq then
            buffer[i] = nil
            return
        end
    end
end

-- Known staging copy routine PCs (for PC-gated filtering)
-- These are discovered from log analysis; add more as we learn them
-- Format: [(k<<16)|pc] = true (24-bit addressing: bank + PC)
local STAGING_COPY_PCS = {
    -- Bank $00 routines (cutscenes, some gameplay)
    [0x00893D] = true,  -- Bank $00, PC $893D
    [0x008952] = true,  -- Bank $00, PC $8952
    [0x008966] = true,  -- Bank $00, PC $8966
    [0x00897A] = true,  -- Bank $00, PC $897A
    -- Bank $01 routines (gameplay - discovered from STAGING_SUMMARY logs)
    [0x018FA9] = true,  -- Bank $01, PC $8FA9 (most common gameplay staging writer)
    [0x019927] = true,  -- Bank $01, PC $9927
    [0x01E409] = true,  -- Bank $01, PC $E409
}
-- Enable PC-gating via env var (default off for discovery mode)
local STAGING_PC_GATING_ENABLED = os.getenv("STAGING_PC_GATING") == "1"

-- Read→write pairs for this staging fill
-- Format: {read_prg, read_pc, read_k, write_wram, write_pc, write_k, cpu}
local staging_read_write_pairs = {}
local staging_pair_total = 0  -- True count (not capped like the pairs array)

-- Summary: which PRG regions fed writes (aggregated)
-- Format: [prg_offset] = {count = N, cpus = {snes = n1, sa1 = n2}}
local staging_prg_sources = {}

-- Summary: which WRAM regions the staging writer reads FROM (aggregated)
-- This reveals if staging is fed from an intermediate WRAM buffer
-- Format: [wram_offset] = {count = N, cpus = {snes = n1, sa1 = n2}}
local staging_wram_sources = {}
local staging_wram_read_write_pairs = {}
local staging_wram_pair_total = 0

local function init_staging_stats()
    return {
        count = 0,
        unique_addrs = {},  -- set: addr -> true
        unique_count = 0,
        min_addr = nil,
        max_addr = nil,
        last_addr = nil,
        sequential_count = 0,  -- addr == last + 1
        jump_count = 0,        -- addr != last + 1 (non-sequential)
        pc_samples = {},       -- {pc, addr} pairs
        first_write_addr = nil,
        last_write_addr = nil,
    }
end

-- Reset staging tracking for new fill
local function reset_staging_tracking()
    staging_first_pc = nil
    staging_active = false
    last_staging_write_frame = nil
    staging_session_start_seq = nil
    -- Reset PRG ring buffers
    prg_ring_buffer.snes = {}
    prg_ring_buffer.sa1 = {}
    prg_ring_head.snes = 0
    prg_ring_head.sa1 = 0
    staging_read_write_pairs = {}
    staging_pair_total = 0
    staging_prg_sources = {}
    -- Reset WRAM source ring buffers
    wram_src_ring_buffer.snes = {}
    wram_src_ring_buffer.sa1 = {}
    wram_src_ring_head.snes = 0
    wram_src_ring_head.sa1 = 0
    staging_wram_read_write_pairs = {}
    staging_wram_pair_total = 0
    staging_wram_sources = {}
    -- Reset ring buffer count (gate for hot-path scanning)
    wram_src_seen_any = 0
end

-- Track frame of last staging write (for logging)
local last_staging_write_frame = nil

-- Session-based gating: sequence number when staging session started
-- Reads with seq >= this value are part of the current session
local staging_session_start_seq = nil

-- Format PRG offset as hex (NOT a SNES bus address)
local function format_prg_offset(prg_offset)
    return string.format("0x%06X", prg_offset)
end

-- Log CAUSAL read→write summary (PRG reads → staging writes)
-- NOTE: STAGING_CAUSAL is permanently disabled (PRG callbacks cause timeout)
-- This function is retained for reference but always returns early.
local function log_staging_causal_summary(frame, vram_addr, dma_size)
    if not STAGING_CAUSAL_ENABLED then return end  -- Always disabled

    -- Use staging_pair_total for accurate count (array is capped at 1000)
    if staging_pair_total == 0 or not staging_active then return end
    local pairs_logged = #staging_read_write_pairs

    -- Aggregate PRG sources into runs (similar to old format)
    local prg_addrs = {}
    for addr, _ in pairs(staging_prg_sources) do
        prg_addrs[#prg_addrs + 1] = addr
    end
    table.sort(prg_addrs)

    -- Build runs from sorted addresses
    local runs = {}
    if #prg_addrs > 0 then
        local run_start = prg_addrs[1]
        local run_end = prg_addrs[1]
        for i = 2, #prg_addrs do
            local addr = prg_addrs[i]
            if addr == run_end + 1 then
                run_end = addr
            else
                runs[#runs + 1] = {start = run_start, stop = run_end}
                run_start = addr
                run_end = addr
            end
        end
        runs[#runs + 1] = {start = run_start, stop = run_end}
    end

    -- Compute quality metrics
    local unique_prg_bytes = #prg_addrs
    local max_run_len = 0
    local sum_run_len = 0
    for _, run in ipairs(runs) do
        local len = run.stop - run.start + 1
        sum_run_len = sum_run_len + len
        if len > max_run_len then max_run_len = len end
    end
    -- Coverage: how much of DMA size is accounted for by unique PRG reads
    -- High coverage (> 0.8) suggests direct ROM copy; low suggests decompression/synthesis
    local coverage_ratio = dma_size > 0 and (unique_prg_bytes / dma_size) or 0

    -- Format runs
    local runs_parts = {}
    for _, run in ipairs(runs) do
        if run.start == run.stop then
            runs_parts[#runs_parts + 1] = format_prg_offset(run.start)
        else
            local size = run.stop - run.start + 1
            runs_parts[#runs_parts + 1] = string.format(
                "%s-%s(%d)",
                format_prg_offset(run.start),
                format_prg_offset(run.stop),
                size
            )
        end
    end
    local runs_str = table.concat(runs_parts, ",")
    if #runs_str > 200 then
        runs_str = string.sub(runs_str, 1, 200) .. "..."
    end

    -- Count by CPU
    local cpu_totals = {}
    for _, src in pairs(staging_prg_sources) do
        for cpu, cnt in pairs(src.cpus) do
            cpu_totals[cpu] = (cpu_totals[cpu] or 0) + cnt
        end
    end
    local cpu_parts = {}
    for cpu, cnt in pairs(cpu_totals) do
        cpu_parts[#cpu_parts + 1] = cpu .. "=" .. cnt
    end
    local cpu_str = #cpu_parts > 0 and table.concat(cpu_parts, ",") or "none"

    -- Sample a few PC addresses from pairs (show both read and write PCs with their banks)
    local pc_samples = {}
    for i = 1, math.min(4, pairs_logged) do
        local p = staging_read_write_pairs[i]
        -- Format: "read_bank:read_pc->write_bank:write_pc"
        pc_samples[#pc_samples + 1] = string.format(
            "%02X:%04X->%02X:%04X",
            p.read_k or 0, p.read_pc, p.write_k or 0, p.write_pc
        )
    end
    local pc_str = table.concat(pc_samples, ",")

    -- Quality assessment: is this likely real data or code/noise?
    -- High quality = max_run >= 64 AND coverage > 0.5
    local quality = "LOW"
    if max_run_len >= 64 and coverage_ratio > 0.5 then
        quality = "HIGH"
    elseif max_run_len >= 32 or coverage_ratio > 0.3 then
        quality = "MED"
    end

    log(string.format(
        "STAGING_CAUSAL: frame=%d vram_word=0x%04X size=%d pairs=%d quality=%s unique_prg=%d max_run=%d coverage=%.2f prg_runs=[%s] cpus={%s} read->write_pcs=[%s]",
        frame, vram_addr, dma_size, staging_pair_total, quality, unique_prg_bytes, max_run_len, coverage_ratio, runs_str, cpu_str, pc_str
    ))
end

-- Log WRAM source summary (the intermediate buffer detection data)
-- This shows which WRAM regions the staging writer reads FROM
-- Includes quality metrics: unique_wram, max_run, coverage, quality
local function log_staging_wram_source_summary(frame, vram_addr, dma_size)
    if not STAGING_WRAM_SOURCE_ENABLED or not staging_active then return end
    if staging_wram_pair_total == 0 then
        -- Explicit log for zero pairs - helps distinguish "feature off" from "no matches in range"
        if STAGING_WRAM_SOURCE_ENABLED then
            log(string.format(
                "STAGING_WRAM_SOURCE: frame=%d vram_word=0x%04X size=%d NO_WRAM_PAIRS (source not in 0x%04X-0x%04X or not WRAM)",
                frame, vram_addr, dma_size, STAGING_WRAM_SRC_START, STAGING_WRAM_SRC_END
            ))
        end
        return
    end

    local pairs_logged = #staging_wram_read_write_pairs

    -- Aggregate WRAM sources into runs
    local wram_addrs = {}
    for addr, _ in pairs(staging_wram_sources) do
        wram_addrs[#wram_addrs + 1] = addr
    end
    table.sort(wram_addrs)

    -- Build runs from sorted addresses
    local runs = {}
    if #wram_addrs > 0 then
        local run_start = wram_addrs[1]
        local run_end = wram_addrs[1]
        for i = 2, #wram_addrs do
            local addr = wram_addrs[i]
            if addr == run_end + 1 then
                run_end = addr
            else
                runs[#runs + 1] = {start = run_start, stop = run_end}
                run_start = addr
                run_end = addr
            end
        end
        runs[#runs + 1] = {start = run_start, stop = run_end}
    end

    -- Compute quality metrics (same approach as PRG)
    local unique_wram_bytes = #wram_addrs
    local max_run_len = 0
    for _, run in ipairs(runs) do
        local len = run.stop - run.start + 1
        if len > max_run_len then max_run_len = len end
    end
    local coverage_ratio = dma_size > 0 and (unique_wram_bytes / dma_size) or 0

    -- Quality assessment
    local quality = "LOW"
    if max_run_len >= 64 and coverage_ratio > 0.5 then
        quality = "HIGH"
    elseif max_run_len >= 32 or coverage_ratio > 0.3 then
        quality = "MED"
    end

    -- Format runs (use %05X for WRAM addresses up to 0x1FFFF)
    local runs_parts = {}
    for _, run in ipairs(runs) do
        if run.start == run.stop then
            runs_parts[#runs_parts + 1] = string.format("0x%05X", run.start)
        else
            local size = run.stop - run.start + 1
            runs_parts[#runs_parts + 1] = string.format("0x%05X-0x%05X(%d)", run.start, run.stop, size)
        end
    end
    local runs_str = table.concat(runs_parts, ",")
    if #runs_str > 200 then
        runs_str = string.sub(runs_str, 1, 200) .. "..."
    end

    -- Top N source addresses by count (for discovery)
    local top_sources = {}
    for addr, data in pairs(staging_wram_sources) do
        top_sources[#top_sources + 1] = {addr = addr, count = data.count}
    end
    table.sort(top_sources, function(a, b) return a.count > b.count end)
    local top_parts = {}
    for i = 1, math.min(8, #top_sources) do
        local src = top_sources[i]
        top_parts[#top_parts + 1] = string.format("0x%05X:%d", src.addr, src.count)
    end
    local top_str = #top_parts > 0 and table.concat(top_parts, ",") or "none"

    -- Count by CPU
    local cpu_totals = {}
    for _, src in pairs(staging_wram_sources) do
        for cpu, cnt in pairs(src.cpus) do
            cpu_totals[cpu] = (cpu_totals[cpu] or 0) + cnt
        end
    end
    local cpu_parts = {}
    for cpu, cnt in pairs(cpu_totals) do
        cpu_parts[#cpu_parts + 1] = cpu .. "=" .. cnt
    end
    local cpu_str = #cpu_parts > 0 and table.concat(cpu_parts, ",") or "none"

    log(string.format(
        "STAGING_WRAM_SOURCE: frame=%d vram_word=0x%04X size=%d wram_pairs=%d quality=%s unique_wram=%d max_run=%d coverage=%.2f top=[%s] wram_runs=[%s] cpus={%s}",
        frame, vram_addr, dma_size, staging_wram_pair_total, quality, unique_wram_bytes, max_run_len, coverage_ratio, top_str, runs_str, cpu_str
    ))
end

-- WRAM SOURCE read callback factory during staging
-- Tracks what WRAM region the staging copy routine READS FROM (not the staging area itself)
-- This is the KEY feature: reveals the intermediate buffer that feeds staging
-- Uses RING BUFFER to capture multiple reads (not just last one)
--
-- PERFORMANCE: Gated by staging_active to avoid emu.getState() on every WRAM read (~120KB coverage).
-- STAGING_WRAM_PREARM: Pre-arm WRAM source tracking BEFORE staging_active.
-- WARNING: This reintroduces the "millions of callbacks" failure mode that caused timeouts.
-- Use only for short, controlled runs. Keep OFF for normal tracing.
local STAGING_WRAM_PREARM = os.getenv("STAGING_WRAM_PREARM") == "1"

local function make_staging_wram_source_reader(cpu_label)
    return function(address, value)
        -- GATE: Only track reads when staging session is active (or prearm enabled)
        if not staging_active and not STAGING_WRAM_PREARM then
            return
        end

        local frame = get_canonical_frame()

        -- Only fetch PC when PC-gating is enabled (saves expensive emu.getState() overhead)
        -- Default mode: address-only tracking (fast), PC-gating mode: fetch PC and filter
        local read_pc, read_k = 0, 0
        if STAGING_PC_GATING_ENABLED then
            local pc_snapshot = get_cpu_state_snapshot()
            if not pc_snapshot then return end
            read_pc = pc_snapshot.pc_val or 0
            read_k = pc_snapshot.k_val or 0

            local full_pc = (read_k << 16) | read_pc
            if not STAGING_COPY_PCS[full_pc] then return end
        end

        -- Normalize to relative WRAM offset (0x00000-0x1FFFF) for consistent aggregation
        local normalized_addr = address
        if wram_address_mode == "absolute" then
            normalized_addr = (address - 0x7E0000) & 0x1FFFF
        end

        -- Push to ring buffer (for causal pairing)
        read_sequence = read_sequence + 1
        push_ring(wram_src_ring_buffer, wram_src_ring_head, cpu_label, {
            addr = normalized_addr,
            frame = frame,
            seq = read_sequence,
            read_pc = read_pc,
            read_k = read_k
        })
        wram_src_seen_any = wram_src_seen_any + 1
    end
end

local function record_staging_write(addr, pc_snapshot)
    local frame = get_canonical_frame()

    -- Activate staging session on first write
    -- Note: PRG read callbacks are disabled, WRAM source callback is gated on staging_active,
    -- so ring buffers are empty at this point. Just use current read_sequence.
    if not staging_active then
        staging_active = true
        staging_first_pc = pc_snapshot
        staging_session_start_seq = read_sequence
    end

    -- Track frame of last staging write (for logging)
    last_staging_write_frame = frame

    -- Initialize stats for new frame
    if staging_current_frame ~= frame then
        -- Store previous frame stats
        if staging_current_frame and staging_current_stats and staging_current_stats.count > 0 then
            staging_frame_stats[staging_current_frame] = staging_current_stats
        end
        -- Prune old frames (keep only last N)
        local keep_from = frame - STAGING_HISTORY_FRAMES
        for f, _ in pairs(staging_frame_stats) do
            if f < keep_from then
                staging_frame_stats[f] = nil
            end
        end
        staging_current_frame = frame
        staging_current_stats = init_staging_stats()
    end

    local stats = staging_current_stats
    stats.count = stats.count + 1

    -- Track unique addresses
    if not stats.unique_addrs[addr] then
        stats.unique_addrs[addr] = true
        stats.unique_count = stats.unique_count + 1
    end

    -- Track min/max
    if stats.min_addr == nil or addr < stats.min_addr then
        stats.min_addr = addr
    end
    if stats.max_addr == nil or addr > stats.max_addr then
        stats.max_addr = addr
    end

    -- Track sequential vs jump pattern
    if stats.last_addr ~= nil then
        if addr == stats.last_addr + 1 then
            stats.sequential_count = stats.sequential_count + 1
        else
            stats.jump_count = stats.jump_count + 1
        end
    end
    stats.last_addr = addr

    -- Track first/last write addresses
    if stats.first_write_addr == nil then
        stats.first_write_addr = addr
    end
    stats.last_write_addr = addr

    -- Sample PCs
    if pc_snapshot and #stats.pc_samples < STAGING_WATCH_PC_SAMPLES then
        stats.pc_samples[#stats.pc_samples + 1] = {
            addr = addr,
            pc = pc_snapshot.pc_val or 0,
            k = pc_snapshot.k_val or 0,
        }
    end

    -- ========================================================================
    -- WRAM SOURCE READ→STAGING WRITE PAIRING (using ring buffers)
    -- Find what WRAM address the staging writer read from (intermediate buffer detection)
    -- PERFORMANCE: Only scan if WRAM source tracking is enabled AND ring buffer has entries
    -- NOTE: PRG ring buffer scan removed - PRG read callbacks are permanently disabled
    -- ========================================================================
    if STAGING_WRAM_SOURCE_ENABLED and staging_session_start_seq and wram_src_seen_any > 0 then
        local best_wram_read, best_wram_cpu = find_best_read_from_rings(wram_src_ring_buffer, staging_session_start_seq)

        if best_wram_read then
            staging_wram_pair_total = staging_wram_pair_total + 1

            if #staging_wram_read_write_pairs < 1000 then
                staging_wram_read_write_pairs[#staging_wram_read_write_pairs + 1] = {
                    read_wram = best_wram_read.addr,
                    read_pc = best_wram_read.read_pc or 0,
                    read_k = best_wram_read.read_k or 0,
                    write_wram = addr,
                    write_pc = pc_snapshot and pc_snapshot.pc_val or 0,
                    write_k = pc_snapshot and pc_snapshot.k_val or 0,
                    cpu = best_wram_cpu
                }
            end

            -- Aggregate: track which WRAM offsets are sources
            local wram_addr = best_wram_read.addr
            if not staging_wram_sources[wram_addr] then
                staging_wram_sources[wram_addr] = {count = 0, cpus = {}}
            end
            local src = staging_wram_sources[wram_addr]
            src.count = src.count + 1
            src.cpus[best_wram_cpu] = (src.cpus[best_wram_cpu] or 0) + 1

            -- Clear the read from ring buffer so it can't be double-paired
            consume_ring_entry(wram_src_ring_buffer, best_wram_cpu, best_wram_read.seq)
        end
    end
end

local function get_staging_summary(src_addr, src_size)
    -- Collect stats from recent frames that overlap with DMA source range
    local total_count = 0
    local total_unique = 0
    local total_sequential = 0
    local total_jumps = 0
    local all_pcs = {}
    local frames_with_writes = 0
    local min_addr, max_addr = nil, nil

    -- Include current frame stats
    if staging_current_stats and staging_current_stats.count > 0 then
        staging_frame_stats[staging_current_frame] = staging_current_stats
    end

    for frame, stats in pairs(staging_frame_stats) do
        if stats.count > 0 then
            frames_with_writes = frames_with_writes + 1
            total_count = total_count + stats.count
            total_unique = total_unique + stats.unique_count
            total_sequential = total_sequential + stats.sequential_count
            total_jumps = total_jumps + stats.jump_count

            if stats.min_addr then
                if min_addr == nil or stats.min_addr < min_addr then
                    min_addr = stats.min_addr
                end
            end
            if stats.max_addr then
                if max_addr == nil or stats.max_addr > max_addr then
                    max_addr = stats.max_addr
                end
            end

            for _, pc_info in ipairs(stats.pc_samples) do
                if #all_pcs < 8 then
                    all_pcs[#all_pcs + 1] = pc_info
                end
            end
        end
    end

    -- Determine write pattern
    local pattern = "unknown"
    if total_count == 0 then
        pattern = "NO_SCPU_WRITES"  -- SA-1 or hidden path
    elseif total_sequential > total_jumps * 4 then
        pattern = "SEQUENTIAL_BURST"  -- Decompress/copy
    elseif total_jumps > total_sequential * 2 then
        pattern = "SCATTERED_CHUNKS"  -- Metatile assembly
    else
        pattern = "MIXED"
    end

    return {
        pattern = pattern,
        total_writes = total_count,
        unique_addrs = total_unique,
        sequential = total_sequential,
        jumps = total_jumps,
        min_addr = min_addr,
        max_addr = max_addr,
        frames_with_writes = frames_with_writes,
        pc_samples = all_pcs,
    }
end

local function log_staging_summary_for_dma(src_addr, src_size, vram_addr)
    if not STAGING_WATCH_ENABLED then return end

    local frame = get_canonical_frame()
    -- Skip early frames (menus/intro) if start frame is configured
    if STAGING_START_FRAME > 0 and frame < STAGING_START_FRAME then return end

    local summary = get_staging_summary(src_addr, src_size)

    -- Format PC samples
    local pc_str = ""
    if #summary.pc_samples > 0 then
        local pc_parts = {}
        for _, p in ipairs(summary.pc_samples) do
            pc_parts[#pc_parts + 1] = string.format("%02X:%04X", p.k or 0, p.pc or 0)
        end
        pc_str = " pcs=[" .. table.concat(pc_parts, ",") .. "]"
    end

    log(string.format(
        "STAGING_SUMMARY: frame=%d src=0x%06X size=%d vram=0x%04X pattern=%s writes=%d unique=%d seq=%d jumps=%d range=0x%06X-0x%06X frames=%d%s",
        frame,
        src_addr,
        src_size,
        vram_addr,
        summary.pattern,
        summary.total_writes,
        summary.unique_addrs,
        summary.sequential,
        summary.jumps,
        summary.min_addr or 0,
        summary.max_addr or 0,
        summary.frames_with_writes,
        pc_str
    ))
end

local function on_staging_write(address, value)
    if not STAGING_WATCH_ENABLED then return end
    -- OPTIMIZATION: Only call get_cpu_state_snapshot() when we actually need the PC.
    -- PC is needed for: (1) staging_first_pc on first write, (2) PC sampling (first N writes per frame)
    -- After N samples per frame, we skip the expensive emu.getState() call.
    local pc_snapshot = nil
    local stats = staging_current_stats
    -- Need PC if: not yet active (first write), no stats yet (new frame), or still collecting samples
    local needs_pc = not staging_active
        or not stats
        or #stats.pc_samples < STAGING_WATCH_PC_SAMPLES
    if needs_pc then
        pc_snapshot = get_cpu_state_snapshot()
    end
    record_staging_write(address, pc_snapshot)
end
-- ============================================================================

local function dma_dump_allowed(frame_id)
    if CFG.dma_dump_start_frame > 0 and frame_id < CFG.dma_dump_start_frame then
        return false
    end
    return true
end

local function read8(addr)
    return emu.read(addr, MEM.cpu)
end

local function refresh_vram_inc()
    local vmain = read8(0x2115)
    local inc_sel = vmain & 0x03
    vram_inc_mode = (vmain >> 7) & 0x01
    local inc_lookup = {
        [0] = 1,
        [1] = 32,
        [2] = 128,
        [3] = 128,
    }
    vram_inc_value = inc_lookup[inc_sel] or 1
end

local function log_dma_channel(channel, value)
    -- Refresh VMAIN-based values before logging (since we removed on_vmain_write callback)
    refresh_vram_inc()
    -- Use SHADOWED values captured as registers were written (before DMA runs)
    -- This avoids reading post-DMA state where DAS=0 and VMADD may have changed
    local shadow = dma_shadow[channel]
    local dmap = shadow.dmap
    local bbad = shadow.bbad
    local a1t = shadow.a1t_lo | (shadow.a1t_hi << 8)
    local a1b = shadow.a1b
    local das_raw = shadow.das_lo | (shadow.das_hi << 8)
    local das = das_raw
    local size_text
    if das_raw == 0 then
        das = 0x10000
        size_text = "0x10000 (raw=0x0000)"
    else
        size_text = string.format("0x%04X", das_raw)
    end
    local src = (a1b << 16) | a1t
    local direction = (dmap & 0x80) ~= 0 and "B->A" or "A->B"
    local mode = dmap & 0x07
    -- Use shadowed VRAM address captured at last $2116/$2117 write
    local captured_vmadd = vram_addr_shadow
    local note = ""
    if bbad == 0x18 or bbad == 0x19 then
        note = string.format(
            " VRAM word=0x%04X vmain_inc=%d mode=%d",
            captured_vmadd,
            vram_inc_value,
            vram_inc_mode
        )
    end
    log(string.format(
        "DMA enable=0x%02X ch=%d dir=%s mode=%d bbad=0x%02X src=0x%06X size=%s%s",
        value, channel, direction, mode, bbad, src, size_text, note
    ))

    -- Enhanced SNES DMA-to-VRAM log for Phase 2 correlation (Instrumentation Contract v1.1)
    -- Only log for A->B transfers to VRAM ($2118/$2119)
    if direction == "A->B" and (bbad == 0x18 or bbad == 0x19) then
        local vram_fmt = "SNES_DMA_VRAM: frame=%d run=%s ch=%d dmap=0x%02X src=0x%04X src_bank=0x%02X size=0x%04X vmadd=0x%04X"
        log(string.format(vram_fmt,
            get_canonical_frame(),
            RUN_ID,
            channel,
            dmap,
            a1t,
            a1b,
            das,
            captured_vmadd
        ))

        -- FIXED: Queue DMA compare for execution at frame end (after DMA completes)
        -- Immediate comparison here would read VRAM before DMA writes to it!
        --
        -- Filter for actual VRAM tile DMAs:
        -- 1. DMAP mode 1 = 2-register transfer ($2118 and $2119)
        -- 2. Size in tile-plausible range (32-8192 bytes, excludes 64KB wraparound artifacts)
        -- 3. Size is multiple of 2 (word-addressed VRAM)
        local is_mode_1 = (mode == 1)
        local is_plausible_size = (das >= 32 and das <= 8192 and (das % 2) == 0)
        if CFG.dma_compare_enabled and dma_compare_count < CFG.dma_compare_max
           and is_mode_1 and is_plausible_size then
            dma_compare_count = dma_compare_count + 1
            -- Queue the compare info; actual comparison happens at frame end
            local vram_byte_addr = (captured_vmadd << 1) & 0xFFFF
            pending_dma_compares[#pending_dma_compares + 1] = {
                frame = get_canonical_frame(),
                channel = channel,
                dmap = dmap,
                mode = mode,
                src = src,
                vram_byte_addr = vram_byte_addr,
                das = das,
                compare_size = math.min(das, CFG.dma_compare_sample_bytes),
            }
        end

        -- Log staging buffer write summary when DMA fires from staging range
        -- Use overlap check: [a1t, a1t+das-1] overlaps [STAGING_WATCH_START, STAGING_WATCH_END]
        if STAGING_WATCH_ENABLED and a1b == 0x7E then
            local dma_end = a1t + das - 1
            local overlaps_staging = (dma_end >= STAGING_WATCH_START and a1t <= STAGING_WATCH_END)
            if overlaps_staging then
                log_staging_summary_for_dma(src, das, captured_vmadd)
                -- Log causal read→write summary (which PRG reads fed staging writes)
                log_staging_causal_summary(get_canonical_frame(), captured_vmadd, das)
                -- Log WRAM source summary (if staging reads from intermediate WRAM buffer)
                log_staging_wram_source_summary(get_canonical_frame(), captured_vmadd, das)
                reset_staging_tracking()
            end
        end
    end

    local frame_id = last_state_frame or frame_count
    if CFG.dma_dump_on_vram and direction == "A->B" and (bbad == 0x18 or bbad == 0x19) then
        if not dma_dump_allowed(frame_id) then
            return
        end
        if dma_dump_count < CFG.dma_dump_max and das >= CFG.dma_dump_min_size then
            if not dma_read_mem then
                log("WARNING: DMA dump requested but no CPU memType available")
                return
            end
            dma_dump_count = dma_dump_count + 1
            local path = OUTPUT_DIR .. string.format(
                "dma_src_ch%d_bbad%02X_frame_%s_src_%06X_size_%05X.bin",
                channel,
                bbad,
                tostring(frame_id),
                src,
                das
            )
            local f = io.open(path, "wb")
            if not f then
                log("ERROR: failed to open DMA dump: " .. path)
                return
            end
            -- Clamp dump size to avoid timeout (DAS=0 means 0x10000 bytes)
            local dump_size = math.min(das, CFG.dma_dump_max_size)
            if dump_size < das then
                log(string.format("WARNING: DMA dump truncated %d -> %d bytes", das, dump_size))
            end
            local chunk = {}
            local chunk_len = 0
            local chunk_size = 4096
            for i = 0, dump_size - 1 do
                local read_val = emu.read((src + i) & 0xFFFFFF, dma_read_mem)
                if read_val == nil then
                    read_val = 0
                end
                chunk_len = chunk_len + 1
                chunk[chunk_len] = string.char(read_val & 0xFF)
                if chunk_len >= chunk_size then
                    f:write(table.concat(chunk))
                    chunk = {}
                    chunk_len = 0
                end
            end
            if chunk_len > 0 then
                f:write(table.concat(chunk))
            end
            f:close()
            log("DMA dump saved: " .. path)
        end
    end
end

-- =============================================================================
-- SECTION 6: SA-1 TRACKER
-- Bank mapping state, CCDMA detection, SA-1 DMA control monitoring
-- Hot paths: on_sa1_ctrl_write (per-control), on_sa1_bank_write (per-bank)
-- =============================================================================

local sa1_state = {
    ctrl = 0,
    src = 0,
    dest = 0,
    size = 0,
}

-- SA-1 bank mapping registers (per Instrumentation Contract v1.1)
-- Required for SA-1 bus → ROM file offset translation
local sa1_bank_state = {
    cxb = 0,    -- $2220: ROM bank for $00-$1F
    dxb = 0,    -- $2221: ROM bank for $20-$3F
    exb = 0,    -- $2222: ROM bank for $80-$9F
    fxb = 0,    -- $2223: ROM bank for $A0-$BF
    bmaps = 0,  -- $2224: BW-RAM mapping (SNES side)
    bmap = 0,   -- $2225: BW-RAM mapping (SA-1 side)
}

local function refresh_sa1_bank_state()
    sa1_bank_state.cxb = read8(0x2220)
    sa1_bank_state.dxb = read8(0x2221)
    sa1_bank_state.exb = read8(0x2222)
    sa1_bank_state.fxb = read8(0x2223)
    sa1_bank_state.bmaps = read8(0x2224)
    sa1_bank_state.bmap = read8(0x2225)
end

local function log_sa1_banks(reason)
    refresh_sa1_bank_state()
    local fmt = "SA1_BANKS (%s): frame=%d run=%s cxb=0x%02X dxb=0x%02X exb=0x%02X fxb=0x%02X bmaps=0x%02X bmap=0x%02X"
    log(string.format(fmt,
        reason,
        get_canonical_frame(),
        RUN_ID,
        sa1_bank_state.cxb,
        sa1_bank_state.dxb,
        sa1_bank_state.exb,
        sa1_bank_state.fxb,
        sa1_bank_state.bmaps,
        sa1_bank_state.bmap
    ))
end

local function on_sa1_bank_write(address)
    local addr = address & 0xFFFF
    local reg_names = {
        [0x2220] = "cxb",
        [0x2221] = "dxb",
        [0x2222] = "exb",
        [0x2223] = "fxb",
        [0x2224] = "bmaps",
        [0x2225] = "bmap",
    }
    local reg_name = reg_names[addr] or "unknown"
    log_sa1_banks(string.format("%s_write", reg_name))
end

local function refresh_sa1_state()
    sa1_state.ctrl = read8(0x2230)
    sa1_state.src = read8(0x2232) | (read8(0x2233) << 8) | (read8(0x2234) << 16)
    sa1_state.dest = read8(0x2235) | (read8(0x2236) << 8) | (read8(0x2237) << 16)
    sa1_state.size = read8(0x2238) | (read8(0x2239) << 8)
end

local function log_sa1_dma(reason)
    refresh_sa1_state()
    local ctrl = sa1_state.ctrl
    local enabled = (ctrl & 0x80) ~= 0
    local char_conv = (ctrl & 0x20) ~= 0
    local auto_conv = (ctrl & 0x10) ~= 0
    local src_dev = ctrl & 0x03
    local dest_dev = (ctrl >> 2) & 0x01
    local sa1_fmt = "SA1 DMA (%s): ctrl=0x%02X enabled=%s char_conv=%s auto=%s "
        .. "src_dev=%d dest_dev=%d src=0x%06X dest=0x%06X size=0x%04X"
    log(string.format(sa1_fmt,
        reason,
        ctrl,
        tostring(enabled),
        tostring(char_conv),
        tostring(auto_conv),
        src_dev,
        dest_dev,
        sa1_state.src,
        sa1_state.dest,
        sa1_state.size
    ))
end

-- =============================================================================
-- CCDMA Start Trigger (per Instrumentation Contract v1.1 / Phase 1)
-- =============================================================================
-- CCDMA_START defined as: Rising edge of DCNT.C bit when M=1 (char conversion mode)
-- This is the authoritative start signal, not $2236/$2237 initialization

local prev_dcnt_c = 0  -- Track previous C bit state for rising edge detection
local prev_char_conv_irq = 0  -- Track previous CharConvIrqFlag for rising edge detection
local prev_dcnt_debug = 0  -- Track previous DCNT for debug logging
local prev_m_bit = 0  -- Track previous M bit for rising edge detection

local function log_ccdma_start()
    -- Snapshot all relevant registers at the moment of CCDMA start
    refresh_sa1_state()
    refresh_sa1_bank_state()

    local ctrl = sa1_state.ctrl
    local cdma = read8(0x2231)

    -- Extract SS (Source Select) from DCNT bits 1-0
    -- 00 = ROM, 01 = BW-RAM, 10 = I-RAM
    local ss = ctrl & 0x03
    local ss_names = {[0] = "ROM", [1] = "BW-RAM", [2] = "I-RAM", [3] = "reserved"}

    -- Extract D (Destination) from DCNT bit 2
    -- 0 = I-RAM, 1 = BW-RAM
    local dest_dev = (ctrl >> 2) & 0x01
    local dest_names = {[0] = "I-RAM", [1] = "BW-RAM"}

    local fmt = "CCDMA_START: frame=%d run=%s dcnt=0x%02X cdma=0x%02X ss=%d (%s) "
        .. "dest_dev=%d (%s) src=0x%06X dest=0x%06X size=0x%04X"
    log(string.format(fmt,
        get_canonical_frame(),
        RUN_ID,
        ctrl,
        cdma,
        ss,
        ss_names[ss] or "?",
        dest_dev,
        dest_names[dest_dev] or "?",
        sa1_state.src,
        sa1_state.dest,
        sa1_state.size
    ))
end

-- FIXED: Use the value parameter from callback instead of re-reading $420B
local function on_dma_enable(address, value)
    -- Use the written value if provided, else fall back to readback
    local enable = (value ~= nil) and (value & 0xFF) or (read8(0x420B) & 0xFF)
    if enable == 0 then
        return
    end
    for channel = 0, 7 do
        if (enable & (1 << channel)) ~= 0 then
            log_dma_channel(channel, enable)
        end
    end
end

local function on_hdma_enable(address)
    local value = read8(0x420C)
    if value ~= 0 then
        log(string.format("HDMA enable=0x%02X", value))
    end
end

-- Shadow VMADD from writes (don't read back $2116/$2117 which can return open-bus)
local vmadd_lo, vmadd_hi = 0, 0
local function on_vram_addr_write(address, value)
    -- Capture the WRITTEN value, not a readback
    if address == 0x2116 then
        vmadd_lo = value & 0xFF
    else -- 0x2117
        vmadd_hi = value & 0xFF
    end
    vram_addr_shadow = vmadd_lo | (vmadd_hi << 8)
end

-- Callback to shadow DMA channel register writes (before $420B triggers DMA)
local function on_dma_reg_write(address, value)
    -- Address range: $4300-$437F (8 channels × 16 bytes each, but we only care about 0-6)
    local offset = address - 0x4300
    local channel = math.floor(offset / 16)
    local reg = offset % 16

    if channel >= 0 and channel <= 7 and reg <= 6 then
        local shadow = dma_shadow[channel]
        if reg == 0 then
            shadow.dmap = value
        elseif reg == 1 then
            shadow.bbad = value
        elseif reg == 2 then
            shadow.a1t_lo = value
        elseif reg == 3 then
            shadow.a1t_hi = value
        elseif reg == 4 then
            shadow.a1b = value
        elseif reg == 5 then
            shadow.das_lo = value
        elseif reg == 6 then
            shadow.das_hi = value
        end
    end
end

local function on_sa1_ctrl_write(address)
    -- Read the DCNT value that was just written
    local dcnt = read8(0x2230)

    -- Extract C bit (DMA enable, bit 7) and M bit (mode, bit 5)
    local c_bit = (dcnt >> 7) & 1
    local m_bit = (dcnt >> 5) & 1

    -- Detect CCDMA_START: rising edge of C when M=1 (character conversion mode)
    if c_bit == 1 and prev_dcnt_c == 0 and m_bit == 1 then
        log_ccdma_start()
    end

    -- Update previous C bit state for next comparison
    prev_dcnt_c = c_bit

    -- Also log the general SA1 DMA state as before
    log_sa1_dma("ctrl_write")
end

local function on_sa1_dma_reg_write(address)
    local addr = address or 0
    if addr == 0x2238 or addr == 0x2239 then
        log_sa1_dma("size_write")
    elseif addr == 0x2232 or addr == 0x2233 or addr == 0x2234 then
        log_sa1_dma("src_write")
    elseif addr == 0x2235 or addr == 0x2236 or addr == 0x2237 then
        log_sa1_dma("dest_write")
    end
end

local function on_sa1_bitmap_write(address)
    if (sa1_state.ctrl & 0x20) ~= 0 then
        log(string.format("SA1 bitmap register write: 0x%04X", address))
    end
end

-- =============================================================================
-- SECTION 8: DMA COMPARISON
-- Deferred VRAM verification (runs at frame end after DMA completes)
-- =============================================================================

local state_loaded = PRELOADED_STATE
local frame_event_registered = false

-- Process pending DMA comparisons (deferred from $420B write callback)
-- This runs at frame end after all DMAs have completed
local function process_pending_dma_compares()
    if #pending_dma_compares == 0 then
        return
    end

    for _, info in ipairs(pending_dma_compares) do
        local match_count = 0
        local diff_indices = {}
        local src_sample = {}
        local vram_sample = {}

        -- Now read VRAM after DMA has completed
        for i = 0, info.compare_size - 1 do
            local src_byte = emu.read((info.src + i) & 0xFFFFFF, dma_read_mem) or 0
            local vram_byte = emu.read((info.vram_byte_addr + i) & 0xFFFF, MEM.vram) or 0
            if i < 8 then
                src_sample[i + 1] = string.format("%02X", src_byte)
                vram_sample[i + 1] = string.format("%02X", vram_byte)
            end
            if src_byte == vram_byte then
                match_count = match_count + 1
            else
                if #diff_indices < 8 then
                    diff_indices[#diff_indices + 1] = string.format("%d", i)
                end
            end
        end

        local is_match = match_count == info.compare_size
        local match_pct = (match_count * 100) / info.compare_size
        local diff_str = #diff_indices > 0 and table.concat(diff_indices, ",") or "none"
        local src_str = table.concat(src_sample, " ")
        local vram_str = table.concat(vram_sample, " ")

        log(string.format(
            "DMA_COMPARE: frame=%d ch=%d dmap=0x%02X mode=%d src=0x%06X vram=0x%04X das=%d match=%d/%d (%.1f%%) eq=%s diffs=[%s]",
            info.frame,
            info.channel,
            info.dmap,
            info.mode,
            info.src,
            info.vram_byte_addr,
            info.das,
            match_count,
            info.compare_size,
            match_pct,
            tostring(is_match),
            diff_str
        ))
        log(string.format(
            "DMA_COMPARE_SAMPLE: src=[%s] vram=[%s]",
            src_str,
            vram_str
        ))
    end

    -- Clear the queue
    pending_dma_compares = {}
end

-- =============================================================================
-- SECTION 9: FRAME DETECTION
-- Frame counter, endFrame/exec callbacks, master clock fallback
-- =============================================================================

local function on_end_frame()
    frame_count = frame_count + 1

    -- FIXED: Process pending DMA comparisons at frame end (after all DMAs have completed)
    process_pending_dma_compares()

    local sa1_irq = read8(0x2301)
    if sa1_irq ~= last_sa1_dma_irq then
        log(string.format("SA1 DMA IRQ flag: 0x%02X", sa1_irq))
        last_sa1_dma_irq = sa1_irq
    end

    -- Poll SA-1 status for CCDMA detection (since write callbacks don't work for SA-1 CPU)
    -- $2300 bit 5 = CharConvIrqFlag: set when character conversion DMA starts (auto mode only)
    local sfr = read8(0x2300)
    local char_conv_irq = (sfr >> 5) & 1
    local dcnt = read8(0x2230)
    local c_bit = (dcnt >> 7) & 1
    local m_bit = (dcnt >> 5) & 1

    -- Debug: log non-zero DCNT values to see if character conversion is happening
    if dcnt ~= 0 and dcnt ~= prev_dcnt_debug then
        log(string.format("DCNT_POLL: frame=%d dcnt=0x%02X c=%d m=%d sfr=0x%02X char_irq=%d",
            get_canonical_frame(), dcnt, c_bit, m_bit, sfr, char_conv_irq))
        prev_dcnt_debug = dcnt
    end

    -- Detect character conversion DMA via the IRQ flag (more reliable than polling DCNT)
    if char_conv_irq == 1 and prev_char_conv_irq == 0 then
        -- CharConvIrqFlag just got set: character conversion DMA started
        log_ccdma_start()
        log_sa1_dma("sfr_ccdma")
    elseif c_bit == 1 and m_bit == 1 then
        -- DMA currently active with character conversion mode
        if prev_dcnt_c == 0 then
            log_ccdma_start()
            log_sa1_dma("ctrl_poll_ccdma")
        end
    elseif m_bit == 1 and prev_m_bit == 0 then
        -- M bit just got set (character conversion mode enabled)
        log_ccdma_start()
        log_sa1_dma("m_bit_set")
    end
    prev_dcnt_c = c_bit
    prev_m_bit = m_bit
    prev_char_conv_irq = char_conv_irq

    if CFG.heartbeat_every > 0 and (frame_count % CFG.heartbeat_every) == 0 then
        log(string.format("Heartbeat frame=%d masterClock=%s", frame_count, tostring(last_master_clock)))
    end

    if frame_count >= MAX_FRAMES then
        log("Reached MAX_FRAMES; stopping")
        emu.stop()
    end
end

local function register_frame_event()
    if frame_event_registered then
        return
    end
    frame_event_registered = true
    if FRAME_EVENT == "exec" then
        local last_frame = nil
        local clock_accum = 0
        local start_master_clock = nil
        local max_master_delta = nil

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
                log("MasterClock max seconds reached; stopping")
                emu.stop(1)
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
            -- Cap catch-up frames to avoid timeout on lag/breakpoints
            local max_catchup = 2
            local n = 0
            while clock_accum >= ticks_per_frame and n < max_catchup do
                clock_accum = clock_accum - ticks_per_frame
                on_end_frame()
                n = n + 1
            end
            if n == max_catchup and clock_accum >= ticks_per_frame then
                clock_accum = 0  -- Drop backlog; better than timing out
            end
        end

        local function exec_tick()
            local state = emu.getState and emu.getState() or nil
            local frame_value = nil
            if state then
                last_master_clock = state.masterClock
                frame_value = state["ppu.frameCount"]
                    or state.frameCount
                    or state.framecount
                    or state["ppu.framecount"]
                    or state["snes.ppu.framecount"]
                if frame_value ~= nil then
                    last_state_frame = frame_value
                end
            end
            if frame_value ~= nil and frame_value ~= last_frame then
                last_frame = frame_value
                on_end_frame()
                tick_from_master_clock(state, true)
                return
            end
            tick_from_master_clock(state, false)
        end

        local ref = add_memory_callback_compat(exec_tick, emu.callbackType.exec, 0x0000, 0xFFFF, cpu_type, MEM.cpu)
        if not ref then
            log("ERROR: failed to register exec frame callback")
        else
            log("INFO: Frame callback registered via exec fallback")
        end
    else
        emu.addEventCallback(on_end_frame, emu.eventType.endFrame)
        log("INFO: Frame callback registered via endFrame event")
    end
end

local function load_savestate_if_needed()
    if not SAVESTATE_PATH or state_loaded then
        register_frame_event()
        return
    end
    local ref
    ref = add_memory_callback_compat(function()
        if state_loaded then
            return
        end
        state_loaded = true
        if emu.loadSavestate then
            emu.loadSavestate(SAVESTATE_PATH)
            log("Savestate loaded; reset frame counter")
            frame_count = 0
            register_frame_event()
        else
            log("ERROR: emu.loadSavestate not available")
            emu.stop(2)
        end
    end, emu.callbackType.exec, 0x0000, 0xFFFF, cpu_type, MEM.cpu)
    if not ref then
        log("ERROR: failed to register savestate callback")
    end
end

-- =============================================================================
-- SECTION 10: CALLBACK REGISTRATION
-- Wire up all memory and event callbacks
-- Order matters: DMA before staging, S-CPU before SA-1
-- =============================================================================

add_memory_callback_compat(on_dma_enable, emu.callbackType.write, 0x420B, 0x420B, cpu_type, MEM.cpu)
add_memory_callback_compat(on_hdma_enable, emu.callbackType.write, 0x420C, 0x420C, cpu_type, MEM.cpu)
-- Shadow DMA channel registers as they are written (before $420B triggers DMA)
add_memory_callback_compat(on_dma_reg_write, emu.callbackType.write, 0x4300, 0x437F, cpu_type, MEM.cpu)
add_memory_callback_compat(on_vram_addr_write, emu.callbackType.write, 0x2116, 0x2117, cpu_type, MEM.cpu)
add_memory_callback_compat(on_sa1_bank_write, emu.callbackType.write, 0x2220, 0x2225, cpu_type, MEM.cpu)
add_memory_callback_compat(on_sa1_ctrl_write, emu.callbackType.write, 0x2230, 0x2230, cpu_type, MEM.cpu)
add_memory_callback_compat(on_sa1_dma_reg_write, emu.callbackType.write, 0x2231, 0x2239, cpu_type, MEM.cpu)
add_memory_callback_compat(on_sa1_bitmap_write, emu.callbackType.write, 0x2240, 0x224F, cpu_type, MEM.cpu)

-- Register SA-1 CPU callback for $2230 (DCNT) only - this is the DMA trigger we need
-- Note: sa1_cpu_type is defined near top of file (emu.cpuType.sa1)
-- Note: $2220-$2225 (bank regs) are written by S-CPU to configure SA-1, not by SA-1 itself
-- Registering SA-1 callbacks for all registers causes timeout due to high write frequency
if sa1_cpu_type then
    add_memory_callback_compat(on_sa1_ctrl_write, emu.callbackType.write, 0x2230, 0x2230, sa1_cpu_type, MEM.cpu)
    log("INFO: SA-1 CPU callback registered for $2230 (DCNT)")
else
    log("INFO: SA-1 cpuType not available; SA-1 DMA monitoring limited to S-CPU writes")
end

-- Register staging buffer write watch (rolling log for DMA source analysis)
if STAGING_WATCH_ENABLED then
    if not wram_mem_type then
        log("WARNING: Staging watch enabled but no WRAM memType resolved")
    else
        -- Compute staging watch addresses based on WRAM addressing mode
        local staging_start, staging_end
        if wram_address_mode == "absolute" then
            staging_start = 0x7E0000 + STAGING_WATCH_START
            staging_end = 0x7E0000 + STAGING_WATCH_END
        else
            staging_start = STAGING_WATCH_START
            staging_end = STAGING_WATCH_END
        end

        local snes_staging_ref = add_memory_callback_compat(
            on_staging_write,
            emu.callbackType.write,
            staging_start,
            staging_end,
            cpu_type,
            wram_mem_type
        )
        if snes_staging_ref then
            log(string.format(
                "INFO: Staging watch registered for S-CPU: 0x%06X-0x%06X",
                staging_start, staging_end
            ))
        else
            log("WARNING: failed to register staging write watch for S-CPU")
        end

        -- SA-1 staging callbacks DISABLED - causes timeout due to extremely high write frequency
        -- SA-1 writes to WRAM constantly during decompression/processing, which overwhelms
        -- the 1-second Mesen2 Lua execution limit. Staging analysis relies on S-CPU DMA anyway.
        if sa1_cpu_type then
            log("INFO: SA-1 staging callback SKIPPED (would cause timeout)")
        end

        -- PRG read callbacks PERMANENTLY DISABLED: too many ROM reads (M/frame) cause timeout
        -- STAGING_CAUSAL will show NO_PAIRS; use STAGING_WRAM_SOURCE instead

        -- Register WRAM read callbacks for intermediate buffer detection
        -- Track reads from WRAM OUTSIDE the staging buffer (0x2000-0x2FFF)
        -- This reveals if staging is fed from another WRAM buffer
        -- GATED by STAGING_WRAM_TRACKING because callbacks are expensive (~120KB coverage)
        if wram_mem_type and STAGING_WRAM_TRACKING_ENABLED then
            -- Compute WRAM read ranges (excluding staging buffer)
            local wram_read_ranges = {}
            if wram_address_mode == "absolute" then
                -- Absolute addressing: 0 to STAGING_WATCH_START-1, then STAGING_WATCH_END+1 to 0x1FFFF
                wram_read_ranges = {
                    {start = 0x7E0000, stop = 0x7E0000 + STAGING_WATCH_START - 1},  -- Before staging
                    {start = 0x7E0000 + STAGING_WATCH_END + 1, stop = 0x7E0000 + 0x1FFFF},  -- After staging
                }
            else
                -- Relative addressing: 0 to STAGING_WATCH_START-1, then STAGING_WATCH_END+1 to 0x1FFFF
                wram_read_ranges = {
                    {start = 0, stop = STAGING_WATCH_START - 1},  -- Before staging
                    {start = STAGING_WATCH_END + 1, stop = 0x1FFFF},  -- After staging (128KB WRAM)
                }
            end

            for _, range in ipairs(wram_read_ranges) do
                local wram_read_ref = add_memory_callback_compat(
                    make_staging_wram_source_reader("snes"),
                    emu.callbackType.read,
                    range.start,
                    range.stop,
                    cpu_type,
                    wram_mem_type
                )
                if wram_read_ref then
                    log(string.format(
                        "INFO: WRAM read callback registered for S-CPU: 0x%06X-0x%06X",
                        range.start, range.stop
                    ))
                end
            end

            -- Also try SA-1 WRAM reads
            if sa1_cpu_type then
                for _, range in ipairs(wram_read_ranges) do
                    local sa1_wram_ref = add_memory_callback_compat(
                        make_staging_wram_source_reader("sa1"),
                        emu.callbackType.read,
                        range.start,
                        range.stop,
                        sa1_cpu_type,
                        wram_mem_type
                    )
                    if sa1_wram_ref then
                        log(string.format(
                            "INFO: WRAM read callback registered for SA-1: 0x%06X-0x%06X",
                            range.start, range.stop
                        ))
                    end
                end
            end
        elseif wram_mem_type and not STAGING_WRAM_TRACKING_ENABLED then
            log("INFO: WRAM read tracking (full) disabled (STAGING_WRAM_TRACKING=0)")
        end

        -- Register WRAM SOURCE callbacks (surgical, focused range)
        -- This is the KEY feature: track reads from a specific WRAM region
        -- Use STAGING_WRAM_SOURCE=1 with narrow SRC_START/SRC_END to find intermediate buffer
        -- Requires STAGING_WATCH_ENABLED=1 (for staging_active flag) but NOT STAGING_CAUSAL_ENABLED
        if wram_mem_type and STAGING_WRAM_SOURCE_ENABLED then
            local src_start = STAGING_WRAM_SRC_START
            local src_end = STAGING_WRAM_SRC_END

            -- Adjust for absolute addressing mode if needed
            if wram_address_mode == "absolute" then
                src_start = 0x7E0000 + src_start
                src_end = 0x7E0000 + src_end
            end

            -- Register S-CPU WRAM source read callback
            local snes_wram_src_ref = add_memory_callback_compat(
                make_staging_wram_source_reader("snes"),
                emu.callbackType.read,
                src_start,
                src_end,
                cpu_type,
                wram_mem_type
            )
            if snes_wram_src_ref then
                log(string.format(
                    "INFO: WRAM SOURCE callback registered for S-CPU: 0x%04X-0x%04X (%d bytes)",
                    STAGING_WRAM_SRC_START, STAGING_WRAM_SRC_END, STAGING_WRAM_SRC_END - STAGING_WRAM_SRC_START + 1
                ))
            else
                log("WARNING: Failed to register WRAM SOURCE callback for S-CPU")
            end

            -- SA-1 WRAM source callback DISABLED: emu.getState() returns wrong CPU's state
            if sa1_cpu_type then
                log("INFO: SA-1 WRAM SOURCE callback DISABLED (PC state unreliable across CPUs)")
            end
        elseif wram_mem_type and not STAGING_WRAM_SOURCE_ENABLED then
            log("INFO: WRAM SOURCE tracking disabled (STAGING_WRAM_SOURCE=0). Set STAGING_WRAM_SOURCE=1 to enable.")
        end
    end
end

-- Register cleanup callback for script end
local function on_script_end()
    log("INFO: Script ending, closing log file...")
    if log_file_handle then
        log_file_handle:flush()
    end
    close_log_file()
end

if emu.eventType and emu.eventType.scriptEnded then
    emu.addEventCallback(on_script_end, emu.eventType.scriptEnded)
    log("INFO: Script cleanup callback registered")
else
    log("WARNING: scriptEnded event not available, log may not flush on exit")
end

-- =============================================================================
-- SECTION 11: INITIALIZATION
-- Final setup, error handling, start message
-- =============================================================================

log("INFO: Callback registration complete, starting final initialization...")

-- Wrap final initialization in pcall to catch any errors
local init_ok, init_err = pcall(function()
    refresh_vram_inc()
    log(string.format(
        "Staging watch: enabled=%s range=0x%04X-0x%04X pc_samples=%d history_frames=%d",
        tostring(STAGING_WATCH_ENABLED),
        STAGING_WATCH_START,
        STAGING_WATCH_END,
        STAGING_WATCH_PC_SAMPLES,
        STAGING_HISTORY_FRAMES
    ))
    log("DMA probe start: frame_event=" .. tostring(FRAME_EVENT) .. " max_frames=" .. tostring(MAX_FRAMES))
    -- Warn if user tried to enable STAGING_CAUSAL (env var is now ignored)
    if os.getenv("STAGING_CAUSAL_ENABLED") == "1" then
        log("WARNING: STAGING_CAUSAL_ENABLED ignored - PRG read callbacks permanently disabled (timeout risk). Use STAGING_WRAM_SOURCE instead.")
    end
    -- Warn about debug-only modes that can cause timeout
    if STAGING_WRAM_TRACKING_ENABLED then
        log("WARNING: STAGING_WRAM_TRACKING=1 active - DEBUG MODE, expect possible timeouts")
    end
    if STAGING_WRAM_PREARM then
        log("WARNING: STAGING_WRAM_PREARM=1 active - high timeout risk, use for short runs only")
    end

    -- Log initial SA-1 bank register state (per Instrumentation Contract v1.1)
    log_sa1_banks("init")

    if SAVESTATE_PATH and not PRELOADED_STATE then
        load_savestate_if_needed()
    else
        register_frame_event()
    end
end)
if not init_ok then
    log("ERROR: Final initialization failed: " .. tostring(init_err))
end
