"""Contract tests for Mesen 2 capture format.

These tests validate that our test fixtures match the actual Mesen 2 output format.
If Mesen 2's output format changes, these tests will fail, alerting us to update
our test helpers.

References:
- Real capture files in mesen2_exchange/
- Test helper: tests/fixtures/frame_mapping_helpers.py::create_test_capture()
- Schema documentation: docs/mesen2/02_DATA_CONTRACTS.md
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.fixtures.frame_mapping_helpers import create_test_capture

# Use a real capture file for the contract test
REAL_CAPTURE_PATH = Path(__file__).parents[3] / "mesen2_exchange" / "capture_1768998729.json"


@pytest.fixture
def real_capture() -> dict:
    """Load a real Mesen 2 capture file."""
    if not REAL_CAPTURE_PATH.exists():
        pytest.skip(f"Real capture file not found: {REAL_CAPTURE_PATH}")
    with open(REAL_CAPTURE_PATH) as f:
        return json.load(f)


class TestCaptureSchemaContract:
    """Contract tests validating test fixtures match real Mesen 2 output."""

    def test_real_capture_has_required_top_level_keys(self, real_capture: dict) -> None:
        """Real capture files must have expected top-level structure."""
        # These keys are required by our parser
        required_keys = {"frame", "obsel", "entries"}
        assert required_keys <= set(real_capture.keys()), (
            f"Real capture missing required keys: {required_keys - set(real_capture.keys())}"
        )

    def test_synthetic_capture_has_required_top_level_keys(self) -> None:
        """Synthetic test captures must have same structure as real ones."""
        synthetic = create_test_capture([0, 1, 2])
        required_keys = {"frame", "obsel", "entries", "palettes"}
        assert required_keys <= set(synthetic.keys()), (
            f"Synthetic capture missing required keys: {required_keys - set(synthetic.keys())}"
        )

    def test_entry_structure_matches_real_capture(self, real_capture: dict) -> None:
        """Entry structure in test helper matches real Mesen 2 format."""
        # Get first entry from real capture
        assert len(real_capture["entries"]) > 0, "Real capture has no entries"
        real_entry = real_capture["entries"][0]

        # Get first entry from synthetic
        synthetic = create_test_capture([0])
        synth_entry = synthetic["entries"][0]

        # Required fields for parsing sprite data
        required_fields = {"id", "x", "y", "width", "height", "palette", "tiles"}
        assert required_fields <= set(real_entry.keys()), (
            f"Real entry missing fields: {required_fields - set(real_entry.keys())}"
        )
        assert required_fields <= set(synth_entry.keys()), (
            f"Synthetic entry missing fields: {required_fields - set(synth_entry.keys())}"
        )

    def test_tile_structure_matches_real_capture(self, real_capture: dict) -> None:
        """Tile structure in test helper matches real Mesen 2 format."""
        # Get first tile from real capture
        real_entry = real_capture["entries"][0]
        assert len(real_entry["tiles"]) > 0, "Real entry has no tiles"
        real_tile = real_entry["tiles"][0]

        # Get first tile from synthetic
        synthetic = create_test_capture([0])
        synth_tile = synthetic["entries"][0]["tiles"][0]

        # Required tile fields
        required_tile_fields = {"tile_index", "vram_addr", "pos_x", "pos_y", "data_hex", "rom_offset"}
        assert required_tile_fields <= set(real_tile.keys()), (
            f"Real tile missing fields: {required_tile_fields - set(real_tile.keys())}"
        )
        assert required_tile_fields <= set(synth_tile.keys()), (
            f"Synthetic tile missing fields: {required_tile_fields - set(synth_tile.keys())}"
        )

    def test_coordinate_ranges_are_compatible(self, real_capture: dict) -> None:
        """Entry coordinates fall within expected SNES ranges."""
        for entry in real_capture["entries"]:
            # SNES sprite X: -256 to 255, Y: -256 to 255 (signed 9-bit, stored unsigned)
            assert -256 <= entry["x"] <= 511, f"X coordinate {entry['x']} out of range"
            assert -256 <= entry["y"] <= 511, f"Y coordinate {entry['y']} out of range"
            # Sprite dimensions: 8, 16, 32, or 64 pixels
            assert entry["width"] in {8, 16, 32, 64}, f"Invalid width: {entry['width']}"
            assert entry["height"] in {8, 16, 32, 64}, f"Invalid height: {entry['height']}"

    def test_palette_index_range(self, real_capture: dict) -> None:
        """Palette indices fall within SNES sprite palette range (0-7)."""
        for entry in real_capture["entries"]:
            assert 0 <= entry["palette"] <= 7, f"Palette {entry['palette']} out of range"

    def test_data_hex_is_valid_tile_data(self, real_capture: dict) -> None:
        """Tile data_hex is valid hexadecimal of correct length."""
        real_tile = real_capture["entries"][0]["tiles"][0]

        # SNES 4bpp tile is 32 bytes = 64 hex chars
        assert len(real_tile["data_hex"]) == 64, f"data_hex length {len(real_tile['data_hex'])} != 64"
        # Should be valid hex
        int(real_tile["data_hex"], 16)  # Will raise ValueError if invalid
