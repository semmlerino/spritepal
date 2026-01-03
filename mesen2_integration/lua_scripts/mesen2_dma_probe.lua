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
local LOG_VERSION = "2.19"
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
    -- Default to endFrame always; exec is opt-in only (v2.0: per-instruction overhead is too high)
    FRAME_EVENT = "endFrame"
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

local function parse_bool(value, default_value)
    if value == nil then
        return default_value
    end
    local text = tostring(value):lower()
    if text == "1" or text == "true" or text == "yes" then
        return true
    elseif text == "0" or text == "false" or text == "no" then
        return false
    end
    return default_value
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
    dma_dump_on_vram = os.getenv("DMA_DUMP_ON_VRAM") == "1",  -- v2.0: opt-in (was default ON)
    dma_dump_max = tonumber(os.getenv("DMA_DUMP_MAX")) or 20,
    dma_dump_min_size = tonumber(os.getenv("DMA_DUMP_MIN_SIZE")) or 1,
    dma_dump_max_size = tonumber(os.getenv("DMA_DUMP_MAX_SIZE")) or 16384,  -- 16KB max per dump
    dma_compare_enabled = os.getenv("DMA_COMPARE_ENABLED") ~= "0",
    dma_compare_max = tonumber(os.getenv("DMA_COMPARE_MAX")) or 50,
    dma_compare_sample_bytes = tonumber(os.getenv("DMA_COMPARE_SAMPLE_BYTES")) or 32,
}
-- Dependent config values
CFG.dma_dump_start_frame = tonumber(os.getenv("DMA_DUMP_START_FRAME")) or 0
-- v2.3: DMA log start frame - skip ALL DMA logging until this frame to prevent timeout
-- Defaults to STAGING_START_FRAME - 10 (so we have some context before staging starts)
-- Note: STAGING_START_FRAME not yet defined here, so read env directly
local _staging_start = tonumber(os.getenv("STAGING_START_FRAME")) or 0
CFG.dma_log_start_frame = tonumber(os.getenv("DMA_LOG_START_FRAME")) or math.max(0, _staging_start - 10)

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
-- v2.1: Per-frame cap prevents runaway staging writes from timing out
local STAGING_MAX_WRITES_PER_FRAME = tonumber(os.getenv("STAGING_MAX_WRITES_PER_FRAME")) or 2048
-- v2.1: Sentinel sampling: 0 = full range, >0 = step size (e.g., 0x40 = every 64 bytes)
local STAGING_SENTINEL_STEP = tonumber(os.getenv("STAGING_SENTINEL_STEP") or "0", 16)
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

-- v2.8: BUFFER_WRITE_WATCH - trace what writes to the discovered source buffer
-- This is the next rung: ROM -> source buffer -> staging -> VRAM
-- Target: primary source region discovered in v2.7 (0x01530-0x0161A)
local BUFFER_WRITE_WATCH_ENABLED = os.getenv("BUFFER_WRITE_WATCH") == "1"
local BUFFER_WRITE_START = parse_int(os.getenv("BUFFER_WRITE_START"), 0x1530)
local BUFFER_WRITE_END = parse_int(os.getenv("BUFFER_WRITE_END"), 0x161A)
local BUFFER_WRITE_PC_SAMPLES = tonumber(os.getenv("BUFFER_WRITE_PC_SAMPLES")) or 8

-- Per-frame staging write stats
local staging_frame_stats = {}  -- [frame] = {stats}
local staging_current_frame = nil
local staging_current_stats = nil

-- ROM read tracking during staging fills
local staging_active = false
local staging_first_pc = nil  -- PC that started the fill
-- v2.1: Track writes dropped due to per-frame cap (for diagnostics)
local staging_dropped_writes = 0

-- v2.2: Lazy registration flags (init-time timeout mitigation)
local staging_callbacks_registered = false
local wram_source_callbacks_registered = false

-- v2.8: Buffer write tracking state
local buffer_write_callbacks_registered = false
local buffer_write_frame_stats = {}  -- [frame] = {first_pc, min_addr, max_addr, count, pc_samples}
local buffer_write_current_frame = nil
local buffer_write_current_stats = nil

-- v2.9: Fill session tracking (PRG reads during buffer fill)
-- Session starts on first write to source buffer (0x1530-0x161A)
-- Session ends when staging DMA fires
-- Only log PRG reads during active fill session (bounded window = safe)
local fill_session_active = false
local fill_session_start_frame = nil
local fill_session_prg_reads = {}      -- Ring buffer of {addr, pc, k} during fill
local fill_session_prg_head = 0
local FILL_SESSION_RING_SIZE = 256     -- Enough for typical fill operations
local fill_session_prg_total = 0       -- Total PRG reads during session (may exceed ring size)

-- v2.10: Buffer byte capture for content validation
-- Captures actual bytes written to source buffer during fill session
-- Used to compare against ROM bytes at candidate PRG addresses
local fill_session_buffer_bytes = {}   -- [offset_from_start] = byte value
local fill_session_buffer_min = nil    -- Min address written
local fill_session_buffer_max = nil    -- Max address written

-- v2.11: Cold-start detector and populate session
-- Detects when the tile buffer (0x1530-0x161A) is FIRST populated
-- Triggers bounded PRG logging only during actual tile data fill
local POPULATE_ENABLED = parse_bool(os.getenv("POPULATE_ENABLED"), true)
local POPULATE_HASH_INTERVAL = parse_int(os.getenv("POPULATE_HASH_INTERVAL"), 100)  -- Check hash every N frames
local POPULATE_CYCLE_BUDGET = parse_int(os.getenv("POPULATE_CYCLE_BUDGET"), 50000)  -- Max cycles to log PRG reads
local POPULATE_MIN_CHANGE_BYTES = parse_int(os.getenv("POPULATE_MIN_CHANGE_BYTES"), 32)  -- Min bytes changed to trigger

-- v2.12: Exclude metadata range from triggering
-- Metadata = pointers/indices at 0x157B-0x15BE (68 bytes)
-- Tile data = everything else in the buffer range (0x1530-0x161A minus metadata)
-- Only trigger POPULATE_SESSION when TILE-DATA changes, not metadata churn
local POPULATE_EXCLUDE_START = parse_int(os.getenv("POPULATE_EXCLUDE_START"), 0x157B)
local POPULATE_EXCLUDE_END = parse_int(os.getenv("POPULATE_EXCLUDE_END"), 0x15BE)

-- v2.17: Consolidated populate state into single table (Lua 200 local var limit)
local POPULATE_RING_SIZE = 2048         -- v2.13: Increased to capture full input stream
local POPULATE_STREAM_MAX = 4096        -- Max bytes to capture in order
local HEADER_MARKERS = {0xE0, 0xE1, 0xE2, 0xE3, 0xE4, 0xE5, 0xE6, 0xE7}

-- v2.17: Multi-session config
local POPULATE_CHAIN_ENABLED = parse_bool(os.getenv("POPULATE_CHAIN_ENABLED"), true)
local POPULATE_STABLE_FRAMES = parse_int(os.getenv("POPULATE_STABLE_FRAMES"), 60)

-- Populate state table (reduces local var count by ~25)
local pop = {
    -- Cold-start state
    initial_hash = nil,
    initial_snapshot = nil,
    triggered = false,
    last_hash_frame = 0,
    -- v2.17: Multi-session chaining
    session_number = 0,
    last_session_end_frame = 0,
    cumulative_offsets = {},
    stable_since_frame = nil,
    episode_complete = false,
    -- Session state
    session_active = false,
    session_start_frame = nil,
    session_start_cycle = nil,
    prg_reads = {},
    prg_head = 0,
    prg_total = 0,
    buffer_bytes = {},
    write_count = 0,
    write_pcs = {},
    pc_ranges = {},
    -- v2.14: Stream tracking
    earliest_prg = nil,
    header_candidate = nil,
    stream_bytes = {},
}

-- v2.15: Ablation config (kept separate for clarity)
local ABLATION_ENABLED = parse_bool(os.getenv("ABLATION_ENABLED"), false)
local ABLATION_PRG_START_RAW = parse_int(os.getenv("ABLATION_PRG_START"), 0xE894F4)
local ABLATION_PRG_END_RAW = parse_int(os.getenv("ABLATION_PRG_END"), 0xE89551)
local ABLATION_VALUE = parse_int(os.getenv("ABLATION_VALUE"), 0x00)

-- v2.19 FIX: PRG callback receives CPU addresses (0xC00000+), NOT file offsets!
-- Evidence: prg_runs logs values like 0xC469F6, 0xED04FE which are > 0x3FFFFF (4MB file max).
-- Mesen2 internally maps the registered range (0-prg_size) to CPU space when invoking callback.
-- No conversion needed - use CPU addresses directly.
local ABLATION_PRG_START = ABLATION_PRG_START_RAW
local ABLATION_PRG_END = ABLATION_PRG_END_RAW
local ablation_corrupted_count = 0

-- v2.20: Per-staging-DMA ablation tracking (not session-scoped)
-- ablation_total increments on every corrupted read
-- ablation_last_at_staging snapshots at each STAGING_SUMMARY
-- delta = ablated reads since last staging DMA (meaningful for causality)
local ablation_total = 0
local ablation_last_at_staging = 0

-- Log ablation config at startup
if ABLATION_ENABLED then
    log(string.format(
        "ABLATION_CONFIG: enabled=true range=0x%06X-0x%06X value=0x%02X (CPU addresses, no conversion)",
        ABLATION_PRG_START, ABLATION_PRG_END, ABLATION_VALUE
    ))
end

-- v2.18: READ_COVERAGE - track what bytes are READ from source buffer
-- Answers: "not written" ≠ "not used" - staging may read bytes without rewriting them
-- Uses same source buffer range as BUFFER_WRITE_WATCH (0x1530-0x161A)
local READ_COVERAGE_ENABLED = parse_bool(os.getenv("READ_COVERAGE_ENABLED"), true)
local READ_COVERAGE_TILE_SIZE = 32  -- SNES 4bpp tile = 32 bytes
local read_cov = {
    -- Per-offset read bitmap (offset relative to BUFFER_WRITE_START)
    offsets_read = {},  -- [offset] = true if read at least once
    -- Per-tile stats (8 tiles for 235-byte buffer)
    tiles_read = {},    -- [tile_index] = count of bytes read in that tile
    -- Totals
    total_reads = 0,
    unique_offsets = 0,
    -- Report flag (print once at episode complete)
    reported = false,
}

-- v2.9: Forward declarations for fill session functions (called before definition)
local log_fill_session_summary
local reset_fill_session
local compress_prg_runs

-- v2.11: Forward declarations for populate session functions
local compute_buffer_hash
local take_buffer_snapshot
local check_buffer_cold_start
local log_populate_session_summary
local reset_populate_session

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
local staging_wram_pair_total = 0

local function init_staging_stats()
    return {
        count = 0,
        -- NOTE: unique_addrs hash table REMOVED in v1.9 (caused 28K+ hash ops per staging fill)
        -- Uniqueness is now estimated from (max_addr - min_addr + 1) in get_staging_summary()
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
    staging_wram_pair_total = 0
    staging_wram_sources = {}
    -- Reset ring buffer count (gate for hot-path scanning)
    wram_src_seen_any = 0
    -- v2.1: Reset per-frame cap counter
    staging_dropped_writes = 0
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
    -- NOTE: max_run_len is capped by STAGING_RING_SIZE - if ring size < 64, HIGH is unreachable
    -- v2.5: Recommend STAGING_RING_SIZE >= 256 so 64-byte runs can reach HIGH quality
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

    -- Build source summary from ring buffer ONCE at DMA end (was per-write, now per-DMA)
    -- This is O(ring_size) instead of O(writes × ring_size) - 4000x faster for 4KB DMAs
    staging_wram_sources = {}
    staging_wram_pair_total = 0
    local min_seq = staging_session_start_seq or 0

    for cpu_label, buffer in pairs(wram_src_ring_buffer) do
        for i = 1, RING_BUFFER_SIZE do
            local entry = buffer[i]
            if entry and entry.seq >= min_seq then
                local addr = entry.addr
                if not staging_wram_sources[addr] then
                    staging_wram_sources[addr] = {count = 0, cpus = {}}
                end
                staging_wram_sources[addr].count = staging_wram_sources[addr].count + 1
                staging_wram_sources[addr].cpus[cpu_label] = (staging_wram_sources[addr].cpus[cpu_label] or 0) + 1
                staging_wram_pair_total = staging_wram_pair_total + 1
            end
        end
    end

    if staging_wram_pair_total == 0 then
        log(string.format(
            "STAGING_WRAM_SOURCE: frame=%d vram_word=0x%04X size=%d NO_WRAM_PAIRS (source not in 0x%04X-0x%04X or not WRAM)",
            frame, vram_addr, dma_size, STAGING_WRAM_SRC_START, STAGING_WRAM_SRC_END
        ))
        return
    end

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
    -- NOTE: max_run_len is capped by STAGING_RING_SIZE - if ring size < 64, HIGH is unreachable
    -- v2.5: Recommend STAGING_RING_SIZE >= 256 so 64-byte runs can reach HIGH quality
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
        -- v2.1: Gate on STAGING_START_FRAME first (fast check)
        local frame = get_canonical_frame()
        if STAGING_START_FRAME > 0 and frame < STAGING_START_FRAME then
            return
        end
        -- GATE: Only track reads when staging session is active (or prearm enabled)
        if not staging_active and not STAGING_WRAM_PREARM then
            return
        end

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

        -- v2.18: READ_COVERAGE - track reads from source buffer
        -- Check if this read is within the source buffer range (0x1530-0x161A)
        if READ_COVERAGE_ENABLED and BUFFER_WRITE_WATCH_ENABLED then
            if normalized_addr >= BUFFER_WRITE_START and normalized_addr <= BUFFER_WRITE_END then
                local offset = normalized_addr - BUFFER_WRITE_START
                read_cov.total_reads = read_cov.total_reads + 1
                if not read_cov.offsets_read[offset] then
                    read_cov.offsets_read[offset] = true
                    read_cov.unique_offsets = read_cov.unique_offsets + 1
                    -- Update per-tile count
                    local tile_idx = math.floor(offset / READ_COVERAGE_TILE_SIZE)
                    read_cov.tiles_read[tile_idx] = (read_cov.tiles_read[tile_idx] or 0) + 1
                end
            end
        end
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

    -- NOTE: unique_addrs tracking REMOVED in v1.9 (per-write hash ops were the timeout cause)
    -- Uniqueness is estimated from range in get_staging_summary()

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

    -- NOTE: WRAM source ring buffer summarization moved to log_staging_wram_source_summary()
    -- This was per-write O(writes × ring_size); now it's per-DMA O(ring_size) - 4000x faster
end

local function get_staging_summary(src_addr, src_size)
    -- Collect stats from recent frames that overlap with DMA source range
    local total_count = 0
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

    -- Estimate unique addresses from range (v1.9: removed per-write hash tracking)
    -- For SEQUENTIAL_BURST: unique ≈ range size (accurate)
    -- For SCATTERED_CHUNKS: unique ≤ range size (conservative estimate)
    local estimated_unique = 0
    if min_addr and max_addr then
        estimated_unique = max_addr - min_addr + 1
    end

    return {
        pattern = pattern,
        total_writes = total_count,
        unique_addrs = estimated_unique,
        sequential = total_sequential,
        jumps = total_jumps,
        min_addr = min_addr,
        max_addr = max_addr,
        frames_with_writes = frames_with_writes,
        pc_samples = all_pcs,
    }
end

-- v2.19: Compute a stable hash of the DMA payload currently in WRAM.
-- This gives a deterministic "output signal" for ablation/binary-search against staging DMAs.
-- payload_hash changes → you've found a causal PRG region feeding the exact bytes that went to VRAM.
local function compute_dma_payload_hash(src_24, size)
    if not wram_mem_type or not size or size <= 0 then return nil end

    local start_addr = src_24
    if wram_address_mode == "relative" then
        local bank = (src_24 >> 16) & 0xFF
        local offs = src_24 & 0xFFFF
        if bank ~= 0x7E and bank ~= 0x7F then
            return nil
        end
        start_addr = (bank - 0x7E) * 0x10000 + offs
    end

    -- djb2 hash: hash * 33 + byte
    local hash = 5381
    for i = 0, size - 1 do
        local byte = emu.read(start_addr + i, wram_mem_type, false) or 0
        hash = ((hash * 33) + byte) % 0x100000000
    end
    return hash
end

local function log_staging_summary_for_dma(src_addr, src_size, vram_addr)
    if not STAGING_WATCH_ENABLED then return end

    local frame = get_canonical_frame()
    -- Skip early frames (menus/intro) if start frame is configured
    if STAGING_START_FRAME > 0 and frame < STAGING_START_FRAME then return end

    local summary = get_staging_summary(src_addr, src_size)

    -- v2.19: Compute payload hash for ablation binary-search
    local payload_hash = compute_dma_payload_hash(src_addr, src_size)

    -- Format PC samples
    local pc_str = ""
    if #summary.pc_samples > 0 then
        local pc_parts = {}
        for _, p in ipairs(summary.pc_samples) do
            pc_parts[#pc_parts + 1] = string.format("%02X:%04X", p.k or 0, p.pc or 0)
        end
        pc_str = " pcs=[" .. table.concat(pc_parts, ",") .. "]"
    end

    -- v2.1: Add dropped writes count if any were capped
    local dropped_str = ""
    if staging_dropped_writes > 0 then
        dropped_str = string.format(" dropped=%d", staging_dropped_writes)
    end

    -- v2.20: Per-DMA ablation delta (meaningful for causality testing)
    local ablation_delta = ablation_total - ablation_last_at_staging
    ablation_last_at_staging = ablation_total
    local ablation_str = ""
    if ABLATION_ENABLED then
        ablation_str = string.format(" ablated=%d", ablation_delta)
    end

    log(string.format(
        "STAGING_SUMMARY: frame=%d src=0x%06X size=%d payload_hash=0x%08X vram=0x%04X pattern=%s writes=%d unique=%d seq=%d jumps=%d range=0x%06X-0x%06X frames=%d%s%s%s",
        frame,
        src_addr,
        src_size,
        payload_hash or 0,
        vram_addr,
        summary.pattern,
        summary.total_writes,
        summary.unique_addrs,
        summary.sequential,
        summary.jumps,
        summary.min_addr or 0,
        summary.max_addr or 0,
        summary.frames_with_writes,
        pc_str,
        dropped_str,
        ablation_str
    ))
end

local function on_staging_write(address, value)
    if not STAGING_WATCH_ENABLED then return end
    -- v2.1: Gate capture on STAGING_START_FRAME (was logging-only, now callbacks early-exit)
    local frame = get_canonical_frame()
    if STAGING_START_FRAME > 0 and frame < STAGING_START_FRAME then
        return
    end
    -- v2.1: Per-frame cap prevents runaway writes from timing out
    local stats = staging_current_stats
    if stats and stats.count >= STAGING_MAX_WRITES_PER_FRAME then
        staging_dropped_writes = staging_dropped_writes + 1
        return
    end
    -- OPTIMIZATION: Only call get_cpu_state_snapshot() when we actually need the PC.
    -- PC is needed for: (1) staging_first_pc on first write, (2) PC sampling (first N writes per frame)
    -- After N samples per frame, we skip the expensive emu.getState() call.
    local pc_snapshot = nil
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
    -- v2.3: Skip logging until DMA_LOG_START_FRAME to prevent timeout
    if frame_count < CFG.dma_log_start_frame then return end
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

                -- v2.9: End fill session and log PRG reads that occurred during buffer fill
                if BUFFER_WRITE_WATCH_ENABLED and fill_session_active then
                    log_fill_session_summary(get_canonical_frame(), captured_vmadd, das)
                    reset_fill_session()
                end
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
    -- v2.3: Skip logging until DMA_LOG_START_FRAME to prevent timeout
    if frame_count < CFG.dma_log_start_frame then return end
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
    -- v2.3: Skip logging until DMA_LOG_START_FRAME to prevent timeout
    if frame_count < CFG.dma_log_start_frame then return end
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

-- Forward declaration for try_load_savestate (defined later in file)
-- This allows on_end_frame to call it even though it's defined after
local try_load_savestate

-- v2.2: Lazy staging callback registration (called from on_end_frame)
local function register_staging_callbacks()
    if not wram_mem_type then
        log("WARNING: Staging watch enabled but no WRAM memType resolved")
        return
    end

    -- Compute staging watch addresses based on WRAM addressing mode
    local staging_start, staging_end
    if wram_address_mode == "absolute" then
        staging_start = 0x7E0000 + STAGING_WATCH_START
        staging_end = 0x7E0000 + STAGING_WATCH_END
    else
        staging_start = STAGING_WATCH_START
        staging_end = STAGING_WATCH_END
    end

    -- Sentinel sampling mode (sparse callbacks) vs full range
    local snes_staging_ref
    if STAGING_SENTINEL_STEP > 0 then
        local sentinel_count = 0
        for addr = staging_start, staging_end, STAGING_SENTINEL_STEP do
            local ref = add_memory_callback_compat(
                on_staging_write,
                emu.callbackType.write,
                addr,
                addr,
                cpu_type,
                wram_mem_type
            )
            if ref then sentinel_count = sentinel_count + 1 end
        end
        snes_staging_ref = sentinel_count > 0
        if snes_staging_ref then
            log(string.format(
                "INFO: Staging SENTINEL watch registered (lazy): 0x%06X-0x%06X step=0x%X (%d callbacks) at frame=%d",
                staging_start, staging_end, STAGING_SENTINEL_STEP, sentinel_count, frame_count
            ))
        else
            log("WARNING: failed to register sentinel staging watch for S-CPU")
        end
    else
        snes_staging_ref = add_memory_callback_compat(
            on_staging_write,
            emu.callbackType.write,
            staging_start,
            staging_end,
            cpu_type,
            wram_mem_type
        )
        if snes_staging_ref then
            log(string.format(
                "INFO: Staging watch registered (lazy) for S-CPU: 0x%06X-0x%06X at frame=%d",
                staging_start, staging_end, frame_count
            ))
        else
            log("WARNING: failed to register staging write watch for S-CPU")
        end
    end
end

-- =============================================================================
-- v2.8: BUFFER_WRITE_WATCH - Trace what WRITES to the source buffer
-- This is the next rung: ROM -> source buffer -> staging -> VRAM
-- =============================================================================

local function on_buffer_write(address, value)
    if not BUFFER_WRITE_WATCH_ENABLED then return end

    local frame = get_canonical_frame()
    -- Skip early frames
    if STAGING_START_FRAME > 0 and frame < STAGING_START_FRAME then
        return
    end

    -- v2.17: Multi-session chaining - trigger on tile-data writes unless episode complete
    -- Episode complete = buffer stable for POPULATE_STABLE_FRAMES
    if POPULATE_ENABLED and not pop.episode_complete and not pop.session_active then
        local base_addr = wram_address_mode == "absolute" and 0x7E0000 or 0
        local offset = address - base_addr
        -- Is this a tile-data address? (NOT in metadata exclusion range)
        if offset < POPULATE_EXCLUDE_START or offset > POPULATE_EXCLUDE_END then
            -- Tile-data write detected - start new populate session
            pop.triggered = true
            pop.session_active = true
            pop.session_number = pop.session_number + 1
            pop.session_start_frame = frame
            pop.session_start_cycle = emu.getState and emu.getState().masterClock or 0
            pop.prg_reads = {}
            pop.prg_head = 0
            pop.prg_total = 0
            pop.buffer_bytes = {}
            pop.write_count = 0
            pop.write_pcs = {}
            pop.pc_ranges = {}
            -- v2.14: Initialize stream tracking
            pop.earliest_prg = nil
            pop.header_candidate = nil
            pop.stream_bytes = {}
            -- v2.17: Reset stability tracking when new session starts
            pop.stable_since_frame = nil
            -- Take initial snapshot for comparison at session end
            pop.initial_snapshot = take_buffer_snapshot()
            log(string.format("POPULATE_SESSION_START: session=%d frame=%d trigger=TILE_WRITE offset=0x%04X value=0x%02X cumulative_offsets=%d",
                pop.session_number, frame, offset, value or 0,
                (function() local c=0; for _ in pairs(pop.cumulative_offsets) do c=c+1 end; return c end)()))
        end
    end

    -- v2.9: Start fill session on first write to source buffer
    -- PRG read callbacks are gated on this flag (only log during active fill)
    if not fill_session_active then
        fill_session_active = true
        fill_session_start_frame = frame
        fill_session_prg_reads = {}
        fill_session_prg_head = 0
        fill_session_prg_total = 0
        -- v2.10: Reset buffer byte capture
        fill_session_buffer_bytes = {}
        fill_session_buffer_min = nil
        fill_session_buffer_max = nil
    end

    -- v2.10: Capture the written byte (keyed by absolute address for simplicity)
    -- This lets us compare against ROM bytes later
    fill_session_buffer_bytes[address] = value
    if not fill_session_buffer_min or address < fill_session_buffer_min then
        fill_session_buffer_min = address
    end
    if not fill_session_buffer_max or address > fill_session_buffer_max then
        fill_session_buffer_max = address
    end

    -- v2.11: Track writes during populate session (cold-start detection)
    if pop.session_active then
        -- Get offset within buffer (for cleaner logging)
        local base_addr = wram_address_mode == "absolute" and 0x7E0000 or 0
        local offset = address - base_addr

        -- Only track if NOT in metadata exclusion range
        if offset < POPULATE_EXCLUDE_START or offset > POPULATE_EXCLUDE_END then
            pop.buffer_bytes[offset] = value
            pop.write_count = pop.write_count + 1
            -- v2.17: Track cumulative offsets across ALL sessions
            pop.cumulative_offsets[offset] = true

            -- Track PC with address range (v2.12: enhanced attribution)
            local pc_snapshot = get_cpu_state_snapshot()
            if pc_snapshot then
                local pc_key = string.format("%02X:%04X", pc_snapshot.k_val or 0, pc_snapshot.pc_val or 0)
                pop.write_pcs[pc_key] = (pop.write_pcs[pc_key] or 0) + 1

                -- v2.12: Track address range per PC
                if not pop.pc_ranges[pc_key] then
                    pop.pc_ranges[pc_key] = {min = offset, max = offset, count = 1}
                else
                    local r = pop.pc_ranges[pc_key]
                    if offset < r.min then r.min = offset end
                    if offset > r.max then r.max = offset end
                    r.count = r.count + 1
                end
            end
        end
    end

    -- Initialize or rotate frame stats
    if buffer_write_current_frame ~= frame then
        -- Archive previous frame stats if any
        if buffer_write_current_frame and buffer_write_current_stats then
            buffer_write_frame_stats[buffer_write_current_frame] = buffer_write_current_stats
        end
        buffer_write_current_frame = frame
        buffer_write_current_stats = {
            count = 0,
            min_addr = nil,
            max_addr = nil,
            pc_samples = {},  -- {k, pc} pairs
            first_write_pc = nil,
        }
    end

    local stats = buffer_write_current_stats
    stats.count = stats.count + 1

    -- Track address range
    if not stats.min_addr or address < stats.min_addr then
        stats.min_addr = address
    end
    if not stats.max_addr or address > stats.max_addr then
        stats.max_addr = address
    end

    -- Sample PCs (only first N per frame to limit overhead)
    if #stats.pc_samples < BUFFER_WRITE_PC_SAMPLES then
        local pc_snapshot = get_cpu_state_snapshot()
        if pc_snapshot then
            stats.pc_samples[#stats.pc_samples + 1] = {
                k = pc_snapshot.k_val or 0,
                pc = pc_snapshot.pc_val or 0,
            }
            if not stats.first_write_pc then
                stats.first_write_pc = stats.pc_samples[1]
            end
        end
    end
end

-- v2.9: PRG read callback - logs during active fill session OR populate session
-- This is safe because it's bounded to the fill/populate window (not always-on)
local function on_fill_session_prg_read(address, value)
    -- v2.11: Also track during populate session (cold-start detection)
    if pop.session_active then
        pop.prg_total = pop.prg_total + 1
        pop.prg_head = (pop.prg_head % POPULATE_RING_SIZE) + 1

        local pc_snapshot = get_cpu_state_snapshot()
        local k_val, pc_val = 0, 0
        if pc_snapshot then
            k_val = pc_snapshot.k_val or 0
            pc_val = pc_snapshot.pc_val or 0
        end

        -- v2.12: Store actual byte value for input stream dump
        pop.prg_reads[pop.prg_head] = {
            addr = address,
            value = value,  -- v2.12: Capture actual PRG byte value
            k = k_val,
            pc = pc_val,
        }

        -- v2.14: Track earliest PRG address (stream start candidate)
        if not pop.earliest_prg or address < pop.earliest_prg then
            pop.earliest_prg = address
        end

        -- v2.14: Track first header marker (E0/E1/etc) as stream start candidate
        if not pop.header_candidate then
            for _, marker in ipairs(HEADER_MARKERS) do
                if value == marker then
                    pop.header_candidate = {addr = address, value = value}
                    break
                end
            end
        end

        -- v2.14: Build ordered stream bytes (first N reads in order)
        if #pop.stream_bytes < POPULATE_STREAM_MAX then
            pop.stream_bytes[#pop.stream_bytes + 1] = {addr = address, value = value}
        end
    end

    -- v2.19: Ablation applies to ANY PRG read during populate session (not just fill session)
    -- This ensures PRG corruption affects staging even when BUFFER_WRITE_WATCH=0
    if ABLATION_ENABLED and address >= ABLATION_PRG_START and address <= ABLATION_PRG_END then
        ablation_corrupted_count = ablation_corrupted_count + 1
        ablation_total = ablation_total + 1  -- v2.20: per-DMA tracking
        return ABLATION_VALUE  -- CPU sees corrupted byte
    end

    -- Gate on fill session (the key optimization - only log during buffer fill)
    if not fill_session_active then
        return
    end

    -- Push to ring buffer
    fill_session_prg_total = fill_session_prg_total + 1
    fill_session_prg_head = (fill_session_prg_head % FILL_SESSION_RING_SIZE) + 1

    -- Get PC for this read (optional - may be expensive)
    local pc_snapshot = get_cpu_state_snapshot()
    local k_val, pc_val = 0, 0
    if pc_snapshot then
        k_val = pc_snapshot.k_val or 0
        pc_val = pc_snapshot.pc_val or 0
    end

    fill_session_prg_reads[fill_session_prg_head] = {
        addr = address,
        k = k_val,
        pc = pc_val,
    }

    -- v2.15: Ablation - corrupt reads in specified range to prove causality
    -- Return modified value to CPU, but we logged the original above
    -- NOTE: This is likely unreachable (earlier ablation hook returns first), kept for safety
    if ABLATION_ENABLED and address >= ABLATION_PRG_START and address <= ABLATION_PRG_END then
        ablation_corrupted_count = ablation_corrupted_count + 1
        ablation_total = ablation_total + 1  -- v2.20: per-DMA tracking
        return ABLATION_VALUE  -- CPU sees corrupted byte
    end
    -- Return nil = no modification (CPU sees original value)
end

-- v2.9: Compress PRG reads into contiguous runs for summary
compress_prg_runs = function(reads, total_count)
    if not reads or #reads == 0 then
        return "NO_READS", 0, 0
    end

    -- Sort by address for run detection
    local sorted = {}
    for i = 1, math.min(#reads, FILL_SESSION_RING_SIZE) do
        if reads[i] then
            sorted[#sorted + 1] = reads[i].addr
        end
    end
    if #sorted == 0 then
        return "NO_READS", 0, 0
    end
    table.sort(sorted)

    -- Compress into runs
    local runs = {}
    local run_start = sorted[1]
    local run_end = sorted[1]
    local unique_count = 1

    for i = 2, #sorted do
        local addr = sorted[i]
        if addr == run_end + 1 then
            -- Extend current run
            run_end = addr
        elseif addr > run_end then
            -- New run (skip duplicates)
            runs[#runs + 1] = {start = run_start, stop = run_end}
            run_start = addr
            run_end = addr
            unique_count = unique_count + 1
        end
        -- else: duplicate, skip
    end
    -- Final run
    runs[#runs + 1] = {start = run_start, stop = run_end}

    -- Format runs
    local run_strs = {}
    local max_run_size = 0
    for _, r in ipairs(runs) do
        local size = r.stop - r.start + 1
        if size > max_run_size then max_run_size = size end
        run_strs[#run_strs + 1] = string.format("0x%06X-0x%06X(%d)", r.start, r.stop, size)
    end

    return table.concat(run_strs, ","), #runs, max_run_size
end

-- v2.9: Log fill session summary when staging DMA fires
log_fill_session_summary = function(frame, vram_addr, dma_size)
    if not fill_session_active then
        return
    end

    local ok, prg_runs_str, num_runs, max_run = pcall(function()
        return compress_prg_runs(fill_session_prg_reads, fill_session_prg_total)
    end)

    if not ok then
        log("WARNING: compress_prg_runs failed: " .. tostring(prg_runs_str))
        return
    end

    log(string.format(
        "FILL_SESSION: frame=%d vram=0x%04X dma_size=%d prg_total=%d prg_unique=%d runs=%d max_run=%d prg_runs=[%s]",
        frame,
        vram_addr,
        dma_size,
        fill_session_prg_total,
        math.min(#fill_session_prg_reads, FILL_SESSION_RING_SIZE),
        num_runs,
        max_run,
        prg_runs_str
    ))

    -- v2.10: Dump buffer bytes for content validation
    -- Log the actual bytes written to source buffer during this fill session
    if fill_session_buffer_min and fill_session_buffer_max then
        local byte_count = 0
        local hex_parts = {}
        -- Iterate over address range and collect bytes
        for addr = fill_session_buffer_min, fill_session_buffer_max do
            local b = fill_session_buffer_bytes[addr]
            if b then
                table.insert(hex_parts, string.format("%02X", b))
                byte_count = byte_count + 1
            else
                -- Gap in written addresses - mark with placeholder
                table.insert(hex_parts, "--")
            end
        end
        local hex_str = table.concat(hex_parts, "")
        -- Log with address range and byte count
        log(string.format(
            "FILL_BUFFER_BYTES: frame=%d addr_range=0x%04X-0x%04X bytes=%d hex=%s",
            frame,
            fill_session_buffer_min,
            fill_session_buffer_max,
            byte_count,
            hex_str
        ))
    end
end

-- v2.9: Reset fill session state (called when staging DMA fires)
reset_fill_session = function()
    fill_session_active = false
    fill_session_start_frame = nil
    fill_session_prg_reads = {}
    fill_session_prg_head = 0
    fill_session_prg_total = 0
    -- v2.10: Clear buffer byte capture
    fill_session_buffer_bytes = {}
    fill_session_buffer_min = nil
    fill_session_buffer_max = nil
end

-- =============================================================================
-- v2.11: COLD-START DETECTOR AND POPULATE SESSION
-- Detects when tile buffer is FIRST populated (not metadata updates)
-- =============================================================================

-- Compute a simple hash of the buffer (DJB2-style, fast enough for Lua)
compute_buffer_hash = function()
    if not wram_mem_type then return nil end

    local hash = 5381
    local base_addr = wram_address_mode == "absolute" and 0x7E0000 or 0
    local start_addr = base_addr + BUFFER_WRITE_START
    local end_addr = base_addr + BUFFER_WRITE_END

    for addr = start_addr, end_addr do
        -- Skip the metadata exclusion range
        local offset = addr - base_addr
        if offset < POPULATE_EXCLUDE_START or offset > POPULATE_EXCLUDE_END then
            local byte = emu.read(addr, wram_mem_type, false) or 0
            hash = ((hash * 33) + byte) % 0x100000000
        end
    end
    return hash
end

-- Take a full snapshot of the buffer (for diff analysis)
take_buffer_snapshot = function()
    if not wram_mem_type then return nil end

    local snapshot = {}
    local base_addr = wram_address_mode == "absolute" and 0x7E0000 or 0
    local start_addr = base_addr + BUFFER_WRITE_START
    local end_addr = base_addr + BUFFER_WRITE_END

    for addr = start_addr, end_addr do
        local offset = addr - base_addr
        -- Include all bytes in snapshot (even metadata, for completeness)
        snapshot[offset] = emu.read(addr, wram_mem_type, false) or 0
    end
    return snapshot
end

-- v2.13: Hash-based checking now only logs initial state
-- Session triggering moved to on_buffer_write (immediate, not reactive)
check_buffer_cold_start = function(frame)
    if not POPULATE_ENABLED then return end
    if not wram_mem_type then return end

    -- Only check every N frames to reduce overhead
    if frame - pop.last_hash_frame < POPULATE_HASH_INTERVAL then
        return
    end
    pop.last_hash_frame = frame

    local current_hash = compute_buffer_hash()
    if not current_hash then return end

    -- First check: store initial state (before any writes happen)
    if pop.initial_hash == nil then
        pop.initial_hash = current_hash
        pop.initial_snapshot = take_buffer_snapshot()
        log(string.format("POPULATE_INIT: frame=%d initial_hash=0x%08X snapshot_size=%d",
            frame, current_hash, pop.initial_snapshot and #pop.initial_snapshot or 0))
        return
    end

    -- v2.13: No longer triggers session here - that's done in on_buffer_write
    -- Just update baseline if not yet triggered (metadata-only changes)
    if not pop.triggered and current_hash ~= pop.initial_hash then
        pop.initial_hash = current_hash
        pop.initial_snapshot = take_buffer_snapshot()
    end
end

-- Log populate session summary
log_populate_session_summary = function(frame, reason)
    if not pop.session_active then return end

    local ok, prg_runs_str, num_runs, max_run = pcall(function()
        return compress_prg_runs(pop.prg_reads, pop.prg_total)
    end)

    if not ok then
        prg_runs_str = "ERROR"
        num_runs = 0
        max_run = 0
    end

    -- Format write PCs
    local pc_parts = {}
    for pc_key, count in pairs(pop.write_pcs) do
        table.insert(pc_parts, string.format("%s:%d", pc_key, count))
    end
    table.sort(pc_parts, function(a, b)
        local ca = tonumber(a:match(":(%d+)$")) or 0
        local cb = tonumber(b:match(":(%d+)$")) or 0
        return ca > cb
    end)
    local pcs_str = table.concat(pc_parts, ",", 1, math.min(#pc_parts, 8))

    log(string.format(
        "POPULATE_SESSION: frame=%d-%d reason=%s writes=%d prg_total=%d prg_unique=%d runs=%d max_run=%d write_pcs=[%s] prg_runs=[%s]",
        pop.session_start_frame or 0,
        frame,
        reason,
        pop.write_count,
        pop.prg_total,
        math.min(#pop.prg_reads, POPULATE_RING_SIZE),
        num_runs,
        max_run,
        pcs_str,
        prg_runs_str
    ))

    -- v2.15: Log ablation stats if enabled (v2.19: CPU addresses, no conversion)
    if ABLATION_ENABLED then
        log(string.format(
            "ABLATION_RESULT: frame=%d enabled=true range=0x%06X-0x%06X value=0x%02X corrupted_reads=%d",
            frame, ABLATION_PRG_START, ABLATION_PRG_END, ABLATION_VALUE, ablation_corrupted_count
        ))
    end

    -- v2.16: Coverage metric - which bytes were written during session
    local buffer_size = BUFFER_WRITE_END - BUFFER_WRITE_START + 1
    local bytes_written = 0
    local tiles_touched = {}  -- tile_index -> count of bytes in that tile
    for offset, _ in pairs(pop.buffer_bytes) do
        bytes_written = bytes_written + 1
        -- Compute tile index (32 bytes per tile, relative to BUFFER_WRITE_START)
        local rel_offset = offset - BUFFER_WRITE_START
        if rel_offset >= 0 and rel_offset < buffer_size then
            local tile_idx = math.floor(rel_offset / 32)
            tiles_touched[tile_idx] = (tiles_touched[tile_idx] or 0) + 1
        end
    end
    -- v2.17: Compute cumulative coverage across all sessions
    local cumulative_count = 0
    for _ in pairs(pop.cumulative_offsets) do
        cumulative_count = cumulative_count + 1
    end
    -- Format tile coverage
    local tile_parts = {}
    local tile_count = math.ceil(buffer_size / 32)
    for i = 0, tile_count - 1 do
        if tiles_touched[i] then
            table.insert(tile_parts, string.format("T%d:%d", i, tiles_touched[i]))
        end
    end
    local tiles_str = #tile_parts > 0 and table.concat(tile_parts, ",") or "NONE"
    log(string.format(
        "POPULATE_COVERAGE: session=%d frame=%d buffer_size=%d session_bytes=%d cumulative_bytes=%d coverage=%.1f%% tiles=[%s]",
        pop.session_number, frame, buffer_size, bytes_written, cumulative_count,
        (cumulative_count / buffer_size) * 100, tiles_str
    ))

    -- v2.17: After logging session, reset for next session (chaining)
    pop.session_active = false
    pop.last_session_end_frame = frame

    -- v2.14: Log stream start candidates (for stable convergence)
    local earliest_str = pop.earliest_prg and string.format("0x%06X", pop.earliest_prg) or "NONE"
    local header_str = "NONE"
    local header_file_offset = "N/A"
    if pop.header_candidate then
        header_str = string.format("0x%06X(0x%02X)", pop.header_candidate.addr, pop.header_candidate.value)
        -- Compute HiROM file offset for header
        local bank = (pop.header_candidate.addr >> 16) & 0xFF
        local addr = pop.header_candidate.addr & 0xFFFF
        if bank >= 0xC0 then
            local file_off = (bank - 0xC0) * 0x10000 + addr
            header_file_offset = string.format("0x%06X", file_off)
        end
    end
    log(string.format(
        "POPULATE_STREAM_START: frame=%d earliest_prg=%s header_candidate=%s header_file_offset=%s stream_bytes_captured=%d",
        frame, earliest_str, header_str, header_file_offset, #pop.stream_bytes
    ))

    -- v2.12: ARTIFACT A - Dump final output bytes (ground truth)
    local snapshot = take_buffer_snapshot()
    local output_hash = 0
    if snapshot then
        local hex_parts = {}
        for offset = BUFFER_WRITE_START, BUFFER_WRITE_END do
            local b = snapshot[offset] or 0
            table.insert(hex_parts, string.format("%02X", b))
            -- v2.14: Simple hash (djb2-style)
            output_hash = ((output_hash * 33) + b) % 0xFFFFFFFF
        end
        local hex_str = table.concat(hex_parts, "")
        log(string.format(
            "POPULATE_OUTPUT_BYTES: frame=%d addr_range=0x%04X-0x%04X bytes=%d hash=0x%08X hex=%s",
            frame,
            BUFFER_WRITE_START,
            BUFFER_WRITE_END,
            BUFFER_WRITE_END - BUFFER_WRITE_START + 1,
            output_hash,
            hex_str
        ))
    end

    -- v2.12: ARTIFACT B - Dump input stream bytes (compressed data from ROM)
    -- Format: addr:value pairs, sorted by address for contiguous stream detection
    if pop.prg_reads and #pop.prg_reads > 0 then
        -- Sort by address to reconstruct contiguous streams
        local sorted_reads = {}
        for i = 1, math.min(#pop.prg_reads, POPULATE_RING_SIZE) do
            if pop.prg_reads[i] then
                sorted_reads[#sorted_reads + 1] = pop.prg_reads[i]
            end
        end
        table.sort(sorted_reads, function(a, b) return a.addr < b.addr end)

        -- Find contiguous runs and output as hex streams
        local streams = {}
        local current_stream = nil
        for _, entry in ipairs(sorted_reads) do
            if not current_stream or entry.addr ~= current_stream.end_addr + 1 then
                if current_stream then
                    streams[#streams + 1] = current_stream
                end
                current_stream = {
                    start_addr = entry.addr,
                    end_addr = entry.addr,
                    bytes = {entry.value},
                }
            else
                current_stream.end_addr = entry.addr
                current_stream.bytes[#current_stream.bytes + 1] = entry.value
            end
        end
        if current_stream then
            streams[#streams + 1] = current_stream
        end

        -- Log each contiguous stream (limit to top 5 by length)
        table.sort(streams, function(a, b) return #a.bytes > #b.bytes end)
        for i = 1, math.min(#streams, 5) do
            local stream = streams[i]
            local hex_parts = {}
            for _, b in ipairs(stream.bytes) do
                hex_parts[#hex_parts + 1] = string.format("%02X", b or 0)
            end
            -- v2.14: Include file offset for each stream
            local bank = (stream.start_addr >> 16) & 0xFF
            local addr = stream.start_addr & 0xFFFF
            local file_off_str = "N/A"
            if bank >= 0xC0 then
                file_off_str = string.format("0x%06X", (bank - 0xC0) * 0x10000 + addr)
            end
            log(string.format(
                "POPULATE_INPUT_STREAM: frame=%d prg_range=0x%06X-0x%06X file_offset=%s bytes=%d hex=%s",
                frame,
                stream.start_addr,
                stream.end_addr,
                file_off_str,
                #stream.bytes,
                table.concat(hex_parts, "")
            ))
        end
    end

    -- v2.14: Log first N bytes of ordered stream (in read order, not sorted)
    if #pop.stream_bytes > 0 then
        local first_n = math.min(#pop.stream_bytes, 256)  -- First 256 bytes
        local hex_parts = {}
        local first_addr = pop.stream_bytes[1].addr
        for i = 1, first_n do
            hex_parts[#hex_parts + 1] = string.format("%02X", pop.stream_bytes[i].value or 0)
        end
        local bank = (first_addr >> 16) & 0xFF
        local addr = first_addr & 0xFFFF
        local file_off_str = "N/A"
        if bank >= 0xC0 then
            file_off_str = string.format("0x%06X", (bank - 0xC0) * 0x10000 + addr)
        end
        log(string.format(
            "POPULATE_ORDERED_STREAM: frame=%d first_prg=0x%06X file_offset=%s bytes=%d hex=%s",
            frame, first_addr, file_off_str, first_n, table.concat(hex_parts, "")
        ))
    end

    -- v2.12: ARTIFACT C - Write attribution (which PCs wrote which byte ranges)
    -- Format: pc=XX:XXXX range=0xAAAA-0xBBBB count=N
    local pc_attrib_parts = {}
    for pc_key, range in pairs(pop.pc_ranges) do
        table.insert(pc_attrib_parts, string.format(
            "%s:0x%04X-0x%04X(%d)",
            pc_key, range.min, range.max, range.count
        ))
    end
    -- Sort by count descending
    table.sort(pc_attrib_parts, function(a, b)
        local ca = tonumber(a:match("%((%d+)%)$")) or 0
        local cb = tonumber(b:match("%((%d+)%)$")) or 0
        return ca > cb
    end)
    log(string.format(
        "POPULATE_WRITE_ATTRIBUTION: frame=%d total_writes=%d pc_ranges=[%s]",
        frame,
        pop.write_count,
        table.concat(pc_attrib_parts, ",", 1, math.min(#pc_attrib_parts, 10))
    ))
end

-- Reset populate session
reset_populate_session = function()
    pop.session_active = false
    pop.session_start_frame = nil
    pop.session_start_cycle = nil
    pop.prg_reads = {}
    pop.prg_head = 0
    pop.prg_total = 0
    pop.buffer_bytes = {}
    pop.write_count = 0
    pop.write_pcs = {}
    pop.pc_ranges = {}  -- v2.12
    -- v2.14: Reset stream tracking
    pop.earliest_prg = nil
    pop.header_candidate = nil
    pop.stream_bytes = {}
    -- v2.15: Reset ablation counter
    ablation_corrupted_count = 0
end

local function log_buffer_write_summary(frame)
    if not BUFFER_WRITE_WATCH_ENABLED then return end

    local stats = buffer_write_frame_stats[frame] or buffer_write_current_stats
    if not stats or stats.count == 0 then return end

    -- Format PC samples
    local pc_str = ""
    if #stats.pc_samples > 0 then
        local pc_parts = {}
        for _, p in ipairs(stats.pc_samples) do
            pc_parts[#pc_parts + 1] = string.format("%02X:%04X", p.k or 0, p.pc or 0)
        end
        pc_str = " pcs=[" .. table.concat(pc_parts, ",") .. "]"
    end

    log(string.format(
        "BUFFER_WRITE_SUMMARY: frame=%d writes=%d range=0x%06X-0x%06X%s",
        frame,
        stats.count,
        stats.min_addr or 0,
        stats.max_addr or 0,
        pc_str
    ))
end

local function register_buffer_write_callbacks()
    if not wram_mem_type then
        log("WARNING: Buffer write watch enabled but no WRAM memType resolved")
        return false
    end

    if not BUFFER_WRITE_WATCH_ENABLED then
        return false
    end

    -- Compute buffer write watch addresses based on WRAM addressing mode
    local buffer_start, buffer_end
    if wram_address_mode == "absolute" then
        buffer_start = 0x7E0000 + BUFFER_WRITE_START
        buffer_end = 0x7E0000 + BUFFER_WRITE_END
    else
        buffer_start = BUFFER_WRITE_START
        buffer_end = BUFFER_WRITE_END
    end

    local buffer_ref = add_memory_callback_compat(
        on_buffer_write,
        emu.callbackType.write,
        buffer_start,
        buffer_end,
        cpu_type,
        wram_mem_type
    )

    if buffer_ref then
        log(string.format(
            "INFO: Buffer write watch registered (lazy) for S-CPU: 0x%06X-0x%06X at frame=%d",
            buffer_start, buffer_end, frame_count
        ))

        -- v2.9: Also register PRG read callback for fill session tracking
        -- This callback is gated on fill_session_active (only logs during buffer fill = safe)
        if MEM.prg then
            local prg_size = emu.getMemorySize(MEM.prg) or 0
            if prg_size > 0 then
                local prg_ref = add_memory_callback_compat(
                    on_fill_session_prg_read,
                    emu.callbackType.read,
                    0x000000,
                    prg_size - 1,
                    cpu_type,
                    MEM.prg
                )
                if prg_ref then
                    log(string.format(
                        "INFO: Fill session PRG read callback registered: 0x%06X-0x%06X at frame=%d",
                        0, prg_size - 1, frame_count
                    ))
                else
                    log("WARNING: failed to register fill session PRG read callback")
                end
            end
        end

        return true
    else
        log(string.format(
            "WARNING: failed to register buffer write watch for S-CPU: 0x%06X-0x%06X",
            buffer_start, buffer_end
        ))
        return false
    end
end

-- v2.2: Lazy WRAM source callback registration (called from on_end_frame)
-- v2.4 FIX: Was checking wrong flag (STAGING_WRAM_TRACKING_ENABLED instead of STAGING_WRAM_SOURCE_ENABLED)
local function register_wram_source_callbacks()
    if not wram_mem_type then
        log("WARNING: WRAM source tracking enabled but no WRAM memType resolved")
        return false
    end

    -- v2.4 FIX: This function is for STAGING_WRAM_SOURCE, not the debug-wide WRAM tracker
    if not STAGING_WRAM_SOURCE_ENABLED then
        return false
    end

    -- Compute WRAM read ranges (excluding staging buffer)
    local wram_read_ranges = {}
    if wram_address_mode == "absolute" then
        wram_read_ranges = {
            {start = 0x7E0000 + STAGING_WRAM_SRC_START, stop = 0x7E0000 + STAGING_WRAM_SRC_END},
        }
    else
        wram_read_ranges = {
            {start = STAGING_WRAM_SRC_START, stop = STAGING_WRAM_SRC_END},
        }
    end

    local any_registered = false
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
            any_registered = true
            log(string.format(
                "INFO: WRAM source callback registered (lazy) for S-CPU: 0x%06X-0x%06X at frame=%d",
                range.start, range.stop, frame_count
            ))
        else
            log(string.format(
                "WARNING: failed to register WRAM source callback for S-CPU: 0x%06X-0x%06X",
                range.start, range.stop
            ))
        end
    end

    return any_registered
end

local function on_end_frame()
    -- v2.0: Try savestate load if not yet loaded (deferred from init)
    -- Uses forward-declared try_load_savestate; eliminates permanent exec callback
    if SAVESTATE_PATH and not state_loaded then
        try_load_savestate()
    end

    frame_count = frame_count + 1

    -- v2.11: Cold-start detection (check for tile buffer population)
    if POPULATE_ENABLED and not pop.triggered then
        check_buffer_cold_start(frame_count)
    end

    -- v2.11: End populate session after cycle budget or N frames
    if pop.session_active then
        local elapsed_frames = frame_count - (pop.session_start_frame or 0)
        -- v2.13: End after 10 frames (tight window) or if ring is full
        -- This captures the initial population burst without noise from later frames
        if elapsed_frames >= 10 or pop.prg_total >= POPULATE_RING_SIZE then
            log_populate_session_summary(frame_count, "budget")
            reset_populate_session()
        end
    end

    -- v2.17: Stability detection - mark episode complete if no writes for POPULATE_STABLE_FRAMES
    if POPULATE_CHAIN_ENABLED and pop.triggered and not pop.episode_complete then
        if not pop.session_active then
            -- Not in active session - check stability
            if pop.stable_since_frame == nil then
                -- Start stability timer
                pop.stable_since_frame = frame_count
            elseif frame_count - pop.stable_since_frame >= POPULATE_STABLE_FRAMES then
                -- Buffer has been stable - mark episode complete
                pop.episode_complete = true
                local cumulative_count = 0
                for _ in pairs(pop.cumulative_offsets) do
                    cumulative_count = cumulative_count + 1
                end
                local buffer_size = BUFFER_WRITE_END - BUFFER_WRITE_START + 1
                log(string.format(
                    "POPULATE_EPISODE_COMPLETE: frame=%d sessions=%d stable_frames=%d cumulative_bytes=%d coverage=%.1f%%",
                    frame_count, pop.session_number, POPULATE_STABLE_FRAMES,
                    cumulative_count, (cumulative_count / buffer_size) * 100
                ))
                -- v2.18: Log READ_COVERAGE at episode complete
                if READ_COVERAGE_ENABLED and not read_cov.reported then
                    read_cov.reported = true
                    local read_pct = buffer_size > 0 and (read_cov.unique_offsets / buffer_size * 100) or 0
                    local write_pct = buffer_size > 0 and (cumulative_count / buffer_size * 100) or 0
                    -- Build tile list
                    local tiles_list = {}
                    for tile_idx, byte_count in pairs(read_cov.tiles_read) do
                        tiles_list[#tiles_list + 1] = string.format("T%d:%d", tile_idx, byte_count)
                    end
                    table.sort(tiles_list)
                    local tiles_str = #tiles_list > 0 and table.concat(tiles_list, ",") or "none"
                    log(string.format(
                        "READ_COVERAGE: bytes_read=%d/%d (%.1f%%) bytes_written=%d (%.1f%%) tiles_read=[%s]",
                        read_cov.unique_offsets, buffer_size, read_pct,
                        cumulative_count, write_pct, tiles_str
                    ))
                    -- Key insight: if read > written, staging reads bytes we didn't see get filled
                    if read_cov.unique_offsets > cumulative_count then
                        log(string.format(
                            "READ_COVERAGE_INSIGHT: staging reads %d bytes we didn't observe being written - earlier fill phase exists",
                            read_cov.unique_offsets - cumulative_count
                        ))
                    elseif read_cov.unique_offsets < cumulative_count then
                        log(string.format(
                            "READ_COVERAGE_INSIGHT: staging only reads %d of %d bytes written - remaining bytes unused in this scenario",
                            read_cov.unique_offsets, cumulative_count
                        ))
                    else
                        log("READ_COVERAGE_INSIGHT: staging reads exactly the bytes that were written - clean 1:1 mapping")
                    end
                end
            end
        end
    end

    -- v2.2: Lazy registration (init-time timeout mitigation)
    -- Register expensive callbacks at STAGING_START_FRAME - 2 instead of init
    -- v2.11.1: Handle STAGING_START_FRAME=0 (cold-start trace) - register at frame 0
    -- v2.11.3: Fix off-by-one: frame_count is already incremented, so check +1
    local lazy_register_frame = math.max(0, STAGING_START_FRAME - 2)
    if frame_count == lazy_register_frame + 1 then
        if STAGING_WATCH_ENABLED and not staging_callbacks_registered then
            register_staging_callbacks()
            staging_callbacks_registered = true
        end
        if STAGING_WRAM_SOURCE_ENABLED and not wram_source_callbacks_registered then
            wram_source_callbacks_registered = register_wram_source_callbacks()
            if not wram_source_callbacks_registered then
                log("WARNING: WRAM source callbacks were not registered (will retry next frame)")
            end
        end
        -- v2.8: Buffer write watch for tracing source buffer writers
        if BUFFER_WRITE_WATCH_ENABLED and not buffer_write_callbacks_registered then
            buffer_write_callbacks_registered = register_buffer_write_callbacks()
            if not buffer_write_callbacks_registered then
                log("WARNING: Buffer write callbacks were not registered (will retry next frame)")
            end
        end
    end

    -- v2.8: Log buffer write summary for previous frame (if any activity)
    if BUFFER_WRITE_WATCH_ENABLED and buffer_write_current_frame and buffer_write_current_frame == frame_count - 1 then
        log_buffer_write_summary(buffer_write_current_frame)
    end

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

-- v2.0: Replace exec-based savestate loading with pcall at init + endFrame retry
-- This eliminates permanent per-instruction callback overhead
local savestate_load_attempted = false

-- Assign to forward-declared local (declared in Section 9 before on_end_frame)
try_load_savestate = function()
    if savestate_load_attempted or not SAVESTATE_PATH or state_loaded then
        return false
    end
    savestate_load_attempted = true

    if not emu.loadSavestate then
        log("ERROR: emu.loadSavestate not available")
        emu.stop(2)
        return false
    end

    local ok, err = pcall(emu.loadSavestate, SAVESTATE_PATH)
    if ok then
        state_loaded = true
        frame_count = 0
        log("Savestate loaded; reset frame counter")
        return true
    else
        log("ERROR: savestate load failed: " .. tostring(err))
        emu.stop(2)
        return false
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

-- v2.2: Staging and WRAM source callbacks registered lazily in on_end_frame
-- (init-time registration causes timeout even with sparse sentinels)
-- v2.11.1: Use math.max(0, ...) for cold-start traces (STAGING_START_FRAME=0)
local lazy_register_frame_init = math.max(0, STAGING_START_FRAME - 2)
if STAGING_WATCH_ENABLED then
    log("INFO: Staging watch will be registered lazily at frame=" .. tostring(lazy_register_frame_init))
end
-- v2.3: DMA logging deferred to prevent timeout (logs at init were eating the entire 1s budget)
if CFG.dma_log_start_frame > 0 then
    log("INFO: DMA/HDMA/SA1 logging deferred until frame=" .. tostring(CFG.dma_log_start_frame))
end
if STAGING_WRAM_SOURCE_ENABLED then
    log("INFO: WRAM source tracking will be registered lazily at frame=" .. tostring(lazy_register_frame_init))
end
if BUFFER_WRITE_WATCH_ENABLED then
    log(string.format("INFO: Buffer write watch (0x%06X-0x%06X) will be registered lazily at frame=%d",
        BUFFER_WRITE_START, BUFFER_WRITE_END, lazy_register_frame_init))
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

    -- v2.0: Try savestate load once at init via pcall; if it fails, on_end_frame will retry
    -- Always register frame event (no longer conditional on savestate success)
    if SAVESTATE_PATH and not PRELOADED_STATE then
        try_load_savestate()
    end
    register_frame_event()
end)
if not init_ok then
    log("ERROR: Final initialization failed: " .. tostring(init_err))
end
