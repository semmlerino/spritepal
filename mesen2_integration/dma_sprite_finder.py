#!/usr/bin/env python3
"""
DMA-based sprite offset finder using Mesen2 automation
Launches Mesen2 with DMA monitoring Lua script to discover ROM sprite offsets
"""
from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path
from typing import NamedTuple

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from mesen2_integration.mesen2_config import MesenConfig


class DMATransfer(NamedTuple):
    """Represents a DMA transfer discovered by Mesen2"""
    rom_offset: int
    snes_address: int | None = None
    length: int | None = None
    channel: int | None = None
    is_wram: bool = False

class DMASpriteFinder:
    """Finds sprite offsets using Mesen2 DMA monitoring"""

    def __init__(self, rom_path: str):
        self.config = MesenConfig(rom_path=rom_path)
        self.config.validate_rom_path()
        self.mesen_docs_path = Path("/mnt/c/Users/gabri/OneDrive/Dokumente/Mesen2/")

    def run_dma_scan(self, max_runtime_seconds: int = 30) -> list[DMATransfer]:
        """
        Run Mesen2 with DMA monitoring to discover sprite offsets

        Args:
            max_runtime_seconds: Maximum time to run scan

        Returns:
            List of DMA transfers found
        """
        print("Starting DMA-based sprite offset discovery...")

        # Setup paths
        lua_script = Path(__file__).parent / "lua_scripts" / "dma_logger.lua"
        log_file = self.mesen_docs_path / "dma_log.txt"

        # Clean up any existing log
        if log_file.exists():
            log_file.unlink()

        try:
            # Get command and run Mesen2
            cmd = self.config.get_testrunner_command(str(lua_script))
            wsl_cmd = [str(Path(__file__).parent.parent / "Mesen2.exe"), *cmd[1:]]

            print(f"Executing: {' '.join(cmd[:2])} <ROM> <script>")
            print(f"Max runtime: {max_runtime_seconds} seconds")

            # Run with timeout
            start_time = time.time()
            result = subprocess.run(
                wsl_cmd,
                check=False, capture_output=True,
                text=True,
                timeout=max_runtime_seconds + 10  # Extra buffer for shutdown
            )
            end_time = time.time()

            print(f"Mesen2 execution completed in {end_time - start_time:.2f} seconds")
            print(f"Return code: {result.returncode}")

            if result.stdout:
                print("Mesen2 output:")
                for line in result.stdout.splitlines():
                    if "VRAM DMA" in line or "ERROR" in line:
                        print(f"  {line}")

            if result.stderr:
                print("Errors:")
                print(result.stderr)

            # Parse the log file
            transfers = self._parse_dma_log(log_file)
            print(f"\nFound {len(transfers)} DMA transfers:")

            # Group and display results
            rom_transfers = [t for t in transfers if not t.is_wram]
            wram_transfers = [t for t in transfers if t.is_wram]

            if rom_transfers:
                print(f"  {len(rom_transfers)} ROM->VRAM transfers (sprite candidates)")
                for t in rom_transfers[:10]:  # Show first 10
                    print(f"    ROM 0x{t.rom_offset:06X} -> VRAM ({t.length} bytes)")
                if len(rom_transfers) > 10:
                    print(f"    ... and {len(rom_transfers) - 10} more")

            if wram_transfers:
                print(f"  {len(wram_transfers)} WRAM->VRAM transfers (decompressed data)")

            return transfers

        except subprocess.TimeoutExpired:
            print(f"Scan timed out after {max_runtime_seconds} seconds")
            # Still try to parse partial results
            if log_file.exists():
                transfers = self._parse_dma_log(log_file)
                print(f"Partial results: {len(transfers)} transfers found")
                return transfers
            return []

        except Exception as e:
            print(f"Error during DMA scan: {e}")
            return []

    def _parse_dma_log(self, log_file: Path) -> list[DMATransfer]:
        """Parse the DMA log file created by Lua script"""
        if not log_file.exists():
            print(f"Warning: DMA log file not found at {log_file}")
            return []

        transfers = []

        try:
            with log_file.open() as f:
                content = f.read()

            # Parse ROM offset entries
            rom_pattern = r'ROM_OFFSET:0x([0-9A-Fa-f]+)'
            detail_pattern = r'SNES_ADDR:0x([0-9A-Fa-f]+)\s+LENGTH:(\d+)\s+CHANNEL:(\d+)'
            wram_pattern = r'WRAM_TRANSFER:0x([0-9A-Fa-f]+)'

            lines = content.splitlines()
            i = 0

            while i < len(lines):
                line = lines[i].strip()

                # Check for ROM offset
                rom_match = re.search(rom_pattern, line)
                if rom_match:
                    rom_offset = int(rom_match.group(1), 16)

                    # Look for details on next line
                    snes_addr = None
                    length = None
                    channel = None

                    if i + 1 < len(lines):
                        detail_match = re.search(detail_pattern, lines[i + 1])
                        if detail_match:
                            snes_addr = int(detail_match.group(1), 16)
                            length = int(detail_match.group(2))
                            channel = int(detail_match.group(3))
                            i += 1  # Skip detail line

                    transfers.append(DMATransfer(
                        rom_offset=rom_offset,
                        snes_address=snes_addr,
                        length=length,
                        channel=channel,
                        is_wram=False
                    ))

                # Check for WRAM transfer
                wram_match = re.search(wram_pattern, line)
                if wram_match:
                    wram_addr = int(wram_match.group(1), 16)

                    # WRAM transfers indicate compressed sprites - record for future analysis
                    transfers.append(DMATransfer(
                        rom_offset=wram_addr,  # Store WRAM address in rom_offset field
                        is_wram=True
                    ))

                i += 1

            # Remove duplicates while preserving order
            seen = set()
            unique_transfers = []
            for t in transfers:
                key = (t.rom_offset, t.is_wram)
                if key not in seen:
                    seen.add(key)
                    unique_transfers.append(t)

            return unique_transfers

        except Exception as e:
            print(f"Error parsing DMA log: {e}")
            return []

def main():
    """Test the DMA sprite finder"""
    if len(sys.argv) > 1:
        rom_path = sys.argv[1]
    else:
        rom_path = str(Path(__file__).parent.parent / "Kirby Super Star (USA).sfc")

    if not Path(rom_path).exists():
        print(f"Error: ROM file not found: {rom_path}")
        return 1

    finder = DMASpriteFinder(rom_path)
    transfers = finder.run_dma_scan(max_runtime_seconds=30)

    # Save results for further analysis
    if transfers:
        output_file = Path("dma_discovered_offsets.txt")
        with output_file.open("w") as f:
            f.write("DMA Sprite Offset Discovery Results\n")
            f.write(f"ROM: {rom_path}\n")
            f.write(f"Found: {len(transfers)} transfers\n")
            f.write(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            rom_transfers = [t for t in transfers if not t.is_wram]
            if rom_transfers:
                f.write("ROM->VRAM Transfers (Sprite Candidates):\n")
                for t in rom_transfers:
                    f.write(f"0x{t.rom_offset:06X}")
                    if t.length:
                        f.write(f" ({t.length} bytes)")
                    f.write("\n")

        print(f"\nResults saved to: {output_file}")

        # Show unique ROM offsets for easy use
        rom_offsets = [t.rom_offset for t in transfers if not t.is_wram]
        if rom_offsets:
            print(f"\nUnique ROM offsets found: {len(rom_offsets)}")
            print("Offsets:", ", ".join(f"0x{offset:06X}" for offset in sorted(set(rom_offsets))[:20]))

        return 0
    print("No DMA transfers found")
    return 1

if __name__ == "__main__":
    sys.exit(main())
