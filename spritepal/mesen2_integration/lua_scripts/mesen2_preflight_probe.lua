-- Mesen2 preflight probe (headless-safe)
local OUTPUT_PATH = os.getenv("OUTPUT_PATH")
    or "C:\\CustomScripts\\KirbyMax\\workshop\\exhal-master\\spritepal\\mesen2_exchange\\mesen2_preflight_probe.txt"
local PROBE_SECONDS = tonumber(os.getenv("PROBE_SECONDS")) or 1
local TARGET_FRAMES = tonumber(os.getenv("TARGET_FRAMES")) or 60
local MAX_EXEC_TICKS = tonumber(os.getenv("MAX_EXEC_TICKS")) or 500000

local function write_line(line)
    local f = io.open(OUTPUT_PATH, "a")
    if f then
        f:write(line .. "\n")
        f:close()
    end
end

local function reset_output()
    local f = io.open(OUTPUT_PATH, "w")
    if f then
        f:write("")
        f:close()
    end
end

local function dump_enum(name, tbl)
    write_line("== " .. name .. " ==")
    if not tbl then
        write_line("nil")
        return
    end
    for k, v in pairs(tbl) do
        write_line(string.format("%s.%s = %s", name, tostring(k), tostring(v)))
    end
end

reset_output()
write_line("=== Mesen2 Preflight Probe ===")
write_line("Lua version: " .. tostring(_VERSION))

dump_enum("memType", emu.memType)
dump_enum("callbackType", emu.callbackType)
dump_enum("eventType", emu.eventType)
dump_enum("cpuType", emu.cpuType)

local function dump_state_keys(state)
    local keys = {}
    for k, _ in pairs(state) do
        if type(k) == "string" then
            table.insert(keys, k)
        end
    end
    table.sort(keys)
    write_line(string.format("getState keys (count=%d)", #keys))
    for _, k in ipairs(keys) do
        if k:find("frame") or k:find("scanline") or k:find("clock") or k == "consoleType" or k == "region" then
            write_line("  " .. k .. " = " .. tostring(state[k]))
        end
    end
end

local initial_state = emu.getState and emu.getState() or nil
if initial_state then
    dump_state_keys(initial_state)
end

local exec_count = 0
local frame_count = 0
local start_master = nil
local last_master = nil
local clock_rate = initial_state and initial_state.clockRate or nil
local target_master_delta = clock_rate and (clock_rate * PROBE_SECONDS) or nil
local done = false

local function finalize(reason)
    if done then
        return
    end
    done = true
    write_line("=== Probe Results ===")
    write_line("reason=" .. tostring(reason))
    write_line("exec_count=" .. tostring(exec_count))
    write_line("endFrame_count=" .. tostring(frame_count))
    if initial_state then
        write_line("clockRate=" .. tostring(initial_state.clockRate))
        write_line("frameCount=" .. tostring(initial_state.frameCount))
        write_line("masterClock=" .. tostring(initial_state.masterClock))
    end
    emu.stop(0)
end

local function exec_tick()
    exec_count = exec_count + 1
    local state = emu.getState and emu.getState() or nil
    if state and state.masterClock then
        if start_master == nil then
            start_master = state.masterClock
        end
        last_master = state.masterClock
        if target_master_delta and (state.masterClock - start_master) >= target_master_delta then
            finalize("masterClock_threshold")
            return
        end
    end
    if exec_count >= MAX_EXEC_TICKS then
        finalize("max_exec_ticks")
    end
end

local cpu_type = emu.cpuType and (emu.cpuType.cpu or emu.cpuType.snes) or nil
local ok = pcall(emu.addMemoryCallback, exec_tick, emu.callbackType.exec, 0x0000, 0xFFFF, cpu_type)
if not ok then
    write_line("ERROR: addMemoryCallback(exec) failed")
    finalize("exec_callback_failed")
end

if emu.eventType and emu.eventType.endFrame then
    emu.addEventCallback(function()
        frame_count = frame_count + 1
        if frame_count >= TARGET_FRAMES then
            finalize("target_frames")
        end
    end, emu.eventType.endFrame)
end
