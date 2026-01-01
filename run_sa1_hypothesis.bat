@echo off
REM Gameplay Sprite Capture + DMA Logging
REM Uses mesen2_dma_probe.lua with movie playback to capture:
REM   1. SA-1/DMA events (for timing correlation)
REM   2. Periodic sprite captures (for ROM matching)
REM
REM This follows the same pattern as run_movie_probe.bat (which works reliably).
cd /d "C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal"

set MESEN_EXE=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\tools\mesen2\Mesen2.exe
set ROM_PATH=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\roms\Kirby Super Star (USA).sfc
set LUA_PATH=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\mesen2_integration\lua_scripts\mesen2_dma_probe.lua
set MOVIE_PATH=C:\Users\gabri\Documents\Mesen2\Movies\Kirby Super Star (USA).mmo

REM Output to main exchange directory (not timestamped subdirectory)
set OUTPUT_DIR=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\mesen2_exchange\

REM Run for 10000 frames (~2.75 minutes at 60fps)
set MAX_FRAMES=10000

REM ==== PERIODIC SPRITE CAPTURES (NEW) ====
REM Enable periodic captures for ROM matching correlation
set PERIODIC_CAPTURE_ENABLED=1
set PERIODIC_CAPTURE_START=1500
set PERIODIC_CAPTURE_INTERVAL=750

REM Enable screenshots and VRAM dumps for captures
set CAPTURE_SCREENSHOT=1
set CAPTURE_DUMP_VRAM=1
set CAPTURE_MAX=20
set CAPTURE_TAG_PREFIX=gameplay

REM ==== DMA/SA-1 LOGGING ====
REM Keep SA-1 and DMA logging enabled (critical for correlation)
set HEARTBEAT_EVERY=1000

REM ==== DMA SOURCE VS VRAM COMPARISON (NEW) ====
REM Critical test: does source buffer == VRAM after DMA?
REM If equal: transformation happened BEFORE staging
REM If not equal: CCDMA or mid-transform territory
set DMA_COMPARE_ENABLED=1
set DMA_COMPARE_MAX=100
set DMA_COMPARE_SAMPLE_BYTES=64

REM Disable event-triggered captures (use periodic instead)
set VRAM_DIFF=0
set WRAM_DUMP_ON_VRAM_DIFF=0
set WRAM_DUMP_PREV=0
set DMA_DUMP_ON_VRAM=0
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

REM Show UI for verification
set USE_NOVIDEO=0
set USE_NOAUDIO=0

echo ================================================================================
echo Gameplay Sprite Capture + DMA Logging
echo ================================================================================
echo.
echo This run will capture during movie playback:
echo   - DMA events (dma_probe_log.txt) for timing correlation
echo   - DMA source vs VRAM comparison (DMA_COMPARE lines)
echo   - Sprite captures every 12.5 seconds starting at frame 1500
echo.
echo Output: %OUTPUT_DIR%
echo Frames: %MAX_FRAMES% (~2.75 minutes)
echo.
echo Files generated:
echo   - dma_probe_log.txt          (DMA events for correlation)
echo   - test_capture_gameplay_*.json  (sprite data)
echo   - test_frame_gameplay_*.png     (screenshots)
echo   - test_vram_dump_gameplay_*.bin (VRAM dumps)
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
echo Mesen2 is running. Wait for MAX_FRAMES (%MAX_FRAMES%) to complete.
echo ================================================================================
echo.
echo When complete, run the correlation pipeline:
echo   uv run python scripts/run_full_correlation.py ^
echo       --rom "roms\Kirby Super Star (USA).sfc" ^
echo       --dma-log mesen2_exchange ^
echo       --capture "mesen2_exchange\test_capture_gameplay_*.json" ^
echo       --scan-rom
echo.
if /i "%~1"=="--no-pause" goto :eof
pause
