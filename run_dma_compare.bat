@echo off
REM DMA Source vs VRAM Comparison Test
REM This determines if transformation happens BEFORE or DURING staging
cd /d "C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal"

set MESEN_EXE=.\tools\mesen2\Mesen2.exe
set ROM_PATH=.\roms\Kirby Super Star (USA).sfc
set LUA_PATH=.\mesen2_integration\lua_scripts\mesen2_dma_probe.lua

REM Output directory for this run
set OUTPUT_DIR=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\mesen2_exchange\dma_compare_run\

REM Core settings
set MAX_FRAMES=3000
set DMA_COMPARE_ENABLED=1
set DMA_COMPARE_MAX=100
set DMA_COMPARE_SAMPLE_BYTES=64

REM Disable other features to reduce log noise
set VRAM_DIFF=0
set WRAM_DUMP_ON_VRAM_DIFF=0
set WRAM_DUMP_PREV=0
set DMA_DUMP_ON_VRAM=0
set CAPTURE_ON_VRAM_DIFF=0
set CAPTURE_ON_VRAM_DMA=0
set CAPTURE_SCREENSHOT=0
set CAPTURE_DUMP_VRAM=0
set WRAM_WATCH_WRITES=0

REM Visibility filter (capture all sprites)
set SKIP_VISIBILITY_FILTER=1

echo ============================================
echo DMA Source vs VRAM Comparison Test
echo ============================================
echo.
echo This test determines whether transformation
echo happens BEFORE staging (source == VRAM) or
echo DURING/AFTER staging (source != VRAM).
echo.
echo Output: %OUTPUT_DIR%
echo Max frames: %MAX_FRAMES%
echo Max comparisons: %DMA_COMPARE_MAX%
echo.

mkdir "%OUTPUT_DIR%" 2>NUL

echo Running Mesen2 with DMA comparison probe...
"%MESEN_EXE%" --testrunner "%ROM_PATH%" "%LUA_PATH%"

echo.
echo ============================================
echo Test complete! Analyzing results...
echo ============================================
echo.
echo Look for DMA_COMPARE lines in:
echo   %OUTPUT_DIR%dma_probe_log.txt
echo.
echo Key indicators:
echo   eq=true  : Source == VRAM (transform before staging)
echo   eq=false : Source != VRAM (CCDMA or mid-transform)
echo.
findstr /C:"DMA_COMPARE:" "%OUTPUT_DIR%dma_probe_log.txt" | findstr /C:"eq=true"
echo.
findstr /C:"DMA_COMPARE:" "%OUTPUT_DIR%dma_probe_log.txt" | findstr /C:"eq=false"
echo.
pause
