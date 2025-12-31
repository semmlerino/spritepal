#!/usr/bin/env python3
"""
Simple test of exhal tool to debug decompression issues
"""
import subprocess
import tempfile
from pathlib import Path


def test_exhal_at_offset(rom_path: str, offset: int):
    """Test exhal at a specific offset with detailed output"""
    # Use absolute path to exhal tool
    script_dir = Path(__file__).parent
    exhal_path = script_dir.parent / "tools" / "exhal"

    with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as tmp_file:
        tmp_path = tmp_file.name

    try:
        cmd = [str(exhal_path), rom_path, f"0x{offset:X}", tmp_path]
        print(f"Testing: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10
        )

        print(f"Return code: {result.returncode}")
        if result.stdout:
            print(f"STDOUT: {result.stdout}")
        if result.stderr:
            print(f"STDERR: {result.stderr}")

        if Path(tmp_path).exists():
            size = Path(tmp_path).stat().st_size
            print(f"Output file size: {size} bytes")

            if size > 0:
                with open(tmp_path, 'rb') as f:
                    data = f.read(32)  # Read first 32 bytes
                print(f"First 32 bytes: {' '.join(f'{b:02X}' for b in data)}")
                return True, size
            else:
                print("Output file is empty")
                return False, 0
        else:
            print("No output file created")
            return False, 0

    except Exception as e:
        print(f"Error: {e}")
        return False, 0
    finally:
        if Path(tmp_path).exists():
            Path(tmp_path).unlink()

def main():
    """Test exhal on various offsets"""
    rom_path = "Kirby Super Star (USA).sfc"

    if not Path(rom_path).exists():
        print(f"Error: ROM not found: {rom_path}")
        return

    # Test offsets from different areas
    test_offsets = [
        0x70000,   # From exhal example
        0x80000,   # ROM_SPRITE_AREA_1_START
        0x80100,   # Slightly offset
        0xC0000,   # From existing analysis scripts
        0xE0000,   # From existing analysis scripts
        0x100000,  # ROM_SPRITE_AREA_2_START
    ]

    successful_decompressions = 0

    for offset in test_offsets:
        print(f"\n--- Testing offset 0x{offset:06X} ---")
        success, size = test_exhal_at_offset(rom_path, offset)
        if success:
            successful_decompressions += 1

    print("\n--- SUMMARY ---")
    print(f"Successful decompressions: {successful_decompressions}/{len(test_offsets)}")

    if successful_decompressions == 0:
        print("\n⚠️  No successful decompressions found.")
        print("This might mean:")
        print("1. HAL compression is not used at these offsets")
        print("2. Different compression format is used")
        print("3. Offsets need adjustment (HAL headers might be elsewhere)")

if __name__ == "__main__":
    main()
