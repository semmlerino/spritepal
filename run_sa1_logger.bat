@echo off
REM SA-1 Conversion Logger Runner
REM Purpose: Run the SA-1 register logger to verify character conversion hypothesis
REM
REM This script will:
REM   1. Load Kirby Super Star ROM
REM   2. Log SA-1 DCNT ($2230) and CDMA ($2231) registers for ~5 minutes
REM   3. Output results to mesen2_exchange/sa1_conversion_log.csv
REM   4. Generate hypothesis outcome summary

setlocal

set SCRIPT_DIR=%~dp0
set ROM_PATH=%SCRIPT_DIR%roms\Kirby Super Star (USA).sfc
set LUA_SCRIPT=%SCRIPT_DIR%mesen2_integration\lua_scripts\sa1_conversion_logger.lua
set MESEN_PATH=%SCRIPT_DIR%tools\mesen2\Mesen2.exe

REM Check if ROM exists
if not exist "%ROM_PATH%" (
    echo ERROR: ROM not found: %ROM_PATH%
    echo Please ensure Kirby Super Star (USA).sfc is in the roms\ directory.
    pause
    exit /b 1
)

REM Check if Mesen2 exists
if not exist "%MESEN_PATH%" (
    echo ERROR: Mesen2 not found: %MESEN_PATH%
    echo Please ensure Mesen2.exe is in the tools\mesen2\ directory.
    pause
    exit /b 1
)

REM Check if Lua script exists
if not exist "%LUA_SCRIPT%" (
    echo ERROR: Lua script not found: %LUA_SCRIPT%
    pause
    exit /b 1
)

echo ================================================================================
echo SA-1 Conversion Hypothesis Logger
echo ================================================================================
echo.
echo ROM:    %ROM_PATH%
echo Script: %LUA_SCRIPT%
echo Output: %SCRIPT_DIR%mesen2_exchange\sa1_conversion_log.csv
echo.
echo The logger will run for approximately 5 minutes (18000 frames).
echo Play through sprite-heavy scenes:
echo   - Title screen
echo   - Character select
echo   - Gameplay with enemies
echo   - Boss fights
echo.
echo Press any key to start...
pause > nul

echo.
echo Starting Mesen2 with SA-1 logger...
echo.

REM Run Mesen2 in testrunner mode
"%MESEN_PATH%" --testrunner "%ROM_PATH%" "%LUA_SCRIPT%"

echo.
echo ================================================================================
echo Capture complete!
echo ================================================================================
echo.
echo Results saved to:
echo   mesen2_exchange\sa1_conversion_log.csv
echo   mesen2_exchange\sa1_hypothesis_results.txt
echo   mesen2_exchange\sa1_conversion_debug.txt
echo.
echo Open sa1_hypothesis_results.txt to see the hypothesis outcome.
echo.
pause
