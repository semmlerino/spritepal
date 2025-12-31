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

local LOG_VRAM_MEMORY_WRITES = os.getenv("LOG_VRAM_MEMORY_WRITES") == "1"
local MAX_VRAM_WRITE_LOG = tonumber(os.getenv("MAX_VRAM_WRITE_LOG")) or 20
local VRAM_DIFF_ENABLED = os.getenv("VRAM_DIFF") ~= "0"
local VRAM_SIZE = 0x10000
local VRAM_COARSE_STEP = tonumber(os.getenv("VRAM_COARSE_STEP")) or 16
local VRAM_PAGE_SIZE = tonumber(os.getenv("VRAM_PAGE_SIZE")) or 0x0400
local VRAM_PAGE_LOG_LIMIT = tonumber(os.getenv("VRAM_PAGE_LOG_LIMIT")) or 12
local HEARTBEAT_EVERY = tonumber(os.getenv("HEARTBEAT_EVERY")) or 0
local WRAM_DUMP_ON_VRAM_DIFF = os.getenv("WRAM_DUMP_ON_VRAM_DIFF") ~= "0"
local WRAM_DUMP_START = os.getenv("WRAM_DUMP_START") or "0x0000"
local WRAM_DUMP_ABS_START = os.getenv("WRAM_DUMP_ABS_START")
local WRAM_DUMP_SIZE = tonumber(os.getenv("WRAM_DUMP_SIZE")) or 0x20000
local WRAM_DUMP_PREV = os.getenv("WRAM_DUMP_PREV") ~= "0"
local WRAM_WATCH_WRITES = os.getenv("WRAM_WATCH_WRITES") ~= "0"
local WRAM_WATCH_SAMPLE_LIMIT = tonumber(os.getenv("WRAM_WATCH_SAMPLE_LIMIT")) or 8
local WRAM_WATCH_START = os.getenv("WRAM_WATCH_START")
local WRAM_WATCH_END = os.getenv("WRAM_WATCH_END")
local WRAM_WATCH_CAPTURE_THRESHOLD = tonumber(os.getenv("WRAM_WATCH_CAPTURE_THRESHOLD")) or 0
local WRAM_WATCH_PC_SAMPLES = tonumber(os.getenv("WRAM_WATCH_PC_SAMPLES")) or 0
local ROM_TRACE_ON_WRAM_WRITE = os.getenv("ROM_TRACE_ON_WRAM_WRITE") == "1"
local ROM_TRACE_MAX_READS = tonumber(os.getenv("ROM_TRACE_MAX_READS")) or 200
local ROM_TRACE_MAX_FRAMES = tonumber(os.getenv("ROM_TRACE_MAX_FRAMES")) or 1
local ROM_TRACE_PC_SAMPLES = tonumber(os.getenv("ROM_TRACE_PC_SAMPLES")) or 8
local SKIP_VISIBILITY_FILTER = os.getenv("SKIP_VISIBILITY_FILTER") == "1"
local VISIBLE_Y_EXCLUDE_START = parse_int(os.getenv("VISIBLE_Y_EXCLUDE_START"), 224)
local VISIBLE_Y_EXCLUDE_END = parse_int(os.getenv("VISIBLE_Y_EXCLUDE_END"), 240)
local VISIBLE_X_MIN = parse_int(os.getenv("VISIBLE_X_MIN"), -64)
local VISIBLE_X_MAX = parse_int(os.getenv("VISIBLE_X_MAX"), 256)
local DMA_DUMP_ON_VRAM = os.getenv("DMA_DUMP_ON_VRAM") ~= "0"
local DMA_DUMP_MAX = tonumber(os.getenv("DMA_DUMP_MAX")) or 20
local DMA_DUMP_MIN_SIZE = tonumber(os.getenv("DMA_DUMP_MIN_SIZE")) or 1
local CAPTURE_ON_VRAM_DIFF = os.getenv("CAPTURE_ON_VRAM_DIFF") ~= "0"
local CAPTURE_ON_VRAM_DMA = os.getenv("CAPTURE_ON_VRAM_DMA") ~= "0"
local CAPTURE_ON_WRAM_WRITE = os.getenv("CAPTURE_ON_WRAM_WRITE") ~= "0"
local CAPTURE_SCREENSHOT = os.getenv("CAPTURE_SCREENSHOT") ~= "0"
local CAPTURE_DUMP_VRAM = os.getenv("CAPTURE_DUMP_VRAM") ~= "0"
local CAPTURE_DUMP_WRAM = os.getenv("CAPTURE_DUMP_WRAM") ~= "0"
local CAPTURE_MAX = tonumber(os.getenv("CAPTURE_MAX")) or 20
local CAPTURE_TAG_PREFIX = os.getenv("CAPTURE_TAG_PREFIX") or "probe"
local CAPTURE_START_FRAME = tonumber(os.getenv("CAPTURE_START_FRAME")) or 0
local CAPTURE_START_SECONDS = tonumber(os.getenv("CAPTURE_START_SECONDS")) or 0
local CAPTURE_MIN_INTERVAL = tonumber(os.getenv("CAPTURE_MIN_INTERVAL")) or 0
local CAPTURE_MIN_INTERVAL_SECONDS = tonumber(os.getenv("CAPTURE_MIN_INTERVAL_SECONDS")) or 0
local VRAM_DIFF_START_FRAME = tonumber(os.getenv("VRAM_DIFF_START_FRAME")) or 0
local VRAM_DIFF_START_SECONDS = tonumber(os.getenv("VRAM_DIFF_START_SECONDS")) or 0
local WRAM_DUMP_START_FRAME = tonumber(os.getenv("WRAM_DUMP_START_FRAME")) or CAPTURE_START_FRAME
local WRAM_DUMP_START_SECONDS = tonumber(os.getenv("WRAM_DUMP_START_SECONDS")) or CAPTURE_START_SECONDS
local DMA_DUMP_START_FRAME = tonumber(os.getenv("DMA_DUMP_START_FRAME")) or CAPTURE_START_FRAME
local DMA_DUMP_START_SECONDS = tonumber(os.getenv("DMA_DUMP_START_SECONDS")) or CAPTURE_START_SECONDS
local last_coarse_hash = nil
local last_page_hash = {}
local last_page_initialized = false
local vram_read_error_logged = false
local vram_diff_initialized = false
local vram_diff_armed = false
local script_start_time = os.time()
local last_capture_frame = nil
local last_capture_time = nil
local ROM_TRACE_LOG_FILE = OUTPUT_DIR .. "rom_trace_log.txt"

if not MEM.vram then
    VRAM_DIFF_ENABLED = false
end

local wram_dump_start = parse_int(WRAM_DUMP_START, 0x0000)
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
local prev_wram_snapshot = nil
local prev_wram_frame = nil
local wram_write_counts = {snes = 0, sa1 = 0}
local wram_write_samples = {snes = {}, sa1 = {}}
local wram_write_cpu_samples = {snes = 0, sa1 = 0}
local dma_read_mem = MEM.cpu_debug or MEM.cpu
local dma_dump_count = 0
local pending_dma_capture = false
local pending_dma_count = 0
local capture_count = 0
local frame_count = 0
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
    if VRAM_DIFF_START_FRAME > 0 and frame_id < VRAM_DIFF_START_FRAME then
        return false
    end
    if VRAM_DIFF_START_SECONDS > 0 and (os.time() - script_start_time) < VRAM_DIFF_START_SECONDS then
        return false
    end
    return true
end

local function capture_allowed(frame_id)
    if CAPTURE_START_FRAME > 0 and frame_id < CAPTURE_START_FRAME then
        return false
    end
    if CAPTURE_START_SECONDS > 0 and (os.time() - script_start_time) < CAPTURE_START_SECONDS then
        return false
    end
    if CAPTURE_MIN_INTERVAL > 0 and last_capture_frame and (frame_id - last_capture_frame) < CAPTURE_MIN_INTERVAL then
        return false
    end
    if CAPTURE_MIN_INTERVAL_SECONDS > 0 and last_capture_time and
        (os.time() - last_capture_time) < CAPTURE_MIN_INTERVAL_SECONDS then
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
        dbr_val = dbr_val or 0
    }
end

local function arm_rom_trace(label)
    if not ROM_TRACE_ON_WRAM_WRITE or rom_trace_active then
        return
    end
    local threshold = WRAM_WATCH_CAPTURE_THRESHOLD
    if threshold < 1 then
        threshold = 1
    end
    if (wram_write_counts[label] or 0) < threshold then
        return
    end
    local frame_id = last_state_frame or frame_count
    local max_frames = ROM_TRACE_MAX_FRAMES
    if max_frames < 1 then
        max_frames = 1
    end
    rom_trace_active = true
    rom_trace_remaining = ROM_TRACE_MAX_READS
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
        ROM_TRACE_MAX_READS,
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
    if WRAM_DUMP_START_FRAME > 0 and frame_id < WRAM_DUMP_START_FRAME then
        return false
    end
    if WRAM_DUMP_START_SECONDS > 0 and (os.time() - script_start_time) < WRAM_DUMP_START_SECONDS then
        return false
    end
    return true
end

local function dma_dump_allowed(frame_id)
    if DMA_DUMP_START_FRAME > 0 and frame_id < DMA_DUMP_START_FRAME then
        return false
    end
    if DMA_DUMP_START_SECONDS > 0 and (os.time() - script_start_time) < DMA_DUMP_START_SECONDS then
        return false
    end
    return true
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
        samples[#samples + 1] = string.format("0x%06X", address)
    end
    if WRAM_WATCH_PC_SAMPLES > 0 and wram_write_cpu_samples[label] < WRAM_WATCH_PC_SAMPLES then
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
    if ROM_TRACE_ON_WRAM_WRITE then
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
    for i = 0, WRAM_DUMP_SIZE - 1 do
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
    if not WRAM_DUMP_ON_VRAM_DIFF and not force then
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
        .. string.format("wram_dump_%s_%s_start_%06X_size_%05X.bin", tostring(frame_id), tag, wram_base, WRAM_DUMP_SIZE)
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
        WRAM_DUMP_SIZE,
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
    vram_read_mode = nil
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

local function parse_oam_entry(index)
    local base = index * 4
    local x_low = emu.read(base + 0, MEM.oam)
    local y = emu.read(base + 1, MEM.oam)
    local tile = emu.read(base + 2, MEM.oam)
    local attr = emu.read(base + 3, MEM.oam)

    local hi_byte = emu.read(0x200 + math.floor(index / 4), MEM.oam)
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
    if SKIP_VISIBILITY_FILTER then
        return true
    end
    if entry.y >= VISIBLE_Y_EXCLUDE_START and entry.y < VISIBLE_Y_EXCLUDE_END then
        return false
    end
    if entry.x <= VISIBLE_X_MIN or entry.x >= VISIBLE_X_MAX then
        return false
    end
    return true
end

local function read_vram_word(byte_addr)
    -- Try emu.readWord first (returns 16-bit word)
    if emu.readWord then
        local ok, word = pcall(emu.readWord, byte_addr, MEM.vram)
        if ok and word then
            return word
        end
    end
    -- Fallback: read two consecutive bytes and combine them
    local lo = emu.read(byte_addr, MEM.vram) or 0
    local hi = emu.read(byte_addr + 1, MEM.vram) or 0
    return lo | (hi << 8)
end

local function read_vram_tile_word(vram_addr)
    local tile_data = {}
    local high_nonzero = false

    for i = 0, 15 do
        local word = read_vram_word(vram_addr + (i * 2))
        tile_data[i * 2 + 1] = word & 0xFF
        tile_data[i * 2 + 2] = (word >> 8) & 0xFF
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

local function capture_sprites()
    if not MEM.oam or not MEM.cgram or not MEM.vram then
        log("ERROR: OAM/CGRAM/VRAM memTypes missing; cannot capture sprites")
        return nil, {}, 0, {}, 0, 0
    end

    local obsel = get_obsel()
    local entries = {}
    local visible_count = 0
    local tile_count = 0
    local odd_nonzero_tiles = 0

    for i = 0, 127 do
        local entry = parse_oam_entry(i)
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
    if capture_count >= CAPTURE_MAX then
        return
    end
    if not capture_allowed(frame_id) then
        return
    end
    capture_count = capture_count + 1

    local obsel, entries, visible_count, palettes, tile_count, odd_nonzero_tiles = capture_sprites()
    if not obsel then
        return
    end
    if tile_count > 0 and odd_nonzero_tiles == 0 then
        log("ERROR: VRAM tiles have zero odd-byte data; aborting capture (bad VRAM reads).")
        emu.stop(2)
        return
    end

    local suffix = "_" .. CAPTURE_TAG_PREFIX .. "_" .. tag .. "_" .. tostring(frame_id)
    log("Capturing sprite snapshot " .. suffix)

    if CAPTURE_SCREENSHOT and emu.takeScreenshot then
        local png_data = emu.takeScreenshot()
        if png_data then
            local sf = io.open(OUTPUT_DIR .. "test_frame" .. suffix .. ".png", "wb")
            if sf then
                sf:write(png_data)
                sf:close()
            end
        end
    end

    if CAPTURE_DUMP_VRAM then
        dump_vram(OUTPUT_DIR .. "test_vram_dump" .. suffix .. ".bin")
    end
    if CAPTURE_DUMP_WRAM and wram_mem_type then
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

    last_capture_frame = frame_id
    last_capture_time = os.time()
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

local function poll_vram_diff(frame_id, current_snapshot)
    if not VRAM_DIFF_ENABLED then
        return
    end
    local coarse = hash_stride(0, VRAM_SIZE, VRAM_COARSE_STEP)
    if not vram_diff_allowed(frame_id) then
        last_coarse_hash = coarse
        return
    end
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
    if not vram_diff_armed then
        if not last_page_initialized then
            init_page_hashes()
        end
        last_coarse_hash = coarse
        vram_diff_armed = true
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
    if WRAM_DUMP_ON_VRAM_DIFF and wram_dump_allowed(frame_id) then
        if WRAM_DUMP_PREV and prev_wram_snapshot ~= nil then
            write_wram_snapshot(frame_id, "prev", prev_wram_snapshot, prev_wram_frame)
        end
        if current_snapshot ~= nil then
            write_wram_snapshot(frame_id, "curr", current_snapshot, frame_id)
        else
            local snapshot = capture_wram_snapshot()
            write_wram_snapshot(frame_id, "curr", snapshot, frame_id)
        end
        last_wram_dump_frame = frame_id
    end
    if CAPTURE_ON_VRAM_DIFF and capture_allowed(frame_id) then
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
    local base = 0x4300 + (channel * 0x10)
    local dmap = read8(base + 0)
    local bbad = read8(base + 1)
    local a1t = read8(base + 2) | (read8(base + 3) << 8)
    local a1b = read8(base + 4)
    local das_raw = read8(base + 5) | (read8(base + 6) << 8)
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
        "DMA enable=0x%02X ch=%d dir=%s mode=%d bbad=0x%02X src=0x%06X size=%s%s",
        value, channel, direction, mode, bbad, src, size_text, note
    ))

    local frame_id = last_state_frame or frame_count
    if DMA_DUMP_ON_VRAM and direction == "A->B" and (bbad == 0x18 or bbad == 0x19) then
        if not dma_dump_allowed(frame_id) then
            return
        end
        if dma_dump_count < DMA_DUMP_MAX and das >= DMA_DUMP_MIN_SIZE then
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
                local value = emu.read((src + i) & 0xFFFFFF, dma_read_mem)
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
            log("DMA dump saved: " .. path)
        end
        if CAPTURE_ON_VRAM_DMA and capture_allowed(frame_id) then
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
            if CAPTURE_ON_WRAM_WRITE and count >= WRAM_WATCH_CAPTURE_THRESHOLD then
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

local function on_end_frame()
    frame_count = frame_count + 1

    if not SKIP_INPUT and SAVESTATE_PATH and DOOR_UP_START and DOOR_UP_END then
        if frame_count >= DOOR_UP_START and frame_count <= DOOR_UP_END then
            set_input({up = true}, 0)
        else
            set_input({}, 0)
        end
    end

    local current_snapshot = nil
    if WRAM_DUMP_ON_VRAM_DIFF and WRAM_DUMP_PREV and wram_dump_allowed(last_state_frame or frame_count) then
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

    if pending_dma_capture and CAPTURE_ON_VRAM_DMA then
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
    if wram_triggered and CAPTURE_ON_WRAM_WRITE and capture_allowed(frame_count) then
        write_capture_snapshot("wramwrite", frame_count)
    end

    if HEARTBEAT_EVERY > 0 and (frame_count % HEARTBEAT_EVERY) == 0 then
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
add_memory_callback_compat(on_vmain_write, emu.callbackType.write, 0x2115, 0x2115, cpu_type, MEM.cpu)
add_memory_callback_compat(on_vram_addr_write, emu.callbackType.write, 0x2116, 0x2117, cpu_type, MEM.cpu)
add_memory_callback_compat(on_vram_data_write, emu.callbackType.write, 0x2118, 0x2119, cpu_type, MEM.cpu)
add_memory_callback_compat(on_sa1_ctrl_write, emu.callbackType.write, 0x2230, 0x2230, cpu_type, MEM.cpu)
add_memory_callback_compat(on_sa1_dma_reg_write, emu.callbackType.write, 0x2231, 0x2239, cpu_type, MEM.cpu)
add_memory_callback_compat(on_sa1_bitmap_write, emu.callbackType.write, 0x2240, 0x224F, cpu_type, MEM.cpu)

local sa1_cpu_type = emu.cpuType and (emu.cpuType.sa1 or emu.cpuType.SA1 or emu.cpuType.sa1Cpu or emu.cpuType.sa1cpu) or nil
if ROM_TRACE_ON_WRAM_WRITE then
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
                if ROM_TRACE_PC_SAMPLES > 0 and rom_trace_pc_samples < ROM_TRACE_PC_SAMPLES then
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
    "WRAM config: dump=%s prev=%s watch=%s memType=%s mode=%s base=0x%06X size=0x%05X range=0x%06X-0x%06X",
    tostring(WRAM_DUMP_ON_VRAM_DIFF),
    tostring(WRAM_DUMP_PREV),
    tostring(WRAM_WATCH_WRITES),
    tostring(wram_mem_type),
    wram_address_mode,
    wram_base,
    WRAM_DUMP_SIZE,
    wram_watch_start,
    wram_watch_end
))
log(string.format(
    "WRAM env: WATCH_START=%s WATCH_END=%s",
    tostring(WRAM_WATCH_START),
    tostring(WRAM_WATCH_END)
))
log(string.format(
    "Visibility filter: enabled=%s y_exclude=%d-%d x_range=%d..%d",
    tostring(not SKIP_VISIBILITY_FILTER),
    VISIBLE_Y_EXCLUDE_START,
    VISIBLE_Y_EXCLUDE_END,
    VISIBLE_X_MIN,
    VISIBLE_X_MAX
))
local prg_size_text = rom_trace_prg_size and string.format("0x%X", rom_trace_prg_size) or "nil"
local prg_end_text = rom_trace_prg_end and string.format("0x%06X", rom_trace_prg_end) or "nil"
log(string.format(
    "ROM trace: enabled=%s memType=%s prg_size=%s prg_end=%s max_reads=%d max_frames=%d pc_samples=%d",
    tostring(ROM_TRACE_ON_WRAM_WRITE),
    tostring(MEM.prg),
    prg_size_text,
    prg_end_text,
    ROM_TRACE_MAX_READS,
    ROM_TRACE_MAX_FRAMES,
    ROM_TRACE_PC_SAMPLES
))
log("DMA probe start: frame_event=" .. tostring(FRAME_EVENT) .. " max_frames=" .. tostring(MAX_FRAMES))

if SAVESTATE_PATH and not PRELOADED_STATE then
    load_savestate_if_needed()
else
    register_frame_event()
end
