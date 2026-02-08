@echo off
cd /d "%~dp0"

set MESEN_EXE=.\tools\mesen2\Mesen2.exe
set ROM_PATH=roms\Kirby Super Star (USA).sfc
set LUA_PATH=mesen2_integration\lua_scripts\mesen2_sprite_capture.lua
set MOVIE_PATH=C:\Users\gabri\Documents\Mesen2\Movies\HeavyLobster.mmo

echo ========================================
echo FULL SPRITE CAPTURE (for Assembly)
echo ========================================
echo.
echo Press F9 when Heavy Lobster is fully visible
echo to capture ALL OAM entries with positions!
echo.
echo This captures:
echo   - X, Y position of each sprite part
echo   - Width, Height of each part
echo   - Tile index and flip flags
echo   - Full VRAM tile data
echo   - Palette colors
echo.
echo Output: mesen2_exchange\sprite_capture_*.json
echo.
echo Starting Mesen2...
echo ========================================

start "" "%MESEN_EXE%" --enableStdout "%ROM_PATH%" "%LUA_PATH%"
ping -n 4 127.0.0.1 >NUL
start "" "%MESEN_EXE%" "%MOVIE_PATH%"

echo.
echo When Heavy Lobster appears, PAUSE the game and press F9!
echo.
