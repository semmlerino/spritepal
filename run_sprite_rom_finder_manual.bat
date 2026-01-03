@echo off
cd /d "C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal"

set MESEN_EXE=.\tools\mesen2\Mesen2.exe
set ROM_PATH=roms\Kirby Super Star (USA).sfc
set LUA_PATH=mesen2_integration\lua_scripts\sprite_rom_finder.lua

echo ========================================
echo SPRITE ROM FINDER v6 (Manual Play)
echo ========================================
echo.
echo LEFT-CLICK on sprite = lookup ROM offset
echo RIGHT-CLICK = clear panel
echo.
echo Play normally, pause when you see your target sprite,
echo then click on it to get the ROM offset.
echo.
echo Starting Mesen2...
echo ========================================

start "" "%MESEN_EXE%" --enableStdout "%ROM_PATH%" "%LUA_PATH%"

echo.
echo Output log: mesen2_exchange\sprite_rom_finder.log
