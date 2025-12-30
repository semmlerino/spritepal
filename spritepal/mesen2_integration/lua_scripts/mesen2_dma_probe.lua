-- DMA/SA-1 probe for sprite upload diagnostics (headless-safe)
local OUTPUT_DIR = os.getenv("OUTPUT_DIR") or "C:\\CustomScripts\\KirbyMax\\workshop\\exhal-master\\spritepal\\mesen2_exchange\\"
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
local function log(msg)
    local f = io.open(LOG_FILE, "a")
    if f then
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
    vram = emu.memType.snesVram or emu.memType.snesVideoRam or emu.memType.videoRam,
    wram = emu.memType.snesWorkRam or emu.memType.snesWram or emu.memType.workRam or emu.memType.wram,
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

local function add_memory_callback_compat(callback, cb_type, start_addr, end_addr, cpu_type, mem_type)
    if cpu_type ~= nil and mem_type ~= nil then
        local ok, id = pcall(emu.addMemoryCallback, callback, cb_type, start_addr, end_addr, cpu_type, mem_type)
        if ok then
            return id
        end
    end
    if cpu_type ~= nil then
        local ok, id = pcall(emu.addMemoryCallback, callback, cb_type, start_addr, end_addr, cpu_type)
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
        return tonumber(text, 16) or default_value
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

local LOG_VRAM_MEMORY_WRITES = os.getenv("LOG_VRAM_MEMORY_WRITES") == "1"
local MAX_VRAM_WRITE_LOG = tonumber(os.getenv("MAX_VRAM_WRITE_LOG")) or 20
local VRAM_DIFF_ENABLED = os.getenv("VRAM_DIFF") ~= "0"
local VRAM_SIZE = 0x10000
local VRAM_COARSE_STEP = tonumber(os.getenv("VRAM_COARSE_STEP")) or 16
local VRAM_PAGE_SIZE = tonumber(os.getenv("VRAM_PAGE_SIZE")) or 0x0400
local VRAM_PAGE_LOG_LIMIT = tonumber(os.getenv("VRAM_PAGE_LOG_LIMIT")) or 12
local HEARTBEAT_EVERY = tonumber(os.getenv("HEARTBEAT_EVERY")) or 0
local WRAM_DUMP_ON_VRAM_DIFF = os.getenv("WRAM_DUMP_ON_VRAM_DIFF") ~= "0"
local WRAM_DUMP_START = os.getenv("WRAM_DUMP_START") or "0x2000"
local WRAM_DUMP_ABS_START = os.getenv("WRAM_DUMP_ABS_START")
local WRAM_DUMP_SIZE = tonumber(os.getenv("WRAM_DUMP_SIZE")) or 0x8000
local WRAM_WATCH_WRITES = os.getenv("WRAM_WATCH_WRITES") ~= "0"
local WRAM_WATCH_SAMPLE_LIMIT = tonumber(os.getenv("WRAM_WATCH_SAMPLE_LIMIT")) or 8
local WRAM_WATCH_START = os.getenv("WRAM_WATCH_START")
local WRAM_WATCH_END = os.getenv("WRAM_WATCH_END")
local last_coarse_hash = nil
local last_page_hash = {}
local last_page_initialized = false
local vram_read_error_logged = false
local vram_diff_initialized = false

if not MEM.vram then
    VRAM_DIFF_ENABLED = false
end

local wram_dump_start = parse_int(WRAM_DUMP_START, 0x2000)
local wram_dump_abs_start = parse_int(WRAM_DUMP_ABS_START, nil)
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
local wram_watch_start = parse_int(WRAM_WATCH_START, wram_base)
local wram_watch_end = parse_int(WRAM_WATCH_END, wram_watch_start + WRAM_DUMP_SIZE - 1)
local last_wram_dump_frame = nil
local wram_write_counts = {snes = 0, sa1 = 0}
local wram_write_samples = {snes = {}, sa1 = {}}

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

local function read_vram_byte(addr)
    local value = emu.read(addr, MEM.vram)
    if value == nil then
        if not vram_read_error_logged then
            log("ERROR: VRAM read returned nil; disabling VRAM diff")
            vram_read_error_logged = true
        end
        VRAM_DIFF_ENABLED = false
        return 0
    end
    return value
end

local function hash_stride(start_addr, size, step)
    local h = 2166136261
    local prime = 16777619
    for i = 0, size - 1, step do
        local b = read_vram_byte(start_addr + i)
        if not VRAM_DIFF_ENABLED then
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
        if not VRAM_DIFF_ENABLED then
            return h
        end
        h = (bxor(h, b) * prime) % 4294967296
    end
    return h
end

local function record_wram_write(label, address)
    wram_write_counts[label] = wram_write_counts[label] + 1
    local samples = wram_write_samples[label]
    if #samples < WRAM_WATCH_SAMPLE_LIMIT then
        samples[#samples + 1] = string.format("0x%04X", address)
    end
end

local function dump_wram_region(frame_id)
    if not WRAM_DUMP_ON_VRAM_DIFF then
        return
    end
    if not wram_mem_type then
        log("WARNING: WRAM memType unavailable; skipping WRAM dump")
        return
    end
    if last_wram_dump_frame == frame_id then
        return
    end
    last_wram_dump_frame = frame_id

    local path = OUTPUT_DIR
        .. string.format("wram_dump_%s_start_%06X_size_%04X.bin", tostring(frame_id), wram_base, WRAM_DUMP_SIZE)
    local f = io.open(path, "wb")
    if not f then
        log("ERROR: failed to open WRAM dump: " .. path)
        return
    end

    local chunk = {}
    local chunk_len = 0
    local chunk_size = 4096
    for i = 0, WRAM_DUMP_SIZE - 1 do
        local value = emu.read(wram_base + i, wram_mem_type)
        if value == nil then
            value = 0
        end
        chunk_len = chunk_len + 1
        chunk[chunk_len] = string.char(value & 0xFF)
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

    log(string.format(
        "WRAM dump: frame=%s mode=%s base=0x%06X size=0x%04X path=%s",
        tostring(frame_id),
        wram_address_mode,
        wram_base,
        WRAM_DUMP_SIZE,
        path
    ))
end

local function init_page_hashes()
    if not VRAM_DIFF_ENABLED then
        return
    end
    for base = 0, VRAM_SIZE - 1, VRAM_PAGE_SIZE do
        last_page_hash[base] = hash_block(base, VRAM_PAGE_SIZE)
    end
    last_page_initialized = true
end

local function refine_changed_pages(frame_id)
    local changed = 0
    local logged = 0
    for base = 0, VRAM_SIZE - 1, VRAM_PAGE_SIZE do
        local h = hash_block(base, VRAM_PAGE_SIZE)
        local prev = last_page_hash[base]
        if prev == nil then
            last_page_hash[base] = h
        elseif h ~= prev then
            changed = changed + 1
            if logged < VRAM_PAGE_LOG_LIMIT then
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
            last_page_hash[base] = h
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

local function poll_vram_diff(frame_id)
    if not VRAM_DIFF_ENABLED then
        return
    end
    local coarse = hash_stride(0, VRAM_SIZE, VRAM_COARSE_STEP)
    if last_coarse_hash == nil then
        last_coarse_hash = coarse
        if not last_page_initialized then
            init_page_hashes()
        end
        if not vram_diff_initialized then
            vram_diff_initialized = true
            log(string.format(
                "VRAM diff baseline: frame=%s clock=%s hash=%08X",
                tostring(frame_id),
                tostring(last_master_clock),
                coarse
            ))
        end
        return
    end
    if coarse == last_coarse_hash then
        return
    end
    log(string.format(
        "VRAM diff coarse change: frame=%s clock=%s %08X->%08X",
        tostring(frame_id),
        tostring(last_master_clock),
        last_coarse_hash,
        coarse
    ))
    last_coarse_hash = coarse
    refine_changed_pages(frame_id)
    dump_wram_region(frame_id)
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
    local base = 0x4300 + (channel * 0x10)
    local dmap = read8(base + 0)
    local bbad = read8(base + 1)
    local a1t = read8(base + 2) | (read8(base + 3) << 8)
    local a1b = read8(base + 4)
    local das = read8(base + 5) | (read8(base + 6) << 8)
    local src = (a1b << 16) | a1t
    local direction = (dmap & 0x80) ~= 0 and "B->A" or "A->B"
    local mode = dmap & 0x07
    local note = ""
    if bbad == 0x18 or bbad == 0x19 then
        note = string.format(
            " VRAM word=0x%04X vmain_inc=%d mode=%d",
            vram_word_addr,
            vram_inc_value,
            vram_inc_mode
        )
    end
    log(string.format(
        "DMA enable=0x%02X ch=%d dir=%s mode=%d bbad=0x%02X src=0x%06X size=0x%04X%s",
        value, channel, direction, mode, bbad, src, das, note
    ))
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
    log(string.format(
        "SA1 DMA (%s): ctrl=0x%02X enabled=%s char_conv=%s auto=%s src_dev=%d dest_dev=%d src=0x%06X dest=0x%06X size=0x%04X",
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

local function on_dma_enable(address)
    local value = read8(0x420B)
    if value == 0 then
        return
    end
    for channel = 0, 7 do
        if (value & (1 << channel)) ~= 0 then
            log_dma_channel(channel, value)
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

local function on_vram_addr_write(address)
    refresh_vram_addr()
    log(string.format("VRAM addr write: word=0x%04X (byte=0x%04X)", vram_word_addr, vram_word_addr * 2))
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
    if not WRAM_WATCH_WRITES then
        return
    end
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
        end
        wram_write_counts[label] = 0
        wram_write_samples[label] = {}
    end
    emit("snes")
    emit("sa1")
end

local frame_count = 0
local state_loaded = PRELOADED_STATE
local frame_event_registered = false

local function on_end_frame()
    frame_count = frame_count + 1

    if not SKIP_INPUT and SAVESTATE_PATH and DOOR_UP_START and DOOR_UP_END then
        if frame_count >= DOOR_UP_START and frame_count <= DOOR_UP_END then
            set_input({up = true}, 0)
        else
            set_input({}, 0)
        end
    end

    poll_vram_diff(last_state_frame or frame_count)

    local sa1_irq = read8(0x2301)
    if sa1_irq ~= last_sa1_dma_irq then
        log(string.format("SA1 DMA IRQ flag: 0x%02X", sa1_irq))
        last_sa1_dma_irq = sa1_irq
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

    log_wram_writes(frame_count)

    if HEARTBEAT_EVERY > 0 and (frame_count % HEARTBEAT_EVERY) == 0 then
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
add_memory_callback_compat(on_vmain_write, emu.callbackType.write, 0x2115, 0x2115, cpu_type, MEM.cpu)
add_memory_callback_compat(on_vram_addr_write, emu.callbackType.write, 0x2116, 0x2117, cpu_type, MEM.cpu)
add_memory_callback_compat(on_vram_data_write, emu.callbackType.write, 0x2118, 0x2119, cpu_type, MEM.cpu)
add_memory_callback_compat(on_sa1_ctrl_write, emu.callbackType.write, 0x2230, 0x2230, cpu_type, MEM.cpu)
add_memory_callback_compat(on_sa1_dma_reg_write, emu.callbackType.write, 0x2231, 0x2239, cpu_type, MEM.cpu)
add_memory_callback_compat(on_sa1_bitmap_write, emu.callbackType.write, 0x2240, 0x224F, cpu_type, MEM.cpu)

local sa1_cpu_type = emu.cpuType and (emu.cpuType.sa1 or emu.cpuType.SA1 or emu.cpuType.sa1Cpu or emu.cpuType.sa1cpu) or nil
if WRAM_WATCH_WRITES then
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

if MEM.vram then
    add_memory_callback_compat(function(address, value)
        vram_mem_write_count = vram_mem_write_count + 1
        if LOG_VRAM_MEMORY_WRITES and vram_mem_write_logged < MAX_VRAM_WRITE_LOG then
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
    "WRAM config: dump=%s watch=%s memType=%s mode=%s base=0x%06X size=0x%04X range=0x%06X-0x%06X",
    tostring(WRAM_DUMP_ON_VRAM_DIFF),
    tostring(WRAM_WATCH_WRITES),
    tostring(wram_mem_type),
    wram_address_mode,
    wram_base,
    WRAM_DUMP_SIZE,
    wram_watch_start,
    wram_watch_end
))
log("DMA probe start: frame_event=" .. tostring(FRAME_EVENT) .. " max_frames=" .. tostring(MAX_FRAMES))

if SAVESTATE_PATH and not PRELOADED_STATE then
    load_savestate_if_needed()
else
    register_frame_event()
end
