"""
Tests for round-trip data integrity verification.

Verifies:
- ImageModel checksum tracking and verification
- EditingController ROM constraint validation
- Data integrity through edit cycles
"""

from __future__ import annotations

import numpy as np
import pytest

from ui.sprite_editor.models.image_model import ImageModel

# Use session fixtures for tests that don't modify state
pytestmark = [
    pytest.mark.usefixtures("session_app_context"),
    pytest.mark.shared_state_safe,
    pytest.mark.headless,
    pytest.mark.integration,
]


class TestImageModelChecksum:
    """Test ImageModel checksum functionality for data integrity verification."""

    def test_checksum_computed_on_set_data(self):
        """Verify checksum is computed when set_data is called."""
        model = ImageModel()
        data = np.arange(64, dtype=np.uint8).reshape(8, 8)

        model.set_data(data)

        # Checksum should be non-empty
        assert model.get_initial_checksum() != ""
        assert len(model.get_initial_checksum()) == 32  # SHA256 truncated to 32 hex chars

    def test_checksum_not_computed_when_disabled(self):
        """Verify checksum can be disabled."""
        model = ImageModel()
        data = np.arange(64, dtype=np.uint8).reshape(8, 8)

        model.set_data(data, store_checksum=False)

        assert model.get_initial_checksum() == ""

    def test_verify_integrity_passes_for_unmodified_data(self):
        """Verify integrity check passes when data is unchanged."""
        model = ImageModel()
        data = np.arange(64, dtype=np.uint8).reshape(8, 8)

        model.set_data(data)

        assert model.verify_integrity() is True

    def test_verify_integrity_fails_after_external_modification(self):
        """Verify integrity check fails when data is modified directly."""
        model = ImageModel()
        data = np.arange(64, dtype=np.uint8).reshape(8, 8)

        model.set_data(data)

        # Modify data directly (simulating corruption or external change)
        model.data[0, 0] = 255

        assert model.verify_integrity() is False

    def test_verify_integrity_returns_true_without_checksum(self):
        """Verify integrity check returns True when no checksum was stored."""
        model = ImageModel()
        data = np.arange(64, dtype=np.uint8).reshape(8, 8)

        model.set_data(data, store_checksum=False)

        # Should return True since we can't verify without checksum
        assert model.verify_integrity() is True

    def test_has_been_modified_since_load_detects_changes(self):
        """Verify modification detection via checksum comparison."""
        model = ImageModel()
        data = np.arange(64, dtype=np.uint8).reshape(8, 8)

        model.set_data(data)

        # Initially should not be modified (checksum matches)
        assert model.has_been_modified_since_load() is False

        # Modify via set_pixel
        model.set_pixel(0, 0, 15)

        # Now should be detected as modified
        assert model.has_been_modified_since_load() is True

    def test_current_checksum_changes_with_data(self):
        """Verify current checksum updates when data changes."""
        model = ImageModel()
        data = np.arange(64, dtype=np.uint8).reshape(8, 8)

        model.set_data(data)
        original_checksum = model.get_current_checksum()

        # Modify data
        model.set_pixel(0, 0, 15)

        new_checksum = model.get_current_checksum()
        assert new_checksum != original_checksum

    def test_identical_data_produces_identical_checksum(self):
        """Verify identical data produces identical checksums."""
        model1 = ImageModel()
        model2 = ImageModel()

        data = np.arange(64, dtype=np.uint8).reshape(8, 8)

        model1.set_data(data.copy())
        model2.set_data(data.copy())

        assert model1.get_initial_checksum() == model2.get_initial_checksum()
        assert model1.get_current_checksum() == model2.get_current_checksum()


class TestDataIntegrityThroughEditCycle:
    """Test data integrity through a full edit cycle."""

    @pytest.fixture
    def editing_controller(self, session_app_context):
        """Create an EditingController instance for testing."""
        from ui.sprite_editor.controllers.editing_controller import EditingController

        controller = EditingController()
        return controller

    def test_edit_cycle_preserves_data_integrity(self, editing_controller):
        """Verify data integrity is preserved through load → edit → export."""
        # Create known initial data
        initial_data = np.zeros((8, 8), dtype=np.uint8)
        for i in range(64):
            initial_data[i // 8, i % 8] = i % 16

        # Load into controller
        editing_controller.load_image(initial_data.copy(), [])

        # Make a known edit using controller's public API
        original_pixel = editing_controller.image_model.get_pixel(4, 4)
        new_pixel = (original_pixel + 1) % 16
        editing_controller.set_selected_color(new_pixel)
        editing_controller.handle_pixel_press(4, 4)
        editing_controller.handle_pixel_release(4, 4)

        # Export data
        exported_data = editing_controller.get_image_data()

        # Verify the edit is reflected
        assert exported_data[4, 4] == new_pixel

        # Verify all other pixels are unchanged
        for y in range(8):
            for x in range(8):
                if (x, y) != (4, 4):
                    expected = (y * 8 + x) % 16
                    assert exported_data[y, x] == expected, f"Pixel at ({x}, {y}) changed unexpectedly"

    def test_undo_restores_data_integrity_pencil(self, editing_controller):
        """Verify pencil tool undo restores data to previous state correctly."""
        # Create and load initial data - all zeros
        initial_data = np.zeros((8, 8), dtype=np.uint8)

        editing_controller.load_image(initial_data.copy(), [])

        # Get checksum before edit
        original_checksum = editing_controller.image_model.get_current_checksum()

        # Make an edit using pencil tool (press and release for atomic undo)
        editing_controller.set_tool("pencil")
        editing_controller.set_selected_color(5)
        editing_controller.handle_pixel_press(0, 0)
        editing_controller.handle_pixel_release(0, 0)

        # Verify data changed
        assert editing_controller.image_model.data[0, 0] == 5
        assert editing_controller.image_model.get_current_checksum() != original_checksum

        # Undo the edit
        editing_controller.undo()

        # Verify data restored
        exported_data = editing_controller.get_image_data()
        assert exported_data[0, 0] == 0  # Original value
        # Checksum should match original
        assert editing_controller.image_model.get_current_checksum() == original_checksum

    def test_undo_restores_data_integrity_fill(self, editing_controller):
        """Verify fill tool undo restores data to previous state correctly."""
        # Create and load initial data - all zeros for connected fill
        initial_data = np.zeros((8, 8), dtype=np.uint8)

        editing_controller.load_image(initial_data.copy(), [])

        # Get checksum before edit
        original_checksum = editing_controller.image_model.get_current_checksum()

        # Make an edit using fill tool - fills all connected 0s with 15
        editing_controller.set_tool("fill")
        editing_controller.set_selected_color(15)
        editing_controller.handle_pixel_press(0, 0)

        # Verify ALL pixels changed (all zeros are connected)
        for y in range(8):
            for x in range(8):
                assert editing_controller.image_model.data[y, x] == 15, f"Pixel ({x},{y}) not filled"

        assert editing_controller.image_model.get_current_checksum() != original_checksum

        # Undo the fill
        editing_controller.undo()

        # Verify ALL data restored
        exported_data = editing_controller.get_image_data()
        for y in range(8):
            for x in range(8):
                assert exported_data[y, x] == 0, f"Pixel ({x},{y}) not restored after undo"

        # Checksum should match original
        assert editing_controller.image_model.get_current_checksum() == original_checksum


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
