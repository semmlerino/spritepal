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
  - Rule: always pass **both** `cpuType` and `memType` for add/remove in this build.

**Callback type strings** may be accepted but are unreliable. Use enums/integers and verify by
counting fires.

**Callback address width:** memory callbacks receive `relAddr.Address` (often 16-bit). Do not
assume a 24-bit CPU address is passed to Lua.
When full 24-bit context is required, dump `emu.getState()` keys and look for CPU register
fields (PC/PBR/DBR). If they are missing, treat callback addresses as relative and report
the source region (e.g., WRAM/BW-RAM) instead of absolute ROM offsets.

## Address Spaces & ROM Trace Semantics
Be explicit about which address space is being logged:
- **CPU bus address**: SNES 24-bit address (bank:offset) in CPU space.
- **ROM file offset**: index into the `.sfc/.smc` file after header handling.
- **memType address**: the address as exposed by a specific `emu.memType` callback.

PRG-ROM read callbacks log the **memType address** for `snesPrgRom`. This may or may not
match a ROM file offset depending on build and mapping. If `emu.getMemorySize(snesPrgRom)`
fails, the probe uses a `0xFFFFFF` fallback range, which makes the address space even less
certain. Treat ROM-trace addresses as **seeds** that must be validated.

Required validation before adding offsets:
- Attempt HAL decompression at candidate offsets.
- Reject candidates that fail decompression or produce implausible 4bpp tiles.

Mechanical rule when `prg_size` is known:
- If `seed >= prg_size`, it **cannot** be a linear file offset → treat it as mapped/bus
  space and convert (LoROM/HiROM/SA-1).
- If `seed < prg_size`, it **might** be linear → still validate via decompression.

If `rom_trace_log.txt` does **not** include `prg_size`/`prg_end` on the "ROM trace armed"
lines, your probe script is outdated. Treat all seeds as ambiguous and run the candidate
validator with `--auto-map` before indexing.

If you need CPU bus addresses, use `emu.convertAddress()` to map between memTypes and CPU
space (and document which direction you used).

## VRAM Read Semantics (Current Build)
- `emu.read(addr, emu.memType.snesVideoRam)` is **byte-addressed**.
- `emu.readWord(addr, emu.memType.snesVideoRam)` expects a **byte address**.

This is an API behavior, not SNES hardware behavior (see `00_STABLE_SNES_FACTS.md`).

## emu.convertAddress() (Current Build)
Converts addresses between memory types and CPU address space.

**Signature:** `emu.convertAddress(address, memType?, cpuType?)`

**Parameters:**
- `address` (int, required): Address to convert
- `memType` (MemoryType, optional): Source memory type (defaults to current CPU's default)
- `cpuType` (CpuType, optional): Target CPU type for relative→absolute (defaults to current)

**Returns:** Table `{ address = int, memType = int }` or `nil` if conversion fails.

**Behavior:**
- If `memType` is **relative** (e.g., CPU address space): returns absolute address in ROM/RAM
- If `memType` is **absolute** (e.g., `snesPrgRom`): returns relative CPU bus address

**Example:**
```lua
-- Convert PRG-ROM offset to CPU address
local result = emu.convertAddress(0x1B0000, emu.memType.snesPrgRom, emu.cpuType.snes)
if result then
    print(string.format("CPU address: $%06X", result.address))
end

-- Convert CPU address to ROM offset
local result = emu.convertAddress(0xDB0000, emu.memType.snesMemory, emu.cpuType.snes)
if result and result.memType == emu.memType.snesPrgRom then
    print(string.format("ROM offset: 0x%06X", result.address))
end
```

**Caveats:**
- Returns `nil` for unmapped addresses or failed conversions
- SA-1 bank remapping affects results; probe dynamically if banks change

## Source of Truth
- The canonical Lua API implementation lives in `Mesen2/Core/Debugger/LuaApi.cpp`.
- The old `docs/LuaApi.cpp` snapshot was removed; do not reference it.

## memType / cpuType Names
Memory type names in this build (no aliases exist):
- VRAM: `snesVideoRam`
- OAM: `snesSpriteRam`
- CGRAM: `snesCgRam`

Main CPU key is `emu.cpuType.snes` (no `cpu` key on this build).
SA-1 memory exists in the enum (`sa1`/`sa1Memory` in some builds); if unavailable, probe
via S-CPU I/O registers ($2230-$224F) instead.

## Testrunner CLI (Current Build)
- `--testrunner` expects **exactly one non-.lua file** (the ROM). Any `.lua` files are scripts.
- No `--loadstate` switch. Load savestates via `emu.loadSavestate()` from an **exec callback**.
- `emu.loadSavestate()` does **not** trigger `stateLoaded` in this build.
- If exec-based frame counting stalls, set `FRAME_EVENT=endFrame` in the probe. End-frame callbacks
  continued to fire after load in the latest run and were required for VRAM diff output.

## Runbook (Movie + ROM Trace Flow)
Minimal end-to-end flow to get a validated seed:

1) Run Mesen2 with ROM + Lua and then send the `.mmo` (two-step launch):
```
set OUTPUT_DIR=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\mesen2_exchange\movie_probe_run
set WRAM_WATCH_WRITES=1
set WRAM_WATCH_CAPTURE_THRESHOLD=200
set ROM_TRACE_ON_WRAM_WRITE=1
set ROM_TRACE_MAX_READS=500
set ROM_TRACE_MAX_FRAMES=2
set ROM_TRACE_PC_SAMPLES=8
call run_movie_probe.bat --no-pause
```

2) Summarize ROM trace buckets and pick a seed:
```
python3 scripts/summarize_rom_trace.py mesen2_exchange/movie_probe_run --bucket-size 0x1000 --top 5
```

3) Validate the seed against likely mappings (HAL decompression + tile heuristics):
```
python3 scripts/validate_seed_candidate.py roms/Kirby\ Super\ Star\ (USA).sfc \
  --seed 0xFCC455 --auto-map --tiles 256 --png out.png
```

If the validator returns no plausible candidates, treat the seed as ambiguous and try the
alternate seed (run-start) from the summarizer output.

## Movie Playback (Non-Testrunner)
`--testrunner` cannot load `.mmo` files (only one non-.lua file is allowed). Movie playback
only starts when a ROM is already running: `LoadRomHelper.LoadFile()` plays `.mmo` files
**only if** `EmuApi.IsRunning()` is true, and ROM loading is async.

**Use a two-step launch** so the `.mmo` is sent after the ROM is running. This relies on
Mesen2's SingleInstance IPC (default on).

Example (PowerShell, Windows paths):
```
powershell.exe -NoProfile -Command "
  & 'C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\tools\mesen2\Mesen2.exe' --noaudio --novideo --enableStdout `
    'C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\roms\Kirby Super Star (USA).sfc' `
    'C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\mesen2_integration\lua_scripts\mesen2_dma_probe.lua';
  Start-Sleep -Seconds 3;
  & 'C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\tools\mesen2\Mesen2.exe' `
    'C:\Users\gabri\Documents\Mesen2\Movies\Kirby Super Star (USA).mmo'
"
```

Batch helper: `run_movie_probe.bat`.

When running heavy Lua probes, playback can be very slow. Prefer **time-based** gating
(`CAPTURE_START_SECONDS`, `CAPTURE_MIN_INTERVAL_SECONDS`) and longer wall-clock runs
instead of relying on frame counts.

## Command Line Switches (Non-Testrunner)
From `Mesen2/UI/Utilities/CommandLineHelper.cs`:
- `--noaudio`, `--novideo`, `--noinput`
- `--enableStdout`
- `--recordMovie=filename.mmo` (record only; there is **no** `--playMovie` switch)
- `--loadLastSession`, `--fullscreen`, `--doNotSaveSettings`

If you need to verify movie playback visually, **do not** use `--novideo`
(`run_movie_probe.bat` leaves it off by default).

## DMA/SA-1 Probe Script
Use `mesen2_integration/lua_scripts/mesen2_dma_probe.lua` to log:
- S-CPU DMA/HDMA activity (source/dest and VRAM address)
- SA-1 DMA control and character conversion register writes
- VRAM diff + WRAM staging dumps when `VRAM_DIFF=1` (default) and `WRAM_DUMP_ON_VRAM_DIFF=1`

Useful env toggles:
- `WRAM_DUMP_START` (default `0x0000`) and `WRAM_DUMP_SIZE` (default `0x20000`)
- `WRAM_DUMP_ABS_START` to force absolute addressing (uses `snesMemory`)
- `WRAM_DUMP_PREV=1` to save both current and previous-frame dumps on VRAM diff (default on)
- `WRAM_WATCH_WRITES=1` for per-frame WRAM write summaries (range defaults to dump window)
- `WRAM_WATCH_PC_SAMPLES` to log a few CPU register snapshots per frame on WRAM writes
- `ROM_TRACE_ON_WRAM_WRITE=1` to log PRG-ROM reads triggered by WRAM write bursts
- `ROM_TRACE_MAX_READS` to cap logged ROM reads per burst (default 200)
- `ROM_TRACE_MAX_FRAMES` to cap how many frames a ROM trace stays active (default 1)
- `ROM_TRACE_PC_SAMPLES` to include a few PC/K/DBR samples in ROM read logs (default 8)
- `SKIP_VISIBILITY_FILTER=1` to disable the sprite visibility filter entirely
- `VISIBLE_Y_EXCLUDE_START` / `VISIBLE_Y_EXCLUDE_END` to adjust the 224–239 overscan exclusion
- `VISIBLE_X_MIN` / `VISIBLE_X_MAX` to adjust the horizontal visibility cutoffs (default -64..256)
- `CAPTURE_ON_WRAM_WRITE=1` to emit captures on WRAM write activity
- `WRAM_WATCH_CAPTURE_THRESHOLD` to require a minimum write count before capture
- `DMA_DUMP_ON_VRAM=1` to dump VRAM DMA source streams (A->B to $2118/$2119)
- `DMA_DUMP_MAX` (default `20`) to cap DMA source dumps
- `CAPTURE_ON_VRAM_DIFF=1` / `CAPTURE_ON_VRAM_DMA=1` to emit `test_capture_*.json` on triggers
- `CAPTURE_DUMP_VRAM=1` and `CAPTURE_SCREENSHOT=1` to include VRAM dumps / PNGs
- `CAPTURE_DUMP_WRAM=1` to include WRAM snapshots alongside captures (uses dump window)
- `CAPTURE_START_SECONDS` / `CAPTURE_START_FRAME` to delay captures past the intro
- `CAPTURE_MIN_INTERVAL_SECONDS` / `CAPTURE_MIN_INTERVAL` to spread out captures
- `VRAM_DIFF_START_SECONDS`, `WRAM_DUMP_START_SECONDS`, `DMA_DUMP_START_SECONDS` to skip early churn

ROM read traces are written to `rom_trace_log.txt` in `OUTPUT_DIR`.

### rom_trace_log.txt Format
The ROM trace log uses a line-oriented format. Key line types:

```
# Header (emitted when ROM tracing starts)
ROM trace armed: frame=1234 label=snes prg_size=0x400000 prg_end=0x3FFFFF max_reads=500 max_frames=2

# Read entries (one per ROM read during active trace)
ROM read (snes): frame=1234 addr=0x1B0456 value=0x9A remaining=499 PC=0x8940 K=0x00 DBR=0x7E

# Trace end marker
ROM trace complete: frame=1234 start=1234 label=snes
```

**Field definitions:**
- `frame`: Emulator frame counter when event occurred
- `prg_size`: Size of PRG-ROM in bytes (use to validate seeds)
- `prg_end`: Last valid PRG-ROM address (`prg_size - 1`)
- `addr`: ROM memType address of the read (may require mapping conversion)
- `PC/K/DBR`: Optional CPU state snapshot (when `ROM_TRACE_PC_SAMPLES > 0`)

**Important:** If `prg_size`/`prg_end` are missing from the header, the probe script is
outdated. Treat all `addr` values as ambiguous and use `--auto-map` validation.

## WSL Interop Notes
- Use Windows paths in Lua file I/O (`C:\...`).
- If launching from WSL, pass env vars via `WSLENV` or `cmd.exe /C "set ..."`.

## Support Scripts

### mesen2_preflight_probe.lua
Location: `mesen2_integration/lua_scripts/mesen2_preflight_probe.lua`

Validates Mesen 2 API availability before running capture scripts. Run this when:
- Upgrading Mesen 2 builds
- Debugging callback registration failures
- Verifying headless mode compatibility

**What it checks:**
- Enumerates `emu.memType`, `emu.callbackType`, `emu.eventType`, `emu.cpuType`
- Dumps `emu.getState()` keys (frame, scanline, clock fields)
- Registers exec callback and verifies firing within time threshold
- Reports clock rate, frame count, master clock timing

**Environment variables:**
- `OUTPUT_PATH`: Output file (default: `mesen2_exchange/mesen2_preflight_probe.txt`)
- `PROBE_SECONDS`: Duration in seconds (default: 1)
- `TARGET_FRAMES`: Frame count threshold (default: 60)
- `MAX_EXEC_TICKS`: Exec callback limit (default: 500000)

**Output:**
```
=== Mesen2 Preflight Probe ===
Lua version: Lua 5.4
== memType ==
memType.snesVideoRam = 1
...
=== Probe Results ===
reason=target_frames
exec_count=12345
endFrame_count=60
```

### analyze_capture_quality.py
Location: `scripts/analyze_capture_quality.py`

Validates capture integrity before expanding the tile database.

```bash
python3 scripts/analyze_capture_quality.py <capture_dir_or_file> \
  [--database mesen2_exchange/tile_hash_database.json] \
  [--rom roms/game.sfc]
```

**Reports:**
- Unique-byte distribution (identifies low-info vs high-entropy tiles)
- Odd-byte sanity check (detects VRAM read path issues)
- Hash-hit and scoring stats (when database provided)

### summarize_rom_trace.py
Location: `scripts/summarize_rom_trace.py`

Analyzes `rom_trace_log.txt` to identify candidate ROM offsets by bucketing read addresses.

```bash
python3 scripts/summarize_rom_trace.py <run_dir> \
  [--bucket-size 0x1000] \
  [--top 5]
```

**Bucketing algorithm:**
- Groups ROM read addresses into fixed-size buckets (default 0x1000 = 4KB)
- Ranks buckets by read count
- Reports: bucket start/end, read count, first-read address, run start (lowest address in bucket)
- Use `first` or `min` from the top bucket as seed candidates for decompression validation

**Output fields:**
- `start`/`end`: Bucket address range
- `count`: Number of reads in bucket
- `first`: First chronological read address (likely pointer/table entry)
- `min`/`max`: Address extremes within bucket

### validate_seed_candidate.py
Location: `scripts/validate_seed_candidate.py`

Tests whether a ROM offset contains valid HAL-compressed sprite data.

```bash
python3 scripts/validate_seed_candidate.py <rom.sfc> \
  --seed 0xFCC455 \
  [--auto-map] \
  [--tiles 256] \
  [--png out.png]
```

**Validation criteria (defaults):**
- Decompression succeeds without error
- Output length is multiple of 32 bytes (4bpp tile size)
- At least 32 tiles extracted
- At least 20% of tiles are high-information (> 2 unique byte values)

**Flags:**
- `--auto-map`: Try LoROM/HiROM/SA-1 address conversions if direct offset fails
- `--tiles N`: Request N tiles of output (may truncate or pad)
- `--png FILE`: Render decompressed tiles to image for visual inspection
