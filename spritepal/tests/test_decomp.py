from __future__ import annotations

import pytest

pytestmark = [
    pytest.mark.headless,
    pytest.mark.usefixtures("session_managers"),
    pytest.mark.shared_state_safe,
    pytest.mark.skip_thread_cleanup(reason="Uses session_managers which owns worker threads"),
]
#!/usr/bin/env python3
"""
Test decompression at a known sprite offset.
"""

from pathlib import Path

# NOTE: pythonpath configured in pyproject.toml - no sys.path manipulation needed
from core.app_context import get_app_context


def test_decompression():
    """Test if decompression works at a known sprite offset."""

    # Managers initialized by session_managers fixture
    context = get_app_context()
    extraction_manager = context.core_operations_manager
    rom_extractor = extraction_manager.get_rom_extractor()

    test_rom = "Kirby Super Star (USA).sfc"
    if not Path(test_rom).exists():
        pytest.skip("Test ROM not found - skipping decompression test")

    # Read ROM data
    with Path(test_rom).open("rb") as f:
        rom_data = f.read()

    # Test at a known sprite offset (Kirby main sprite)
    test_offset = 0x20000A  # This is where navigation found a sprite

    print(f"\nTesting at offset 0x{test_offset:06X}...")

    # First, show raw data
    raw_data = rom_data[test_offset : test_offset + 32]
    print(f"Raw data (first 32 bytes): {raw_data.hex()}")

    # Try decompression
    compressed_size, decompressed_data = rom_extractor.rom_injector.find_compressed_sprite(
        rom_data,
        test_offset,
        8192,  # Expected size
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
