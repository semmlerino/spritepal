@echo off
cd /d "C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal"
set MESEN_EXE=.\tools\mesen2\Mesen2.exe
set ROM_PATH=.\roms\Kirby Super Star (USA).sfc
set LUA_PATH=.\mesen2_integration\lua_scripts\mesen2_dma_probe.lua
set OUTPUT_DIR=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\mesen2_exchange\
set MAX_FRAMES=1000

REM Enable DMA comparison with fixes
set DMA_COMPARE_ENABLED=1
set DMA_COMPARE_MAX=100
set DMA_COMPARE_SAMPLE_BYTES=64

REM Disable other features
set VRAM_DIFF=0
set WRAM_DUMP_ON_VRAM_DIFF=0
set DMA_DUMP_ON_VRAM=0
set CAPTURE_ON_VRAM_DIFF=0
set CAPTURE_SCREENSHOT=0
set HEARTBEAT_EVERY=500

"%MESEN_EXE%" --testrunner "%ROM_PATH%" "%LUA_PATH%"
