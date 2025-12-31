#!/usr/bin/env python3
"""
Basic test to verify Mesen2 testrunner mode works from Python/WSL
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from mesen2_integration.mesen2_config import MesenConfig


def test_mesen_basic() -> bool:
    """Test basic Mesen2 execution with simple Lua script
    
    Returns:
        True if test passed, False otherwise
    """
    print("Testing Mesen2 basic execution...")

    # Setup paths
    rom_path = Path(__file__).parent.parent / "Kirby Super Star (USA).sfc"
    lua_script = Path(__file__).parent / "lua_scripts" / "simple_test.lua"

    if not Path(rom_path).exists():
        print(f"Error: ROM file not found: {rom_path}")
        return False

    if not lua_script.exists():
        print(f"Error: Lua script not found: {lua_script}")
        return False

    try:
        # Create config and get command
        config = MesenConfig(rom_path=str(rom_path))
        cmd = config.get_testrunner_command(str(lua_script))

        print(f"Executing command: {' '.join(cmd)}")

        # Run Mesen2 - use WSL path for subprocess since we're in WSL
        wsl_cmd = [str(rom_path.parent / "Mesen2.exe"), *cmd[1:]]  # Replace Windows path with WSL path
        start_time = time.time()
        result = subprocess.run(
            wsl_cmd,
            capture_output=True,
            text=True,
            timeout=30  # 30 second timeout
        )
        end_time = time.time()

        print(f"Execution completed in {end_time - start_time:.2f} seconds")
        print(f"Return code: {result.returncode}")

        if result.stdout:
            print("STDOUT:")
            print(result.stdout)

        if result.stderr:
            print("STDERR:")
            print(result.stderr)

        # Check if output file was created in Mesen2's Documents directory
        mesen_docs_path = "/mnt/c/Users/gabri/OneDrive/Dokumente/Mesen2/"
        output_file = Path(mesen_docs_path) / "mesen_test_output.txt"

        if output_file.exists():
            print(f"\nOutput file created successfully at: {output_file}")
            with output_file.open() as f:
                print(f.read())
            output_file.unlink()  # Clean up
            return True
        else:
            # Also check current directory as fallback
            local_output = Path("mesen_test_output.txt")
            if local_output.exists():
                print("\nOutput file found in current directory:")
                with local_output.open() as f:
                    print(f.read())
                local_output.unlink()
                return True
            else:
                print(f"Error: Expected output file not found at {output_file} or current directory")
                return False

    except subprocess.TimeoutExpired:
        print("Error: Mesen2 execution timed out")
        return False
    except Exception as e:
        print(f"Error running Mesen2: {e}")
        return False

if __name__ == "__main__":
    success = test_mesen_basic()
    if success:
        print("\n✓ Mesen2 basic test PASSED")
        sys.exit(0)
    else:
        print("\n✗ Mesen2 basic test FAILED")
        sys.exit(1)
