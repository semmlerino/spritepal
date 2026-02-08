@echo off
REM Diversity Capture Runner
REM Captures sprites across multiple game states for comprehensive coverage.
REM
REM Prerequisites:
REM   1. Create savestates for different game sections:
REM      - Spring Breeze (various enemies, Whispy Woods)
REM      - Dyna Blade (flying enemies, boss)
REM      - Great Cave Offensive (diverse enemies)
REM      - Revenge of Meta Knight (ship interiors)
REM      - Milky Way Wishes (Marx, various copy abilities)
REM      - The Arena (cycles through all bosses)
REM
REM   2. Place savestates in: mesen2_exchange/savestates/
REM      Naming convention: game_section_description.mss
REM      Example: spring_breeze_whispy.mss, arena_boss1.mss
REM
REM Usage:
REM   run_diversity_capture.bat [savestate_name]
REM   run_diversity_capture.bat spring_breeze_whispy
REM   run_diversity_capture.bat all  (runs all savestates)

cd /d "%~dp0\.."

set MESEN_EXE=tools\mesen2\Mesen2.exe
set ROM_PATH=roms\Kirby Super Star (USA).sfc
set LUA_PATH=mesen2_integration\lua_scripts\mesen2_dma_probe.lua
set SAVESTATE_DIR=mesen2_exchange\savestates
set OUTPUT_BASE=mesen2_exchange\diversity_captures

REM Create output directory
if not exist "%OUTPUT_BASE%" mkdir "%OUTPUT_BASE%"

REM Capture settings
set MAX_FRAMES=3000
set CAPTURE_START_SECONDS=5

REM Check for savestate argument
if "%~1"=="" (
    echo Usage: run_diversity_capture.bat [savestate_name^|all]
    echo.
    echo Available savestates:
    if exist "%SAVESTATE_DIR%" (
        dir /b "%SAVESTATE_DIR%\*.mss" 2>nul
    ) else (
        echo   No savestates found. Create them in %SAVESTATE_DIR%
    )
    goto :eof
)

if /i "%~1"=="all" (
    echo Running all savestates...
    for %%f in ("%SAVESTATE_DIR%\*.mss") do (
        call :run_capture "%%~nf"
    )
    goto :done
)

REM Run single savestate
call :run_capture "%~1"
goto :done

:run_capture
set STATE_NAME=%~1
set STATE_FILE=%SAVESTATE_DIR%\%STATE_NAME%.mss
set OUTPUT_DIR=%OUTPUT_BASE%\%STATE_NAME%_%date:~10,4%%date:~4,2%%date:~7,2%_%time:~0,2%%time:~3,2%

if not exist "%STATE_FILE%" (
    echo Savestate not found: %STATE_FILE%
    exit /b 1
)

echo.
echo ================================================================================
echo Capturing: %STATE_NAME%
echo   Savestate: %STATE_FILE%
echo   Output: %OUTPUT_DIR%
echo   Frames: %MAX_FRAMES%
echo ================================================================================

REM Create output directory for this run
mkdir "%OUTPUT_DIR%" 2>nul

REM Run Mesen with the savestate
REM Note: Mesen2 loads savestate via command line with the ROM
echo Starting Mesen2...
start /wait "" "%MESEN_EXE%" --testrunner "%ROM_PATH%" "%LUA_PATH%"

REM Copy output files (Lua script writes to mesen2_exchange/)
echo Collecting output files...
move /y mesen2_exchange\dma_probe_log.txt "%OUTPUT_DIR%\" 2>nul
move /y mesen2_exchange\sprite_capture_*.json "%OUTPUT_DIR%\" 2>nul
move /y mesen2_exchange\test_*.png "%OUTPUT_DIR%\" 2>nul

echo Done: %STATE_NAME%
exit /b 0

:done
echo.
echo ================================================================================
echo Diversity capture complete.
echo Output in: %OUTPUT_BASE%
echo.
echo Next steps:
echo   1. Run cross-reference analysis:
echo      uv run python scripts/cross_reference_oam_dma.py ^
echo          --capture %OUTPUT_BASE%\*\sprite_capture_*.json ^
echo          --dma-log %OUTPUT_BASE%\*\dma_probe_log.txt
echo.
echo   2. Run staging analysis:
echo      uv run python scripts/analyze_snes_dma_staging.py %OUTPUT_BASE%\*\
echo ================================================================================
