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

REM v2.1: Skip boot/menu frames - only process gameplay (1500+)
set STAGING_START_FRAME=1500

REM v2.1: Per-frame cap (default 2048) - prevents timeout on heavy frames
REM set STAGING_MAX_WRITES_PER_FRAME=2048

REM v2.1: Sentinel sampling (0=full range, 0x40=every 64 bytes = 64x fewer callbacks)
REM Only enable if still timing out after STAGING_START_FRAME
REM set STAGING_SENTINEL_STEP=0x40

REM Track causal PRG read -> staging write pairs (shows ROM source data)
set STAGING_CAUSAL_ENABLED=1

REM PC-gated read tracking (only count reads from known copy routines)
REM Default OFF for discovery: we need to find which PCs read from source buffer
REM Set to 1 only AFTER you've discovered the source PCs
set STAGING_PC_GATING=0

REM WRAM intermediate buffer tracking (PRG -> WRAM buffer -> staging)
REM WARNING: EXPENSIVE - fires on every WRAM read (~120KB coverage)
REM Only enable when investigating intermediate buffer patterns
set STAGING_WRAM_TRACKING=0

REM ==== WRAM SOURCE TRACKING (THE KEY FEATURE) ====
REM Tracks what WRAM region the staging writer READS FROM
REM This reveals the intermediate buffer that feeds the staging area
REM Start narrow (0x0000-0x1FFF), widen if you get no pairs
set STAGING_WRAM_SOURCE=1
set STAGING_WRAM_SRC_START=0x0000
set STAGING_WRAM_SRC_END=0x1FFF

REM Ring buffer size (32 is enough for typical copy loops)
set STAGING_RING_SIZE=32

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
echo Once you know the source buffer range, trace who WRITES to it.
echo.
echo For gameplay frames only (1500+):
echo   grep "STAGING_WRAM_SOURCE.*frame=1[5-9]" mesen2_exchange/dma_probe_log.txt
echo.
if /i "%~1"=="--no-pause" goto :eof
pause
