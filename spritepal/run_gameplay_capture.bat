@echo off
REM Capture sprites during actual gameplay (30 seconds, Spring Breeze)
cd /d "C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal"
echo Running Mesen 2 gameplay capture...
echo This will take ~30 seconds to navigate to gameplay
echo Output: mesen2_exchange\gameplay_capture.json
echo.
.\tools\mesen2\Mesen2.exe --testrunner "roms\Kirby Super Star (USA).sfc" "mesen2_integration\lua_scripts\gameplay_capture.lua"
echo.
echo Capture complete!
echo Now run: uv run python scripts/extract_sprite_from_capture.py mesen2_exchange/gameplay_capture.json
pause
