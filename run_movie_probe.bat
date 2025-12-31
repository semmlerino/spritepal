@echo off
REM Run Mesen2 with ROM + Lua, then send the .mmo to the running instance (SingleInstance IPC).
cd /d "C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal"

set MESEN_EXE=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\tools\mesen2\Mesen2.exe
set ROM_PATH=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\roms\Kirby Super Star (USA).sfc
set LUA_PATH=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\mesen2_integration\lua_scripts\mesen2_dma_probe.lua
set MOVIE_PATH=C:\Users\gabri\Documents\Mesen2\Movies\Kirby Super Star (USA).mmo

REM Toggle UI visibility (set to 1 to hide video/audio)
set USE_NOVIDEO=0
set USE_NOAUDIO=0

REM Lua env controls
if "%OUTPUT_DIR%"=="" set OUTPUT_DIR=C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal\mesen2_exchange\movie_probe_run\
if "%MAX_FRAMES%"=="" set MAX_FRAMES=6000
if "%VRAM_DIFF%"=="" set VRAM_DIFF=1
if "%WRAM_DUMP_ON_VRAM_DIFF%"=="" set WRAM_DUMP_ON_VRAM_DIFF=1
if "%WRAM_DUMP_PREV%"=="" set WRAM_DUMP_PREV=1
if "%DMA_DUMP_ON_VRAM%"=="" set DMA_DUMP_ON_VRAM=1
if "%CAPTURE_ON_VRAM_DIFF%"=="" set CAPTURE_ON_VRAM_DIFF=1
if "%CAPTURE_ON_VRAM_DMA%"=="" set CAPTURE_ON_VRAM_DMA=1
if "%CAPTURE_SCREENSHOT%"=="" set CAPTURE_SCREENSHOT=1
if "%CAPTURE_DUMP_VRAM%"=="" set CAPTURE_DUMP_VRAM=0
if "%CAPTURE_TAG_PREFIX%"=="" set CAPTURE_TAG_PREFIX=movie
if "%CAPTURE_START_SECONDS%"=="" set CAPTURE_START_SECONDS=60
if "%CAPTURE_MIN_INTERVAL_SECONDS%"=="" set CAPTURE_MIN_INTERVAL_SECONDS=15
if "%VRAM_DIFF_START_SECONDS%"=="" set VRAM_DIFF_START_SECONDS=60
if "%WRAM_DUMP_START_SECONDS%"=="" set WRAM_DUMP_START_SECONDS=60
if "%DMA_DUMP_START_SECONDS%"=="" set DMA_DUMP_START_SECONDS=60
REM Enable WRAM watch and ROM tracing to discover sprite offsets
if "%WRAM_WATCH_WRITES%"=="" set WRAM_WATCH_WRITES=1
if "%WRAM_WATCH_START%"=="" set WRAM_WATCH_START=0x001E00
if "%WRAM_WATCH_END%"=="" set WRAM_WATCH_END=0x006100
if "%ROM_TRACE_ON_WRAM_WRITE%"=="" set ROM_TRACE_ON_WRAM_WRITE=1
if "%ROM_TRACE_MAX_READS%"=="" set ROM_TRACE_MAX_READS=500
if "%ROM_TRACE_MAX_FRAMES%"=="" set ROM_TRACE_MAX_FRAMES=2
if "%ROM_TRACE_PC_SAMPLES%"=="" set ROM_TRACE_PC_SAMPLES=8

set VIDEO_ARGS=
set AUDIO_ARGS=
if /i "%USE_NOVIDEO%"=="1" set VIDEO_ARGS=--novideo
if /i "%USE_NOAUDIO%"=="1" set AUDIO_ARGS=--noaudio

echo Starting Mesen2 with ROM + Lua...
start "" "%MESEN_EXE%" %AUDIO_ARGS% %VIDEO_ARGS% --enableStdout ^
  "%ROM_PATH%" ^
  "%LUA_PATH%"

echo Waiting for ROM to start...
ping -n 6 127.0.0.1 >NUL

echo Sending movie file to running instance...
start "" "%MESEN_EXE%" "%MOVIE_PATH%"

echo Output: %OUTPUT_DIR%
if /i "%~1"=="--no-pause" goto :eof
pause
