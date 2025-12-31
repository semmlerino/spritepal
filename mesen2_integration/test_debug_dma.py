#!/usr/bin/env python3
"""
Test debug DMA logger to diagnose issues
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from mesen2_integration.mesen2_config import MesenConfig


def test_debug_dma():
    """Run debug DMA script"""
    print("Running debug DMA logger...")

    # Setup paths
    rom_path = str(Path(__file__).parent.parent / "Kirby Super Star (USA).sfc")
    lua_script = Path(__file__).parent / "lua_scripts" / "debug_dma.lua"

    config = MesenConfig(rom_path=rom_path)
    cmd = config.get_testrunner_command(str(lua_script))
    wsl_cmd = [str(Path(__file__).parent.parent / "Mesen2.exe"), *cmd[1:]]

    print(f"Executing: {' '.join(cmd[:2])} <ROM> <debug_script>")

    # Run with timeout
    result = subprocess.run(
        wsl_cmd,
        capture_output=True,
        text=True,
        timeout=30
    )

    print(f"Return code: {result.returncode}")

    if result.stdout:
        print("Output:")
        print(result.stdout)

    if result.stderr:
        print("Errors:")
        print(result.stderr)

    # Check debug log
    debug_log = Path("/mnt/c/Users/gabri/OneDrive/Dokumente/Mesen2/debug_log.txt")
    if debug_log.exists():
        print("\nDebug log contents:")
        with debug_log.open() as f:
            print(f.read())
    else:
        print("Debug log not found")

if __name__ == "__main__":
    test_debug_dma()
