@echo off
cd /d "C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal"
echo Starting Mesen2 test...
tools\mesen2\Mesen2.exe --testrunner "roms\Kirby Super Star (USA).sfc" "mesen2_integration\lua_scripts\minimal_test.lua"
echo Exit code: %errorlevel%
echo.
echo Checking for output file...
if exist minimal_test_output.txt (
    echo Output file found:
    type minimal_test_output.txt
) else (
    echo Output file NOT found
)
pause
