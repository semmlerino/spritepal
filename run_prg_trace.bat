@echo off
REM PRG Read Tracer - Log ROM reads following causal byte
REM Usage: run_prg_trace.bat [target_addr]
REM
REM Examples:
REM   run_prg_trace.bat             - Trace default 0xE9E667
REM   run_prg_trace.bat 0xE93AEB    - Trace 0xE93AEB

cd /d "C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal"

set MESEN_EXE=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\tools\mesen2\Mesen2.exe
set ROM_PATH=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\roms\Kirby Super Star (USA).sfc
set LUA_PATH=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\mesen2_integration\lua_scripts\prg_read_tracer.lua
set MOVIE_PATH=C:\Users\gabri\Documents\Mesen2\Movies\Kirby Super Star (USA).mmo
set OUTPUT_DIR=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\mesen2_exchange\
set LOG_FILE=%OUTPUT_DIR%dma_probe_log.txt

REM Default target address
set TARGET_ADDR=0xE9E667
if not "%~1"=="" set TARGET_ADDR=%~1

set MAX_FRAMES=1900
set TRACE_LIMIT=100

echo [PRG_TRACE] Tracing ROM reads following %TARGET_ADDR%...

REM Clear old log
if exist "%LOG_FILE%" del /f /q "%LOG_FILE%"

echo [PRG_TRACE] Starting Mesen2...
start "" "%MESEN_EXE%" "%ROM_PATH%" "%LUA_PATH%"
ping -n 7 127.0.0.1 >NUL

echo [PRG_TRACE] Sending movie file...
start "" "%MESEN_EXE%" "%MOVIE_PATH%"

echo [PRG_TRACE] Waiting for traces...
:wait_trace
ping -n 2 127.0.0.1 >NUL
findstr /c:"MAX_FRAMES" "%LOG_FILE%" >NUL 2>&1
if errorlevel 1 goto wait_trace

ping -n 2 127.0.0.1 >NUL

echo [PRG_TRACE] Closing Mesen2...
taskkill /IM Mesen2.exe /F >NUL 2>&1
ping -n 2 127.0.0.1 >NUL

echo [PRG_TRACE] Complete - check mesen2_exchange for prg_trace_%TARGET_ADDR:~2%.log
echo.
echo Quick analysis hints:
echo   - Index: Sequential reads from nearby table
echo   - Opcode: Few reads, then branch to far address
echo   - Pointer: Read 2-3 bytes, then jump to computed address
echo   - Length: Sequential streaming of N bytes
