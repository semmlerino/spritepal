#!/usr/bin/env python3
"""Test if Mesen2 executes Lua scripts"""

import subprocess
from pathlib import Path

base_dir = Path(__file__).parent.absolute()
mesen_exe = base_dir / ".." / "Mesen2.exe"
rom_path = base_dir / ".." / "Kirby Super Star (USA).sfc"
lua_script = base_dir / "lua_scripts" / "simple_test.lua"
log_path = Path("C:/Users/gabri/OneDrive/Dokumente/Mesen2/simple_test_log.txt")


def wsl_to_windows_path(wsl_path: Path) -> str:
    """Convert WSL path to Windows path"""
    result = subprocess.run(["wslpath", "-w", str(wsl_path)], capture_output=True, text=True, check=True)
    return result.stdout.strip()


# Convert paths for Windows
mesen_win = wsl_to_windows_path(mesen_exe)
rom_win = wsl_to_windows_path(rom_path)
lua_win = wsl_to_windows_path(lua_script)

# Try running Mesen2 with the simple test script
print("Testing Lua script execution...")
print(f"Mesen2: {mesen_win}")
print(f"ROM: {rom_win}")
print(f"Script: {lua_win}")

# Clear previous log
if log_path.exists():
    log_path.unlink()

# Run with minimal options - try using WSL paths directly
# Mesen2.exe should be able to be called directly from WSL
cmd = [
    str(mesen_exe),  # Use WSL path
    str(rom_path),  # Use WSL path
    "--testrunner",
    "10",
    "--script",
    str(lua_script),  # Use WSL path
]
print(f"\nCommand (WSL paths): {' '.join(cmd)}")

# Try direct execution from WSL
try:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
except FileNotFoundError:
    # If direct execution fails, try with cmd.exe
    print("Direct execution failed, trying cmd.exe...")
    cmd_str = f'"{mesen_win}" "{rom_win}" --testrunner 10 --script "{lua_win}"'
    result = subprocess.run(f"cmd.exe /c {cmd_str}", shell=True, capture_output=True, text=True, timeout=10)

print(f"Return code: {result.returncode}")
if result.stdout:
    print(f"Stdout: {result.stdout[:500]}")
if result.stderr:
    print(f"Stderr: {result.stderr[:500]}")

# Check if log was created
if log_path.exists():
    print("\nSUCCESS: Log file created!")
    with open(log_path) as f:
        print("Log contents:")
        print(f.read())
else:
    print("\nERROR: No log file created - Lua script may not be executing")
