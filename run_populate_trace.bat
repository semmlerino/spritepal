@echo off
REM Cold-Start Populate Trace (v2.11)
REM Detects when the tile buffer (0x1530-0x161A) is FIRST populated
REM This identifies the ROM source for the 235 bytes of tile data
REM
REM Strategy:
REM   1. STAGING_START_FRAME=0 (trace from beginning)
REM   2. POPULATE_ENABLED=1 (hash-based cold-start detection)
REM   3. Only trigger when buffer content changes (excluding metadata range)
REM   4. Bounded PRG logging during the "populate session"

cd /d "C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal"

set MESEN_EXE=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\tools\mesen2\Mesen2.exe
set ROM_PATH=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\roms\Kirby Super Star (USA).sfc
set LUA_PATH=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\mesen2_integration\lua_scripts\mesen2_dma_probe.lua
set MOVIE_PATH=C:\Users\gabri\Documents\Mesen2\Movies\Kirby Super Star (USA).mmo

set OUTPUT_DIR=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\mesen2_exchange\

REM Run enough frames to catch level loading
set MAX_FRAMES=2500

REM ==== COLD-START DETECTION (v2.11) ====
REM Trace from frame 0 to catch initial buffer population
set STAGING_START_FRAME=0

REM Hash-based detection: check every 100 frames, trigger on 32+ byte change
set POPULATE_ENABLED=1
set POPULATE_HASH_INTERVAL=100
set POPULATE_MIN_CHANGE_BYTES=32

REM Exclude metadata range (the 12-byte pointers at 0x157B-0x15BE)
set POPULATE_EXCLUDE_START=0x157B
set POPULATE_EXCLUDE_END=0x15BE

REM ==== BUFFER WATCH (tile buffer region) ====
REM The target buffer where tile data lands before staging
set BUFFER_WRITE_WATCH=1
set BUFFER_WRITE_START=0x1530
set BUFFER_WRITE_END=0x161A
set BUFFER_WRITE_PC_SAMPLES=16

REM ==== STAGING TRACKING (minimal - just for context) ====
set STAGING_WATCH_ENABLED=1
set STAGING_WATCH_START=0x2000
set STAGING_WATCH_END=0x2FFF
set STAGING_WATCH_PC_SAMPLES=4

REM ==== WRAM SOURCE (to see what feeds staging) ====
set STAGING_WRAM_SOURCE=1
set STAGING_WRAM_SRC_START=0x0000
set STAGING_WRAM_SRC_END=0x1FFFF
set STAGING_RING_SIZE=256

REM ==== DISABLE EXPENSIVE FEATURES ====
set STAGING_CAUSAL_ENABLED=0
set STAGING_PC_GATING=0
set STAGING_WRAM_TRACKING=0
set PERIODIC_CAPTURE_ENABLED=0
set VRAM_DIFF=0
set DMA_COMPARE_ENABLED=0
set CAPTURE_ON_VRAM_DIFF=0
set CAPTURE_ON_VRAM_DMA=0
set WRAM_DUMP_ON_VRAM_DIFF=0
set WRAM_WATCH_WRITES=0
set ROM_TRACE_ON_WRAM_WRITE=0

REM Minimal logging until something interesting happens
set HEARTBEAT_EVERY=500

echo.
echo ===============================================
echo COLD-START POPULATE TRACE (v2.11)
echo ===============================================
echo.
echo Strategy:
echo   1. Hash buffer every 100 frames (excluding metadata at 0x157B-0x15BE)
echo   2. When hash changes by 32+ bytes, open "populate session"
echo   3. Log PRG reads during populate session (bounded)
echo   4. Dump final buffer bytes for ROM comparison
echo.
echo Look for in logs:
echo   POPULATE_INIT      - Initial buffer state captured
echo   POPULATE_CHANGE    - Buffer content changed
echo   POPULATE_SESSION   - Populate session summary with PRG runs
echo   POPULATE_BUFFER_DUMP - Final buffer hex dump (for ROM search)
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
echo Mesen2 is running. Wait for frame %MAX_FRAMES% to complete.
echo ===============================================
echo.
echo After completion, check mesen2_exchange/dma_probe_log.txt for:
echo   grep "POPULATE" mesen2_exchange/dma_probe_log.txt
echo.

if /i "%~1"=="--no-pause" goto :eof
pause
