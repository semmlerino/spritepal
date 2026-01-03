@echo off
REM PRG Ablation Sweep (v2.25)
REM Binary-search which 1MB PRG chunks causally feed staging DMA payloads
REM v2.25: Decouple ablation from BUFFER_WRITE_WATCH (critical bug fix)
REM v2.24: Per-CPU toggles (ABLATE_SNES/ABLATE_SA1), SNES exec-guard
REM v2.23: Fix emu.stop() re-entry bug (script_stopping guard)
REM v2.22: SA-1 PRG ablation UNGATED (exec guard only) - tests upstream producer hypothesis
REM
REM Protocol:
REM   1. Run baseline (ABLATION_ENABLED=0) - record payload_hash for target DMAs
REM   2. Ablate each chunk - compare payload_hash
REM   3. If hash changes, subdivide that chunk for finer granularity
REM
REM PRG chunks (HiROM):
REM   Chunk 0: 0xC00000-0xCFFFFF (file 0x000000-0x0FFFFF)
REM   Chunk 1: 0xD00000-0xDFFFFF (file 0x100000-0x1FFFFF)
REM   Chunk 2: 0xE00000-0xEFFFFF (file 0x200000-0x2FFFFF) -- likely hit (0xE894F4 was proven earlier)
REM   Chunk 3: 0xF00000-0xFFFFFF (file 0x300000-0x3FFFFF)
REM
REM Interpretation:
REM   - corrupted_reads=0: chunk not touched
REM   - corrupted_reads>0 but payload_hash unchanged: touched but not causal
REM   - payload_hash changes: FOUND causal PRG region

cd /d "C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal"

set MESEN_EXE=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\tools\mesen2\Mesen2.exe
set ROM_PATH=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\roms\Kirby Super Star (USA).sfc
set LUA_PATH=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\mesen2_integration\lua_scripts\mesen2_dma_probe.lua
set MOVIE_PATH=C:\Users\gabri\Documents\Mesen2\Movies\Kirby Super Star (USA).mmo

set OUTPUT_DIR=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\mesen2_exchange\

set MAX_FRAMES=2500

REM === ABLATION CONFIG ===
REM Set to 1 to enable corruption, 0 for baseline
REM STEP 2: Baseline done, now ablating Bank C (most accessed for staging fills)
set ABLATION_ENABLED=1

REM === PRG CHUNKS (uncomment one pair for each run) ===
REM Baseline: run with ABLATION_ENABLED=0 first
REM set ABLATION_PRG_START=0xC00000
REM set ABLATION_PRG_END=0xCFFFFF

REM Chunk 0: 0xC00000-0xCFFFFF
REM set ABLATION_PRG_START=0xC00000
REM set ABLATION_PRG_END=0xCFFFFF

REM Chunk 1: 0xD00000-0xDFFFFF
REM set ABLATION_PRG_START=0xD00000
REM set ABLATION_PRG_END=0xDFFFFF

REM Chunk 2: 0xE00000-0xEFFFFF (LIKELY HIT - 0xE894F4 was proven causal earlier)
REM set ABLATION_PRG_START=0xE00000
REM set ABLATION_PRG_END=0xEFFFFF

REM === 256KB QUARTER CHUNKS (safer than 1MB, finer than whole bank) ===
REM Quarter 2.0: 0xE00000-0xE3FFFF
REM set ABLATION_PRG_START=0xE00000
REM set ABLATION_PRG_END=0xE3FFFF

REM Quarter 2.1: 0xE40000-0xE7FFFF
REM set ABLATION_PRG_START=0xE40000
REM set ABLATION_PRG_END=0xE7FFFF

REM Quarter 2.2: 0xE80000-0xEBFFFF (contains proven 94-byte range for early frames)
REM set ABLATION_PRG_START=0xE80000
REM set ABLATION_PRG_END=0xEBFFFF

REM Quarter 2.3: 0xEC0000-0xEFFFFF (direct ROM→VRAM for BG tiles, not staging path)
REM set ABLATION_PRG_START=0xEC0000
REM set ABLATION_PRG_END=0xEFFFFF

REM === RESULTS LOG ===
REM Chunk 0 (Bank C): TESTED - no payload_hash flips (non-causal for sprite staging)
REM Quarter 2.2 (0xE80000-0xEBFFFF): CAUSAL - 4 payload_hash flips at frames 1681,1684,1760,1769
REM Bank EB (0xEB0000-0xEBFFFF): TESTED - NO flips despite SA1_BURST reads from 0xEBBxxx
REM   -> 0xEBBxxx reads are NOT on critical path for these 4 DMAs
REM   -> Causal bytes must be in E8, E9, or EA
REM
REM === 64KB BISECTION OF QUARTER 2.2 ===
REM Bank E8: 0xE80000-0xE8FFFF (earlier evidence: 0xE894F4 was proven causal)
set ABLATION_PRG_START=0xE80000
set ABLATION_PRG_END=0xE8FFFF

REM Bank E9: 0xE90000-0xE9FFFF
REM set ABLATION_PRG_START=0xE90000
REM set ABLATION_PRG_END=0xE9FFFF

REM Bank EA: 0xEA0000-0xEAFFFF
REM set ABLATION_PRG_START=0xEA0000
REM set ABLATION_PRG_END=0xEAFFFF

REM Bank EB: 0xEB0000-0xEBFFFF (TESTED: no flips - not causal for 4 flip DMAs)
REM set ABLATION_PRG_START=0xEB0000
REM set ABLATION_PRG_END=0xEBFFFF

REM === FINER BISECTION OF E8 (after E8 confirmed) ===
REM 0xE80000-0xE87FFF (lower 32KB)
REM set ABLATION_PRG_START=0xE80000
REM set ABLATION_PRG_END=0xE87FFF

REM 0xE88000-0xE8FFFF (upper 32KB - contains 0xE894F4)
REM set ABLATION_PRG_START=0xE88000
REM set ABLATION_PRG_END=0xE8FFFF

REM 0xE89000-0xE89FFF (4KB around 0xE894F4)
REM set ABLATION_PRG_START=0xE89000
REM set ABLATION_PRG_END=0xE89FFF

REM Chunk 3: 0xF00000-0xFFFFFF
REM set ABLATION_PRG_START=0xF00000
REM set ABLATION_PRG_END=0xFFFFFF

set ABLATION_VALUE=0xFF

REM === MINIMAL CONFIG - disable 0x1530 buffer distractions ===
REM Staging DMAs from 0x7E2000 occur at frame 1495. Set start to catch them.
set STAGING_START_FRAME=1490
set STAGING_WATCH_ENABLED=1
set STAGING_WATCH_START=0x2000
set STAGING_WATCH_END=0x2FFF
set STAGING_WATCH_PC_SAMPLES=4

REM v2.25: BUFFER_WRITE_WATCH no longer required for ablation (decoupled in Lua script)
REM Can now safely set BUFFER_WRITE_WATCH=0 when only doing ablation experiments
set BUFFER_WRITE_WATCH=1
set BUFFER_WRITE_START=0x1530
set BUFFER_WRITE_END=0x161A
set READ_COVERAGE_ENABLED=0
set STAGING_WRAM_SOURCE=0
set STAGING_WRAM_TRACKING=0

REM Disable expensive comparison features
set STAGING_CAUSAL_ENABLED=0
set STAGING_PC_GATING=0
set DMA_COMPARE_ENABLED=0
set PERIODIC_CAPTURE_ENABLED=0
set VRAM_DIFF=0
set CAPTURE_ON_VRAM_DIFF=0
set CAPTURE_ON_VRAM_DMA=0
set WRAM_DUMP_ON_VRAM_DIFF=0
set WRAM_WATCH_WRITES=0
set ROM_TRACE_ON_WRAM_WRITE=0

REM Keep populate for hash tracking
set POPULATE_ENABLED=1
set POPULATE_HASH_INTERVAL=100
set POPULATE_MIN_CHANGE_BYTES=32
set POPULATE_EXCLUDE_START=0x157B
set POPULATE_EXCLUDE_END=0x15BE

set HEARTBEAT_EVERY=500

echo.
echo ===============================================
echo PRG ABLATION SWEEP (v2.25 - ablation decoupled from BUFFER_WRITE_WATCH)
echo ===============================================
echo.
echo ABLATION_ENABLED=%ABLATION_ENABLED%
if "%ABLATION_ENABLED%"=="0" (
    echo MODE: BASELINE - record payload_hash values
) else (
    echo MODE: ABLATION - testing PRG range
    echo.
    echo   *** ACTIVE RANGE: %ABLATION_PRG_START% - %ABLATION_PRG_END% ***
    echo.
    echo   If Lua log shows different range, close this window and reopen!
)
echo.
echo ABLATION_VALUE=0x%ABLATION_VALUE%
echo.
echo Noise reduction: BUFFER_WRITE_WATCH=0, READ_COVERAGE_ENABLED=0, STAGING_WRAM_SOURCE=0
echo.
echo Quick check after run (sprite VRAM 0x4000-0x5FFF only):
echo   grep "STAGING_SUMMARY.*vram=0x4\|STAGING_SUMMARY.*vram=0x5" mesen2_exchange/dma_probe_log.txt ^| head -10
echo.
echo Compare baseline vs ablation (match on frame+vram+src+size):
echo   Baseline: prg_sweep_baseline.txt
echo   Ablation: mesen2_exchange/dma_probe_log.txt
echo   Look for payload_hash differences in matching entries
echo.
echo ===============================================
echo.
echo Press any key to start...
pause > nul

echo.
echo Starting Mesen2 with ROM + Lua...
start "" "%MESEN_EXE%" --enableStdout "%ROM_PATH%" "%LUA_PATH%"

echo Waiting for ROM to start...
ping -n 6 127.0.0.1 >NUL

echo Sending movie file to running instance...
start "" "%MESEN_EXE%" "%MOVIE_PATH%"

echo.
echo ===============================================
echo Mesen2 is running. Wait for completion.
echo ===============================================
echo.
echo After run, save log as:
if "%ABLATION_ENABLED%"=="0" (
    echo   copy mesen2_exchange\dma_probe_log.txt prg_sweep_baseline.txt
) else (
    echo   copy mesen2_exchange\dma_probe_log.txt prg_sweep_bank_E8.txt
)
echo.

if /i "%~1"=="--no-pause" goto :eof
pause
