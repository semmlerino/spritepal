@echo off
REM Block Boundary Detector - Measure compressed block sizes
REM Usage: run_block_boundary.bat [target_addr]
REM
REM Examples:
REM   run_block_boundary.bat             - Analyze 0xE9E667 (default)
REM   run_block_boundary.bat 0xE93AEB    - Analyze 0xE93AEB

cd /d "C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal"

set MESEN_EXE=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\tools\mesen2\Mesen2.exe
set ROM_PATH=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\roms\Kirby Super Star (USA).sfc
set LUA_PATH=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\mesen2_integration\lua_scripts\block_boundary_detector.lua
set MOVIE_PATH=C:\Users\gabri\Documents\Mesen2\Movies\Kirby Super Star (USA).mmo
set OUTPUT_DIR=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\mesen2_exchange\
set LOG_FILE=%OUTPUT_DIR%dma_probe_log.txt

REM Default target address
set TARGET_ADDR=0xE9E667
if not "%~1"=="" set TARGET_ADDR=%~1

set MAX_FRAMES=1900
set MAX_READS=2000

echo [BLOCK_BOUNDARY] Detecting block sizes for %TARGET_ADDR%...

REM Clear old log
if exist "%LOG_FILE%" del /f /q "%LOG_FILE%"

echo [BLOCK_BOUNDARY] Starting Mesen2...
start "" "%MESEN_EXE%" "%ROM_PATH%" "%LUA_PATH%"
ping -n 7 127.0.0.1 >NUL

echo [BLOCK_BOUNDARY] Sending movie file...
start "" "%MESEN_EXE%" "%MOVIE_PATH%"

echo [BLOCK_BOUNDARY] Waiting for analysis...
:wait_complete
ping -n 2 127.0.0.1 >NUL
findstr /c:"COMPLETE" "%LOG_FILE%" >NUL 2>&1
if errorlevel 1 goto wait_complete

ping -n 2 127.0.0.1 >NUL

echo [BLOCK_BOUNDARY] Closing Mesen2...
taskkill /IM Mesen2.exe /F >NUL 2>&1
ping -n 2 127.0.0.1 >NUL

echo [BLOCK_BOUNDARY] Complete - check mesen2_exchange\block_boundaries_%TARGET_ADDR:~2%.log
