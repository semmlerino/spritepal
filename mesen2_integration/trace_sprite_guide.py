#!/usr/bin/env python3
"""
Interactive Guide for Tracing Sprites in Mesen 2
================================================
This script provides step-by-step guidance for using Mesen 2's debugger
to trace sprites back to their ROM locations in Kirby Super Star.
"""

import subprocess
import sys
from pathlib import Path


class SpriteTraceGuide:
    def __init__(self):
        self.sprite_name = ""
        self.vram_address = ""
        self.snes_address = ""
        self.notes = []

    def print_header(self, text: str):
        """Print a formatted header."""
        print(f"\n{'=' * 60}")
        print(f"  {text}")
        print("=" * 60)

    def print_step(self, number: int, title: str):
        """Print a step header."""
        print(f"\n[Step {number}] {title}")
        print("-" * 40)

    def wait_for_user(self, prompt: str = "Press Enter when ready..."):
        """Wait for user input."""
        input(f"\n→ {prompt}")

    def get_input(self, prompt: str, default: str = "") -> str:
        """Get user input with optional default."""
        if default:
            result = input(f"→ {prompt} [{default}]: ").strip()
            return result if result else default
        return input(f"→ {prompt}: ").strip()

    def run_guide(self):
        """Run the interactive sprite tracing guide."""

        self.print_header("Mesen 2 Sprite Tracing Guide for Kirby Super Star")

        print("\nThis guide will walk you through tracing a sprite from the screen")
        print("back to its location in the ROM using Mesen 2's debugging tools.")

        # Get sprite info
        self.sprite_name = self.get_input("Which sprite are you tracing? (e.g., Cappy, Kirby)", "Cappy")

        # Step 1: Launch and Pause
        self.print_step(1, "Locate the Sprite On-Screen")
        print("""
1. Launch Kirby Super Star in Mesen 2
2. Navigate to where your sprite appears (e.g., a level with Cappy)
3. PAUSE the game when the sprite is visible (F5 or Debug > Break)

Tips:
- Use save states to quickly return to this point
- Frame advance (F6) helps position sprites exactly
""")
        self.wait_for_user("Press Enter when game is paused with sprite visible...")

        # Step 2: Find in VRAM
        self.print_step(2, "Find the Sprite's Tiles in VRAM")
        print("""
1. Open: Tools > Tile Viewer (or press Ctrl+Shift+T)
2. In the Tile Viewer window:
   - Ensure "Type: Sprite" is selected (not Background)
   - Look for your sprite's graphics in the tile grid
   - Click on a tile that belongs to your sprite

3. When you click a tile, note the VRAM address shown
   (Usually displayed as something like $1E00)

Tips:
- Sprites often use multiple tiles (2x2, 4x4, etc.)
- The address bar shows: VRAM: $XXXX when you select a tile
- You can also check Tools > Sprite Viewer for OAM info
""")

        vram_input = self.get_input("Enter the VRAM address of the sprite tile (e.g., $1E00)")
        self.vram_address = vram_input.replace("$", "").replace("0x", "").upper()

        # Calculate range for multi-tile sprites
        num_tiles = self.get_input("How many tiles does the sprite use?", "4")
        try:
            tiles = int(num_tiles)
            bytes_per_tile = 32  # 4bpp = 32 bytes per 8x8 tile
            total_bytes = tiles * bytes_per_tile
            end_addr = int(self.vram_address, 16) + total_bytes - 1

            print(f"\n✓ Sprite uses VRAM range: ${self.vram_address}-${end_addr:04X}")
            print(f"  ({tiles} tiles = {total_bytes} bytes)")
        except:
            print(f"\n✓ Using VRAM address: ${self.vram_address}")

        # Step 3: Set Breakpoint
        self.print_step(3, "Set VRAM Write Breakpoint")
        print(f"""
1. Open: Debug > Debugger (Ctrl+D)
2. In the Breakpoints panel, right-click and choose "Add..."
3. Configure the breakpoint:
   - Memory Type: VRAM
   - Address Range: ${self.vram_address}-${end_addr:04X}
   - Check: [✓] Write
   - Uncheck: [ ] Read, [ ] Execute
4. Click OK to create the breakpoint

The breakpoint is now set to trigger when the game writes
sprite data to VRAM address ${self.vram_address}.
""")
        self.wait_for_user("Press Enter when breakpoint is set...")

        # Step 4: Trigger Loading
        self.print_step(4, "Trigger Sprite Loading")
        print(f"""
Now we need the game to load {self.sprite_name}'s graphics fresh:

1. Reset to before the sprite appears:
   - Option A: Use Debug > Reset (if sprite loads at game start)
   - Option B: Load a save state from before the level
   - Option C: Exit and re-enter the area

2. Click "Run" or press F5 to resume execution

3. The debugger should BREAK when the sprite graphics load
   (The game will pause and the debugger will highlight a line)

Note: The breakpoint might trigger multiple times. You can
disable it after the first hit to avoid repeated breaks.
""")
        self.wait_for_user("Press Enter when debugger has broken on VRAM write...")

        # Step 5: Find Source Address
        self.print_step(5, "Analyze the Source Address")
        print("""
The debugger is now paused at the VRAM write. Look for:

A) Direct Store to VRAM ($2118/$2119):
   Look for: STA $2118 or STA $2119
   Check previous instructions for source (LDA from address)

B) DMA Transfer (more common):
   Look for: STA $420B (DMA enable register)
   Check DMA registers in Memory Viewer:
   - $4304: Source Bank (XX)
   - $4302-$4303: Source Address (YYYY)
   - Combined: $XX:YYYY is your SNES address

C) Look for patterns like:
   - LDA [$20],Y  (reading from pointer at $20)
   - LDA $95B000,X (direct long address)

To view registers/memory:
- View > Memory Viewer
- Enter address like $4302 to see DMA registers
- Or check CPU registers panel for current values
""")

        snes_input = self.get_input("Enter the source SNES address (e.g., $95:B000 or 95B000)")
        self.snes_address = snes_input.strip()

        # Step 6: Extract with our tool
        self.print_step(6, "Extract the Sprite Data")
        print(f"""
Great! You found the SNES address: {self.snes_address}

Now use the extraction tool to get the sprite:

  python mesen2_sprite_extractor.py {self.snes_address}

If extraction fails, try scanning nearby:

  python mesen2_sprite_extractor.py {self.snes_address} --scan

This will:
1. Convert SNES address to ROM offset
2. Decompress with exhal
3. Convert to PNG for viewing
""")

        run_now = self.get_input("Run extractor now? (y/n)", "y")
        if run_now.lower() == "y":
            self.run_extractor()

        # Save notes
        self.save_trace_log()

    def run_extractor(self):
        """Run the sprite extractor with the found address."""
        script_path = Path(__file__).parent.parent / "mesen2_sprite_extractor.py"
        if not script_path.exists():
            print(f"Error: Extractor script not found at {script_path}")
            return

        print(f"\nRunning: python {script_path.name} {self.snes_address}")
        result = subprocess.run(
            [sys.executable, str(script_path), self.snes_address, "--scan"], check=False, capture_output=False
        )

        if result.returncode == 0:
            print("\n✓ Extraction successful!")
        else:
            print("\n✗ Extraction failed. Check the output above.")

    def save_trace_log(self):
        """Save the trace information to a log file."""
        log_dir = Path("extracted_sprites/trace_logs")
        log_dir.mkdir(parents=True, exist_ok=True)

        log_file = log_dir / f"{self.sprite_name.replace(' ', '_').lower()}_trace.txt"

        with open(log_file, "w") as f:
            f.write(f"Sprite Trace Log: {self.sprite_name}\n")
            f.write("=" * 40 + "\n\n")
            f.write(f"Sprite Name: {self.sprite_name}\n")
            f.write(f"VRAM Address: ${self.vram_address}\n")
            f.write(f"SNES Address: {self.snes_address}\n")
            f.write("\nExtraction Command:\n")
            f.write(f"  python mesen2_sprite_extractor.py {self.snes_address}\n")

            if self.notes:
                f.write("\nNotes:\n")
                f.writelines(f"  - {note}\n" for note in self.notes)

        print(f"\n✓ Trace log saved to: {log_file}")


def main():
    guide = SpriteTraceGuide()

    try:
        guide.run_guide()
        print("\n" + "=" * 60)
        print("  Sprite tracing complete!")
        print("=" * 60)
    except KeyboardInterrupt:
        print("\n\nGuide interrupted by user.")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
