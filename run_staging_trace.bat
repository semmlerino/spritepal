@echo off
REM Staging Buffer Write Trace
REM Traces what code writes to WRAM 0x2000 (sprite staging area)
REM This identifies the "missing link" - what populates the staging buffer
REM before DMA transfers it to VRAM.

cd /d "C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal"

set MESEN_EXE=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\tools\mesen2\Mesen2.exe
set ROM_PATH=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\roms\Kirby Super Star (USA).sfc
set LUA_PATH=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\mesen2_integration\lua_scripts\mesen2_dma_probe.lua
set MOVIE_PATH=C:\Users\gabri\Documents\Mesen2\Movies\Kirby Super Star (USA).mmo

set OUTPUT_DIR=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\mesen2_exchange\

REM Run until we have good data (around frame 1500 area)
set MAX_FRAMES=2000

REM ==== STAGING BUFFER WRITE TRACKING (THE KEY) ====
set STAGING_WATCH_ENABLED=1
set STAGING_WATCH_START=0x2000
set STAGING_WATCH_END=0x2FFF
set STAGING_WATCH_PC_SAMPLES=8

REM v2.2: Lazy registration frame - callbacks registered at this frame (not at init)
REM This solves init-time timeout by deferring expensive callback registration
set STAGING_START_FRAME=1500

REM v2.1: Per-frame cap (default 2048) - prevents timeout on heavy frames
REM set STAGING_MAX_WRITES_PER_FRAME=2048

REM v2.2: Sentinel sampling (0=full range, N=every N bytes)
REM With lazy registration, init timeout is gone - you can use full-range (0) or dense sampling
REM Examples: 0=full range (4096 callbacks), 32=every 32 bytes (128 callbacks), 64=every 64 bytes (64 callbacks)
REM set STAGING_SENTINEL_STEP=0

REM Track causal PRG read -> staging write pairs (shows ROM source data)
set STAGING_CAUSAL_ENABLED=1

REM PC-gated read tracking (only count reads from known copy routines)
REM v2.5: DISABLED - staging WRITE PCs != WRAM READ PCs (off by 1-3 bytes in copy loop)
REM Need to discover read PCs first before enabling this
REM Known write PCs: 01:8FA9, 00:8952, 00:893D (not useful for read gating)
set STAGING_PC_GATING=0

REM WRAM intermediate buffer tracking (PRG -> WRAM buffer -> staging)
REM WARNING: EXPENSIVE - fires on every WRAM read (~120KB coverage)
REM Only enable when investigating intermediate buffer patterns
set STAGING_WRAM_TRACKING=0

REM ==== WRAM SOURCE TRACKING (THE KEY FEATURE) ====
REM Tracks what WRAM region the staging writer READS FROM
REM This reveals the intermediate buffer that feeds the staging area
REM Now safe with increased ScriptTimeout (set to 5+ seconds in Mesen2)
REM v2.7: Full 128KB WRAM ($0000-$1FFFF = banks $7E+$7F)
REM       Previous 0xFFFF was only 64KB (bank $7E) - missed half of WRAM!
set STAGING_WRAM_SOURCE=1
set STAGING_WRAM_SRC_START=0x0000
set STAGING_WRAM_SRC_END=0x1FFFF

REM Ring buffer size - must be >= largest expected staging DMA
REM v2.5: Increased to 256 so 64-byte DMAs can reach near-100% coverage
set STAGING_RING_SIZE=256

REM ==== BUFFER WRITE TRACKING (v2.8) ====
REM Traces what WRITES to the discovered source buffer region
REM This is the next rung: ROM -> source buffer -> staging -> VRAM
REM                            ^^^^^^^^^^^^^^^^^
REM                         BUFFER_WRITE_WATCH reveals this
REM
REM Target: Primary source region discovered in v2.7:
REM   0x01530-0x0161A (235 bytes) = $7E:1530-$7E:161A
REM
REM NOTE: Start with this DISABLED until STAGING_WRAM_SOURCE is confirmed working
REM Then enable to trace the ROM->source link
set BUFFER_WRITE_WATCH=1
set BUFFER_WRITE_START=0x1530
set BUFFER_WRITE_END=0x161A
set BUFFER_WRITE_PC_SAMPLES=8

REM ==== PERIODIC CAPTURES (for correlation) ====
set PERIODIC_CAPTURE_ENABLED=1
set PERIODIC_CAPTURE_START=1500
set PERIODIC_CAPTURE_INTERVAL=500
set CAPTURE_MAX=5
set CAPTURE_TAG_PREFIX=staging_trace
set CAPTURE_SCREENSHOT=1
set CAPTURE_DUMP_VRAM=0

REM ==== WRAM DUMPS (staging region only) ====
set WRAM_DUMP_ON_VRAM_DIFF=0
set WRAM_DUMP_PREV=0

REM ==== MINIMAL DMA LOGGING ====
set HEARTBEAT_EVERY=500

REM Disable noise
set VRAM_DIFF=0
set DMA_COMPARE_ENABLED=0
set CAPTURE_ON_VRAM_DIFF=0
set CAPTURE_ON_VRAM_DMA=0
set CAPTURE_DUMP_WRAM=0
set WRAM_WATCH_WRITES=0
set ROM_TRACE_ON_WRAM_WRITE=0

REM No startup delays
set CAPTURE_START_SECONDS=0
set VRAM_DIFF_START_SECONDS=0
set WRAM_DUMP_START_SECONDS=0
set DMA_DUMP_START_SECONDS=0

REM Show UI
set USE_NOVIDEO=0
set USE_NOAUDIO=0

echo ================================================================================
echo Staging Buffer Write Trace
echo ================================================================================
echo.
echo This run traces the WRAM intermediate buffer that feeds staging.
echo.
echo Data flow being traced:
echo   PRG ROM -^> ??? -^> [source buffer] -^> staging $7E:2000 -^> VRAM
echo                        ^^^^^^^^^^^^
echo                     STAGING_WRAM_SOURCE reveals this
echo.
echo Expected output in dma_probe_log.txt:
echo   STAGING_WRAM_SOURCE: frame=X wram_pairs=N wram_runs=[...] (THE KEY)
echo   STAGING_CAUSAL: frame=X pairs=N prg_runs=[...] (likely all NO_PAIRS)
echo   STAGING_SUMMARY: frame=X pcs=[...] pattern=...
echo.
echo Output: %OUTPUT_DIR%
echo Frames: %MAX_FRAMES%
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
echo ================================================================================
echo Mesen2 is running. Wait for frame %MAX_FRAMES% to complete.
echo ================================================================================
echo.
echo After completion, look for:
echo   grep "STAGING_SUMMARY" mesen2_exchange/dma_probe_log.txt
echo   grep "STAGING_CAUSAL" mesen2_exchange/dma_probe_log.txt   (PRG source tracking)
echo   grep "STAGING_WRAM_SOURCE" mesen2_exchange/dma_probe_log.txt   (THE KEY DATA)
echo.
echo STAGING_WRAM_SOURCE shows what WRAM region feeds the staging buffer.
echo.
echo v2.8: BUFFER_WRITE_WATCH traces who WRITES to the source buffer.
echo   Set BUFFER_WRITE_WATCH=1, BUFFER_WRITE_START/END to the discovered region
echo   grep "BUFFER_WRITE_SUMMARY" mesen2_exchange/dma_probe_log.txt
echo.
echo v2.9: FILL_SESSION logs PRG/ROM reads ONLY during buffer fill window.
echo   This is the key: bounded PRG logging = safe, gives ROM offset runs.
echo   grep "FILL_SESSION" mesen2_exchange/dma_probe_log.txt
echo.
echo For gameplay frames only (1500+):
echo   grep "STAGING_WRAM_SOURCE.*frame=1[5-9]" mesen2_exchange/dma_probe_log.txt
echo.
if /i "%~1"=="--no-pause" goto :eof
pause
