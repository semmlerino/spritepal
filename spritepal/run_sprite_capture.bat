@echo off
REM Run Mesen 2 in testrunner mode to auto-capture sprites
cd /d "C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal"
echo Running Mesen 2 sprite capture...
echo Output will be in mesen2_exchange\test_capture.json
echo.
.\tools\mesen2\Mesen2.exe --testrunner "roms\Kirby Super Star (USA).sfc" "mesen2_integration\lua_scripts\test_sprite_capture.lua"
echo.
echo Capture complete! Check mesen2_exchange\ for output files.
pause
