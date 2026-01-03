@echo off
cd /d "C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal"

set MESEN_EXE=.\tools\mesen2\Mesen2.exe
set ROM_PATH=roms\Kirby Super Star (USA).sfc
set LUA_PATH=mesen2_integration\lua_scripts\sprite_rom_finder.lua
set MOVIE_PATH=C:\Users\gabri\Documents\Mesen2\Movies\Kirby Super Star (USA).mmo

echo ========================================
echo SPRITE ROM FINDER v7 (Movie Mode)
echo ========================================
echo.
echo LEFT-CLICK on sprite = lookup ROM offset
echo RIGHT-CLICK = clear panel
echo.
echo Usage:
echo   1. Wait for movie to reach gameplay
echo   2. Pause (Space/P) when target sprite visible
echo   3. Click on the sprite
echo   4. Panel shows idx + file offset
echo   5. Console shows: --offset 0xNNNNNN
echo.
echo Starting Mesen2...
echo ========================================

start "" "%MESEN_EXE%" --enableStdout "%ROM_PATH%" "%LUA_PATH%"
ping -n 4 127.0.0.1 >NUL
start "" "%MESEN_EXE%" "%MOVIE_PATH%"

echo.
echo Output log: mesen2_exchange\sprite_rom_finder.log
