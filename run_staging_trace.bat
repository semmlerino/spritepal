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

REM Track ROM reads during staging fills (shows source data)
set STAGING_ROM_READS_ENABLED=1

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
echo This run will trace what S-CPU code writes to WRAM $7E:2000-$2FFF
echo (the sprite staging buffer before DMA to VRAM).
echo.
echo Expected output in dma_probe_log.txt:
echo   STAGING_SUMMARY: frame=X ... pcs=[PC1,PC2,...] pattern=...
echo   STAGING_ROM_READS: frame=X ... prg_runs=[...]
echo.
echo The "pcs" field tells you which code addresses write the staging buffer.
echo The "prg_runs" field shows ROM read bursts that correlate with fills.
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
echo   grep "STAGING_ROM_READS" mesen2_exchange/dma_probe_log.txt
echo.
if /i "%~1"=="--no-pause" goto :eof
pause
