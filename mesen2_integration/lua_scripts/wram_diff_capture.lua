-- WRAM Diff Capture for payload_hash flip analysis
-- Dumps $7E2000-$7E27FF at target frame for baseline vs ablated comparison
--
-- Usage: Set WRAM_DUMP_FRAME env var (default 1795)
-- Output: wram_dump_frame_NNNN.bin in mesen2_exchange/

local OUTPUT_DIR = os.getenv("OUTPUT_DIR") or "C:\\CustomScripts\\KirbyMax\\workshop\\exhal-master\\spritepal\\mesen2_exchange\\"
local LOG_FILE = OUTPUT_DIR .. "dma_probe_log.txt"

-- Target frame for WRAM dump (first flip frame)
local DUMP_FRAME = tonumber(os.getenv("WRAM_DUMP_FRAME")) or 1795
local MAX_FRAMES = tonumber(os.getenv("MAX_FRAMES")) or 2500

-- WRAM region to dump (staging buffer)
local WRAM_START = 0x7E2000
local WRAM_END = 0x7E27FF
local WRAM_SIZE = WRAM_END - WRAM_START + 1  -- 2048 bytes

-- Ablation config (from env)
-- NOTE: Addresses are CPU addresses (0xC00000+). Callback receives CPU addresses.
-- But registration range uses FILE OFFSETS (0-0x3FFFFF for 4MB ROM).
local ABLATION_ENABLED = (os.getenv("ABLATION_ENABLED") == "1")
local ABLATION_PRG_START_CPU = tonumber(os.getenv("ABLATION_PRG_START") or "0") or 0
local ABLATION_PRG_END_CPU = tonumber(os.getenv("ABLATION_PRG_END") or "0") or 0
local ABLATION_VALUE = tonumber(os.getenv("ABLATION_VALUE") or "0xFF") or 0xFF

-- Convert CPU address to file offset for SA-1 HiROM
-- CPU 0xC00000-0xFFFFFF maps to file 0x000000-0x3FFFFF
local function cpu_to_file(cpu_addr)
    if cpu_addr >= 0xC00000 then
        return cpu_addr - 0xC00000
    end
    return cpu_addr  -- Already a file offset?
end

local ABLATION_PRG_START = cpu_to_file(ABLATION_PRG_START_CPU)
local ABLATION_PRG_END = cpu_to_file(ABLATION_PRG_END_CPU)

local log_handle = nil
local dump_done = false
local ablation_hits = 0
local frame_count = 0  -- Maintain our own frame counter (Mesen2 API quirk)
local script_stopping = false  -- Guard to prevent callback re-entry after emu.stop()

local function log(msg)
    if not log_handle then
        log_handle = io.open(LOG_FILE, "a")
    end
    if log_handle then
        log_handle:write(os.date("%H:%M:%S") .. " " .. msg .. "\n")
        log_handle:flush()
    end
end

local function dump_wram(frame)
    local addr_suffix = ""
    if ABLATION_ENABLED and ABLATION_PRG_START_CPU > 0 then
        addr_suffix = string.format("_%06X", ABLATION_PRG_START_CPU)
    end
    local filename = string.format("wram_dump_frame_%04d%s%s.bin",
        frame,
        ABLATION_ENABLED and "_ablated" or "_baseline",
        addr_suffix)
    local filepath = OUTPUT_DIR .. filename

    local f = io.open(filepath, "wb")
    if not f then
        log(string.format("ERROR: Could not open %s for writing", filepath))
        return
    end

    -- Read WRAM byte by byte
    local bytes = {}
    for addr = WRAM_START, WRAM_END do
        local val = emu.read(addr, emu.memType.snesMemory, false) or 0
        table.insert(bytes, string.char(val))
    end

    f:write(table.concat(bytes))
    f:close()

    -- Also log hex summary (first 64 bytes)
    local hex_summary = {}
    for i = 1, math.min(64, #bytes) do
        table.insert(hex_summary, string.format("%02X", string.byte(bytes[i])))
    end

    log(string.format("WRAM_DUMP: frame=%d file=%s size=%d first_64=[%s]",
        frame, filename, WRAM_SIZE, table.concat(hex_summary, " ")))
end

-- Ablation callback
-- NOTE: Callback receives CPU addresses (0xC00000+), so check against CPU range
local function on_prg_read(address, value)
    if script_stopping then return nil end
    if ABLATION_ENABLED and address >= ABLATION_PRG_START_CPU and address <= ABLATION_PRG_END_CPU then
        ablation_hits = ablation_hits + 1
        if ablation_hits <= 5 then
            log(string.format("ABLATION_HIT: addr=0x%06X frame=%d value=0x%02X->0x%02X",
                address, frame_count, value, ABLATION_VALUE))
        end
        return ABLATION_VALUE
    end
    return nil
end

-- Frame callback
local function on_frame()
    -- Early exit if already stopping
    if script_stopping then
        return
    end

    frame_count = frame_count + 1

    if frame_count == DUMP_FRAME and not dump_done then
        dump_wram(frame_count)
        dump_done = true
        log(string.format("WRAM_DUMP_COMPLETE: frame=%d ablation=%s hits=%d",
            frame_count, ABLATION_ENABLED and "yes" or "no", ablation_hits))
    end

    if frame_count >= MAX_FRAMES then
        log(string.format("MAX_FRAMES: frame=%d stopping", frame_count))
        script_stopping = true
        emu.stop()
    end
end

-- Initialize
log(string.format("WRAM_DIFF_CAPTURE: start dump_frame=%d wram=0x%04X-0x%04X ablation=%s cpu_range=0x%06X-0x%06X file_range=0x%06X-0x%06X",
    DUMP_FRAME, WRAM_START, WRAM_END,
    ABLATION_ENABLED and "ENABLED" or "DISABLED",
    ABLATION_PRG_START_CPU, ABLATION_PRG_END_CPU,
    ABLATION_PRG_START, ABLATION_PRG_END))

-- CPU type constants
local snes_cpu_type = emu.cpuType and emu.cpuType.snes or nil
local sa1_cpu_type = emu.cpuType and emu.cpuType.sa1 or nil
log(string.format("CPU types: snes=%s sa1=%s", tostring(snes_cpu_type), tostring(sa1_cpu_type)))

-- Register callbacks
if ABLATION_ENABLED then
    -- Register S-CPU PRG read callback
    if snes_cpu_type then
        local ok, id = pcall(emu.addMemoryCallback, on_prg_read, emu.callbackType.read,
            ABLATION_PRG_START, ABLATION_PRG_END, snes_cpu_type, emu.memType.snesPrgRom)
        if ok then
            log(string.format("ABLATION_CALLBACK_SNES: registered id=%s", tostring(id)))
        else
            log(string.format("ABLATION_CALLBACK_SNES: FAILED - %s", tostring(id)))
        end
    end

    -- Register SA-1 PRG read callback (Kirby Super Star uses SA-1!)
    if sa1_cpu_type then
        local ok, id = pcall(emu.addMemoryCallback, on_prg_read, emu.callbackType.read,
            ABLATION_PRG_START, ABLATION_PRG_END, sa1_cpu_type, emu.memType.snesPrgRom)
        if ok then
            log(string.format("ABLATION_CALLBACK_SA1: registered id=%s", tostring(id)))
        else
            log(string.format("ABLATION_CALLBACK_SA1: FAILED - %s", tostring(id)))
        end
    else
        log("WARNING: SA-1 CPU type not available - SA-1 reads won't be ablated!")
    end
end

emu.addEventCallback(on_frame, emu.eventType.endFrame)
log("FRAME_CALLBACK: registered")
