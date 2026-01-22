#!/usr/bin/env python3
"""
Test enhanced DMA logger to capture detailed transfer information
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from mesen2_integration.mesen2_config import MesenConfig


def test_enhanced_dma():
    """Run enhanced DMA logger"""
    print("Running enhanced DMA logger...")

    # Setup paths
    rom_path = str(Path(__file__).parent.parent / "Kirby Super Star (USA).sfc")
    lua_script = Path(__file__).parent / "lua_scripts" / "minimal_vram.lua"

    config = MesenConfig(rom_path=rom_path)
    cmd = config.get_testrunner_command(str(lua_script))
    wsl_cmd = [str(Path(__file__).parent.parent / "Mesen2.exe"), *cmd[1:]]

    print("Executing enhanced DMA logger...")
    print("This will capture detailed information about all VRAM transfers")

    # Run with timeout
    result = subprocess.run(
        wsl_cmd,
        capture_output=True,
        text=True,
        timeout=45,  # Give more time for detailed logging
    )

    print(f"Return code: {result.returncode}")

    if result.stdout:
        # Show key output lines
        lines = result.stdout.splitlines()
        rom_sprites = [line for line in lines if "ROM SPRITE:" in line]
        wram_sprites = [line for line in lines if "WRAM SPRITE:" in line]

        print("\nKey findings:")
        print(f"  ROM sprite transfers: {len(rom_sprites)}")
        print(f"  WRAM sprite transfers: {len(wram_sprites)}")

        if rom_sprites:
            print("\nFirst few ROM sprite transfers:")
            for line in rom_sprites[:5]:
                print(f"  {line}")

        if wram_sprites:
            print(f"\nWRAM transfers detected: {len(wram_sprites)}")

    # Check minimal VRAM log file
    enhanced_log = Path("/mnt/c/Users/gabri/OneDrive/Dokumente/Mesen2/minimal_vram.txt")
    if enhanced_log.exists():
        print("\nEnhanced log created successfully")

        # Parse log for summary
        with enhanced_log.open() as f:
            content = f.read()

        rom_successes = content.count("ROM_OFFSET: $")
        wram_transfers = content.count("WRAM range")
        total_transfers = content.count("TRANSFER_")

        print("Summary from log file:")
        print(f"  Total transfers: {total_transfers}")
        print(f"  Successful ROM conversions: {rom_successes}")
        print(f"  WRAM transfers (compressed): {wram_transfers}")

        if rom_successes > 0:
            print(f"\n✓ SUCCESS: Found {rom_successes} ROM sprite offsets!")
            # Extract ROM offsets
            import re

            rom_offsets = re.findall(r"ROM_OFFSET: \$([0-9A-Fa-f]+)", content)
            if rom_offsets:
                unique_offsets = sorted(set(rom_offsets))[:10]  # First 10 unique
                print("First ROM offsets found:")
                for offset in unique_offsets:
                    print(f"  0x{offset}")
        else:
            print("No direct ROM->VRAM transfers found")
            if wram_transfers > 0:
                print("However, compressed sprites via WRAM were detected")
    else:
        print("Enhanced log file not found")


if __name__ == "__main__":
    test_enhanced_dma()
