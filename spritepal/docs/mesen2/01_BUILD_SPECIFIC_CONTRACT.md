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
  - Current build uses `ForceParamCount(6)`. **ID-only removal is not supported**.
  - **All 6 parameters required for removal**:
    1. `id` — callback reference returned by `addMemoryCallback`
    2. `cb_type` — `emu.callbackType.read`, `.write`, or `.exec`
    3. `start` — start address (must match registration)
    4. `end` — end address (must match registration)
    5. `cpuType` — e.g., `emu.cpuType.snes`
    6. `memType` — e.g., `emu.memType.snesWorkRam`
  - Removal fails silently if parameters don't exactly match the registration.

**Callback type enum values** (from `ScriptingContext.h:12-17`):
- `emu.callbackType.read` = 0
- `emu.callbackType.write` = 1
- `emu.callbackType.exec` = 2

String-based callback types may be accepted but are unreliable. Use enums and verify by
counting callback fires.

**Event type enum values** (from `EventType.h:3-16`):
- `emu.eventType.nmi` — NMI interrupt
- `emu.eventType.irq` — IRQ interrupt
- `emu.eventType.startFrame` — Start of frame
- `emu.eventType.endFrame` — End of frame (most reliable for captures)
- `emu.eventType.reset` — Console reset
- `emu.eventType.scriptEnded` — Script termination
- `emu.eventType.inputPolled` — Input polling occurred
- `emu.eventType.stateLoaded` — Savestate loaded (file-based only; see Testrunner CLI section)
- `emu.eventType.stateSaved` — Savestate saved
- `emu.eventType.codeBreak` — Debugger breakpoint hit

**Callback address width:** memory callbacks receive `relAddr.Address` (often 16-bit). Do not
assume a 24-bit CPU address is passed to Lua.
When full 24-bit context is required, use `emu.getState()` to access CPU registers.

### emu.getState() Key Fields (SNES)
| Field | Type | Description |
|-------|------|-------------|
| `cpu.a` | int | Accumulator (16-bit) |
| `cpu.x`, `cpu.y` | int | Index registers |
| `cpu.sp` | int | Stack pointer |
| `cpu.pc` | int | Program counter (16-bit offset) |
| `cpu.k` | int | Program bank (PBR, 8-bit) |
| `cpu.db` | int | Data bank (DBR, 8-bit) |
| `cpu.d` | int | Direct page register |
| `cpu.ps` | int | Processor status (flags) |
| `masterClock` | int | Master clock counter |
| `frameCount` | int | Frame counter |
| `scanline` | int | Current scanline |
| `cycle` | int | Current cycle within scanline |

**Full 24-bit PC**: `(cpu.k << 16) | cpu.pc`

If CPU fields are missing in your build, treat callback addresses as relative and report
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
- **CRITICAL**: `emu.readWord()` returns **big-endian** words (high byte in bits 15:8).
  To get the correct byte order for SNES tile data:
  ```lua
  local word = emu.readWord(byte_addr, emu.memType.snesVideoRam)
  local byte0 = (word >> 8) & 0xFF   -- first byte in memory (from high byte of returned word)
  local byte1 = word & 0xFF          -- second byte in memory (from low byte of returned word)
  ```
- Byte-by-byte reads (`emu.read`) may be broken in some builds (all odd bytes = 0).
  Force word mode and swap bytes as shown above.

This is an API behavior, not SNES hardware behavior (see `00_STABLE_SNES_FACTS.md`).

> ⚠️ **Build-Specific Behavior**
>
> The `emu.readWord()` big-endian behavior and any VMAIN manipulation are
> **Mesen2 API quirks**, not SNES hardware requirements. On real hardware,
> VMAIN ($2115) controls increment timing per the PPU spec
> (see [SNESdev VRAM](https://snes.nesdev.org/wiki/VRAM)).
> Do not generalize these workarounds to other emulators or hardware.

### Which Memory Types Are Affected?

The big-endian `emu.readWord()` behavior has been **verified** for:
- `snesVideoRam` (VRAM) — confirmed, byte swap required

**Not verified** (assume same behavior but test first):
- `snesSpriteRam` (OAM)
- `snesCgRam` (CGRAM)
- `snesWorkRam` (WRAM)
- `snesPrgRom` (PRG-ROM)

When reading from a new memory type, verify byte order before assuming.

### Side Effects of PPU Register Access

Reading/writing PPU registers from Lua **may affect emulator state**:
- VRAM address ($2116/$2117) changes affect subsequent reads
- VMAIN ($2115) changes affect increment behavior
- Reading $2139/$213A (VRAM data) may trigger address increment

**Best practice:** Save and restore PPU state if your script modifies registers.
This is an emulator interaction concern, not a SNES hardware limitation.

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

### Worked Examples (SA-1 / LoROM / Header Handling)

**SA-1 (Kirby Super Star) — ROM offset to CPU address:**
```
Input:  0x1B0000 (snesPrgRom)
Output: $DB0000 (snesMemory, S-CPU view)

Why: SA-1 default mapping: banks $C0-$FF → ROM $000000-$3FFFFF
     0x1B0000 is in the second 1MB (banks $D0-$DF)
     $D0 + (0x1B - 0x10) = $DB, so CPU address is $DB:0000
```

**SA-1 — CPU address to ROM offset (reverse):**
```
Input:  $DB0000 (snesMemory)
Output: 0x1B0000 (snesPrgRom)
```

**LoROM (hypothetical) — ROM offset to CPU address:**
```
Input:  0x018000 (snesPrgRom, assuming LoROM)
Output: $038000 (snesMemory)

Why: LoROM maps odd banks to ROM: bank 03 offset $8000+ → ROM ((03 & 7F) << 15) | (8000 & 7FFF)
     = 0x018000
```

**Header handling:**
- `emu.convertAddress()` operates on **headerless** ROM addresses
- If your ROM file has a 512-byte SMC header, subtract 0x200 from file offsets before conversion
- The tile database stores `rom_header_offset` in metadata for this purpose

```lua
-- Example: file offset → headerless ROM offset → CPU address
local file_offset = 0x1B0200  -- from hex editor
local header_offset = 512      -- SMC header
local rom_offset = file_offset - header_offset  -- 0x1B0000
local result = emu.convertAddress(rom_offset, emu.memType.snesPrgRom)
```

**Failure cases (returns nil):**
- Address outside ROM bounds (>= `emu.getMemorySize(snesPrgRom)`)
- Unmapped bank in current mapping configuration
- Invalid memType/cpuType combination

**Caveats:**
- Returns `nil` for unmapped addresses or failed conversions
- SA-1 bank remapping affects results; probe dynamically if banks change

## Source of Truth
- The canonical Lua API implementation lives in `Mesen2/Core/Debugger/LuaApi.cpp`.
- The old `docs/LuaApi.cpp` snapshot was removed; do not reference it.

## memType / cpuType Names

**Naming convention:** Mesen2 lowercases the first character of C++ enum names when exposing them
to Lua. For example, `SnesVideoRam` in `MemoryType.h` becomes `snesVideoRam` in Lua
(see `LuaApi.cpp:170-171`).

Memory type names in this build (no aliases exist):
- VRAM: `snesVideoRam` (from `MemoryType::SnesVideoRam`)
- OAM: `snesSpriteRam` (from `MemoryType::SnesSpriteRam`)
- CGRAM: `snesCgRam` (from `MemoryType::SnesCgRam`)
- WRAM: `snesWorkRam` (from `MemoryType::SnesWorkRam`)
- PRG-ROM: `snesPrgRom` (from `MemoryType::SnesPrgRom`)

Main CPU key is `emu.cpuType.snes` (from `CpuType::Snes`; no `cpu` alias exists).

**SA-1 types available:**
- `emu.cpuType.sa1` (from `CpuType::Sa1`)
- `emu.memType.sa1Memory` (from `MemoryType::Sa1Memory`) — SA-1's view of CPU address space
- `emu.memType.sa1InternalRam` (from `MemoryType::Sa1InternalRam`) — SA-1 IRAM (2KB)

If SA-1 types are unavailable in your build, probe via S-CPU I/O registers ($2220-$224F).

## Testrunner CLI (Current Build)
- `--testrunner` expects **exactly one non-.lua file** (the ROM). Any `.lua` files are scripts.
- No `--loadstate` switch. Load savestates via `emu.loadSavestate()` from an **exec callback**.
- `emu.loadSavestate()` does **not** trigger `stateLoaded` in this build.
  - **Source verification:** `LuaApi::LoadSavestate` (LuaApi.cpp:1057-1069) uses the stream-based
    `SaveStateManager::LoadState(istream&)` which does not call `ProcessEvent(EventType::StateLoaded)`.
    Only the file-based `LoadState(string filepath)` (SaveStateManager.cpp:235) triggers the event.
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

## Movie Recording Workflow
To create movies for reproducible sprite capture:

1. **Start recording** (GUI method):
   - Open ROM in Mesen 2
   - Navigate to game state you want to capture (specific room/level)
   - Menu: Tools → Movies → Record Movie
   - Play through the sequence
   - Menu: Tools → Movies → Stop Movie

2. **Start recording** (CLI method):
   ```
   Mesen2.exe "rom.sfc" --recordMovie="output.mmo"
   ```
   Recording stops when you close Mesen 2 or call `emu.stop()` from Lua.

3. **Movie file location**: Default `Documents\Mesen2\Movies\`

4. **Best practices for probe-friendly movies**:
   - Start from a clean state (no savestate)
   - Include 2-3 seconds of gameplay before the target sprites appear
   - Keep movies short (30-60 seconds) to reduce probe time
   - Test playback before running probes: movies can desync on different ROM revisions

**Note:** There is no `--playMovie` CLI switch. Use the two-step launch pattern
(see "Movie Playback" above) for automated playback.

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

## Lua Script Quick Reference

| Script | Purpose | Key Env Vars |
|--------|---------|--------------|
| `mesen2_preflight_probe.lua` | Validate API availability on new builds | `OUTPUT_PATH`, `PROBE_SECONDS`, `TARGET_FRAMES` |
| `mesen2_dma_probe.lua` | DMA/SA-1 diagnostics, VRAM diff, WRAM staging | `OUTPUT_DIR`, `MAX_FRAMES`, `VRAM_DIFF`, `WRAM_DUMP_*`, `ROM_TRACE_*` |
| `gameplay_capture.lua` | Auto-capture at frame 1800 (gameplay with Kirby visible) | — |
| `mesen2_sprite_capture.lua` | Manual F9 hotkey capture | — |
| `test_sprite_capture.lua` | Auto-capture at configurable frame (default 700) | `TARGET_FRAME`, `OUTPUT_DIR`, `SAVESTATE_PATH`, `CAPTURE_FRAMES` |
| `mesen2_click_extractor.lua` | F9 capture + DMA tracking for ROM offset discovery | — |
| `mesen2_sprite_finder_final.lua` | DMA monitoring for ROM offset correlation | — |
| `callback_signature_probe.lua` | Debug callback parameter signatures | — |
| `snes9x_sprite_dumper.lua` | Legacy: SNES9x compatibility (not Mesen 2) | — |

**Python support scripts** (in `scripts/`):

| Script | Purpose |
|--------|---------|
| `analyze_capture_quality.py` | Validate capture integrity (odd-byte sanity, entropy) |
| `summarize_rom_trace.py` | Bucket ROM trace addresses, identify seeds |
| `validate_seed_candidate.py` | Test if ROM offset contains valid HAL-compressed data |
| `summarize_wram_overlaps.py` | Rank frames by WRAM↔VRAM tile overlap |
| `analyze_wram_staging.py` | Compare WRAM dump to VRAM tiles, find staging ranges |
| `extract_sprite_from_capture.py` | Extract sprites from capture JSON to PNG |

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

### summarize_wram_overlaps.py
Location: `scripts/summarize_wram_overlaps.py`

Ranks capture frames by WRAM↔VRAM tile overlap to identify which frames have active
staging buffers vs background-only or prefetch activity.

```bash
python3 scripts/summarize_wram_overlaps.py <run_dir> [--top-only]
```

**Output:**
- Frame number, overlap percentage, and tile counts
- Helps identify which WRAM-triggered captures are useful for correlation

**Flags:**
- `--top-only`: Show only the highest-overlap frames (reduces noise)

### analyze_wram_staging.py
Location: `scripts/analyze_wram_staging.py`

Compares WRAM dump contents against VRAM capture tiles to find staging buffer ranges
and validate the decompression pipeline.

```bash
python3 scripts/analyze_wram_staging.py \
  --capture <capture.json> \
  --wram <wram_dump.bin> \
  --database <tile_hash_database.json> \
  --rom <rom.sfc> \
  [--wram-start 0x0000] \
  [--emit-range] \
  [--range-pad 0x200] \
  [--range-align]
```

**Key options:**
- `--wram-start`: Override WRAM dump start offset for alignment scans
- `--emit-range`: Output a suggested WRAM watch range based on substring matches
- `--range-pad`: Padding to add around discovered ranges
- `--range-align`: Align emitted range to tile boundaries

**Reports:**
- Byte-level overlap between WRAM and VRAM tiles
- Substring match locations (for misaligned staging buffers)
- Suggested watch ranges for future captures

---

## Appendix: Minimal Lua Script Template

Use this template as a starting point for new Mesen 2 Lua scripts:

```lua
-- Minimal Mesen 2 Lua Script Template
-- Usage: Mesen2.exe --testrunner "rom.sfc" "script.lua"

local OUTPUT_DIR = os.getenv("OUTPUT_DIR") or "."
local MAX_FRAMES = tonumber(os.getenv("MAX_FRAMES")) or 300

-- Validate API availability (fail-fast)
assert(emu.read, "emu.read not available")
assert(emu.memType.snesVideoRam, "snesVideoRam memType not available")

local frame_count = 0

-- End-frame callback: runs once per frame
local function on_end_frame()
    frame_count = frame_count + 1

    -- Example: read VRAM byte at address 0x0000
    local vram_byte = emu.read(0x0000, emu.memType.snesVideoRam)

    -- Example: get CPU state
    local state = emu.getState()
    local pc_full = (state.cpu.k << 16) | state.cpu.pc

    if frame_count >= MAX_FRAMES then
        print(string.format("Stopping after %d frames", frame_count))
        emu.stop()
    end
end

-- Register callback
emu.addEventCallback(on_end_frame, emu.eventType.endFrame)

print("Script loaded. Running for " .. MAX_FRAMES .. " frames...")
```

**Key patterns:**
- Use `os.getenv()` for configurable parameters
- Validate API availability with `assert()` at script start
- Use `emu.stop()` to exit cleanly in testrunner mode
- Access CPU registers via `emu.getState().cpu.*`
