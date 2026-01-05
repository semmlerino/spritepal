#!/usr/bin/env python3
"""
Mushroom Sprite Finder
Traces a visible mushroom sprite back to its ROM offset using savestate analysis
"""

import re
import subprocess
from pathlib import Path


class MushroomSpriteFinder:
    def __init__(self):
        self.base_dir = Path(__file__).parent.absolute()
        self.mesen_exe = self.base_dir / ".." / "Mesen2.exe"
        self.rom_path = self.base_dir / ".." / "Kirby Super Star (USA).sfc"
        self.lua_script = self.base_dir / "lua_scripts" / "mushroom_sprite_tracker.lua"
        self.log_path = Path("C:/Users/gabri/OneDrive/Dokumente/Mesen2/mushroom_sprite_log.txt")

        # Savestate paths
        self.before_savestate = self.base_dir / ".." / "Before.mss"
        self.entering_savestate = self.base_dir / ".." / "Entering.mss"
        self.sprite_savestate = self.base_dir / ".." / "Sprite.mss"

    def wsl_to_windows_path(self, wsl_path: Path) -> str:
        """Convert WSL path to Windows path"""
        result = subprocess.run(["wslpath", "-w", str(wsl_path)], capture_output=True, text=True, check=True)
        return result.stdout.strip()

    def run_transition_test(self) -> dict | None:
        """Run the door transition test to find mushroom sprite ROM offset"""

        print("=== Mushroom Sprite Finder ===")
        print(f"ROM: {self.rom_path.name}")
        print(f"Savestate: {self.before_savestate.name}")
        print("Target VRAM: $6A00 (mushroom sprite location)")
        print()

        # Convert paths for Windows
        mesen_win = self.wsl_to_windows_path(self.mesen_exe)
        rom_win = self.wsl_to_windows_path(self.rom_path)
        lua_win = self.wsl_to_windows_path(self.lua_script)
        before_win = self.wsl_to_windows_path(self.before_savestate)

        # Build Mesen2 command
        # We'll run for ~300 frames to capture the door transition
        # Input format: P1,P2,P3,P4|frame1_inputs,frame2_inputs...
        input_str = ",,|,Up,Up,Up,Up,Up,Up,Up,Up,Up,Up"  # Press Up to go through door

        cmd = [
            mesen_win,
            rom_win,
            "--testrunner",
            "300",
            "--loadstate",
            before_win,
            "--script",
            lua_win,
            "--input",
            input_str,
        ]

        print("Starting Mesen2 with mushroom tracker...")
        print(f"Command: {' '.join(cmd)}")
        print()

        # Clear previous log
        if self.log_path.exists():
            self.log_path.unlink()

        # Run Mesen2 via cmd.exe
        # Need to quote arguments properly for Windows
        cmd_parts = []
        for arg in cmd:
            if " " in arg or "," in arg or "|" in arg:
                cmd_parts.append(f'"{arg}"')
            else:
                cmd_parts.append(arg)
        cmd_str = " ".join(cmd_parts)
        full_cmd = ["cmd.exe", "/c", cmd_str]

        try:
            result = subprocess.run(full_cmd, check=False, capture_output=True, text=True, timeout=30)
            print("Mesen2 execution completed")
            if result.returncode != 0:
                print(f"Mesen2 returned code: {result.returncode}")
                if result.stderr:
                    print(f"Stderr: {result.stderr[:500]}")
                if result.stdout:
                    print(f"Stdout: {result.stdout[:500]}")
        except subprocess.TimeoutExpired:
            print("Mesen2 execution timed out (this is normal)")

        # Parse the log file
        return self.parse_mushroom_log()

    def parse_mushroom_log(self) -> dict | None:
        """Parse the mushroom sprite log to find ROM offsets"""

        if not self.log_path.exists():
            print("ERROR: Log file not found!")
            return None

        print("\nParsing mushroom sprite log...")

        with open(self.log_path) as f:
            content = f.read()

        # Look for mushroom DMA detections
        pattern = (
            r"MUSHROOM SPRITE DMA DETECTED.*?ROM Offset: \$([0-9A-F]+).*?VRAM Target: \$([0-9A-F]+).*?Size: (\d+) bytes"
        )
        matches = re.findall(pattern, content, re.DOTALL)

        if not matches:
            print("No mushroom sprite DMA transfers detected!")
            print("\nLog content:")
            print(content[:2000])  # Show first part of log
            return None

        print(f"\nFound {len(matches)} mushroom sprite transfers:")

        transfers = []
        for i, (rom_offset, vram_addr, size) in enumerate(matches, 1):
            rom_offset_int = int(rom_offset, 16)
            vram_addr_int = int(vram_addr, 16)
            size_int = int(size)

            print(f"{i}. ROM ${rom_offset} -> VRAM ${vram_addr} ({size_int} bytes)")

            transfers.append({"rom_offset": rom_offset_int, "vram_addr": vram_addr_int, "size": size_int})

        # Return the first transfer (likely the main sprite data)
        if transfers:
            primary = transfers[0]
            print(f"\nPrimary mushroom sprite location: ROM offset ${primary['rom_offset']:06X}")
            return primary

        return None

    def extract_sprite(self, rom_offset: int) -> bool:
        """Extract the sprite at the discovered ROM offset"""

        print(f"\n=== Extracting Sprite from ROM Offset ${rom_offset:06X} ===")

        # Use exhal to decompress
        exhal_exe = self.base_dir / ".." / "exhal.exe"
        exhal_win = self.wsl_to_windows_path(exhal_exe)
        rom_win = self.wsl_to_windows_path(self.rom_path)

        # Output file for decompressed data
        output_file = self.base_dir / f"mushroom_sprite_{rom_offset:06X}.bin"
        output_win = self.wsl_to_windows_path(output_file)

        cmd = [exhal_win, rom_win, str(rom_offset), output_win]

        print(f"Running exhal: {' '.join(cmd)}")

        try:
            result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=10)

            if result.returncode == 0:
                print("Successfully decompressed sprite data!")

                # Check output file size
                if output_file.exists():
                    size = output_file.stat().st_size
                    print(f"Decompressed size: {size} bytes")

                    # For a 16x16 sprite in 4bpp, we expect ~128 bytes
                    if size >= 128:
                        print("✓ Size matches expected mushroom sprite!")

                        # Now use SpritePal to extract as image
                        self.extract_as_image(rom_offset)
                        return True
                    print(f"Warning: Size {size} is smaller than expected for 16x16 sprite")
            else:
                print(f"Exhal failed: {result.stderr}")

        except Exception as e:
            print(f"Error running exhal: {e}")

        return False

    def extract_as_image(self, rom_offset: int):
        """Use SpritePal's ROMExtractor to extract sprite as image"""

        print("\n=== Extracting Sprite as Image ===")

        # Import SpritePal components
        import sys

        sys.path.insert(0, str(self.base_dir / ".."))

        from core.rom_extractor import ROMExtractor

        extractor = ROMExtractor(str(self.rom_path))

        # Extract with different tile counts to find the right size
        for tile_count in [4, 8, 16, 32]:
            try:
                sprite_data = extractor.extract_sprite(rom_offset, tile_count)

                if sprite_data:
                    # Save as PNG
                    output_path = self.base_dir / f"mushroom_sprite_{rom_offset:06X}_{tile_count}tiles.png"
                    sprite_data.save(str(output_path))
                    print(f"✓ Saved {tile_count}-tile sprite to {output_path.name}")
            except Exception as e:
                print(f"  Failed with {tile_count} tiles: {e}")

    def run(self):
        """Main execution"""

        # Step 1: Run the transition test
        transfer = self.run_transition_test()

        if not transfer:
            print("\nFailed to detect mushroom sprite transfer!")
            return

        # Step 2: Extract the sprite
        rom_offset = transfer["rom_offset"]
        success = self.extract_sprite(rom_offset)

        if success:
            print("\n=== SUCCESS ===")
            print(f"Mushroom sprite found at ROM offset: ${rom_offset:06X}")
            print(f"VRAM location when visible: ${transfer['vram_addr']:04X}")
            print(f"Size in VRAM: {transfer['size']} bytes")
            print("\nWorkflow validated: We can trace visible sprites to ROM offsets!")
        else:
            print(f"\nPartial success - found ROM offset ${rom_offset:06X} but extraction needs refinement")


if __name__ == "__main__":
    finder = MushroomSpriteFinder()
    finder.run()
