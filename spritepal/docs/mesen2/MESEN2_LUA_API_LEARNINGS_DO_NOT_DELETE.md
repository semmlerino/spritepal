# Mesen 2 Lua API Learnings - DO NOT DELETE

## Tested On
- Mesen2 2.1.1+137ae7ce3bf3f539d007e2c4ef3cb3b6c97672a1 (Windows build, `tools/mesen2/Mesen2.exe`)
- OS: Windows via WSL2 interop
- Core: SNES (SA-1, Kirby Super Star)

## Critical Discovery Date: 2025-08-12

This document captures hard-won knowledge about Mesen 2's Lua API discovered through systematic debugging. The official documentation was incomplete/misleading, requiring empirical testing to discover the actual API.

## Executive Summary

**Key Insight**: Mesen 2's Lua API uses SNES-specific enum names, not generic ones. Documentation may show generic names, but the actual implementation requires platform-specific names.

## Compatibility Contract (Probe-First, Fail-Fast)

These scripts are **build-sensitive**. Treat every new Mesen2 build as unknown until it passes a probe.

**Required probes (run at script start, fail fast if missing):**
- Enumerate `emu.memType`, `emu.callbackType`, `emu.eventType`, `emu.cpuType`.
- Dump `emu.getState()` keys (at least keys containing `frame`, `scanline`, `clock`).
- Verify a memory callback **actually fires** (see "Success criteria" below).
- Verify VRAM reads are byte-addressed (read two consecutive bytes and ensure they differ; `emu.readWord` should accept a byte address).

**Ready-made probe script:** `mesen2_integration/lua_scripts/mesen2_preflight_probe.lua`
Outputs to `mesen2_exchange/mesen2_preflight_probe.txt` by default.

**Build signature capture (log to file per run):**
- `emu.getState().consoleType`, `.region`, `.clockRate`, `.frameCount`, `.masterClock` if present.
- Mesen2 executable version/hash (manual if API not available).

**Fail-fast rules (do not continue):**
- No callbacks fire in 1–2 seconds of runtime.
- `snesVideoRam` reads do not behave as byte-addressed (or hashes are unstable across frames).
- `emu.getState()` lacks `frameCount` or `masterClock` and you rely on frame-based timing.

## Mesen 2 Lua API Reference

### Memory Types (`emu.memType`)

**Observed values (Mesen2 2.1.1+137ae7c, Windows, SNES core).** Treat numeric values as examples,
not truth—enumerate per build.

| Purpose | Enum | Observed Value | Usage |
|---------|------|----------------|-------|
| CPU Memory | `emu.memType.snesMemory` | 0 | Main CPU address space |
| Program ROM | `emu.memType.snesPrgRom` | 14 | ROM data |
| Work RAM | `emu.memType.snesWorkRam` | 15 | System RAM |
| Video RAM | `emu.memType.snesVideoRam` | 17 | VRAM for tiles/tilemaps |
| Sprite RAM | `emu.memType.snesSpriteRam` | 18 | OAM (Object Attribute Memory) |
| Palette RAM | `emu.memType.snesCgRam` | 19 | Color palette data |
| Save RAM | `emu.memType.snesSaveRam` | 16 | Battery-backed SRAM |
| SA-1 Memory | `emu.memType.sa1Memory` | unknown | SA-1 coprocessor memory (SA-1 games) |
| SNES Registers | `emu.memType.snesRegister` | unknown | PPU/CPU registers |

**Alias note**: Some Mesen2 builds expose `snesOam`, `snesVram`, and `snesCgram` instead of
`snesSpriteRam`, `snesVideoRam`, and `snesCgRam`. Observed on Mesen2 2.1.1+137ae7c (Windows).
Use a fallback (`emu.memType.snesOam or emu.memType.snesSpriteRam`) to stay compatible.

**Finding unknown enum values:** Run this at script start to discover all memType values in your build:

```lua
-- Dump all memType values to file (run once per Mesen2 build)
local f = io.open("C:\\path\\to\\memtype_dump.txt", "w")
f:write("emu.memType enum values:\n")
for k, v in pairs(emu.memType) do
    f:write(string.format("  %s = %d\n", k, v))
end
f:close()
emu.log("memType dump written")
```

Store results per build—values may differ between versions.

### CPU Types (`emu.cpuType`)

Used by `emu.addMemoryCallback` to choose which processor to observe (main CPU vs SA-1, etc.).
Enumerate at runtime to confirm availability:

```lua
for k, v in pairs(emu.cpuType or {}) do
    emu.log(string.format("cpuType.%s = %s", k, tostring(v)))
end
```

Observed on Mesen2 2.1.1+137ae7c (SNES core): the main CPU key is `snes` (not `cpu`).
Use a fallback like `emu.cpuType.cpu or emu.cpuType.snes`.

### Lua Version / Bit Ops (Observed)

Observed on this build: Lua 5.4 with 5.3-style bitwise operators (`&`, `|`, `<<`, `>>`).
If your build lacks these, use the `bit` library (e.g., `bit.band`, `bit.rshift`) or
define a small compatibility shim and stick to one style.

### Event Types (`emu.eventType`)

**Observed values (Mesen2 2.1.1+137ae7c, Windows, SNES core).** Enumerate per build.

| Event | Enum | Value |
|-------|------|-------|
| NMI | `emu.eventType.nmi` | 0 |
| IRQ | `emu.eventType.irq` | 1 |
| Start Frame | `emu.eventType.startFrame` | 2 |
| End Frame | `emu.eventType.endFrame` | 3 |
| Reset | `emu.eventType.reset` | 4 |
| Script Ended | `emu.eventType.scriptEnded` | 5 |
| Input Polled | `emu.eventType.inputPolled` | 6 |
| State Loaded | `emu.eventType.stateLoaded` | 7 |
| State Saved | `emu.eventType.stateSaved` | 8 |
| Code Break | `emu.eventType.codeBreak` | 9 |

### Callback Types (`emu.callbackType`)

⚠️ **CRITICAL: Values are build-dependent.** Observed on Mesen2 2.1.1+137ae7c (Windows, SNES core):

| Type | Enum | Observed Value | Common Mistake |
|------|------|----------------|----------------|
| Read | `emu.callbackType.read` | 0 | ✅ Correct |
| Write | `emu.callbackType.write` | **1** | ❌ Often assumed to be 2 |
| Exec | `emu.callbackType.exec` | 2 | ❌ Often assumed to be 0 |

**What works (observed on this build):**
```lua
-- CORRECT - These work:
emu.addMemoryCallback(callback, emu.callbackType.write, 0x420B, 0x420B)  -- ✅ Best
emu.addMemoryCallback(callback, 1, 0x420B, 0x420B)  -- ✅ Works (write = 1)

emu.addMemoryCallback(callback, 2, 0x420B, 0x420B)  -- ❌ Wrong value (2 is exec!)
```

**Discovery:** String values like `"write"` may be accepted without error in this build, but we did not
observe them firing reliably. Treat string callback types as **unsupported** unless a probe shows
they behave identically to the enum/integer for your build.

#### Callback Signature Probe (Observed)

Probe script: `mesen2_integration/lua_scripts/callback_signature_probe.lua`

- Lua 5.4
- `emu.addMemoryCallback(..., cb_type, start, end)` and the 5-arg form with `cpuType`
  both registered successfully and fired with identical counts for exec callbacks.
- Passing `memType` as a 6th argument did not change exec callback behavior in our probe, but the
  core expects it and validates the enum; pass it when you want explicit memory-type routing.
- `callbackType.exec` + string `"exec"` **did fire**, but only at address `$FFFE` with far
  fewer events, suggesting a signature/type mismatch rather than a valid exec hook.
- Observed `address` values for `cpuType.snes` exec callbacks were **16-bit** (e.g., `$8004`
  .. `$D6AC`), not full 24-bit CPU addresses. Do not assume bank bits are present.
- `emu.cpuType` keys in this build include `snes` for the main CPU (no `cpu` key).

**Success criteria for callback registration (required):**
- Callback fires > 0 times within a known window (e.g., 60 frames).
- Log counts and address min/max; reject registrations that only fire at `$FFFE` or never.
- Treat any signature that returns an ID but never fires as **failure** (do not proceed).

### Memory Callback Signatures (Observed)

Observed on Mesen2 2.1.1+137ae7c (Windows, SNES core), from `Mesen2/Core/Debugger/LuaApi.cpp`:
- Lua signature is `emu.addMemoryCallback(callback, cb_type, start, end, cpuType?, memType?)`
  (end defaults to start; cpuType/memType default to `_context->GetDefault*()`).
- `cpuType` is 5th, `memType` is 6th. If you want to pass only memType, use `nil` for cpuType.
- `memType` controls whether callbacks use CPU or PPU memory paths and how address matching is done.

**Recommendation:** use a compat helper that tries both forms and logs what worked.

```lua
local function add_memory_callback_compat(callback, cb_type, start_addr, end_addr, cpu_type, mem_type)
    if cpu_type ~= nil and mem_type ~= nil then
        local ok, id = pcall(emu.addMemoryCallback, callback, cb_type, start_addr, end_addr, cpu_type, mem_type)
        if ok then return id, "callback, type, start, end, cpuType, memType" end
    end
    if cpu_type ~= nil then
        local ok, id = pcall(emu.addMemoryCallback, callback, cb_type, start_addr, end_addr, cpu_type)
        if ok then return id, "callback, type, start, end, cpuType" end
    end
    local ok, id = pcall(emu.addMemoryCallback, callback, cb_type, start_addr, end_addr)
    if ok then return id, "callback, type, start, end" end
    return nil, "failed"
end

-- Usage:
-- local cpu_type = emu.cpuType and (emu.cpuType.cpu or emu.cpuType.snes) or nil
-- local mem_type = emu.memType and (emu.memType.snesMemory or emu.memType.snesDebug) or nil
-- local id, sig = add_memory_callback_compat(cb, emu.callbackType.exec, 0x8000, 0xFFFF, cpu_type, mem_type)
-- emu.log("addMemoryCallback via " .. sig)
```

## Working Code Patterns

### Memory Callbacks
```lua
-- CORRECT - Register a write callback
local cpu_type = emu.cpuType and (emu.cpuType.cpu or emu.cpuType.snes) or nil
local mem_type = emu.memType and (emu.memType.snesMemory or emu.memType.snesDebug) or nil
local callback_id, signature = add_memory_callback_compat(
    function(address, value)
        emu.log(string.format("Write: $%04X = $%02X", address, value))
    end,
    emu.callbackType.write,  -- Use enum (value 1) - NOT string "write"!
    0x420B,   -- start address
    0x420B,   -- end address
    cpu_type,
    mem_type
)
emu.log("Callback signature: " .. tostring(signature))

-- Alternative using integer (but enum is clearer):
local callback_id, signature = add_memory_callback_compat(
    function(address, value)
        -- callback code
    end,
    1,        -- 1 = write (NOT 2!)
    0x420B,
    0x420B,
    cpu_type,
    mem_type
)

-- Remove when done (compat helper below)
remove_memory_callback_compat(callback_id, emu.callbackType.write, 0x420B, 0x420B, cpu_type, mem_type)
```

**Callbacks use both cpuType and memType:**

`emu.addMemoryCallback` selects a CPU (main CPU, SA-1, SPC, etc.) via `emu.cpuType`.
`memType` (optional 6th arg in current builds) controls which memory domain is observed and
how address matching is performed. Do not pass memType values as the 5th argument.

**Callback address width (observed):** `ScriptingContext::InternalCallMemoryCallback` always
pushes `relAddr.Address` into Lua. For CPU memory this is a 16-bit address. Even when a
non-relative `memType` is used for matching, the address passed to Lua is still the relative
address (not an absolute ROM offset). Do not assume bank bits are present.

**Hard rule:** the callback address is **not** guaranteed to match the registration range
format. If you register a 24-bit range, the callback may still pass a 16-bit `relAddr.Address`.
Always treat the callback address as **relative** and reconstruct context separately.

### Callback Removal (Compat Helper)
```lua
-- Current build requires full signature (ForceParamCount(6)).
-- Keep ID-only removal as an opportunistic fallback for unknown builds.
local function remove_memory_callback_compat(callback_id, cb_type, start_addr, end_addr, cpu_type, mem_type)
    if pcall(emu.removeMemoryCallback, callback_id) then
        return true, "id"
    end
    if cb_type ~= nil then
        if pcall(emu.removeMemoryCallback, callback_id, cb_type, start_addr or 0, end_addr or 0) then
            return true, "id+type+range"
        end
        if cpu_type ~= nil and mem_type ~= nil then
            if pcall(emu.removeMemoryCallback, callback_id, cb_type, start_addr or 0, end_addr or 0, cpu_type, mem_type) then
                return true, "id+type+range+cpuType+memType"
            end
        end
        if cpu_type ~= nil then
            if pcall(emu.removeMemoryCallback, callback_id, cb_type, start_addr or 0, end_addr or 0, cpu_type) then
                return true, "id+type+range+cpuType"
            end
        end
    end
    return false, "failed"
end

-- Usage:
-- local cpu_type = emu.cpuType and (emu.cpuType.cpu or emu.cpuType.snes) or nil
-- local mem_type = emu.memType and (emu.memType.snesMemory or emu.memType.snesDebug) or nil
-- local ok, sig = remove_memory_callback_compat(id, emu.callbackType.exec, 0x8000, 0xFFFF, cpu_type, mem_type)
-- emu.log("removeMemoryCallback via " .. sig)
```

**From `Mesen2/Core/Debugger/LuaApi.cpp` (current build):** `removeMemoryCallback` uses `ForceParamCount(6)` and
`checkminparams(3)`, so **id-only** calls will error here. Pass at least `id`, `cb_type`,
and `start_addr` (plus end/cpuType/memType when possible).

### Event Callbacks
```lua
-- CORRECT - Register frame callback
local frame_id = emu.addEventCallback(
    function()
        -- Called at end of frame
    end,
    emu.eventType.endFrame  -- or use integer 3
)

-- Remove when done
emu.removeEventCallback(frame_id)
```

### Savestate Loading (Exec Callback Only - Build Dependent)
Observed on Mesen2 2.1.1+137ae7c (Windows, SNES core): `emu.loadSavestate()` only succeeds
from exec callbacks. Event callbacks can fail silently in this build.

```lua
-- Read savestate file
local f = io.open(SAVESTATE_PATH, "rb")
local state_bytes = f:read("*a")
f:close()

-- Load from exec callback
local load_ref
load_ref = emu.addMemoryCallback(function(address, value)
    if not state_loaded then
        state_loaded = true
        emu.loadSavestate(state_bytes)
        remove_memory_callback_compat(load_ref, emu.callbackType.exec, 0x8000, 0xFFFF)
    end
end, emu.callbackType.exec, 0x8000, 0xFFFF)
```

#### Headless Testrunner Quirk (Observed)
Observed on Mesen2 2.1.1+137ae7c (Windows, SNES core): after loading a savestate from an
exec callback in headless testrunner mode, `emu.eventType.endFrame` callbacks may stop
firing (no frame events, no captures). Re-registering the endFrame callback after load
did not fix this in our tests. Workaround: drive capture logic from exec callbacks (or
try other event types such as `emu.eventType.nmi` if available) and add a MAX_FRAMES
escape so scripts do not run forever.

**Additional observation:** after `emu.loadSavestate()` in testrunner, `emu.getState()` may
report a fixed `frameCount`/`ppu.frameCount` while `masterClock` keeps incrementing. This
breaks frame detection based on `frameCount`. Consider a fallback that derives frames from
`masterClock` or manually counts frames in a reliable event path.

#### Deterministic Savestate + Testrunner Strategy (Decision Tree)

**Goal:** avoid hangs and detect stalled frame events reliably.

1) **Attempt normal event path**
- Register `endFrame` (or `nmi`) before loading state.
- After `emu.loadSavestate()`, wait for N events (e.g., 10).
- If event count advances → OK, continue.

2) **If events stall, switch to exec-based ticking**
- Use an exec callback on main CPU.
- Derive a tick when `emu.getState()["ppu.frameCount"]` changes.
- If `frameCount` is frozen but `masterClock` changes, fall back to a **masterClock-based tick**:
  - `ticks += (masterClock - lastMasterClock)`.
  - Trigger a "frame" when ticks exceed a threshold (`clockRate / 60` for NTSC; probe rate).
  - This is only for **timing and capture**; do not treat it as real video frames.

3) **Bail-out conditions (required)**
- No exec callbacks fire within 1–2 seconds.
- `masterClock` does not advance for M ticks.
- You exceed `MAX_FRAMES` or `MAX_MASTER_CLOCK_DELTA`.

When bailing, `emu.log()` a clear reason and `emu.stop(1)` so headless runs don’t hang.

#### TestRunner CLI (From Source)
- `--testrunner` uses `CommandLineHelper` to parse arguments. Any `.lua` files are treated
  as scripts, and there must be **exactly one non-`.lua` file** (the ROM). Order does not
  matter.
- There is **no** `--loadstate` CLI switch. Load savestates via Lua (`emu.loadSavestate`)
  from an exec callback on the **main CPU** (`checksavestateconditions()` in `LuaApi.cpp`).
- Lua `emu.loadSavestate()` uses `SaveStateManager::LoadState(istream)` and **does not**
  call `ProcessEvent(StateLoaded)`. Do not expect `emu.eventType.stateLoaded` to fire for
  Lua-loaded savestates.

### Memory Reads
```lua
-- CORRECT - Read from different memory types
local cpu_value = emu.read(0x420B, emu.memType.snesMemory)     -- CPU memory
local oam_byte = emu.read(0, emu.memType.snesSpriteRam)        -- OAM
local vram_byte = emu.read(0x0000, emu.memType.snesVideoRam)   -- VRAM (byte-addressed)
local palette = emu.read(0, emu.memType.snesCgRam)             -- CGRAM

-- Read 16-bit value
local word = emu.readWord(0x2116, emu.memType.snesMemory)
```
**CGRAM/OAM note (observed):** `emu.read(..., snesCgRam)` and `emu.read(..., snesSpriteRam)`
return bytes and appear byte-addressed. For a CGRAM color, read two bytes and combine
`lo | (hi << 8)`. Verify on your build.

**Disable side effects (implementation detail from LuaApi.cpp):** `emu.read`/`emu.write` treat
the type parameter as `memType | 0x100` to disable side effects. For CPU memory,
`emu.memType.snesDebug` appears to map to `snesMemory` with the no-side-effects flag set.
Treat this as build-specific; confirm with a probe on new versions. Prefer explicit OR
(`emu.memType.snesMemory | 0x100`) if you need this behavior.

### OAM (Sprite) Access
```lua
-- CORRECT - Read OAM/sprite data
local oam_data = {}
for i = 0, 543 do  -- 544 bytes total (512 sprite + 32 high table)
    oam_data[i] = emu.read(i, emu.memType.snesSpriteRam)
end
```

### VRAM Access

**⚠️ CRITICAL: snesVideoRam is BYTE-ADDRESSED in Mesen2 Lua.**

The address parameter for `snesVideoRam` is a **byte offset**:
- `emu.read(0, snesVideoRam)` → byte at VRAM byte offset 0
- `emu.read(1, snesVideoRam)` → byte at VRAM byte offset 1
- `emu.readWord(0x6A00, snesVideoRam)` → 16-bit word starting at byte offset 0x6A00

```lua
-- CORRECT - Read VRAM directly (address is byte offset)
local tile_lo = emu.read(0x6A00, emu.memType.snesVideoRam)
local tile_hi = emu.read(0x6A01, emu.memType.snesVideoRam)
local tile_word = emu.readWord(0x6A00, emu.memType.snesVideoRam)

-- To read 32 bytes of tile data starting at VRAM byte address $6A00:
local byte_addr = 0x6A00
local tile_data = {}
for i = 0, 31 do
    tile_data[i + 1] = emu.read(byte_addr + i, emu.memType.snesVideoRam)
end
```

**Bug symptom:** If tile reads show every other byte missing/zero, byte-swapped words, or
repeating 2-byte patterns, double-check byte addressing and stride. A strictly sequential
`00 01 02 03 ...` pattern often indicates you're accidentally emitting a loop index or
address counter rather than reading VRAM.

### Screenshot Capture (Headless-Friendly)
```lua
-- `emu.takeScreenshot()` returns PNG bytes and works in --testrunner mode
local png_data = emu.takeScreenshot()
local file = io.open("C:\\path\\to\\frame_700.png", "wb")
file:write(png_data)
file:close()
```

### Input Simulation
```lua
emu.setInput(0, {start=true})   -- Controller 0, Start button
emu.setInput(0, {a=true})       -- A button
emu.setInput(0, {right=true})   -- D-pad right
emu.setInput(0, {})             -- Release all buttons
```

### Key Detection
```lua
local pressed = emu.isKeyPressed("F9")  -- Returns true/false
```

### Address Conversion (Build Dependent)
Observed on Mesen2 2.1.1+137ae7c (Windows, SNES core): `emu.convertAddress()` returned 0.
Re-test on newer builds.

```lua
-- Did not work in our testing:
local result = emu.convertAddress({address = 0x368000, type = emu.memType.snesMemory})
-- result.address = 0, result.type = nil
```

## Common Pitfalls and Solutions

### Pitfall 1: Using Generic Memory Types
```lua
-- WRONG
emu.read(addr, emu.memType.cpu)  -- This exists but wrong for SNES!

-- CORRECT
emu.read(addr, emu.memType.snesMemory)
```

### Pitfall 2: Wrong OAM Access Method
```lua
-- WRONG - Don't use PPU memory space
emu.read(0x2000 + i, emu.memType.ppu)

-- CORRECT - Use sprite RAM directly
emu.read(i, emu.memType.snesSpriteRam)
```

### Pitfall 3: Missing Required Parameters
```lua
-- WRONG - emu.read needs memory type
local value = emu.read(0x420B)  -- Error: too few parameters

-- CORRECT
local value = emu.read(0x420B, emu.memType.snesMemory)
```

### Pitfall 4: Wrong Callback Parameter Order
```lua
-- WRONG - Old parameter order from other emulators
emu.addMemoryCallback(0x420B, 0x420B, "write", callback)

-- CORRECT - Callback first, then type, then addresses
emu.addMemoryCallback(callback, emu.callbackType.write, 0x420B, 0x420B)

-- Some builds accept optional cpuType and memType as 5th/6th arguments
emu.addMemoryCallback(
    callback,
    emu.callbackType.write,
    0x420B,
    0x420B,
    emu.cpuType.cpu or emu.cpuType.snes,
    emu.memType.snesMemory
)
```

### Pitfall 5: SNES `emu.getState()` Shape (Map Keys, Not Nested Tables)
`emu.getState()` returns a **flat map** (Serializer::Map), not nested tables. On this build,
keys appear to be derived via `Serializer::NormalizeName` (leading `_` removed, `state.` prefix
stripped, prefixes joined with dots), but treat this as **heuristic** and **probe keys every build**.

```lua
-- WRONG - Nested tables do not exist in Map mode
local frame = emu.getState().ppu.frameCount

-- CORRECT - Use map keys (dot-separated) or top-level framecount
local state = emu.getState()
local frame = state.frameCount or state["ppu.frameCount"]

-- Safest: maintain your own frame counter if events are reliable
local frame_count = 0
emu.addEventCallback(function()
    frame_count = frame_count + 1
end, emu.eventType.endFrame)
```

## Diagnostic Script Template

When working with unknown emulator APIs, use this approach:

```lua
-- 1. Enumerate available functions
for k, v in pairs(emu) do
    if type(v) == "function" then
        emu.log("emu." .. k .. "()")
    elseif type(v) == "table" then
        emu.log("emu." .. k .. " = table")
        -- Enumerate table contents
        for k2, v2 in pairs(v) do
            emu.log("  ." .. k2 .. " = " .. tostring(v2))
        end
    end
end

-- 2. Test different parameter formats with pcall
local function safe_test(name, func)
    local success, result = pcall(func)
    emu.log(name .. ": " .. (success and "SUCCESS" or "FAILED"))
    return success, result
end

-- 3. Try different formats systematically (signature + type matrix)
local fired = {}
local function make_cb(label)
    return function()
        fired[label] = (fired[label] or 0) + 1
    end
end

local cpu_type = emu.cpuType and (emu.cpuType.cpu or emu.cpuType.snes) or nil
local probes = {
    {label = "enum+cpuType", cb_type = emu.callbackType.exec, cpu = cpu_type},
    {label = "enum", cb_type = emu.callbackType.exec, cpu = nil},
    {label = "string", cb_type = "exec", cpu = cpu_type},
}

local ids = {}
for _, p in ipairs(probes) do
    local id, sig = add_memory_callback_compat(make_cb(p.label), p.cb_type, 0x8000, 0xFFFF, p.cpu)
    ids[#ids + 1] = {id = id, label = p.label, sig = sig, cpu = p.cpu}
end

-- Report after ~1 second (60 frames)
local frames = 0
emu.addEventCallback(function()
    frames = frames + 1
    if frames == 60 then
        for _, r in ipairs(ids) do
            emu.log(string.format("%s (%s) fired=%s", r.label, r.sig, tostring(fired[r.label])))
            if r.id then
                remove_memory_callback_compat(r.id, emu.callbackType.exec, 0x8000, 0xFFFF, r.cpu)
            end
        end
        emu.stop()
    end
end, emu.eventType.endFrame)
```

## Known-Good Minimal Harness (Starter)

Use this as a baseline for new scripts so you always get a build signature and a
sanity check that callbacks fire.

```lua
-- Build signature
emu.log("Lua version: " .. tostring(_VERSION))
for k, v in pairs(emu.memType or {}) do
    emu.log(string.format("memType.%s = %s", k, tostring(v)))
end
for k, v in pairs(emu.callbackType or {}) do
    emu.log(string.format("callbackType.%s = %s", k, tostring(v)))
end

-- Minimal endFrame sanity check
local frames = 0
emu.addEventCallback(function()
    frames = frames + 1
    if frames == 5 then
        emu.log("endFrame callbacks firing ✅")
        emu.stop()
    end
end, emu.eventType.endFrame)
```

## Complete Working Example

```lua
-- Mesen 2 SNES DMA Monitor (Working)
local function monitor_dma()
    local callback_id = emu.addMemoryCallback(
        function(address, value)
            if value ~= 0 then
                emu.log(string.format("DMA triggered: $%02X", value))
                -- Read DMA parameters
                for ch = 0, 7 do
                    if (value & (1 << ch)) ~= 0 then
                        local base = 0x4300 + (ch * 0x10)
                        local dest = emu.read(base + 1, emu.memType.snesMemory)
                        emu.log(string.format("  Channel %d -> $21%02X", ch, dest))
                    end
                end
            end
        end,
        emu.callbackType.write,  -- or integer 1 (NOT 2!)
        0x420B,   -- DMA enable register
        0x420B
    )
    
    return callback_id
end

-- Start monitoring
local id = monitor_dma()
emu.log("DMA monitoring active, callback ID: " .. id)
```

## Other Platforms

Mesen 2 supports multiple systems. Each has its own memory type enums:
- NES: `emu.memType.nesMemory`, `emu.memType.nesPrgRom`, etc.
- Game Boy: `emu.memType.gameboyMemory`, `emu.memType.gbPrgRom`, etc.
- PC Engine: `emu.memType.pceMemory`, `emu.memType.pcePrgRom`, etc.

Always check which platform-specific enums are needed!

## Key Takeaways

1. **Probe-first is mandatory** - enumerate enums, getState keys, and verify callbacks fire
2. **Use platform-specific enums** - SNES uses `snes*` prefixes
3. **Callback signatures vary** - Prefer a compat wrapper; some builds require `cpuType`/`memType` 5th/6th args
4. **Enums/integers are reliable; strings are not** (treat strings as unsupported unless a probe shows identical behavior)
5. **Memory reads require type parameter** - No default
6. **Callback goes first** in parameter order
7. **Address width is not guaranteed** - current probe showed 16-bit addrs for `cpuType.snes` exec callbacks
8. **Test with pcall()** to avoid crashes during development

## PREFLIGHT CHECKLIST (Run on New Mesen2 Builds)

Because of build variance, run these checks when using a new Mesen2 version:

```lua
-- preflight_check.lua - Run once per Mesen2 build
local output = {}

-- 1. Dump memType enum values
output[#output + 1] = "=== memType enum ==="
for k, v in pairs(emu.memType) do
    output[#output + 1] = string.format("  %s = %d", k, v)
end

-- 2. Verify callbackType values (critical!)
output[#output + 1] = "\n=== callbackType values ==="
output[#output + 1] = string.format("  read = %d (expect 0)", emu.callbackType.read)
output[#output + 1] = string.format("  write = %d (expect 1)", emu.callbackType.write)
output[#output + 1] = string.format("  exec = %d (expect 2)", emu.callbackType.exec)

-- 3. Test VRAM byte-addressing
output[#output + 1] = "\n=== VRAM addressing test ==="
local byte0 = emu.read(0, emu.memType.snesVideoRam)
local byte1 = emu.read(1, emu.memType.snesVideoRam)
local word0 = emu.readWord(0, emu.memType.snesVideoRam)
output[#output + 1] = string.format("  byte[0] = $%02X, byte[1] = $%02X, word[0] = $%04X", byte0, byte1, word0)
output[#output + 1] = "  If word[0] == byte[0] + (byte[1] << 8), VRAM is byte-addressed (correct)"

-- 4. Test savestate loading context
output[#output + 1] = "\n=== Savestate test ==="
output[#output + 1] = "  Test emu.loadSavestate() from event vs exec callbacks manually"

-- Write results
local f = io.open("C:\\temp\\mesen2_preflight.txt", "w")
f:write(table.concat(output, "\n"))
f:close()
emu.log("Preflight check complete - see C:\\temp\\mesen2_preflight.txt")
emu.stop()
```

### Expected Results

| Check | Expected | If Wrong |
|-------|----------|----------|
| `callbackType.write` | 1 | Callbacks won't fire |
| `callbackType.exec` | 2 | Callbacks won't fire |
| VRAM word[0] == byte[0] + (byte[1] << 8) | True | Confirms byte-addressing |
| memType has `snesVideoRam` | Present | May need alias (`snesVram`) |

---

**Last Updated**: 2025-12-30
**Value**: Essential for any Mesen 2 Lua development

## DO NOT DELETE THIS FILE
This knowledge was hard-won through systematic debugging. Future developers will need this information as the official documentation is incomplete or misleading regarding the actual API implementation.
