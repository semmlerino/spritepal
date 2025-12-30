# 01 Build-Specific Contract (Mesen2 Lua)

This document is **build-specific**. Re-run probes and re-validate on every Mesen2 build
change (or OS/core change).

## Tested On
- Mesen2 2.1.1+137ae7ce3bf3f539d007e2c4ef3cb3b6c97672a1 (Windows build, `tools/mesen2/Mesen2.exe`)
- OS: Windows via WSL2 interop
- Core: SNES (SA-1, Kirby Super Star)

## Mandatory Probe (Fail-Fast)
Run the probe at script start and abort if any of these fail:
- Enumerate `emu.memType`, `emu.callbackType`, `emu.eventType`, `emu.cpuType`.
- Dump `emu.getState()` keys; confirm presence of frame/clock fields you rely on.
- Register a callback and **prove it fires** within a known window.
- Verify VRAM reads produce non-zero bytes in both even/odd positions.

Canonical probe script:
- `mesen2_integration/lua_scripts/mesen2_preflight_probe.lua`

## Lua API Signatures (Current Build)
From `Mesen2/Core/Debugger/LuaApi.cpp`:
- `emu.addMemoryCallback(callback, cb_type, start, end, cpuType?, memType?)`
- `emu.removeMemoryCallback(id, cb_type, start, end, cpuType?, memType?)`
  - Current build uses `ForceParamCount(6)`. **ID-only removal is not supported** here.

**Callback type strings** may be accepted but are unreliable. Use enums/integers and verify by
counting fires.

**Callback address width:** memory callbacks receive `relAddr.Address` (often 16-bit). Do not
assume a 24-bit CPU address is passed to Lua.
When full 24-bit context is required, dump `emu.getState()` keys and look for CPU register
fields (PC/PBR/DBR). If they are missing, treat callback addresses as relative and report
the source region (e.g., WRAM/BW-RAM) instead of absolute ROM offsets.

## VRAM Read Semantics (Current Build)
- `emu.read(addr, emu.memType.snesVideoRam)` is **byte-addressed**.
- `emu.readWord(addr, emu.memType.snesVideoRam)` expects a **byte address**.

This is an API behavior, not SNES hardware behavior (see `00_STABLE_SNES_FACTS.md`).

## Source of Truth
- The canonical Lua API implementation lives in `Mesen2/Core/Debugger/LuaApi.cpp`.
- The old `docs/LuaApi.cpp` snapshot was removed; do not reference it.

## memType / cpuType Aliases
Observed aliases in this build:
- VRAM: `snesVram` or `snesVideoRam`
- OAM: `snesOam` or `snesSpriteRam`
- CGRAM: `snesCgram` or `snesCgRam`

Main CPU key is `emu.cpuType.snes` (no `cpu` key on this build).
SA-1 memory exists in the enum (`sa1`/`sa1Memory` in some builds); if unavailable, probe
via S-CPU I/O registers ($2230-$224F) instead.

## Testrunner CLI (Current Build)
- `--testrunner` expects **exactly one non-.lua file** (the ROM). Any `.lua` files are scripts.
- No `--loadstate` switch. Load savestates via `emu.loadSavestate()` from an **exec callback**.
- `emu.loadSavestate()` does **not** trigger `stateLoaded` in this build.
- If exec-based frame counting stalls, set `FRAME_EVENT=endFrame` in the probe. End-frame callbacks
  continued to fire after load in the latest run and were required for VRAM diff output.

## DMA/SA-1 Probe Script
Use `mesen2_integration/lua_scripts/mesen2_dma_probe.lua` to log:
- S-CPU DMA/HDMA activity (source/dest and VRAM address)
- SA-1 DMA control and character conversion register writes
- VRAM diff + WRAM staging dumps when `VRAM_DIFF=1` (default) and `WRAM_DUMP_ON_VRAM_DIFF=1`

Useful env toggles:
- `WRAM_DUMP_START` (default `0x2000`) and `WRAM_DUMP_SIZE` (default `0x8000`)
- `WRAM_DUMP_ABS_START` to force absolute addressing (uses `snesMemory`)
- `WRAM_WATCH_WRITES=1` for per-frame WRAM write summaries (range defaults to dump window)

## WSL Interop Notes
- Use Windows paths in Lua file I/O (`C:\...`).
- If launching from WSL, pass env vars via `WSLENV` or `cmd.exe /C "set ..."`.
