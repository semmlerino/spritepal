-- Callback signature probe for Mesen2 testrunner mode
local OUTPUT_PATH = "C:\\CustomScripts\\KirbyMax\\workshop\\exhal-master\\"
    .. "spritepal\\mesen2_exchange\\callback_signature_probe.txt"

local function write_line(line)
    local f = io.open(OUTPUT_PATH, "a")
    if f then
        f:write(line .. "\n")
        f:close()
    end
end

write_line("=== Callback Signature Probe ===")
write_line("Lua version: " .. tostring(_VERSION))

if emu.memType then
    for k, v in pairs(emu.memType) do
        write_line(string.format("memType.%s = %s", k, tostring(v)))
    end
end

if emu.callbackType then
    for k, v in pairs(emu.callbackType) do
        write_line(string.format("callbackType.%s = %s", k, tostring(v)))
    end
end

if emu.cpuType then
    for k, v in pairs(emu.cpuType) do
        write_line(string.format("cpuType.%s = %s", k, tostring(v)))
    end
end

local counts = {}
local first_addr = {}
local max_addr = {}
local ids = {}

local function make_cb(label)
    return function(addr, value)
        counts[label] = (counts[label] or 0) + 1
        if not first_addr[label] then
            first_addr[label] = addr
            max_addr[label] = addr
        elseif addr > (max_addr[label] or 0) then
            max_addr[label] = addr
        end
    end
end

local function try_add(label, cb_type, cpu_type, mem_type)
    local ok, id
    if cpu_type ~= nil and mem_type ~= nil then
        ok, id = pcall(emu.addMemoryCallback, make_cb(label), cb_type, 0x8000, 0xFFFF, cpu_type, mem_type)
    elseif cpu_type ~= nil then
        ok, id = pcall(emu.addMemoryCallback, make_cb(label), cb_type, 0x8000, 0xFFFF, cpu_type)
    else
        ok, id = pcall(emu.addMemoryCallback, make_cb(label), cb_type, 0x8000, 0xFFFF)
    end
    ids[#ids + 1] = {label = label, id = ok and id or nil}
    write_line(string.format("register %s (cpuType=%s memType=%s) -> %s",
        label, tostring(cpu_type ~= nil), tostring(mem_type ~= nil), tostring(ok)))
end

local cpu_default = emu.cpuType and (emu.cpuType.cpu or emu.cpuType.snes) or nil
local mem_default = emu.memType and (emu.memType.snesMemory or emu.memType.snesDebug) or nil

try_add("enum_exec_cpu", emu.callbackType.exec, cpu_default, nil)
try_add("enum_exec_cpu_mem", emu.callbackType.exec, cpu_default, mem_default)
try_add("enum_exec_mem_only", emu.callbackType.exec, nil, mem_default)
try_add("enum_exec_nocpu", emu.callbackType.exec, nil, nil)
try_add("string_exec_cpu", "exec", cpu_default, nil)
try_add("string_exec_nocpu", "exec", nil, nil)

local frames = 0
emu.addEventCallback(function()
    frames = frames + 1
    if frames == 60 then
        write_line("--- Results after 60 frames ---")
        for _, entry in ipairs(ids) do
            local label = entry.label
            write_line(string.format("%s: fired=%s first_addr=%s max_addr=%s", label, tostring(counts[label] or 0),
                tostring(first_addr[label] or "nil"), tostring(max_addr[label] or "nil")))
            if entry.id then
                pcall(emu.removeMemoryCallback, entry.id)
            end
        end
        emu.stop()
    end
end, emu.eventType.endFrame)
