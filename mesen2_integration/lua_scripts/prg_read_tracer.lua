-- PRG Read Tracer: Log ROM reads following causal byte
-- This reveals whether the causal byte is used as: index, opcode, pointer, or length
--
-- Usage: Set TARGET_ADDR env var to CPU address (e.g., 0xE9E667)
-- Output: prg_trace_[addr].log in mesen2_exchange/

local OUTPUT_DIR = os.getenv("OUTPUT_DIR") or "C:\\CustomScripts\\KirbyMax\\workshop\\exhal-master\\spritepal\\mesen2_exchange\\"
local LOG_FILE = OUTPUT_DIR .. "dma_probe_log.txt"

-- Target byte to trace (CPU address)
local TARGET_ADDR_CPU = tonumber(os.getenv("TARGET_ADDR") or "0xE9E667") or 0xE9E667
local MAX_FRAMES = tonumber(os.getenv("MAX_FRAMES")) or 2500
local TRACE_LIMIT = tonumber(os.getenv("TRACE_LIMIT")) or 100  -- Max PRG reads to log per trigger

-- Convert CPU address to file offset for SA-1 HiROM
local function cpu_to_file(cpu_addr)
    if cpu_addr >= 0xC00000 then
        return cpu_addr - 0xC00000
    end
    return cpu_addr
end

local TARGET_FILE_OFFSET = cpu_to_file(TARGET_ADDR_CPU)

-- Trace output file
local TRACE_FILE = string.format("%sprg_trace_%06X.log", OUTPUT_DIR, TARGET_ADDR_CPU)

local log_handle = nil
local trace_handle = nil
local frame_count = 0
local script_stopping = false

-- Trace state
local tracing_active = false
local trace_count = 0
local trigger_frame = 0
local trigger_value = 0
local trace_buffer = {}

local function log(msg)
    if not log_handle then
        log_handle = io.open(LOG_FILE, "a")
    end
    if log_handle then
        log_handle:write(os.date("%H:%M:%S") .. " " .. msg .. "\n")
        log_handle:flush()
    end
end

local function write_trace(lines)
    if not trace_handle then
        trace_handle = io.open(TRACE_FILE, "a")
    end
    if trace_handle then
        for _, line in ipairs(lines) do
            trace_handle:write(line .. "\n")
        end
        trace_handle:flush()
    end
end

-- Callback when target byte is read (triggers trace)
local function on_target_read(address, value)
    if script_stopping then return nil end
    if address == TARGET_ADDR_CPU and not tracing_active then
        -- Start tracing
        tracing_active = true
        trace_count = 0
        trigger_frame = frame_count
        trigger_value = value
        trace_buffer = {}

        table.insert(trace_buffer, string.format("=== TRIGGER: frame=%d addr=0x%06X value=0x%02X ===",
            frame_count, address, value))

        log(string.format("TRACE_TRIGGER: frame=%d addr=0x%06X value=0x%02X",
            frame_count, address, value))
    end
    return nil  -- Don't modify the value
end

-- Callback for all PRG reads (captures trace data)
local function on_prg_read(address, value)
    if script_stopping then return nil end
    if not tracing_active then return nil end

    -- Skip the target address itself
    if address == TARGET_ADDR_CPU then return nil end

    trace_count = trace_count + 1

    -- Log the read
    local cpu_bank = math.floor(address / 0x10000)
    local cpu_offset = address % 0x10000
    local file_offset = cpu_to_file(address)

    table.insert(trace_buffer, string.format("  [%3d] CPU:%02X:%04X (file:0x%06X) = 0x%02X",
        trace_count, cpu_bank, cpu_offset, file_offset, value))

    -- Stop after limit
    if trace_count >= TRACE_LIMIT then
        tracing_active = false
        table.insert(trace_buffer, string.format("=== TRACE_END: %d reads captured ===", trace_count))
        table.insert(trace_buffer, "")

        write_trace(trace_buffer)
        trace_buffer = {}

        log(string.format("TRACE_COMPLETE: frame=%d reads=%d", trigger_frame, trace_count))
    end

    return nil
end

-- Frame callback
local function on_frame()
    if script_stopping then return end

    frame_count = frame_count + 1

    -- If trace is still active at frame end, flush it
    if tracing_active and trace_count > 0 then
        tracing_active = false
        table.insert(trace_buffer, string.format("=== TRACE_END (frame end): %d reads ===", trace_count))
        table.insert(trace_buffer, "")

        write_trace(trace_buffer)
        trace_buffer = {}

        log(string.format("TRACE_COMPLETE_FRAME_END: frame=%d reads=%d", trigger_frame, trace_count))
    end

    if frame_count >= MAX_FRAMES then
        log(string.format("MAX_FRAMES: frame=%d stopping", frame_count))
        script_stopping = true
        emu.stop()
    end
end

-- Initialize
log(string.format("PRG_READ_TRACER: start target=0x%06X (file=0x%06X) trace_file=%s",
    TARGET_ADDR_CPU, TARGET_FILE_OFFSET, TRACE_FILE))

-- Clear old trace file
local f = io.open(TRACE_FILE, "w")
if f then
    f:write(string.format("PRG Read Trace for 0x%06X\n", TARGET_ADDR_CPU))
    f:write(string.format("Started: %s\n", os.date()))
    f:write("==============================================\n\n")
    f:close()
end

-- CPU type constants
local snes_cpu_type = emu.cpuType and emu.cpuType.snes or nil
local sa1_cpu_type = emu.cpuType and emu.cpuType.sa1 or nil
log(string.format("CPU types: snes=%s sa1=%s", tostring(snes_cpu_type), tostring(sa1_cpu_type)))

-- Register target byte callback (both CPUs)
-- Only need to watch the specific target byte
if snes_cpu_type then
    local ok, id = pcall(emu.addMemoryCallback, on_target_read, emu.callbackType.read,
        TARGET_FILE_OFFSET, TARGET_FILE_OFFSET, snes_cpu_type, emu.memType.snesPrgRom)
    if ok then
        log(string.format("TARGET_CALLBACK_SNES: registered id=%s", tostring(id)))
    end
end

if sa1_cpu_type then
    local ok, id = pcall(emu.addMemoryCallback, on_target_read, emu.callbackType.read,
        TARGET_FILE_OFFSET, TARGET_FILE_OFFSET, sa1_cpu_type, emu.memType.snesPrgRom)
    if ok then
        log(string.format("TARGET_CALLBACK_SA1: registered id=%s", tostring(id)))
    end
end

-- Register full PRG read callback for trace capture
-- This needs to cover the full ROM range
if snes_cpu_type then
    local ok, id = pcall(emu.addMemoryCallback, on_prg_read, emu.callbackType.read,
        0x000000, 0x3FFFFF, snes_cpu_type, emu.memType.snesPrgRom)
    if ok then
        log(string.format("TRACE_CALLBACK_SNES: registered id=%s (full PRG)", tostring(id)))
    end
end

if sa1_cpu_type then
    local ok, id = pcall(emu.addMemoryCallback, on_prg_read, emu.callbackType.read,
        0x000000, 0x3FFFFF, sa1_cpu_type, emu.memType.snesPrgRom)
    if ok then
        log(string.format("TRACE_CALLBACK_SA1: registered id=%s (full PRG)", tostring(id)))
    end
end

emu.addEventCallback(on_frame, emu.eventType.endFrame)
log("FRAME_CALLBACK: registered")
