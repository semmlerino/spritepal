@echo off
REM WRAM diff capture for baseline vs ablated comparison
REM Usage: run_wram_diff.bat [baseline|ablated]
REM
REM Captures $7E2000-$7E27FF at frame 1795 (first flip frame)

cd /d "C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal"

set MESEN_EXE=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\tools\mesen2\Mesen2.exe
set ROM_PATH=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\roms\Kirby Super Star (USA).sfc
set LUA_PATH=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\mesen2_integration\lua_scripts\wram_diff_capture.lua
set MOVIE_PATH=C:\Users\gabri\Documents\Mesen2\Movies\Kirby Super Star (USA).mmo
set OUTPUT_DIR=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\mesen2_exchange\
set LOG_FILE=%OUTPUT_DIR%dma_probe_log.txt

set MAX_FRAMES=1850
set WRAM_DUMP_FRAME=1795

if "%~1"=="ablated" (
    echo [WRAM_DIFF] Running ABLATED capture...
    set ABLATION_ENABLED=1
    set ABLATION_PRG_START=0xE9E667
    set ABLATION_PRG_END=0xE9E667
    set ABLATION_VALUE=0xFF
) else (
    echo [WRAM_DIFF] Running BASELINE capture...
    set ABLATION_ENABLED=0
    set ABLATION_PRG_START=0x0
    set ABLATION_PRG_END=0x0
)

REM Clear old log
if exist "%LOG_FILE%" del /f /q "%LOG_FILE%"

echo [WRAM_DIFF] Starting Mesen2...
start "" "%MESEN_EXE%" "%ROM_PATH%" "%LUA_PATH%"
ping -n 7 127.0.0.1 >NUL

echo [WRAM_DIFF] Sending movie file...
start "" "%MESEN_EXE%" "%MOVIE_PATH%"

echo [WRAM_DIFF] Waiting for WRAM dump...
:wait_dump
ping -n 2 127.0.0.1 >NUL
findstr /c:"WRAM_DUMP_COMPLETE" "%LOG_FILE%" >NUL 2>&1
if errorlevel 1 goto wait_dump

ping -n 2 127.0.0.1 >NUL

echo [WRAM_DIFF] Closing Mesen2...
taskkill /IM Mesen2.exe /F >NUL 2>&1
ping -n 2 127.0.0.1 >NUL

echo [WRAM_DIFF] Complete - check mesen2_exchange for wram_dump_frame_1795_*.bin
