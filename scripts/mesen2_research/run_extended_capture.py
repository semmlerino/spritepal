#!/usr/bin/env python3
"""
Launch extended Mesen2 sprite capture session
"""

import subprocess
import sys
from pathlib import Path

from mesen2_config import get_mesen_executable, wsl_to_windows_path


def run_extended_capture():
    """Run extended sprite capture session"""
    print("=== LAUNCHING EXTENDED MESEN2 SPRITE CAPTURE ===")

    # Get paths
    mesen_exe = get_mesen_executable()
    rom_path = wsl_to_windows_path("../Kirby Super Star (USA).sfc")
    lua_script_path = wsl_to_windows_path("lua_scripts/extended_sprite_capture.lua")

    print(f"Mesen2: {mesen_exe}")
    print(f"ROM: {rom_path}")
    print(f"Script: {lua_script_path}")

    if not Path("../Kirby Super Star (USA).sfc").exists():
        print("❌ ROM file not found")
        return 1

    if not Path("lua_scripts/extended_sprite_capture.lua").exists():
        print("❌ Lua script not found")
        return 1

    # Extended capture configuration
    print("\\n📊 CAPTURE CONFIGURATION:")
    print("• Duration: 5 minutes (18,000 frames)")
    print("• Input phases: 12 diverse gameplay scenarios")
    print("• Target: 100+ runtime sprite offsets")
    print("• Output: Timestamped capture file")

    # Build command
    cmd = [mesen_exe, "--testrunner", rom_path, "--testScript", lua_script_path]

    print("\\n🚀 Starting extended capture...")
    print("This will run for 5 minutes with automated gameplay")
    print("Progress updates every 30 seconds")

    try:
        # Run with real-time output
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True
        )

        for line_count, line in enumerate(process.stdout, 1):
            # Print important progress lines
            if any(
                keyword in line
                for keyword in [
                    "PHASE",
                    "PROGRESS",
                    "NEW ROM SPRITE",
                    "NEW WRAM SPRITE",
                    "EXTENDED CAPTURE",
                    "ROM offsets found",
                    "✓",
                ]
            ):
                print(f"[{line_count:4d}] {line.strip()}")
            elif line_count % 50 == 0:  # Print every 50th line to show activity
                print(f"[{line_count:4d}] {line.strip()[:80]}...")

        process.wait()

        if process.returncode == 0:
            print("\\n✅ EXTENDED CAPTURE COMPLETED SUCCESSFULLY")

            # Check for output file
            capture_files = list(
                Path("/mnt/c/Users/gabri/OneDrive/Dokumente/Mesen2/LuaScriptData/Example").glob("sprite_capture_*.txt")
            )
            if capture_files:
                latest_file = max(capture_files, key=lambda x: Path(x).stat().st_mtime)
                print(f"📄 Latest capture file: {Path(latest_file).name}")

                # Quick analysis
                try:
                    with open(latest_file) as f:
                        content = f.read()

                    import re

                    capture_time = re.search(r"Capture Time: ([0-9.]+) seconds", content)
                    rom_offsets = re.search(r"ROM Offsets Found: (\\d+)", content)
                    sprites_captured = re.search(r"Sprites Captured: (\\d+)/(\\d+)", content)

                    if capture_time:
                        print(f"⏱️  Actual capture time: {capture_time.group(1)} seconds")
                    if rom_offsets:
                        print(f"🎯 ROM offsets discovered: {rom_offsets.group(1)}")
                    if sprites_captured:
                        print(f"📈 Sprites captured: {sprites_captured.group(1)}/{sprites_captured.group(2)}")

                except Exception as e:
                    print(f"Note: Could not analyze capture file: {e}")

            return 0
        else:
            print(f"\\n❌ CAPTURE FAILED (return code: {process.returncode})")
            return process.returncode

    except Exception as e:
        print(f"\\n❌ ERROR RUNNING CAPTURE: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(run_extended_capture())
