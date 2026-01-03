@echo off
REM Parameterized ablation runner for automated bisection
REM Usage: run_ablation_range.bat <start_addr> <end_addr>
REM Example: run_ablation_range.bat 0xE9E000 0xE9FFFF
REM
REM Runs headlessly, waits for Mesen2 to complete, then exits.

if "%~1"=="" (
    echo Usage: run_ablation_range.bat ^<start_addr^> ^<end_addr^>
    echo Example: run_ablation_range.bat 0xE9E000 0xE9FFFF
    exit /b 1
)

if "%~2"=="" (
    echo Usage: run_ablation_range.bat ^<start_addr^> ^<end_addr^>
    exit /b 1
)

cd /d "C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal"

set MESEN_EXE=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\tools\mesen2\Mesen2.exe
set ROM_PATH=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\roms\Kirby Super Star (USA).sfc
set LUA_PATH=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\mesen2_integration\lua_scripts\mesen2_dma_probe.lua
set MOVIE_PATH=C:\Users\gabri\Documents\Mesen2\Movies\Kirby Super Star (USA).mmo
set OUTPUT_DIR=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\mesen2_exchange\
set LOG_FILE=%OUTPUT_DIR%dma_probe_log.txt

set MAX_FRAMES=2500

REM Ablation config from arguments
set ABLATION_ENABLED=1
set ABLATION_PRG_START=%~1
set ABLATION_PRG_END=%~2
set ABLATION_VALUE=0xFF

REM Staging config (minimal for bisection)
set STAGING_START_FRAME=1490
set STAGING_WATCH_ENABLED=1
set STAGING_WATCH_START=0x2000
set STAGING_WATCH_END=0x2FFF
set STAGING_WATCH_PC_SAMPLES=4

REM Disable expensive features
set BUFFER_WRITE_WATCH=0
set BUFFER_WRITE_START=0x1530
set BUFFER_WRITE_END=0x161A
set READ_COVERAGE_ENABLED=0
set STAGING_WRAM_SOURCE=0
set STAGING_WRAM_TRACKING=0
set STAGING_CAUSAL_ENABLED=0
set STAGING_PC_GATING=0
set DMA_COMPARE_ENABLED=0
set PERIODIC_CAPTURE_ENABLED=0
set VRAM_DIFF=0
set CAPTURE_ON_VRAM_DIFF=0
set CAPTURE_ON_VRAM_DMA=0

REM Per-CPU ablation (S-CPU only for sprite staging)
set ABLATE_SNES=1
set ABLATE_SA1=0

echo [BISECT] Range: %ABLATION_PRG_START% - %ABLATION_PRG_END%

REM Clear old log completely
if exist "%LOG_FILE%" del /f /q "%LOG_FILE%"
REM Double-check it's gone
if exist "%LOG_FILE%" (
    echo [BISECT] ERROR: Could not delete old log file
    exit /b 1
)

REM Start Mesen2 with ROM + Lua
echo [BISECT] Starting Mesen2...
start "" "%MESEN_EXE%" "%ROM_PATH%" "%LUA_PATH%"

REM Wait for Mesen2 to initialize (6 seconds)
echo [BISECT] Waiting for Mesen2 to initialize...
ping -n 7 127.0.0.1 >NUL

REM Send movie file to running instance
echo [BISECT] Sending movie file...
start "" "%MESEN_EXE%" "%MOVIE_PATH%"

REM Wait for log file to be created first
echo [BISECT] Waiting for log file...
:wait_log_exists
ping -n 2 127.0.0.1 >NUL
if not exist "%LOG_FILE%" goto wait_log_exists

REM Now wait for actual gameplay data (STAGING_SUMMARY or frame=2000+)
echo [BISECT] Waiting for gameplay to complete...
:wait_gameplay
ping -n 3 127.0.0.1 >NUL
findstr /c:"MAX_FRAMES" "%LOG_FILE%" >NUL 2>&1
if errorlevel 1 goto wait_gameplay

REM Give it a moment to finish writing
ping -n 2 127.0.0.1 >NUL

REM Close Mesen2 so next iteration can start clean
echo [BISECT] Closing Mesen2...
taskkill /IM Mesen2.exe /F >NUL 2>&1
ping -n 2 127.0.0.1 >NUL

echo [BISECT] Complete
exit /b 0
