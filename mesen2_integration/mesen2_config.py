"""
Configuration and path utilities for Mesen2 integration
"""
from __future__ import annotations

import subprocess
from pathlib import Path

# Mesen2 executable location (relative to mesen2_integration directory)
MESEN_EXE_PATH = "../Mesen2.exe"

def wsl_to_windows_path(wsl_path: str | Path) -> str:
    """Convert WSL path to Windows path using wslpath command

    Args:
        wsl_path: Path in WSL format (e.g., /mnt/c/path/to/file)

    Returns:
        Windows path (e.g., C:\\path\\to\\file)

    Raises:
        subprocess.CalledProcessError: If wslpath command fails
    """
    try:
        result = subprocess.run(
            ["wslpath", "-w", str(wsl_path)],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to convert WSL path {wsl_path}: {e}") from e

def get_mesen_exe_path() -> str:
    """Get the Windows path to Mesen2.exe"""
    # This file is in mesen2_integration/, Mesen2.exe is in parent (spritepal/)
    mesen_path = Path(__file__).parent / MESEN_EXE_PATH  # Changed from parent.parent to parent
    if not mesen_path.exists():
        raise FileNotFoundError(f"Mesen2.exe not found at {mesen_path}")

    return wsl_to_windows_path(mesen_path)

def get_windows_path(local_path: str | Path) -> str:
    """Convert a local path to Windows format for Mesen2

    Args:
        local_path: Path relative to current directory or absolute

    Returns:
        Windows-formatted path
    """
    path = Path(local_path)
    if not path.is_absolute():
        path = Path.cwd() / path

    return wsl_to_windows_path(path)

class MesenConfig:
    """Configuration container for Mesen2 settings"""

    def __init__(self, rom_path: str | None = None):
        self.rom_path = rom_path
        self.mesen_exe = get_mesen_exe_path()

    def validate_rom_path(self) -> None:
        """Ensure ROM path is set and file exists"""
        if not self.rom_path:
            raise ValueError("ROM path not set")

        rom_path = Path(self.rom_path)
        if not rom_path.exists():
            raise FileNotFoundError(f"ROM file not found: {rom_path}")

    def get_testrunner_command(self, lua_script_path: str) -> list[str]:
        """Build command line for Mesen2 testrunner mode

        Args:
            lua_script_path: Path to Lua script to execute

        Returns:
            Command line arguments list
        """
        if not self.rom_path:
            raise ValueError("ROM path must be set before getting command")

        cmd = [
            self.mesen_exe,
            "--testrunner",
            get_windows_path(self.rom_path),
            get_windows_path(lua_script_path)
        ]

        return cmd
