-- Block Boundary Detector: Measure contiguous read spans from stream starts
-- Detects where sequential reads end to determine compressed block sizes
--
-- Usage: Set TARGET_ADDR env var to CPU address (e.g., 0xE9E667)
-- Output: block_boundaries_[addr].log in mesen2_exchange/

local OUTPUT_DIR = os.getenv("OUTPUT_DIR") or "C:\\CustomScripts\\KirbyMax\\workshop\\exhal-master\\spritepal\\mesen2_exchange\\"
local LOG_FILE = OUTPUT_DIR .. "dma_probe_log.txt"

-- Target byte to trace (CPU address)
local TARGET_ADDR_CPU = tonumber(os.getenv("TARGET_ADDR") or "0xE9E667") or 0xE9E667
local MAX_FRAMES = tonumber(os.getenv("MAX_FRAMES")) or 2500
local MAX_READS_PER_BLOCK = tonumber(os.getenv("MAX_READS")) or 2000  -- Capture up to 2KB blocks

-- Convert CPU address to file offset for SA-1 HiROM
local function cpu_to_file(cpu_addr)
    if cpu_addr >= 0xC00000 then
        return cpu_addr - 0xC00000
    end
    return cpu_addr
end

local TARGET_FILE_OFFSET = cpu_to_file(TARGET_ADDR_CPU)

-- Output file
local BOUNDARY_FILE = string.format("%sblock_boundaries_%06X.log", OUTPUT_DIR, TARGET_ADDR_CPU)

local log_handle = nil
local boundary_handle = nil
local frame_count = 0
local script_stopping = false

-- Block tracking state
local in_block = false
local block_start_addr = 0
local last_sequential_addr = 0
local sequential_count = 0
local block_frame = 0
local blocks_detected = {}

-- Gap tolerance: allow small gaps in sequential reads (for interleaved code reads)
local GAP_TOLERANCE = 16  -- Allow up to 16 bytes gap before considering block ended

local function log(msg)
    if not log_handle then
        log_handle = io.open(LOG_FILE, "a")
    end
    if log_handle then
        log_handle:write(os.date("%H:%M:%S") .. " " .. msg .. "\n")
        log_handle:flush()
    end
end

local function write_boundary(line)
    if not boundary_handle then
        boundary_handle = io.open(BOUNDARY_FILE, "a")
    end
    if boundary_handle then
        boundary_handle:write(line .. "\n")
        boundary_handle:flush()
    end
end

local function finish_block(reason)
    if not in_block then return end

    local block_size = last_sequential_addr - block_start_addr + 1
    local block_end = last_sequential_addr

    local entry = {
        frame = block_frame,
        start_addr = block_start_addr,
        end_addr = block_end,
        size = block_size,
        sequential_reads = sequential_count,
        reason = reason
    }
    table.insert(blocks_detected, entry)

    write_boundary(string.format(
        "BLOCK: frame=%d start=0x%06X end=0x%06X size=%d (0x%X) reads=%d reason=%s",
        block_frame, block_start_addr, block_end, block_size, block_size, sequential_count, reason))

    log(string.format("BLOCK_END: frame=%d size=%d reason=%s", block_frame, block_size, reason))

    in_block = false
    sequential_count = 0
end

-- Callback when target byte is read (starts block tracking)
local function on_target_read(address, value)
    if script_stopping then return nil end
    if address == TARGET_ADDR_CPU then
        -- Finish any previous block
        if in_block then
            finish_block("new_trigger")
        end

        -- Start new block
        in_block = true
        block_start_addr = address
        last_sequential_addr = address
        sequential_count = 1
        block_frame = frame_count

        write_boundary(string.format("\n=== TRIGGER: frame=%d addr=0x%06X value=0x%02X ===",
            frame_count, address, value))

        log(string.format("BLOCK_START: frame=%d addr=0x%06X", frame_count, address))
    end
    return nil
end

-- Callback for all PRG reads (tracks sequential span)
local function on_prg_read(address, value)
    if script_stopping then return nil end
    if not in_block then return nil end

    -- Skip the trigger address itself (already counted)
    if address == block_start_addr then return nil end

    -- Get bank of trigger and this address
    local trigger_bank = math.floor(block_start_addr / 0x10000)
    local this_bank = math.floor(address / 0x10000)

    -- FILTER: Only consider reads in the same bank as the trigger
    -- Reads from other banks (like 00:841F) are decoder routine/table lookups
    if this_bank ~= trigger_bank then
        -- Ignore reads from other banks - don't end the block
        return nil
    end

    -- Check if this read is sequential (or within gap tolerance)
    local gap = address - last_sequential_addr

    if gap >= 1 and gap <= GAP_TOLERANCE then
        -- Sequential or small gap - extend the block
        last_sequential_addr = address
        sequential_count = sequential_count + 1

        -- Safety limit
        if sequential_count >= MAX_READS_PER_BLOCK then
            finish_block("max_reads")
        end
    elseif address < block_start_addr or gap > GAP_TOLERANCE then
        -- Non-sequential read within same bank (jumped backwards or too far forward)
        -- Block has ended
        finish_block(string.format("non_seq_0x%06X", address))
    end

    return nil
end

-- Frame callback
local function on_frame()
    if script_stopping then return end

    frame_count = frame_count + 1

    -- If block is still open at frame end, it spans frames (rare but possible)
    -- We'll let it continue to next frame

    if frame_count >= MAX_FRAMES then
        if in_block then
            finish_block("max_frames")
        end

        -- Write summary
        write_boundary("\n" .. string.rep("=", 60))
        write_boundary("SUMMARY")
        write_boundary(string.rep("=", 60))
        write_boundary(string.format("Target: 0x%06X", TARGET_ADDR_CPU))
        write_boundary(string.format("Blocks detected: %d", #blocks_detected))

        if #blocks_detected > 0 then
            local total_size = 0
            local min_size = 999999
            local max_size = 0
            for _, b in ipairs(blocks_detected) do
                total_size = total_size + b.size
                if b.size < min_size then min_size = b.size end
                if b.size > max_size then max_size = b.size end
            end
            local avg_size = total_size / #blocks_detected

            write_boundary(string.format("Size range: %d - %d bytes", min_size, max_size))
            write_boundary(string.format("Average size: %.1f bytes", avg_size))
            write_boundary(string.format("Total data: %d bytes", total_size))

            write_boundary("\nAll blocks:")
            for i, b in ipairs(blocks_detected) do
                write_boundary(string.format("  [%2d] frame=%d 0x%06X-0x%06X size=%d",
                    i, b.frame, b.start_addr, b.end_addr, b.size))
            end
        end

        log(string.format("COMPLETE: %d blocks detected", #blocks_detected))
        script_stopping = true
        emu.stop()
    end
end

-- Initialize
log(string.format("BLOCK_BOUNDARY_DETECTOR: target=0x%06X (file=0x%06X)",
    TARGET_ADDR_CPU, TARGET_FILE_OFFSET))

-- Clear old output file
local f = io.open(BOUNDARY_FILE, "w")
if f then
    f:write(string.format("Block Boundary Analysis for 0x%06X\n", TARGET_ADDR_CPU))
    f:write(string.format("Started: %s\n", os.date()))
    f:write(string.format("Gap tolerance: %d bytes\n", GAP_TOLERANCE))
    f:write("==============================================\n")
    f:close()
end

-- CPU type constants
local snes_cpu_type = emu.cpuType and emu.cpuType.snes or nil
local sa1_cpu_type = emu.cpuType and emu.cpuType.sa1 or nil
log(string.format("CPU types: snes=%s sa1=%s", tostring(snes_cpu_type), tostring(sa1_cpu_type)))

-- Register target byte callback (both CPUs)
if snes_cpu_type then
    pcall(emu.addMemoryCallback, on_target_read, emu.callbackType.read,
        TARGET_FILE_OFFSET, TARGET_FILE_OFFSET, snes_cpu_type, emu.memType.snesPrgRom)
end
if sa1_cpu_type then
    pcall(emu.addMemoryCallback, on_target_read, emu.callbackType.read,
        TARGET_FILE_OFFSET, TARGET_FILE_OFFSET, sa1_cpu_type, emu.memType.snesPrgRom)
end

-- Register full PRG read callback for boundary detection
if snes_cpu_type then
    pcall(emu.addMemoryCallback, on_prg_read, emu.callbackType.read,
        0x000000, 0x3FFFFF, snes_cpu_type, emu.memType.snesPrgRom)
end
if sa1_cpu_type then
    pcall(emu.addMemoryCallback, on_prg_read, emu.callbackType.read,
        0x000000, 0x3FFFFF, sa1_cpu_type, emu.memType.snesPrgRom)
end

emu.addEventCallback(on_frame, emu.eventType.endFrame)
log("FRAME_CALLBACK: registered")
