@echo off
REM Capture sprites during actual gameplay (starting frame 2000, every 30 seconds)
cd /d "C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal"
echo Running Mesen 2 gameplay multi-capture...
echo Starting at frame 2000 (after menus/cutscenes)
echo Capturing every 30 seconds (1800 frames), up to 10 captures
echo Output: mesen2_exchange\gameplay_frame_*.png + gameplay_capture_frame_*.json
echo.
.\tools\mesen2\Mesen2.exe --testrunner "roms\Kirby Super Star (USA).sfc" "mesen2_integration\lua_scripts\gameplay_multi_capture.lua"
echo.
echo Capture complete!
echo Now run: uv run python scripts/run_full_correlation.py --rom "roms\Kirby Super Star (USA).sfc" --dma-log mesen2_exchange --capture "mesen2_exchange\gameplay_capture_frame_*.json" --scan-rom
pause
