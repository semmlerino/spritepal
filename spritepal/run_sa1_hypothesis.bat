@echo off
REM SA-1 Hypothesis Verification Runner
REM Uses the existing mesen2_dma_probe.lua with movie playback to capture SA-1 register data.
REM
REM This follows the same pattern as run_movie_probe.bat (which works reliably).
cd /d "C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal"

set MESEN_EXE=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\tools\mesen2\Mesen2.exe
set ROM_PATH=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\roms\Kirby Super Star (USA).sfc
set LUA_PATH=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\mesen2_integration\lua_scripts\mesen2_dma_probe.lua
set MOVIE_PATH=C:\Users\gabri\Documents\Mesen2\Movies\Kirby Super Star (USA).mmo

REM Create unique output directory for this hypothesis run
for /f "tokens=2-4 delims=/ " %%a in ('date /t') do (set "mydate=%%c%%a%%b")
for /f "tokens=1-2 delims=: " %%a in ('time /t') do (set "mytime=%%a%%b")
set OUTPUT_DIR=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\mesen2_exchange\sa1_hypothesis_run_%mydate%_%mytime%\

REM Focus settings for SA-1 hypothesis verification
REM Run for 10000 frames (~2.75 minutes at 60fps) with minimal other logging
set MAX_FRAMES=10000

REM Disable heavy logging that isn't needed for SA-1 hypothesis
set VRAM_DIFF=0
set WRAM_DUMP_ON_VRAM_DIFF=0
set WRAM_DUMP_PREV=0
set DMA_DUMP_ON_VRAM=0
set CAPTURE_ON_VRAM_DIFF=0
set CAPTURE_ON_VRAM_DMA=0
set CAPTURE_SCREENSHOT=0
set CAPTURE_DUMP_VRAM=0
set WRAM_WATCH_WRITES=0
set ROM_TRACE_ON_WRAM_WRITE=0

REM Keep these settings - SA-1 register writes will still be logged
set HEARTBEAT_EVERY=1000
set CAPTURE_TAG_PREFIX=sa1_hyp

REM Skip intro/title - start monitoring at 60 seconds
set CAPTURE_START_SECONDS=0
set VRAM_DIFF_START_SECONDS=0
set WRAM_DUMP_START_SECONDS=0
set DMA_DUMP_START_SECONDS=0

REM Show UI for verification
set USE_NOVIDEO=0
set USE_NOAUDIO=0

echo ================================================================================
echo SA-1 Conversion Hypothesis Verification
echo ================================================================================
echo.
echo This run will capture SA-1 register writes during movie playback.
echo.
echo Output: %OUTPUT_DIR%
echo Frames: %MAX_FRAMES% (~2.75 minutes)
echo.
echo The dma_probe_log.txt will contain SA1 DMA entries like:
echo   SA1 DMA (ctrl_write): ctrl=0xXX enabled=Y/N char_conv=Y/N auto=Y/N
echo.
echo Look for "char_conv=Y" entries - these indicate character conversion is active.
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
echo When complete, check:
echo   %OUTPUT_DIR%dma_probe_log.txt
echo.
echo Search for "char_conv=Y" to verify hypothesis.
echo.
if /i "%~1"=="--no-pause" goto :eof
pause
