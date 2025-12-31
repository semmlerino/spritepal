-- SA-1 Conversion Logger
-- Purpose: Log $2230 (DCNT) and $2231 (CDMA) registers to verify SA-1 character conversion hypothesis
-- Output: CSV file with frame number, register values, and conversion active flag

local DEFAULT_OUTPUT = "C:\\CustomScripts\\KirbyMax\\workshop\\exhal-master\\"
    .. "spritepal\\mesen2_exchange\\"
local OUTPUT_DIR = os.getenv("OUTPUT_DIR") or DEFAULT_OUTPUT
local MAX_FRAMES = tonumber(os.getenv("MAX_FRAMES")) or 18000  -- ~5 minutes at 60fps
local LOG_INTERVAL = tonumber(os.getenv("LOG_INTERVAL")) or 1  -- Log every N frames

if not OUTPUT_DIR:match("[/\\]$") then
    OUTPUT_DIR = OUTPUT_DIR .. "\\"
end

-- Ensure output directory exists
os.execute('mkdir "' .. OUTPUT_DIR:gsub("\\", "\\\\") .. '" 2>NUL')

local CSV_FILE = OUTPUT_DIR .. "sa1_conversion_log.csv"
local LOG_FILE = OUTPUT_DIR .. "sa1_conversion_debug.txt"

-- Memory type compatibility
local MEM = {
    cpu = emu.memType.snesMemory or emu.memType.cpuMemory or emu.memType.cpu,
}

local frame_count = 0
local conversion_active_count = 0
local conversion_inactive_count = 0
local csv_file = nil
local start_time = os.time()

local function log(msg)
    local f = io.open(LOG_FILE, "a")
    if f then
        f:write(os.date("%H:%M:%S") .. " " .. msg .. "\n")
        f:close()
    end
    print(msg)
end

local function init_csv()
    csv_file = io.open(CSV_FILE, "w")
    if csv_file then
        csv_file:write("frame,dcnt_hex,cdma_hex,dcnt_bin,cdma_bin,conversion_active\n")
        csv_file:flush()
        log("CSV initialized: " .. CSV_FILE)
    else
        log("ERROR: Could not create CSV file: " .. CSV_FILE)
        emu.stop(1)
    end
end

local function byte_to_binary(byte)
    local result = ""
    for i = 7, 0, -1 do
        result = result .. ((byte >> i) & 1)
    end
    return result
end

local function read_byte_safe(addr, mem_type)
    local ok, value = pcall(emu.read, addr, mem_type)
    if ok and value then
        return value
    end
    return 0
end

local function log_sa1_registers()
    frame_count = frame_count + 1

    -- Only log at specified interval
    if frame_count % LOG_INTERVAL ~= 0 then
        return
    end

    -- Read SA-1 control registers
    -- $2230 = DCNT (DMA control)
    -- $2231 = CDMA (Character conversion DMA control)
    local dcnt = read_byte_safe(0x2230, MEM.cpu)
    local cdma = read_byte_safe(0x2231, MEM.cpu)

    -- Check character conversion mode bit (bit 7 of CDMA)
    -- CDMA bit 7: 1 = Character conversion DMA enabled
    local conversion_active = (cdma & 0x80) ~= 0

    if conversion_active then
        conversion_active_count = conversion_active_count + 1
    else
        conversion_inactive_count = conversion_inactive_count + 1
    end

    -- Write to CSV
    if csv_file then
        csv_file:write(string.format(
            "%d,0x%02X,0x%02X,%s,%s,%s\n",
            frame_count,
            dcnt,
            cdma,
            byte_to_binary(dcnt),
            byte_to_binary(cdma),
            conversion_active and "ACTIVE" or "inactive"
        ))

        -- Flush every 60 frames
        if frame_count % 60 == 0 then
            csv_file:flush()
        end
    end

    -- Progress logging every 600 frames (~10 seconds)
    if frame_count % 600 == 0 then
        local elapsed = os.time() - start_time
        local pct = (frame_count / MAX_FRAMES) * 100
        log(string.format(
            "Progress: frame %d/%d (%.1f%%), elapsed %ds, conversion active: %d/%d samples",
            frame_count, MAX_FRAMES, pct, elapsed,
            conversion_active_count, conversion_active_count + conversion_inactive_count
        ))
    end

    -- Check for completion
    if frame_count >= MAX_FRAMES then
        finish_capture()
    end
end

local function finish_capture()
    local elapsed = os.time() - start_time
    local total_samples = conversion_active_count + conversion_inactive_count
    local active_pct = total_samples > 0 and (conversion_active_count / total_samples * 100) or 0

    -- Write summary
    local summary = string.format([[
================================================================================
SA-1 CONVERSION HYPOTHESIS TEST RESULTS
================================================================================

Duration: %d frames (%d seconds)
Log interval: every %d frames
Total samples: %d

RESULTS:
  Conversion ACTIVE:   %d samples (%.2f%%)
  Conversion inactive: %d samples (%.2f%%)

HYPOTHESIS OUTCOME:
]], frame_count, elapsed, LOG_INTERVAL, total_samples,
    conversion_active_count, active_pct,
    conversion_inactive_count, 100 - active_pct)

    if active_pct > 90 then
        summary = summary .. "  CONFIRMED - Conversion bit consistently SET (>90%)\n"
        summary = summary .. "  SA-1 character conversion is active during sprite loads.\n"
        summary = summary .. "  Proceed with Strategy A (VRAM-based DB with timing correlation).\n"
    elseif active_pct < 10 then
        summary = summary .. "  FALSIFIED - Conversion bit consistently NOT SET (<10%)\n"
        summary = summary .. "  SA-1 character conversion is NOT active.\n"
        summary = summary .. "  STOP. Investigate alternatives:\n"
        summary = summary .. "    - Palette remapping\n"
        summary = summary .. "    - Runtime tile composition\n"
        summary = summary .. "    - Different compression variant\n"
        summary = summary .. "    - Interlaced plane storage\n"
    else
        summary = summary .. string.format("  PARTIAL - Conversion bit toggles (%.1f%% active)\n", active_pct)
        summary = summary .. "  SA-1 character conversion is used for SOME sprite types.\n"
        summary = summary .. "  Pipeline must route sprites to appropriate strategy.\n"
        summary = summary .. "  Review CSV for patterns (which frames have conversion active).\n"
    end

    summary = summary .. "\nOutput files:\n"
    summary = summary .. "  " .. CSV_FILE .. "\n"
    summary = summary .. "  " .. LOG_FILE .. "\n"
    summary = summary .. "================================================================================\n"

    log(summary)

    -- Write summary to separate file
    local summary_file = io.open(OUTPUT_DIR .. "sa1_hypothesis_results.txt", "w")
    if summary_file then
        summary_file:write(summary)
        summary_file:close()
    end

    -- Close CSV
    if csv_file then
        csv_file:close()
        csv_file = nil
    end

    log("Capture complete. Stopping emulator.")
    emu.stop(0)
end

-- Initialize
log("================================================================================")
log("SA-1 Conversion Logger starting")
log(string.format("MAX_FRAMES=%d, LOG_INTERVAL=%d", MAX_FRAMES, LOG_INTERVAL))
log(string.format("Output: %s", OUTPUT_DIR))
log("================================================================================")

init_csv()

-- Register frame callback
emu.addEventCallback(log_sa1_registers, emu.eventType.endFrame)

-- Cleanup on script end
emu.addEventCallback(function()
    if csv_file then
        csv_file:close()
    end
    log("Script ended")
end, emu.eventType.scriptEnded)
