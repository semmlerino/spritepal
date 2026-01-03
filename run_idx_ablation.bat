@echo off
REM Per-idx Ablation Test
REM
REM This script runs the ablation test for a specific idx.
REM
REM USAGE:
REM   1. Edit per_idx_ablation_v1.lua:
REM      - Set ABLATION_TARGET_IDX (6, 40, etc.)
REM      - Set ABLATION_ENABLED = false  (for baseline)
REM   2. Run this script
REM   3. Edit per_idx_ablation_v1.lua:
REM      - Set ABLATION_ENABLED = true  (for ablation)
REM   4. Run this script again
REM   5. Compare: mesen2_exchange\ablation_idx*_baseline.log vs ablation_idx*_ablation.log
REM

cd /d "C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal"

set MESEN_EXE=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\tools\mesen2\Mesen2.exe
set ROM_PATH=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\roms\Kirby Super Star (USA).sfc
set LUA_PATH=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\mesen2_integration\lua_scripts\per_idx_ablation_v1.lua
set MOVIE_PATH=C:\Users\gabri\Documents\Mesen2\Movies\Kirby Super Star (USA).mmo

set OUTPUT_DIR=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\mesen2_exchange\

echo.
echo ===============================================
echo Per-idx Ablation Test
echo ===============================================
echo.
echo BEFORE RUNNING:
echo   Edit mesen2_integration\lua_scripts\per_idx_ablation_v1.lua
echo   Set: ABLATION_TARGET_IDX = your_target_idx
echo   Set: ABLATION_ENABLED = false (baseline) or true (ablation)
echo.
echo Output will be in mesen2_exchange\ablation_idx*_[baseline/ablation].log
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
echo Results: mesen2_exchange\ablation_idx*_[baseline/ablation].log
echo ===============================================
echo.

pause
