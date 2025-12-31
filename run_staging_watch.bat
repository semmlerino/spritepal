@echo off
REM Staging Buffer Write Watch Test
REM Traces who fills $7E:2000 before DMA uploads it to VRAM
cd /d "C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal"

set MESEN_EXE=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\tools\mesen2\Mesen2.exe
set ROM_PATH=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\roms\Kirby Super Star (USA).sfc
set LUA_PATH=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\mesen2_integration\lua_scripts\mesen2_dma_probe.lua
set MOVIE_PATH=C:\Users\gabri\Documents\Mesen2\Movies\Kirby Super Star (USA).mmo

set OUTPUT_DIR=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\mesen2_exchange\

REM Skip early frames (menus/intro), run deep into gameplay
set MAX_FRAMES=6000
set STAGING_START_FRAME=1500

REM ==== STAGING WATCH ====
REM Enable rolling write log for DMA source buffer
set STAGING_WATCH_ENABLED=1
set STAGING_WATCH_START=0x2000
set STAGING_WATCH_END=0x33FF
set STAGING_WATCH_PC_SAMPLES=8
set STAGING_HISTORY_FRAMES=3

REM ==== ROM READ TRACKING ====
REM Log which ROM addresses are read during staging fills
set STAGING_ROM_READS_ENABLED=1

REM ==== DMA COMPARISON ====
REM Keep DMA comparison to see which DMAs fire from staging
set DMA_COMPARE_ENABLED=1
set DMA_COMPARE_MAX=50
set DMA_COMPARE_SAMPLE_BYTES=64

REM Disable other features to reduce noise
set VRAM_DIFF=0
set WRAM_DUMP_ON_VRAM_DIFF=0
set WRAM_DUMP_PREV=0
set DMA_DUMP_ON_VRAM=0
set CAPTURE_ON_VRAM_DIFF=0
set CAPTURE_ON_VRAM_DMA=0
set CAPTURE_SCREENSHOT=0
set CAPTURE_DUMP_VRAM=0
set WRAM_WATCH_WRITES=0

set HEARTBEAT_EVERY=500

echo ================================================================================
echo Staging Buffer Write Watch Test (Gameplay Focus)
echo ================================================================================
echo.
echo This test traces who writes to $7E:2000-$7E:33FF before DMA uploads to VRAM.
echo Skipping first %STAGING_START_FRAME% frames (menus/intro), running to frame %MAX_FRAMES%.
echo.
echo Expected output in dma_probe_log.txt:
echo   STAGING_SUMMARY: frame=N src=0x7E2000 pattern=SEQUENTIAL_BURST writes=X ...
echo   STAGING_ROM_READS: frame=N pc=00:893D vram=0x6000 runs=[C2:9A00-C2:9B7F,...] ...
echo.
echo Pattern meanings:
echo   SEQUENTIAL_BURST  = Decompress/copy (single fill operation)
echo   SCATTERED_CHUNKS  = Metatile assembly (pieces built up)
echo   NO_SCPU_WRITES    = SA-1 or hidden path (not visible to S-CPU callback)
echo   MIXED             = Combination of sequential and scattered
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
echo When complete, search for staging summaries:
echo   findstr "STAGING_SUMMARY:" mesen2_exchange\dma_probe_log.txt
echo.
pause
