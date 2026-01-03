@echo off
REM Asset Selector Tracer v3 with Movie Playback
REM Full idx→DMA payload attribution join
REM
REM Key features:
REM   - Fixed linkage metric (table_path denominator)
REM   - Session tracking tied to DP_PTR_SET
REM   - DMA capture and attribution
REM   - Per-idx database report

cd /d "C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal"

set MESEN_EXE=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\tools\mesen2\Mesen2.exe
set ROM_PATH=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\roms\Kirby Super Star (USA).sfc
set LUA_PATH=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\mesen2_integration\lua_scripts\asset_selector_tracer_v3.lua
set MOVIE_PATH=C:\Users\gabri\Documents\Mesen2\Movies\Kirby Super Star (USA).mmo

set OUTPUT_DIR=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\mesen2_exchange\

echo.
echo ===============================================
echo Asset Selector Tracer v3 (idx-^>DMA join)
echo ===============================================
echo.
echo Features:
echo   - Correct linkage metric (table-path streams only)
echo   - Session tracking: DP_PTR_SET -^> timeout/DMA
echo   - VRAM sprite region DMA capture
echo   - Per-idx database with record types, DMA identities
echo.
echo Output: mesen2_exchange\asset_selector_v3.log
echo ===============================================
echo.

echo Starting Mesen2 with ROM + Lua...
start "" "%MESEN_EXE%" --enableStdout "%ROM_PATH%" "%LUA_PATH%"

echo Waiting for ROM to start (6 seconds)...
ping -n 6 127.0.0.1 >NUL

echo Sending movie file to running instance...
start "" "%MESEN_EXE%" "%MOVIE_PATH%"

echo.
echo ===============================================
echo Mesen2 is running. Wait for 3000 frames.
echo Results: mesen2_exchange\asset_selector_v3.log
echo ===============================================
echo.

pause
