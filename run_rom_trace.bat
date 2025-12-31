@echo off
REM ROM Trace Run - Captures PRG-ROM read addresses during gameplay
REM This helps discover which ROM offsets contain the active sprite graphics
cd /d "C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal"

set MESEN_EXE=tools\mesen2\Mesen2.exe
set ROM_PATH=roms\Kirby Super Star (USA).sfc
set LUA_PATH=mesen2_integration\lua_scripts\mesen2_dma_probe.lua

REM Output directory for trace data
set OUTPUT_DIR=mesen2_exchange\rom_trace_run\

REM Tracing configuration
set MAX_FRAMES=3600
set ROM_TRACE_ON_WRAM_WRITE=1
set ROM_TRACE_MAX_READS=1000
set ROM_TRACE_MAX_FRAMES=3
set ROM_TRACE_PC_SAMPLES=16

REM WRAM staging area to watch (from 03_GAME_MAPPING docs)
set WRAM_WATCH_WRITES=1
set WRAM_WATCH_START=0x001E00
set WRAM_WATCH_END=0x006100

REM Capture settings - capture on VRAM DMA events
set CAPTURE_ON_VRAM_DMA=1
set CAPTURE_ON_VRAM_DIFF=0
set VRAM_DIFF=0
set CAPTURE_START_SECONDS=5
set CAPTURE_MIN_INTERVAL_SECONDS=10
set CAPTURE_TAG_PREFIX=romtrace

REM DMA tracking
set DMA_DUMP_ON_VRAM=1
set DMA_DUMP_START_SECONDS=5

REM Create output directory
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

echo === ROM Trace Run ===
echo Output: %OUTPUT_DIR%
echo Watching WRAM: %WRAM_WATCH_START% - %WRAM_WATCH_END%
echo ROM trace on WRAM write: enabled
echo.
echo Starting Mesen2... Play the game normally for ~60 seconds.
echo The script will trace ROM reads when sprite data is staged.
echo.

"%MESEN_EXE%" --enableStdout "%ROM_PATH%" "%LUA_PATH%"

echo.
echo === Trace Complete ===
echo Check %OUTPUT_DIR% for:
echo   - rom_trace_log.txt (ROM read addresses)
echo   - dma_probe_log.txt (DMA transfers)
echo   - sprite captures
echo.
pause
