
from __future__ import annotations

import pytest

pytestmark = [
    pytest.mark.headless,
    pytest.mark.rom_data,
]
#!/usr/bin/env python3
"""
Test decompression at a known sprite offset.
"""

import os
import sys

# Add the parent directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.di_container import inject
from core.managers import initialize_managers
from core.protocols.manager_protocols import ExtractionManagerProtocol


def test_decompression():
    """Test if decompression works at a known sprite offset."""

    # Initialize managers
    print("Initializing managers...")
    initialize_managers()
    extraction_manager = inject(ExtractionManagerProtocol)
    rom_extractor = extraction_manager.get_rom_extractor()

    test_rom = "Kirby Super Star (USA).sfc"
    if not os.path.exists(test_rom):
        pytest.skip("Test ROM not found - skipping decompression test")

    # Read ROM data
    with open(test_rom, "rb") as f:
        rom_data = f.read()

    # Test at a known sprite offset (Kirby main sprite)
    test_offset = 0x20000A  # This is where navigation found a sprite

    print(f"\nTesting at offset 0x{test_offset:06X}...")

    # First, show raw data
    raw_data = rom_data[test_offset:test_offset + 32]
    print(f"Raw data (first 32 bytes): {raw_data.hex()}")

    # Try decompression
    compressed_size, decompressed_data = rom_extractor.rom_injector.find_compressed_sprite(
        rom_data, test_offset, 8192  # Expected size
    )
    print("\nDecompression successful!")
    print(f"Compressed size: {compressed_size} bytes")
    print(f"Decompressed size: {len(decompressed_data)} bytes")
    print(f"First 32 bytes of decompressed: {decompressed_data[:32].hex()}")

    # Check if it looks like tile data
    num_tiles = len(decompressed_data) // 32
    print(f"Number of tiles: {num_tiles}")

    # Assertions
    assert compressed_size > 0, "Compressed size should be positive"
    assert len(decompressed_data) > 0, "Decompressed data should not be empty"
    assert num_tiles > 0, "Should have at least one tile"

    print("\nTest complete!")

if __name__ == "__main__":
    try:
        test_decompression()
        sys.exit(0)
    except Exception as e:
        print(f"Test failed: {e}")
        sys.exit(1)
