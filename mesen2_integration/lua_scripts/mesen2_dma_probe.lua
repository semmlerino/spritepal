-- DMA/SA-1 probe for sprite upload diagnostics (headless-safe)
-- =============================================================================
-- INSTRUMENTATION CONTRACT v1.1
-- =============================================================================
local LOG_VERSION = "1.1"
local RUN_ID = string.format("%d_%04x", os.time(), math.random(0, 0xFFFF))
local log_header_written = false

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
local SKIP_INPUT = os.getenv("SKIP_INPUT") == "1"
local DOOR_UP_START = tonumber(os.getenv("DOOR_UP_START"))
local DOOR_UP_END = tonumber(os.getenv("DOOR_UP_END"))

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

local function log(msg)
    local f = io.open(LOG_FILE, "a")
    if f then
        -- Write header on first log call
        if not log_header_written then
            local rom = get_rom_info()
            local header = string.format(
                "# LOG_VERSION=%s RUN_ID=%s ROM=%s SHA256=%s PRG_SIZE=%s\n",
                LOG_VERSION,
                RUN_ID,
                rom.name or "unknown",
                rom.sha256 or "N/A",
                rom.prg_size and string.format("0x%X", rom.prg_size) or "N/A"
            )
            f:write(header)
            log_header_written = true
        end
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

local MEM = {
    cpu = emu.memType.snesMemory or emu.memType.cpuMemory or emu.memType.cpu or emu.memType.CpuMemory,
    cpu_debug = emu.memType.snesMemoryDebug or emu.memType.cpuMemoryDebug or emu.memType.cpuDebug,
    prg = emu.memType.snesPrgRom,
    vram = emu.memType.snesVram or emu.memType.snesVideoRam or emu.memType.videoRam,
    wram = emu.memType.snesWorkRam or emu.memType.snesWram or emu.memType.workRam or emu.memType.wram,
    oam = emu.memType.snesOam or emu.memType.snesSpriteRam,
    cgram = emu.memType.snesCgram or emu.memType.snesCgRam,
}
if not MEM.cpu then
    log("ERROR: could not resolve CPU memory type; aborting")
    emu.stop(2)
    return
end
if not MEM.vram then
    log("WARNING: could not resolve VRAM memory type; VRAM memType writes will not be logged")
end

local cpu_type = emu.cpuType and (emu.cpuType.snes or emu.cpuType.cpu) or nil

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

local vram_word_addr = 0
local vram_inc_mode = 0
local vram_inc_value = 1
local vram_trans = 0
local vram_write_count = 0
local vram_write_2118 = 0
local vram_write_2119 = 0
local vram_mem_write_count = 0
local vram_mem_write_logged = 0
local last_master_clock = nil
local last_state_frame = nil
local last_sa1_dma_irq = nil

-- Consolidated configuration table to stay under Lua's 200 local variable limit
local CFG = {
    -- VRAM settings
    log_vram_memory_writes = os.getenv("LOG_VRAM_MEMORY_WRITES") == "1",
    max_vram_write_log = tonumber(os.getenv("MAX_VRAM_WRITE_LOG")) or 20,
    vram_diff_enabled = os.getenv("VRAM_DIFF") ~= "0",
    vram_size = 0x10000,
    vram_coarse_step = tonumber(os.getenv("VRAM_COARSE_STEP")) or 16,
    vram_page_size = tonumber(os.getenv("VRAM_PAGE_SIZE")) or 0x0400,
    vram_page_log_limit = tonumber(os.getenv("VRAM_PAGE_LOG_LIMIT")) or 12,
    -- General
    heartbeat_every = tonumber(os.getenv("HEARTBEAT_EVERY")) or 0,
    skip_visibility_filter = os.getenv("SKIP_VISIBILITY_FILTER") == "1",
    -- WRAM dump settings
    wram_dump_on_vram_diff = os.getenv("WRAM_DUMP_ON_VRAM_DIFF") ~= "0",
    wram_dump_start = os.getenv("WRAM_DUMP_START") or "0x0000",
    wram_dump_abs_start = os.getenv("WRAM_DUMP_ABS_START"),
    wram_dump_size = tonumber(os.getenv("WRAM_DUMP_SIZE")) or 0x20000,
    wram_dump_prev = os.getenv("WRAM_DUMP_PREV") ~= "0",
    -- WRAM watch settings
    wram_watch_writes = os.getenv("WRAM_WATCH_WRITES") ~= "0",
    wram_watch_sample_limit = tonumber(os.getenv("WRAM_WATCH_SAMPLE_LIMIT")) or 8,
    wram_watch_start = os.getenv("WRAM_WATCH_START"),
    wram_watch_end = os.getenv("WRAM_WATCH_END"),
    wram_watch_capture_threshold = tonumber(os.getenv("WRAM_WATCH_CAPTURE_THRESHOLD")) or 0,
    wram_watch_pc_samples = tonumber(os.getenv("WRAM_WATCH_PC_SAMPLES")) or 0,
    -- ROM trace settings
    rom_trace_on_wram_write = os.getenv("ROM_TRACE_ON_WRAM_WRITE") == "1",
    rom_trace_max_reads = tonumber(os.getenv("ROM_TRACE_MAX_READS")) or 200,
    rom_trace_max_frames = tonumber(os.getenv("ROM_TRACE_MAX_FRAMES")) or 1,
    rom_trace_pc_samples = tonumber(os.getenv("ROM_TRACE_PC_SAMPLES")) or 8,
    -- Visibility
    visible_y_exclude_start = parse_int(os.getenv("VISIBLE_Y_EXCLUDE_START"), 224),
    visible_y_exclude_end = parse_int(os.getenv("VISIBLE_Y_EXCLUDE_END"), 240),
    visible_x_min = parse_int(os.getenv("VISIBLE_X_MIN"), -64),
    visible_x_max = parse_int(os.getenv("VISIBLE_X_MAX"), 256),
    dma_dump_on_vram = os.getenv("DMA_DUMP_ON_VRAM") ~= "0",
    dma_dump_max = tonumber(os.getenv("DMA_DUMP_MAX")) or 20,
    dma_dump_min_size = tonumber(os.getenv("DMA_DUMP_MIN_SIZE")) or 1,
    dma_compare_enabled = os.getenv("DMA_COMPARE_ENABLED") ~= "0",
    dma_compare_max = tonumber(os.getenv("DMA_COMPARE_MAX")) or 50,
    dma_compare_sample_bytes = tonumber(os.getenv("DMA_COMPARE_SAMPLE_BYTES")) or 32,
    capture_on_vram_diff = os.getenv("CAPTURE_ON_VRAM_DIFF") ~= "0",
    capture_on_vram_dma = os.getenv("CAPTURE_ON_VRAM_DMA") ~= "0",
    capture_on_wram_write = os.getenv("CAPTURE_ON_WRAM_WRITE") ~= "0",
    capture_screenshot = os.getenv("CAPTURE_SCREENSHOT") ~= "0",
    capture_dump_vram = os.getenv("CAPTURE_DUMP_VRAM") ~= "0",
    capture_dump_wram = os.getenv("CAPTURE_DUMP_WRAM") ~= "0",
    capture_max = tonumber(os.getenv("CAPTURE_MAX")) or 20,
    capture_tag_prefix = os.getenv("CAPTURE_TAG_PREFIX") or "probe",
    capture_start_frame = tonumber(os.getenv("CAPTURE_START_FRAME")) or 0,
    capture_start_seconds = tonumber(os.getenv("CAPTURE_START_SECONDS")) or 0,
    capture_min_interval = tonumber(os.getenv("CAPTURE_MIN_INTERVAL")) or 0,
    capture_min_interval_seconds = tonumber(os.getenv("CAPTURE_MIN_INTERVAL_SECONDS")) or 0,
    vram_diff_start_frame = tonumber(os.getenv("VRAM_DIFF_START_FRAME")) or 0,
    vram_diff_start_seconds = tonumber(os.getenv("VRAM_DIFF_START_SECONDS")) or 0,
    periodic_capture_enabled = os.getenv("PERIODIC_CAPTURE_ENABLED") == "1",
    periodic_capture_start = tonumber(os.getenv("PERIODIC_CAPTURE_START")) or 2000,
    periodic_capture_interval = tonumber(os.getenv("PERIODIC_CAPTURE_INTERVAL")) or 1800,
}
-- Dependent config values
CFG.wram_dump_start_frame = tonumber(os.getenv("WRAM_DUMP_START_FRAME")) or CFG.capture_start_frame
CFG.wram_dump_start_seconds = tonumber(os.getenv("WRAM_DUMP_START_SECONDS")) or CFG.capture_start_seconds
CFG.dma_dump_start_frame = tonumber(os.getenv("DMA_DUMP_START_FRAME")) or CFG.capture_start_frame
CFG.dma_dump_start_seconds = tonumber(os.getenv("DMA_DUMP_START_SECONDS")) or CFG.capture_start_seconds

-- Runtime state table
local STATE = {
    next_periodic_capture_frame = CFG.periodic_capture_start,
    periodic_capture_count = 0,
    last_coarse_hash = nil,
    last_page_hash = {},
    last_page_initialized = false,
    vram_read_error_logged = false,
    vram_diff_initialized = false,
    vram_diff_armed = false,
    script_start_time = os.time(),
    last_capture_frame = nil,
    last_capture_time = nil,
}
local ROM_TRACE_LOG_FILE = OUTPUT_DIR .. "rom_trace_log.txt"

if not MEM.vram then
    CFG.vram_diff_enabled = false
end

local wram_dump_start = parse_int(CFG.wram_dump_start, 0x0000)
local wram_dump_abs_start = parse_int(CFG.wram_dump_abs_start, nil)
local wram_mem_type = MEM.wram
local wram_base = wram_dump_start
local wram_address_mode = "relative"
if wram_dump_abs_start ~= nil then
    wram_mem_type = MEM.cpu
    wram_base = wram_dump_abs_start
    wram_address_mode = "absolute"
elseif not wram_mem_type then
    wram_mem_type = MEM.cpu
    wram_base = 0x7E0000 + wram_dump_start
    wram_address_mode = "absolute"
end
local wram_watch_start = parse_int(CFG.wram_watch_start, wram_base)
local wram_watch_end = parse_int(CFG.wram_watch_end, wram_watch_start + CFG.wram_dump_size - 1)
local _last_wram_dump_frame = nil  -- luacheck: ignore (reserved for future use)
local prev_wram_snapshot = nil
local prev_wram_frame = nil
local wram_write_counts = {snes = 0, sa1 = 0}
local wram_write_samples = {snes = {}, sa1 = {}}
local wram_write_cpu_samples = {snes = 0, sa1 = 0}
local dma_read_mem = MEM.cpu_debug or MEM.cpu
local dma_dump_count = 0
local dma_compare_count = 0

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

-- ============================================================================
-- STAGING BUFFER WRITE TRACKING (Rolling Log)
-- Tracks writes to DMA source range ($7E:2000) to diagnose fill patterns
-- ============================================================================
local STAGING_WATCH_ENABLED = os.getenv("STAGING_WATCH_ENABLED") == "1"
local STAGING_WATCH_START = tonumber(os.getenv("STAGING_WATCH_START") or "0x2000", 16) or 0x2000
local STAGING_WATCH_END = tonumber(os.getenv("STAGING_WATCH_END") or "0x33FF", 16) or 0x33FF
local STAGING_WATCH_PC_SAMPLES = tonumber(os.getenv("STAGING_WATCH_PC_SAMPLES")) or 4
local STAGING_HISTORY_FRAMES = tonumber(os.getenv("STAGING_HISTORY_FRAMES")) or 3
local STAGING_START_FRAME = tonumber(os.getenv("STAGING_START_FRAME")) or 0
local STAGING_ROM_READS_ENABLED = os.getenv("STAGING_ROM_READS_ENABLED") == "1"

-- Per-frame staging write stats
local staging_frame_stats = {}  -- [frame] = {stats}
local staging_current_frame = nil
local staging_current_stats = nil

-- ROM read tracking during staging fills
local staging_active = false
local staging_rom_reads = {}  -- [bank:addr] = count
local staging_rom_read_count = 0
local staging_first_pc = nil  -- PC that started the fill
local staging_rom_read_cpu_counts = {}  -- [cpu_label] = count (e.g., "snes", "sa1")

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

-- Reset ROM read tracking for new staging fill
local function reset_staging_rom_reads()
    staging_rom_reads = {}
    staging_rom_read_count = 0
    staging_first_pc = nil
    staging_active = false
    last_staging_write_frame = nil
    staging_rom_read_cpu_counts = {}
end

-- Track frame of last staging write (for frame-gating PRG reads)
local last_staging_write_frame = nil

-- Record a PRG ROM read during staging (address is PRG file offset)
local function record_staging_rom_read(prg_offset, cpu_label)
    if not staging_active then return end
    staging_rom_reads[prg_offset] = (staging_rom_reads[prg_offset] or 0) + 1
    staging_rom_read_count = staging_rom_read_count + 1
    if cpu_label then
        staging_rom_read_cpu_counts[cpu_label] = (staging_rom_read_cpu_counts[cpu_label] or 0) + 1
    end
end

-- Summarize ROM reads as contiguous runs
local function get_staging_rom_runs()
    -- Collect and sort all addresses
    local addrs = {}
    for key, _ in pairs(staging_rom_reads) do
        addrs[#addrs + 1] = key
    end
    if #addrs == 0 then
        return {}
    end
    table.sort(addrs)

    -- Build runs of contiguous addresses
    local runs = {}
    local run_start = addrs[1]
    local run_end = addrs[1]

    for i = 2, #addrs do
        local addr = addrs[i]
        if addr == run_end + 1 then
            -- Extend current run
            run_end = addr
        else
            -- End current run, start new one
            runs[#runs + 1] = {start = run_start, stop = run_end}
            run_start = addr
            run_end = addr
        end
    end
    -- Don't forget last run
    runs[#runs + 1] = {start = run_start, stop = run_end}

    return runs
end

-- Format PRG offset as hex (NOT a SNES bus address)
-- These are file offsets into the PRG ROM, not bank:addr
local function format_prg_offset(prg_offset)
    return string.format("0x%06X", prg_offset)
end

-- Count keys in a map (Lua # operator doesn't work on maps)
local function count_map_keys(t)
    local n = 0
    for _ in pairs(t) do n = n + 1 end
    return n
end

-- Log ROM reads summary when DMA fires
local function log_staging_rom_reads(frame, vram_addr, dma_size)
    if not STAGING_ROM_READS_ENABLED or not staging_active then return end
    if staging_rom_read_count == 0 then return end

    local runs = get_staging_rom_runs()
    local runs_str_parts = {}
    for _, run in ipairs(runs) do
        if run.start == run.stop then
            runs_str_parts[#runs_str_parts + 1] = format_prg_offset(run.start)
        else
            runs_str_parts[#runs_str_parts + 1] = format_prg_offset(run.start) .. "-" .. format_prg_offset(run.stop)
        end
    end
    local runs_str = table.concat(runs_str_parts, ",")
    if #runs_str > 200 then
        runs_str = string.sub(runs_str, 1, 200) .. "..."
    end

    local pc_str = "unknown"
    if staging_first_pc then
        pc_str = string.format("%02X:%04X", staging_first_pc.k or 0, staging_first_pc.pc or 0)
    end

    local unique_count = count_map_keys(staging_rom_reads)

    -- Format CPU counts
    local cpu_parts = {}
    for cpu, cnt in pairs(staging_rom_read_cpu_counts) do
        cpu_parts[#cpu_parts + 1] = cpu .. "=" .. cnt
    end
    local cpu_str = #cpu_parts > 0 and table.concat(cpu_parts, ",") or "none"

    log(string.format(
        "STAGING_ROM_READS: frame=%d pc=%s vram_word=0x%04X size=%d prg_runs=[%s] unique=%d total=%d cpus={%s}",
        frame, pc_str, vram_addr, dma_size, runs_str, unique_count, staging_rom_read_count, cpu_str
    ))
end

-- PRG/ROM read callback factory during staging
-- Note: address is PRG file offset (0 to prg_size-1), NOT a SNES bus address
-- Frame-gated: only record if we're in the same frame as the staging write
local function make_staging_rom_reader(cpu_label)
    return function(address, value)
        if not staging_active then return end
        -- Frame-gate: ignore PRG reads from different frames (reduces noise)
        if last_staging_write_frame and get_canonical_frame() ~= last_staging_write_frame then
            return
        end
        record_staging_rom_read(address, cpu_label)
    end
end

local function record_staging_write(addr, pc_snapshot)
    local frame = get_canonical_frame()

    -- Activate ROM read tracking on first write (if enabled)
    if STAGING_ROM_READS_ENABLED and not staging_active then
        staging_active = true
        staging_first_pc = pc_snapshot
    end

    -- Track frame of last staging write (for frame-gating PRG reads)
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
        "STAGING_SUMMARY: frame=%d src=0x%06X size=%d vram=0x%04X pattern=%s writes=%d unique=%d seq=%d jumps=%d range=0x%04X-0x%04X frames=%d%s",
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
    local pc_snapshot = get_cpu_state_snapshot()
    record_staging_write(address, pc_snapshot)
end
-- ============================================================================

-- OAM DMA capture: store OAM from DMA source buffer instead of MEM.oam timing
local oam_dma_buffer = nil      -- Raw 544-byte OAM from last DMA
local oam_dma_frame = nil       -- Frame when OAM was captured
local OAM_DMA_SIZE = 544        -- 512 bytes low table + 32 bytes high table
local OAM_DMA_MIN_SIZE = 512    -- Minimum: just the low table (some games skip high table)

local pending_dma_capture = false
local pending_dma_count = 0
local capture_count = 0
-- frame_count and get_canonical_frame() moved to line ~286

local rom_trace_active = false
local rom_trace_remaining = 0
local rom_trace_end_frame = nil
local rom_trace_arm_frame = nil
local rom_trace_label = nil
local rom_trace_pc_samples = 0
local rom_trace_prg_size = nil
local rom_trace_prg_end = nil

local function bxor(a, b)
    if bit32 and bit32.bxor then
        return bit32.bxor(a, b)
    end
    if bit and bit.bxor then
        return bit.bxor(a, b)
    end
    local res = 0
    local bitval = 1
    local aa = a
    local bb = b
    for _ = 0, 31 do
        local abit = aa % 2
        local bbit = bb % 2
        if abit ~= bbit then
            res = res + bitval
        end
        aa = (aa - abit) / 2
        bb = (bb - bbit) / 2
        bitval = bitval * 2
    end
    return res
end

local function vram_diff_allowed(frame_id)
    if CFG.vram_diff_start_frame > 0 and frame_id < CFG.vram_diff_start_frame then
        return false
    end
    if CFG.vram_diff_start_seconds > 0 and (os.time() - STATE.script_start_time) < CFG.vram_diff_start_seconds then
        return false
    end
    return true
end

local function capture_allowed(frame_id)
    if CFG.capture_start_frame > 0 and frame_id < CFG.capture_start_frame then
        return false
    end
    if CFG.capture_start_seconds > 0 and (os.time() - STATE.script_start_time) < CFG.capture_start_seconds then
        return false
    end
    if CFG.capture_min_interval > 0 and STATE.last_capture_frame and (frame_id - STATE.last_capture_frame) < CFG.capture_min_interval then
        return false
    end
    if CFG.capture_min_interval_seconds > 0 and STATE.last_capture_time and
        (os.time() - STATE.last_capture_time) < CFG.capture_min_interval_seconds then
        return false
    end
    return true
end

local function log_rom(msg)
    local f = io.open(ROM_TRACE_LOG_FILE, "a")
    if f then
        f:write(os.date("%H:%M:%S") .. " " .. msg .. "\n")
        f:close()
    end
end
-- get_cpu_state_snapshot() moved to line ~295

local function arm_rom_trace(label)
    if not CFG.rom_trace_on_wram_write or rom_trace_active then
        return
    end
    local threshold = CFG.wram_watch_capture_threshold
    if threshold < 1 then
        threshold = 1
    end
    if (wram_write_counts[label] or 0) < threshold then
        return
    end
    local frame_id = last_state_frame or frame_count
    local max_frames = CFG.rom_trace_max_frames
    if max_frames < 1 then
        max_frames = 1
    end
    rom_trace_active = true
    rom_trace_remaining = CFG.rom_trace_max_reads
    rom_trace_end_frame = frame_id + max_frames - 1
    rom_trace_arm_frame = frame_id
    rom_trace_label = label
    rom_trace_pc_samples = 0
    local prg_size_text = rom_trace_prg_size and string.format("0x%X", rom_trace_prg_size) or "nil"
    local prg_end_text = rom_trace_prg_end and string.format("0x%06X", rom_trace_prg_end) or "nil"
    log_rom(string.format(
        "ROM trace armed: frame=%s label=%s prg_size=%s prg_end=%s max_reads=%d max_frames=%d",
        tostring(frame_id),
        tostring(label),
        prg_size_text,
        prg_end_text,
        CFG.rom_trace_max_reads,
        max_frames
    ))
    log(string.format(
        "ROM trace armed: frame=%s label=%s prg_size=%s prg_end=%s",
        tostring(frame_id),
        tostring(label),
        prg_size_text,
        prg_end_text
    ))
end

local function rom_trace_allowed(frame_id)
    if not rom_trace_active then
        return false
    end
    if rom_trace_remaining <= 0 then
        return false
    end
    if rom_trace_end_frame ~= nil and frame_id > rom_trace_end_frame then
        rom_trace_active = false
        log_rom(string.format(
            "ROM trace expired: frame=%s start=%s label=%s remaining=%d",
            tostring(frame_id),
            tostring(rom_trace_arm_frame),
            tostring(rom_trace_label),
            rom_trace_remaining
        ))
        return false
    end
    return true
end

local function wram_dump_allowed(frame_id)
    if CFG.wram_dump_start_frame > 0 and frame_id < CFG.wram_dump_start_frame then
        return false
    end
    if CFG.wram_dump_start_seconds > 0 and (os.time() - STATE.script_start_time) < CFG.wram_dump_start_seconds then
        return false
    end
    return true
end

local function dma_dump_allowed(frame_id)
    if CFG.dma_dump_start_frame > 0 and frame_id < CFG.dma_dump_start_frame then
        return false
    end
    if CFG.dma_dump_start_seconds > 0 and (os.time() - STATE.script_start_time) < CFG.dma_dump_start_seconds then
        return false
    end
    return true
end

local function read_vram_byte(addr)
    local value = emu.read(addr, MEM.vram)
    if value == nil then
        if not STATE.vram_read_error_logged then
            log("ERROR: VRAM read returned nil; disabling VRAM diff")
            STATE.vram_read_error_logged = true
        end
        CFG.vram_diff_enabled = false
        return 0
    end
    return value
end

local function hash_stride(start_addr, size, step)
    local h = 2166136261
    local prime = 16777619
    for i = 0, size - 1, step do
        local b = read_vram_byte(start_addr + i)
        if not CFG.vram_diff_enabled then
            return h
        end
        h = (bxor(h, b) * prime) % 4294967296
    end
    return h
end

local function hash_block(start_addr, size)
    local h = 2166136261
    local prime = 16777619
    for i = 0, size - 1 do
        local b = read_vram_byte(start_addr + i)
        if not CFG.vram_diff_enabled then
            return h
        end
        h = (bxor(h, b) * prime) % 4294967296
    end
    return h
end

local function record_wram_write(label, address)
    wram_write_counts[label] = wram_write_counts[label] + 1
    local samples = wram_write_samples[label]
    if #samples < CFG.wram_watch_sample_limit then
        samples[#samples + 1] = string.format("0x%06X", address)
    end
    if CFG.wram_watch_pc_samples > 0 and wram_write_cpu_samples[label] < CFG.wram_watch_pc_samples then
        wram_write_cpu_samples[label] = wram_write_cpu_samples[label] + 1
        local snapshot = get_cpu_state_snapshot()
        if snapshot then
            log(string.format(
                "WRAM write CPU (%s): addr=0x%06X %s=0x%04X %s=0x%02X %s=0x%02X",
                label,
                address,
                snapshot.pc_key or "PC",
                snapshot.pc_val or 0,
                snapshot.k_key or "K",
                snapshot.k_val or 0,
                snapshot.dbr_key or "DBR",
                snapshot.dbr_val or 0
            ))
        end
    end
    if CFG.rom_trace_on_wram_write then
        arm_rom_trace(label)
    end
end

local function capture_wram_snapshot()
    if not wram_mem_type then
        return nil
    end
    local chunks = {}
    local chunk = {}
    local chunk_len = 0
    local chunk_size = 4096
    for i = 0, CFG.wram_dump_size - 1 do
        local value = emu.read(wram_base + i, wram_mem_type)
        if value == nil then
            value = 0
        end
        chunk_len = chunk_len + 1
        chunk[chunk_len] = string.char(value & 0xFF)
        if chunk_len >= chunk_size then
            chunks[#chunks + 1] = table.concat(chunk)
            chunk = {}
            chunk_len = 0
        end
    end
    if chunk_len > 0 then
        chunks[#chunks + 1] = table.concat(chunk)
    end
    return table.concat(chunks)
end

local function write_wram_snapshot(frame_id, label, snapshot, source_frame, force)
    if not CFG.wram_dump_on_vram_diff and not force then
        return
    end
    if not snapshot then
        return
    end
    local tag = label or "curr"
    if source_frame ~= nil then
        tag = tag .. "_f" .. tostring(source_frame)
    end
    local path = OUTPUT_DIR
        .. string.format("wram_dump_%s_%s_start_%06X_size_%05X.bin", tostring(frame_id), tag, wram_base, CFG.wram_dump_size)
    local f = io.open(path, "wb")
    if not f then
        log("ERROR: failed to open WRAM dump: " .. path)
        return
    end
    f:write(snapshot)
    f:close()

    log(string.format(
        "WRAM dump: frame=%s label=%s mode=%s base=0x%06X size=0x%05X path=%s",
        tostring(frame_id),
        tag,
        wram_address_mode,
        wram_base,
        CFG.wram_dump_size,
        path
    ))
end

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

local vram_read_mode = os.getenv("VRAM_READ_MODE")
if vram_read_mode ~= "word" and vram_read_mode ~= "byte" then
    vram_read_mode = "word"  -- Default to word mode; byte mode broken in some Mesen2 builds
end

local function get_obsel()
    local obsel = emu.read(0x2101, MEM.cpu)
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

-- One-shot diagnostic: tracks which OAM source was used for this capture
local oam_source_logged = false

-- Read OAM byte: prefer DMA-captured buffer ONLY if it matches this frame
local function read_oam_byte(offset, frame_id)
    if oam_dma_buffer
        and oam_dma_frame == frame_id
        and offset < OAM_DMA_SIZE
    then
        if not oam_source_logged then
            oam_source_logged = true
            log(string.format("OAM_SOURCE: frame=%d USING_DMA_BUFFER (oam_dma_frame=%d)",
                frame_id, oam_dma_frame))
        end
        return oam_dma_buffer[offset + 1] or 0  -- Lua 1-indexed
    end

    -- Fallback to direct OAM read
    if not oam_source_logged then
        oam_source_logged = true
        local reason = "unknown"
        if not oam_dma_buffer then
            reason = "no_buffer"
        elseif oam_dma_frame ~= frame_id then
            reason = string.format("frame_mismatch(dma=%s,capture=%d)",
                tostring(oam_dma_frame), frame_id)
        elseif offset >= OAM_DMA_SIZE then
            reason = "offset_oob"
        end
        log(string.format("OAM_SOURCE: frame=%d FALLBACK_DIRECT reason=%s MEM.oam=%s",
            frame_id, reason, tostring(MEM.oam ~= nil)))
    end

    if MEM.oam then
        local ok, v = pcall(emu.read, offset, MEM.oam)
        if ok and v then return v end
    end
    return 0
end

local function parse_oam_entry(index, frame_id)
    local base = index * 4
    local x_low = read_oam_byte(base + 0, frame_id)
    local y = read_oam_byte(base + 1, frame_id)
    local tile = read_oam_byte(base + 2, frame_id)
    local attr = read_oam_byte(base + 3, frame_id)

    local hi_byte = read_oam_byte(0x200 + math.floor(index / 4), frame_id)
    local hi_bit_pos = (index % 4) * 2
    local x_bit9 = (hi_byte >> hi_bit_pos) & 1
    local size_bit = (hi_byte >> (hi_bit_pos + 1)) & 1

    local x = x_low + (x_bit9 * 256)
    if x >= 256 then
        x = x - 512
    end

    return {
        id = index,
        x = x,
        y = y,
        tile = tile,
        name_table = (attr & 0x01),
        palette = (attr >> 1) & 0x07,
        priority = (attr >> 4) & 0x03,
        flip_h = ((attr >> 6) & 0x01) == 1,
        flip_v = ((attr >> 7) & 0x01) == 1,
        size_large = size_bit == 1,
    }
end

local function get_sprite_size(obsel, is_large)
    local sizes = SIZE_TABLE[obsel.size_select] or {8, 8, 16, 16}
    return is_large and sizes[3] or sizes[1], is_large and sizes[4] or sizes[2]
end

local function is_visible(entry)
    if CFG.skip_visibility_filter then
        return true
    end
    if entry.y >= CFG.visible_y_exclude_start and entry.y < CFG.visible_y_exclude_end then
        return false
    end
    if entry.x <= CFG.visible_x_min or entry.x >= CFG.visible_x_max then
        return false
    end
    return true
end

local function read_vram_word(byte_addr)
    -- Try emu.readWord first (returns 16-bit word in big-endian format)
    if emu.readWord then
        local ok, word = pcall(emu.readWord, byte_addr, MEM.vram)
        if ok and word then
            return word
        end
    end
    -- Fallback: read two consecutive bytes and combine as big-endian (like emu.readWord)
    -- First byte goes in high bits so read_vram_tile_word's swap logic works correctly
    local first_byte = emu.read(byte_addr, MEM.vram) or 0
    local second_byte = emu.read(byte_addr + 1, MEM.vram) or 0
    return (first_byte << 8) | second_byte
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

local function capture_sprites(frame_id)
    -- Reset one-shot OAM source diagnostic for this capture
    oam_source_logged = false

    -- Only VRAM and CGRAM are required; OAM can come from DMA buffer
    if not MEM.cgram or not MEM.vram then
        log("ERROR: CGRAM/VRAM memTypes missing; cannot capture sprites")
        return nil, {}, 0, {}, 0, 0
    end

    local obsel = get_obsel()
    local entries = {}
    local visible_count = 0
    local tile_count = 0
    local odd_nonzero_tiles = 0

    for i = 0, 127 do
        local entry = parse_oam_entry(i, frame_id)
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
                    for _, b in ipairs(tile_bytes) do
                        hex = hex .. string.format("%02X", b)
                    end
                    table.insert(entry.tile_data, {
                        tile_index = tile_index,
                        vram_addr = vram_addr,
                        pos_x = tx,
                        pos_y = ty,
                        data_hex = hex,
                    })
                end
            end
            table.insert(entries, entry)
        end
    end

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

local function write_capture_snapshot(tag, frame_id)
    if capture_count >= CFG.capture_max then
        return
    end
    if not capture_allowed(frame_id) then
        return
    end
    capture_count = capture_count + 1

    local obsel, entries, visible_count, palettes, tile_count, odd_nonzero_tiles = capture_sprites(frame_id)
    if not obsel then
        return
    end
    -- Note: odd_nonzero_tiles==0 can happen with valid tiles (e.g., 2-plane data)
    -- Log a warning but don't abort - let the capture proceed for analysis
    if tile_count > 0 and odd_nonzero_tiles == 0 then
        log("WARNING: All VRAM tiles have zero odd-byte data (may be 2-plane or empty tiles)")
    end

    local suffix = "_" .. CFG.capture_tag_prefix .. "_" .. tag .. "_" .. tostring(frame_id)
    log("Capturing sprite snapshot " .. suffix)

    if CFG.capture_screenshot and emu.takeScreenshot then
        local png_data = emu.takeScreenshot()
        if png_data then
            local sf = io.open(OUTPUT_DIR .. "test_frame" .. suffix .. ".png", "wb")
            if sf then
                sf:write(png_data)
                sf:close()
            end
        end
    end

    if CFG.capture_dump_vram then
        dump_vram(OUTPUT_DIR .. "test_vram_dump" .. suffix .. ".bin")
    end
    if CFG.capture_dump_wram and wram_mem_type then
        local snapshot = capture_wram_snapshot()
        if snapshot then
            write_wram_snapshot(frame_id, "capture", snapshot, frame_id, true)
        end
    end

    local f = io.open(OUTPUT_DIR .. "test_capture" .. suffix .. ".json", "w")
    if not f then
        log("Failed to open capture json output")
        return
    end
    f:write("{\n")
    f:write('  "schema_version": "1.0",\n')
    f:write(string.format('  "frame": %d,\n', frame_id))
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
            if tidx < #entry.tile_data then
                f:write(',')
            end
            f:write('\n')
        end
        f:write('      ]\n')
        f:write('    }')
        if idx < #entries then
            f:write(',')
        end
        f:write('\n')
    end
    f:write('  ],\n')

    f:write('  "palettes": {\n')
    for pi = 0, 7 do
        f:write(string.format('    "%d": [', pi))
        for ci, c in ipairs(palettes[pi]) do
            f:write(tostring(c))
            if ci < 16 then
                f:write(',')
            end
        end
        f:write(']')
        if pi < 7 then
            f:write(',')
        end
        f:write('\n')
    end
    f:write('  }\n')
    f:write('}\n')
    f:close()

    local s = io.open(OUTPUT_DIR .. "capture_summary" .. suffix .. ".txt", "w")
    if not s then
        log("Failed to open capture summary output")
        return
    end
    s:write("Sprite Capture Summary\n")
    s:write("======================\n")
    s:write(string.format("Frame: %d\n", frame_id))
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

    STATE.last_capture_frame = frame_id
    STATE.last_capture_time = os.time()
end

local function init_page_hashes()
    if not CFG.vram_diff_enabled then
        return
    end
    for base = 0, CFG.vram_size - 1, CFG.vram_page_size do
        STATE.last_page_hash[base] = hash_block(base, CFG.vram_page_size)
    end
    STATE.last_page_initialized = true
end

local function refine_changed_pages(frame_id)
    local changed = 0
    local logged = 0
    for base = 0, CFG.vram_size - 1, CFG.vram_page_size do
        local h = hash_block(base, CFG.vram_page_size)
        local prev = STATE.last_page_hash[base]
        if prev == nil then
            STATE.last_page_hash[base] = h
        elseif h ~= prev then
            changed = changed + 1
            if logged < CFG.vram_page_log_limit then
                log(string.format(
                    "VRAM diff: frame=%s clock=%s page=0x%04X %08X->%08X",
                    tostring(frame_id),
                    tostring(last_master_clock),
                    base,
                    prev,
                    h
                ))
                logged = logged + 1
            end
            STATE.last_page_hash[base] = h
        end
    end
    if changed > 0 then
        log(string.format(
            "VRAM diff summary: frame=%s changed_pages=%d",
            tostring(frame_id),
            changed
        ))
    end
end

local function poll_vram_diff(frame_id, current_snapshot)
    if not CFG.vram_diff_enabled then
        return
    end
    local coarse = hash_stride(0, CFG.vram_size, CFG.vram_coarse_step)
    if not vram_diff_allowed(frame_id) then
        STATE.last_coarse_hash = coarse
        return
    end
    if STATE.last_coarse_hash == nil then
        STATE.last_coarse_hash = coarse
        if not STATE.last_page_initialized then
            init_page_hashes()
        end
        if not STATE.vram_diff_initialized then
            STATE.vram_diff_initialized = true
            log(string.format(
                "VRAM diff baseline: frame=%s clock=%s hash=%08X",
                tostring(frame_id),
                tostring(last_master_clock),
                coarse
            ))
        end
        return
    end
    if not STATE.vram_diff_armed then
        if not STATE.last_page_initialized then
            init_page_hashes()
        end
        STATE.last_coarse_hash = coarse
        STATE.vram_diff_armed = true
        return
    end
    if coarse == STATE.last_coarse_hash then
        return
    end
    log(string.format(
        "VRAM diff coarse change: frame=%s clock=%s %08X->%08X",
        tostring(frame_id),
        tostring(last_master_clock),
        STATE.last_coarse_hash,
        coarse
    ))
    STATE.last_coarse_hash = coarse
    refine_changed_pages(frame_id)
    if CFG.wram_dump_on_vram_diff and wram_dump_allowed(frame_id) then
        if CFG.wram_dump_prev and prev_wram_snapshot ~= nil then
            write_wram_snapshot(frame_id, "prev", prev_wram_snapshot, prev_wram_frame)
        end
        if current_snapshot ~= nil then
            write_wram_snapshot(frame_id, "curr", current_snapshot, frame_id)
        else
            local snapshot = capture_wram_snapshot()
            write_wram_snapshot(frame_id, "curr", snapshot, frame_id)
        end
        _last_wram_dump_frame = frame_id
    end
    if CFG.capture_on_vram_diff and capture_allowed(frame_id) then
        write_capture_snapshot("vramdiff", frame_id)
    end
end

local function read8(addr)
    return emu.read(addr, MEM.cpu)
end

local function refresh_vram_addr()
    local lo = read8(0x2116)
    local hi = read8(0x2117)
    vram_word_addr = lo | (hi << 8)
end

local function refresh_vram_inc()
    local vmain = read8(0x2115)
    local inc_sel = vmain & 0x03
    local trans = (vmain >> 2) & 0x03
    vram_inc_mode = (vmain >> 7) & 0x01
    local inc_lookup = {
        [0] = 1,
        [1] = 32,
        [2] = 128,
        [3] = 128,
    }
    vram_inc_value = inc_lookup[inc_sel] or 1
    vram_trans = trans
end

local function log_dma_channel(channel, value)
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
        -- This tells us HOW the staging buffer was filled (sequential burst vs scattered)
        if STAGING_WATCH_ENABLED and a1b == 0x7E then
            local src_in_staging = (a1t >= STAGING_WATCH_START and a1t <= STAGING_WATCH_END)
            if src_in_staging then
                log_staging_summary_for_dma(src, das, captured_vmadd)
                -- Log ROM reads that occurred during this staging fill
                log_staging_rom_reads(get_canonical_frame(), captured_vmadd, das)
                reset_staging_rom_reads()
            end
        end
    end

    -- OAM DMA capture: BBAD=0x04 ($2104 = OAMDATA)
    -- Capture the DMA source buffer as authoritative OAM for this frame
    -- Accept transfers >= 512 bytes (low table only) - some games skip high table
    if direction == "A->B" and bbad == 0x04 and das >= OAM_DMA_MIN_SIZE then
        -- Read OAMADDR ($2102/$2103) to check if we're writing from start
        local oamaddr_lo = emu.read(0x2102, emu.memType.snesRegister) or 0
        local oamaddr_hi = emu.read(0x2103, emu.memType.snesRegister) or 0
        local oamaddr = oamaddr_lo + ((oamaddr_hi & 0x01) * 256)

        -- Capture min(das, 544) bytes, pad with zeros if needed
        local capture_size = math.min(das, OAM_DMA_SIZE)
        local oam_bytes = {}
        local read_ok = true
        local nil_count = 0
        for i = 0, capture_size - 1 do
            local addr = src + i
            local ok, val = pcall(emu.read, addr, dma_read_mem or emu.memType.snesMemory)
            if ok then
                -- Treat nil as 0 and count it
                if val == nil then
                    val = 0
                    nil_count = nil_count + 1
                end
                oam_bytes[i + 1] = val
            else
                read_ok = false
                break
            end
        end
        -- Pad to 544 bytes if we only got 512 (high table missing)
        if read_ok and #oam_bytes >= OAM_DMA_MIN_SIZE then
            for i = #oam_bytes + 1, OAM_DMA_SIZE do
                oam_bytes[i] = 0
            end
            oam_dma_buffer = oam_bytes
            -- OAM DMA fires during vblank, before on_end_frame() increments frame_count.
            -- Adjust by +1 if using frame_count (not last_state_frame) so the buffer
            -- matches the capture call that happens after the frame_count increment.
            local f = get_canonical_frame()
            if last_state_frame == nil then
                f = f + 1
            end
            oam_dma_frame = f
            log(string.format(
                "OAM_DMA_CAPTURE: frame=%d src=0x%06X das=%d read=%d oamaddr=%d nils=%d",
                oam_dma_frame, src, das, capture_size, oamaddr, nil_count
            ))
            if oamaddr ~= 0 then
                log(string.format("WARNING: OAM DMA starts at OAMADDR=%d, not 0 (index assumptions may be off)", oamaddr))
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
            local chunk = {}
            local chunk_len = 0
            local chunk_size = 4096
            for i = 0, das - 1 do
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
        if CFG.capture_on_vram_dma and capture_allowed(frame_id) then
            pending_dma_capture = true
            pending_dma_count = pending_dma_count + 1
        end
    end
end

local function advance_vram_addr(wrote_high_byte)
    if vram_inc_mode == 0 and not wrote_high_byte then
        vram_word_addr = (vram_word_addr + vram_inc_value) & 0x7FFF
        return
    end
    if vram_inc_mode == 1 and wrote_high_byte then
        vram_word_addr = (vram_word_addr + vram_inc_value) & 0x7FFF
    end
end

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

local function on_vmain_write(address)
    refresh_vram_inc()
    log(string.format(
        "VMAIN write: vmain=0x%02X inc=%d mode=%d trans=%d",
        read8(0x2115),
        vram_inc_value,
        vram_inc_mode,
        vram_trans
    ))
end

-- FIXED: Shadow VMADD from writes (don't read back $2116/$2117 which can return 0/open-bus)
local vmadd_lo, vmadd_hi = 0, 0
local function on_vram_addr_write(address, value)
    -- Capture the WRITTEN value, not a readback
    if address == 0x2116 then
        vmadd_lo = value & 0xFF
    else -- 0x2117
        vmadd_hi = value & 0xFF
    end
    vram_word_addr = vmadd_lo | (vmadd_hi << 8)
    vram_addr_shadow = vram_word_addr
    log(string.format("VRAM addr write: word=0x%04X (byte=0x%04X)", vram_word_addr, (vram_word_addr * 2) & 0xFFFF))
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

local function on_vram_data_write(address, value)
    local wrote_high = address == 0x2119
    local word_addr = vram_word_addr
    local byte_addr = (word_addr * 2) & 0xFFFF
    vram_write_count = vram_write_count + 1
    if wrote_high then
        vram_write_2119 = vram_write_2119 + 1
    else
        vram_write_2118 = vram_write_2118 + 1
    end
    log(string.format(
        "VRAM write: frame=%s clock=%s reg=0x%04X value=0x%02X word=0x%04X byte=0x%04X inc=%d mode=%d trans=%d",
        tostring(last_state_frame or frame_count),
        tostring(last_master_clock),
        address,
        value & 0xFF,
        word_addr,
        byte_addr,
        vram_inc_value,
        vram_inc_mode,
        vram_trans
    ))
    advance_vram_addr(wrote_high)
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

local function log_wram_writes(frame_id)
    if not CFG.wram_watch_writes then
        return false
    end
    local triggered = false
    local function emit(label)
        local count = wram_write_counts[label] or 0
        if count > 0 then
            local samples = wram_write_samples[label] or {}
            local sample_text = #samples > 0 and table.concat(samples, ",") or "none"
            log(string.format(
                "Frame %d WRAM writes (%s) count=%d range=0x%06X-0x%06X samples=%s",
                frame_id,
                label,
                count,
                wram_watch_start,
                wram_watch_end,
                sample_text
            ))
            if CFG.capture_on_wram_write and count >= CFG.wram_watch_capture_threshold then
                triggered = true
            end
        end
        wram_write_counts[label] = 0
        wram_write_samples[label] = {}
        wram_write_cpu_samples[label] = 0
    end
    emit("snes")
    emit("sa1")
    return triggered
end

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

local function on_end_frame()
    frame_count = frame_count + 1

    -- FIXED: Process pending DMA comparisons at frame end (after all DMAs have completed)
    process_pending_dma_compares()

    if not SKIP_INPUT and SAVESTATE_PATH and DOOR_UP_START and DOOR_UP_END then
        if frame_count >= DOOR_UP_START and frame_count <= DOOR_UP_END then
            set_input({up = true}, 0)
        else
            set_input({}, 0)
        end
    end

    local current_snapshot = nil
    if CFG.wram_dump_on_vram_diff and CFG.wram_dump_prev and wram_dump_allowed(last_state_frame or frame_count) then
        current_snapshot = capture_wram_snapshot()
    end
    poll_vram_diff(last_state_frame or frame_count, current_snapshot)
    prev_wram_snapshot = current_snapshot
    prev_wram_frame = last_state_frame or frame_count

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

    if pending_dma_capture and CFG.capture_on_vram_dma then
        local tag = "vramdma"
        if pending_dma_count > 1 then
            tag = tag .. "_x" .. tostring(pending_dma_count)
        end
        if capture_allowed(last_state_frame or frame_count) then
            write_capture_snapshot(tag, last_state_frame or frame_count)
        end
        pending_dma_capture = false
        pending_dma_count = 0
    end

    if vram_write_count > 0 then
        log(string.format(
            "Frame %d VRAM writes: %d (2118=%d 2119=%d) masterClock=%s",
            frame_count,
            vram_write_count,
            vram_write_2118,
            vram_write_2119,
            tostring(last_master_clock)
        ))
        vram_write_count = 0
        vram_write_2118 = 0
        vram_write_2119 = 0
    end
    if vram_mem_write_count > 0 then
        log(string.format(
            "Frame %d VRAM memType writes: %d (logged=%d)",
            frame_count,
            vram_mem_write_count,
            vram_mem_write_logged
        ))
        vram_mem_write_count = 0
        vram_mem_write_logged = 0
    end

    local wram_triggered = log_wram_writes(frame_count)
    if wram_triggered and CFG.capture_on_wram_write and capture_allowed(frame_count) then
        write_capture_snapshot("wramwrite", frame_count)
    end

    -- Periodic sprite captures for gameplay correlation
    if CFG.periodic_capture_enabled and frame_count >= STATE.next_periodic_capture_frame then
        STATE.periodic_capture_count = STATE.periodic_capture_count + 1
        log(string.format("PERIODIC_CAPTURE: frame=%d capture_num=%d", frame_count, STATE.periodic_capture_count))
        write_capture_snapshot("gameplay", frame_count)
        STATE.next_periodic_capture_frame = frame_count + CFG.periodic_capture_interval
    end

    if CFG.heartbeat_every > 0 and (frame_count % CFG.heartbeat_every) == 0 then
        log(string.format("Heartbeat frame=%d masterClock=%s", frame_count, tostring(last_master_clock)))
    end

    if rom_trace_active and rom_trace_end_frame ~= nil and frame_count > rom_trace_end_frame then
        rom_trace_active = false
        log_rom(string.format(
            "ROM trace frame limit reached: frame=%d start=%s label=%s remaining=%d",
            frame_count,
            tostring(rom_trace_arm_frame),
            tostring(rom_trace_label),
            rom_trace_remaining
        ))
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
            while clock_accum >= ticks_per_frame do
                clock_accum = clock_accum - ticks_per_frame
                on_end_frame()
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
        end
    else
        emu.addEventCallback(on_end_frame, emu.eventType.endFrame)
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

add_memory_callback_compat(on_dma_enable, emu.callbackType.write, 0x420B, 0x420B, cpu_type, MEM.cpu)
add_memory_callback_compat(on_hdma_enable, emu.callbackType.write, 0x420C, 0x420C, cpu_type, MEM.cpu)
-- Shadow DMA channel registers as they are written (before $420B triggers DMA)
add_memory_callback_compat(on_dma_reg_write, emu.callbackType.write, 0x4300, 0x437F, cpu_type, MEM.cpu)
add_memory_callback_compat(on_vmain_write, emu.callbackType.write, 0x2115, 0x2115, cpu_type, MEM.cpu)
add_memory_callback_compat(on_vram_addr_write, emu.callbackType.write, 0x2116, 0x2117, cpu_type, MEM.cpu)
add_memory_callback_compat(on_vram_data_write, emu.callbackType.write, 0x2118, 0x2119, cpu_type, MEM.cpu)
add_memory_callback_compat(on_sa1_bank_write, emu.callbackType.write, 0x2220, 0x2225, cpu_type, MEM.cpu)
add_memory_callback_compat(on_sa1_ctrl_write, emu.callbackType.write, 0x2230, 0x2230, cpu_type, MEM.cpu)
add_memory_callback_compat(on_sa1_dma_reg_write, emu.callbackType.write, 0x2231, 0x2239, cpu_type, MEM.cpu)
add_memory_callback_compat(on_sa1_bitmap_write, emu.callbackType.write, 0x2240, 0x224F, cpu_type, MEM.cpu)

local sa1_cpu_type = emu.cpuType
    and (emu.cpuType.sa1 or emu.cpuType.SA1 or emu.cpuType.sa1Cpu or emu.cpuType.sa1cpu)
    or nil

-- Register SA-1 CPU callback for $2230 (DCNT) only - this is the DMA trigger we need
-- Note: $2220-$2225 (bank regs) are written by S-CPU to configure SA-1, not by SA-1 itself
-- Registering SA-1 callbacks for all registers causes timeout due to high write frequency
if sa1_cpu_type then
    add_memory_callback_compat(on_sa1_ctrl_write, emu.callbackType.write, 0x2230, 0x2230, sa1_cpu_type, MEM.cpu)
    log("INFO: SA-1 CPU callback registered for $2230 (DCNT)")
else
    log("INFO: SA-1 cpuType not available; SA-1 DMA monitoring limited to S-CPU writes")
end

if CFG.rom_trace_on_wram_write then
    if not MEM.prg then
        log("WARNING: ROM trace enabled but no PRG-ROM memType resolved")
    else
        local prg_size = 0
        if emu.getMemorySize then
            local ok, size = pcall(emu.getMemorySize, MEM.prg)
            if ok and size and size > 0 then
                prg_size = size
            end
        end
        local prg_end = prg_size > 0 and (prg_size - 1) or 0xFFFFFF
        rom_trace_prg_size = prg_size > 0 and prg_size or nil
        rom_trace_prg_end = prg_end
        local function make_prg_reader(label)
            return function(address, value)
                local frame_id = last_state_frame or frame_count
                if not rom_trace_allowed(frame_id) then
                    return
                end
                rom_trace_remaining = rom_trace_remaining - 1
                local extra = ""
                if CFG.rom_trace_pc_samples > 0 and rom_trace_pc_samples < CFG.rom_trace_pc_samples then
                    rom_trace_pc_samples = rom_trace_pc_samples + 1
                    local snapshot = get_cpu_state_snapshot()
                    if snapshot then
                        extra = string.format(
                            " %s=0x%04X %s=0x%02X %s=0x%02X",
                            snapshot.pc_key or "PC",
                            snapshot.pc_val or 0,
                            snapshot.k_key or "K",
                            snapshot.k_val or 0,
                            snapshot.dbr_key or "DBR",
                            snapshot.dbr_val or 0
                        )
                    end
                end
                log_rom(string.format(
                    "ROM read (%s): frame=%s addr=0x%06X value=0x%02X remaining=%d%s",
                    label,
                    tostring(frame_id),
                    address,
                    value & 0xFF,
                    rom_trace_remaining,
                    extra
                ))
                if rom_trace_remaining <= 0 then
                    rom_trace_active = false
                    log_rom(string.format(
                        "ROM trace complete: frame=%s start=%s label=%s",
                        tostring(frame_id),
                        tostring(rom_trace_arm_frame),
                        tostring(rom_trace_label)
                    ))
                end
            end
        end
        local snes_prg_ref = add_memory_callback_compat(
            make_prg_reader("snes"),
            emu.callbackType.read,
            0x000000,
            prg_end,
            cpu_type,
            MEM.prg
        )
        if not snes_prg_ref then
            log("WARNING: failed to register PRG-ROM read trace for S-CPU")
        end
        if sa1_cpu_type then
            local sa1_prg_ref = add_memory_callback_compat(
                make_prg_reader("sa1"),
                emu.callbackType.read,
                0x000000,
                prg_end,
                sa1_cpu_type,
                MEM.prg
            )
            if not sa1_prg_ref then
                log("WARNING: failed to register PRG-ROM read trace for SA-1")
            end
        else
            log("INFO: SA-1 cpuType not available; ROM trace limited to S-CPU")
        end
    end
end
if CFG.wram_watch_writes then
    if not wram_mem_type then
        log("WARNING: WRAM watch enabled but no WRAM memType resolved")
    else
        local snes_ref = add_memory_callback_compat(
            function(address, value)
                record_wram_write("snes", address)
            end,
            emu.callbackType.write,
            wram_watch_start,
            wram_watch_end,
            cpu_type,
            wram_mem_type
        )
        if not snes_ref then
            log("WARNING: failed to register WRAM write watch for S-CPU")
        end
        if sa1_cpu_type then
            local sa1_ref = add_memory_callback_compat(
                function(address, value)
                    record_wram_write("sa1", address)
                end,
                emu.callbackType.write,
                wram_watch_start,
                wram_watch_end,
                sa1_cpu_type,
                wram_mem_type
            )
            if not sa1_ref then
                log("WARNING: failed to register WRAM write watch for SA-1")
            end
        else
            log("INFO: SA-1 cpuType not available; WRAM watch limited to S-CPU")
        end
    end
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

        -- Also try SA-1 (may not work due to API limitation)
        if sa1_cpu_type then
            local sa1_staging_ref = add_memory_callback_compat(
                on_staging_write,
                emu.callbackType.write,
                staging_start,
                staging_end,
                sa1_cpu_type,
                wram_mem_type
            )
            if sa1_staging_ref then
                log(string.format(
                    "INFO: Staging watch registered for SA-1: 0x%06X-0x%06X",
                    staging_start, staging_end
                ))
            else
                log("INFO: SA-1 staging callback not available (expected)")
            end
        end

        -- Register PRG read callback for ROM read tracking during staging fills
        if STAGING_ROM_READS_ENABLED and MEM.prg then
            local prg_size = 0
            local ok, size = pcall(emu.getMemorySize, MEM.prg)
            if ok then prg_size = size end

            if prg_size > 0 then
                -- Register S-CPU PRG read callback
                local snes_prg_ref = add_memory_callback_compat(
                    make_staging_rom_reader("snes"),
                    emu.callbackType.read,
                    0,
                    prg_size - 1,
                    cpu_type,
                    MEM.prg
                )
                if snes_prg_ref then
                    log(string.format(
                        "INFO: PRG read callback registered for S-CPU staging ROM tracking: 0-0x%X (%d bytes)",
                        prg_size - 1, prg_size
                    ))
                else
                    log("WARNING: failed to register PRG read callback for S-CPU staging")
                end

                -- Register SA-1 PRG read callback if available
                if sa1_cpu_type then
                    local sa1_prg_ref = add_memory_callback_compat(
                        make_staging_rom_reader("sa1"),
                        emu.callbackType.read,
                        0,
                        prg_size - 1,
                        sa1_cpu_type,
                        MEM.prg
                    )
                    if sa1_prg_ref then
                        log(string.format(
                            "INFO: PRG read callback registered for SA-1 staging ROM tracking: 0-0x%X (%d bytes)",
                            prg_size - 1, prg_size
                        ))
                    else
                        log("INFO: SA-1 PRG read callback not available (expected on non-SA1 ROMs)")
                    end
                end
            else
                log("WARNING: PRG size is 0, cannot register ROM read callback")
            end
        end
    end
end

if MEM.vram then
    add_memory_callback_compat(function(address, value)
        vram_mem_write_count = vram_mem_write_count + 1
        if CFG.log_vram_memory_writes and vram_mem_write_logged < CFG.max_vram_write_log then
            vram_mem_write_logged = vram_mem_write_logged + 1
            log(string.format(
                "VRAM mem write: frame=%s clock=%s addr=0x%04X value=0x%02X",
                tostring(last_state_frame or frame_count),
                tostring(last_master_clock),
                address,
                value & 0xFF
            ))
        end
    end, emu.callbackType.write, 0x0000, 0xFFFF, cpu_type, MEM.vram)
end

refresh_vram_addr()
refresh_vram_inc()
log(string.format(
    "WRAM config: dump=%s prev=%s watch=%s memType=%s mode=%s base=0x%06X size=0x%05X range=0x%06X-0x%06X",
    tostring(CFG.wram_dump_on_vram_diff),
    tostring(CFG.wram_dump_prev),
    tostring(CFG.wram_watch_writes),
    tostring(wram_mem_type),
    wram_address_mode,
    wram_base,
    CFG.wram_dump_size,
    wram_watch_start,
    wram_watch_end
))
log(string.format(
    "WRAM env: WATCH_START=%s WATCH_END=%s",
    tostring(CFG.wram_watch_start),
    tostring(CFG.wram_watch_end)
))
log(string.format(
    "Staging watch: enabled=%s range=0x%04X-0x%04X pc_samples=%d history_frames=%d",
    tostring(STAGING_WATCH_ENABLED),
    STAGING_WATCH_START,
    STAGING_WATCH_END,
    STAGING_WATCH_PC_SAMPLES,
    STAGING_HISTORY_FRAMES
))
log(string.format(
    "Visibility filter: enabled=%s y_exclude=%d-%d x_range=%d..%d",
    tostring(not CFG.skip_visibility_filter),
    CFG.visible_y_exclude_start,
    CFG.visible_y_exclude_end,
    CFG.visible_x_min,
    CFG.visible_x_max
))
local prg_size_text = rom_trace_prg_size and string.format("0x%X", rom_trace_prg_size) or "nil"
local prg_end_text = rom_trace_prg_end and string.format("0x%06X", rom_trace_prg_end) or "nil"
log(string.format(
    "ROM trace: enabled=%s memType=%s prg_size=%s prg_end=%s max_reads=%d max_frames=%d pc_samples=%d",
    tostring(CFG.rom_trace_on_wram_write),
    tostring(MEM.prg),
    prg_size_text,
    prg_end_text,
    CFG.rom_trace_max_reads,
    CFG.rom_trace_max_frames,
    CFG.rom_trace_pc_samples
))
log("DMA probe start: frame_event=" .. tostring(FRAME_EVENT) .. " max_frames=" .. tostring(MAX_FRAMES))

-- Log initial SA-1 bank register state (per Instrumentation Contract v1.1)
log_sa1_banks("init")

if SAVESTATE_PATH and not PRELOADED_STATE then
    load_savestate_if_needed()
else
    register_frame_event()
end
