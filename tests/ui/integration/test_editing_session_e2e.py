"""
End-to-end tests for editing session integrity.

These tests cover:
- P2: End-to-end editing session workflow
- Canvas changes reaching ROM injection layer
- Undo/redo consistency with injection state
- Validation gate for injection

This verifies the complete flow:
ROM → Extract → Edit (canvas) → Validate → Prepare Injection → Save

Related tests:
- test_editing_controller_integration.py - Controller logic tests
- test_rom_workflow_integration.py - ROM workflow signal tests
- tests/integration/test_rom_injection.py - Low-level injection tests
"""

from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

import numpy as np
import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtTest import QSignalSpy

from ui.sprite_editor.controllers.editing_controller import EditingController


class MockPreviewCoordinator(QObject):
    """Mock coordinator that exposes signals for testing."""

    preview_ready = Signal(bytes, int, int, str, int, int, int, bool)
    preview_error = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.request_manual_preview_called = False
        self.request_full_preview_called = False
        self.last_requested_offset = -1

    def set_rom_data_provider(self, provider: object) -> None:
        pass

    def request_manual_preview(self, offset: int) -> None:
        self.request_manual_preview_called = True
        self.last_requested_offset = offset

    def request_full_preview(self, offset: int) -> None:
        self.request_full_preview_called = True
        self.last_requested_offset = offset

    def cleanup(self) -> None:
        pass


@pytest.fixture
def editing_controller(qtbot) -> EditingController:
    """Fixture for EditingController."""
    return EditingController()


class TestEditToInjectionDataFlow:
    """Tests for canvas edit data flowing to injection layer."""

    def test_edited_pixel_data_available_for_injection(self, qtbot, editing_controller: EditingController) -> None:
        """Verify edited pixel data is accessible via get_image_data()."""
        # Setup: Load initial image
        initial_data = np.zeros((8, 8), dtype=np.uint8)
        editing_controller.load_image(initial_data)

        # Action: Edit a pixel
        editing_controller.set_selected_color(5)
        editing_controller.handle_pixel_press(2, 3)
        editing_controller.handle_pixel_release(2, 3)

        # Verify: Data accessible for injection
        result_data = editing_controller.get_image_data()
        assert result_data is not None
        assert result_data[3, 2] == 5  # numpy is row,col (y,x)

    def test_multiple_edits_accumulated(self, qtbot, editing_controller: EditingController) -> None:
        """Verify multiple edits are accumulated in image data."""
        initial_data = np.zeros((16, 16), dtype=np.uint8)
        editing_controller.load_image(initial_data)

        # Multiple edits
        pixels_to_edit = [(0, 0, 1), (5, 5, 2), (15, 15, 3), (8, 8, 4)]
        for x, y, color in pixels_to_edit:
            editing_controller.set_selected_color(color)
            editing_controller.handle_pixel_press(x, y)
            editing_controller.handle_pixel_release(x, y)

        # Verify all edits present
        result_data = editing_controller.get_image_data()
        assert result_data is not None
        for x, y, color in pixels_to_edit:
            assert result_data[y, x] == color, f"Edit at ({x},{y}) not preserved"

    def test_palette_data_available_for_injection(self, qtbot, editing_controller: EditingController) -> None:
        """Verify palette data is accessible via get_flat_palette()."""
        initial_data = np.zeros((8, 8), dtype=np.uint8)
        editing_controller.load_image(initial_data)

        # Set custom palette
        custom_colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
        editing_controller.set_palette(custom_colors)

        # Verify palette accessible
        palette = editing_controller.get_flat_palette()
        assert palette is not None
        # First 3 colors should match our custom colors
        assert len(palette) >= 3


class TestUndoRedoConsistencyWithInjection:
    """Tests for undo/redo consistency with injection state."""

    def test_undo_state_available_for_injection(self, qtbot, editing_controller: EditingController) -> None:
        """Verify undo restores data that would be injected."""
        initial_data = np.zeros((8, 8), dtype=np.uint8)
        editing_controller.load_image(initial_data)

        # Edit
        editing_controller.set_selected_color(7)
        editing_controller.handle_pixel_press(4, 4)
        editing_controller.handle_pixel_release(4, 4)

        # Verify edit
        assert editing_controller.get_image_data()[4, 4] == 7

        # Undo
        editing_controller.undo()

        # Verify undo state is what would be injected
        undo_data = editing_controller.get_image_data()
        assert undo_data is not None
        assert undo_data[4, 4] == 0  # Back to original

    def test_redo_state_available_for_injection(self, qtbot, editing_controller: EditingController) -> None:
        """Verify redo restores data that would be injected."""
        initial_data = np.zeros((8, 8), dtype=np.uint8)
        editing_controller.load_image(initial_data)

        # Edit and undo
        editing_controller.set_selected_color(9)
        editing_controller.handle_pixel_press(3, 3)
        editing_controller.handle_pixel_release(3, 3)
        editing_controller.undo()

        # Redo
        editing_controller.redo()

        # Verify redo state is what would be injected
        redo_data = editing_controller.get_image_data()
        assert redo_data is not None
        assert redo_data[3, 3] == 9  # Edit restored

    def test_undo_redo_signals_for_ui_sync(self, qtbot, editing_controller: EditingController) -> None:
        """Verify undo/redo emit signals for UI synchronization."""
        spy_undo = QSignalSpy(editing_controller.undoStateChanged)

        initial_data = np.zeros((8, 8), dtype=np.uint8)
        editing_controller.load_image(initial_data)
        initial_count = spy_undo.count()

        # Edit
        editing_controller.set_selected_color(1)
        editing_controller.handle_pixel_press(0, 0)
        editing_controller.handle_pixel_release(0, 0)

        assert spy_undo.count() > initial_count
        # can_undo should be True
        args = spy_undo.at(spy_undo.count() - 1)
        assert args[0] is True  # can_undo


class TestValidationGateForInjection:
    """Tests for validation preventing invalid data injection."""

    def test_valid_image_passes_validation(self, qtbot, editing_controller: EditingController) -> None:
        """Verify valid image passes ROM validation."""
        # 8x8 image with colors 0-15 is valid
        valid_data = np.zeros((8, 8), dtype=np.uint8)
        valid_data[0:4, 0:4] = 5  # Use color index 5
        editing_controller.load_image(valid_data)

        # Force validation
        editing_controller.force_validation()

        assert editing_controller.is_valid_for_rom() is True
        assert editing_controller.get_validation_errors() == []

    def test_excessive_colors_blocks_injection(self, qtbot, editing_controller: EditingController) -> None:
        """Verify >16 colors blocks ROM injection."""
        # Create image with 17+ unique colors
        invalid_data = np.zeros((8, 8), dtype=np.uint8)
        for i in range(17):
            x, y = i % 8, i // 8
            invalid_data[y, x] = i  # Colors 0-16 (17 colors)

        editing_controller.load_image(invalid_data)
        editing_controller.force_validation()

        assert editing_controller.is_valid_for_rom() is False
        errors = editing_controller.get_validation_errors()
        assert any("colors" in e.lower() for e in errors)

    def test_misaligned_dimensions_blocks_injection(self, qtbot, editing_controller: EditingController) -> None:
        """Verify non-tile-aligned dimensions block ROM injection."""
        # 7x9 is not aligned to 8px tile boundary
        misaligned_data = np.zeros((9, 7), dtype=np.uint8)
        editing_controller.load_image(misaligned_data)
        editing_controller.force_validation()

        assert editing_controller.is_valid_for_rom() is False
        errors = editing_controller.get_validation_errors()
        assert any("multiple" in e.lower() for e in errors)

    def test_validation_signal_emitted_on_state_change(self, qtbot, editing_controller: EditingController) -> None:
        """Verify validationChanged signal emitted when validity changes."""
        spy_validation = QSignalSpy(editing_controller.validationChanged)

        # Start with valid data
        valid_data = np.zeros((8, 8), dtype=np.uint8)
        editing_controller.load_image(valid_data)
        editing_controller.force_validation()

        initial_count = spy_validation.count()

        # Edit to make invalid (use color index > 15)
        # Note: We need to directly manipulate the data since set_selected_color
        # is clamped to valid palette indices
        editing_controller.image_model.data[0, 0] = 16
        editing_controller.force_validation()

        assert spy_validation.count() > initial_count

    def test_high_palette_index_blocks_injection(self, qtbot, editing_controller: EditingController) -> None:
        """Verify palette index > 15 blocks injection."""
        # Create image with index 16 (invalid for 4bpp)
        invalid_data = np.zeros((8, 8), dtype=np.uint8)
        invalid_data[0, 0] = 16  # Index 16 is invalid

        editing_controller.load_image(invalid_data)
        editing_controller.force_validation()

        assert editing_controller.is_valid_for_rom() is False
        errors = editing_controller.get_validation_errors()
        assert any("index" in e.lower() or "15" in e for e in errors)


class TestInjectionPreparation:
    """Tests for preparing edited data for injection."""

    def test_image_data_format_for_injection(self, qtbot, editing_controller: EditingController) -> None:
        """Verify image data format is suitable for 4bpp conversion."""
        data = np.zeros((16, 16), dtype=np.uint8)
        data[0:8, 0:8] = 3  # Some color
        editing_controller.load_image(data)

        result = editing_controller.get_image_data()

        # Must be numpy array
        assert isinstance(result, np.ndarray)
        # Must be 2D (height, width)
        assert result.ndim == 2
        # Must be uint8 for palette indices
        assert result.dtype == np.uint8

    def test_unsaved_changes_tracking(self, qtbot, editing_controller: EditingController) -> None:
        """Verify unsaved changes are tracked for injection warnings."""
        data = np.zeros((8, 8), dtype=np.uint8)
        editing_controller.load_image(data)

        # Clear undo history to establish "saved" baseline
        editing_controller.clear_undo_history()
        assert editing_controller.has_unsaved_changes() is False

        # Make edit
        editing_controller.set_selected_color(1)
        editing_controller.handle_pixel_press(0, 0)
        editing_controller.handle_pixel_release(0, 0)

        assert editing_controller.has_unsaved_changes() is True


class TestSignalOrderingForInjection:
    """Tests for signal ordering during edit-to-injection flow."""

    def test_image_change_signals_before_validation(self, qtbot, editing_controller: EditingController) -> None:
        """Verify imageChanged signals emit before validationChanged."""
        signals_order: list[str] = []

        def on_image_changed() -> None:
            signals_order.append("image")

        def on_validation_changed(valid: bool, errors: list[str]) -> None:
            signals_order.append("validation")

        editing_controller.imageChanged.connect(on_image_changed)
        editing_controller.validationChanged.connect(on_validation_changed)

        # Load image (triggers both signals)
        data = np.zeros((8, 8), dtype=np.uint8)
        editing_controller.load_image(data)

        # Edit (triggers image change, then validation)
        editing_controller.set_selected_color(1)
        editing_controller.handle_pixel_press(0, 0)
        editing_controller.handle_pixel_release(0, 0)

        # Image changes should come before validation
        image_indices = [i for i, s in enumerate(signals_order) if s == "image"]
        validation_indices = [i for i, s in enumerate(signals_order) if s == "validation"]

        if image_indices and validation_indices:
            # At least one image signal should precede validation
            assert min(image_indices) < max(validation_indices)

    def test_undo_state_signals_after_edit(self, qtbot, editing_controller: EditingController) -> None:
        """Verify undoStateChanged signals after edit completion."""
        spy_undo = QSignalSpy(editing_controller.undoStateChanged)

        data = np.zeros((8, 8), dtype=np.uint8)
        editing_controller.load_image(data)
        initial_count = spy_undo.count()

        # Edit
        editing_controller.set_selected_color(2)
        editing_controller.handle_pixel_press(1, 1)
        editing_controller.handle_pixel_release(1, 1)

        # Undo state should have updated
        assert spy_undo.count() > initial_count


# =============================================================================
# Eraser Tool Tests
# Source: tests/ui/test_editing_eraser.py
# =============================================================================


class TestEraserTool:
    """Tests for eraser and pencil tool behavior.

    Source: tests/ui/test_editing_eraser.py
    """

    def test_eraser_tool_uses_transparent_color(self):
        """Test that eraser tool always uses color 0 regardless of selected color."""
        controller = EditingController()

        # Create a 2x2 image filled with color 1
        data = np.full((2, 2), 1, dtype=np.uint8)
        controller.load_image(data)

        # Select color 2 (to ensure it's NOT used)
        controller.set_selected_color(2)
        assert controller.get_selected_color() == 2

        # Set tool to Eraser
        controller.set_tool("eraser")
        assert controller.get_current_tool_name() == "eraser"

        # Perform a stroke
        # 1. Press at 0,0
        controller.handle_pixel_press(0, 0)
        assert controller.image_model.get_pixel(0, 0) == 0, "Eraser press should set pixel to 0"

        # 2. Move to 0,1
        controller.handle_pixel_move(0, 1)
        assert controller.image_model.get_pixel(0, 1) == 0, "Eraser move should set pixel to 0"

        # 3. Release
        controller.handle_pixel_release(0, 1)

    def test_pencil_tool_uses_selected_color(self):
        """Verify pencil tool still uses selected color."""
        controller = EditingController()

        # Create a 2x2 image filled with color 1
        data = np.full((2, 2), 1, dtype=np.uint8)
        controller.load_image(data)

        # Select color 2
        controller.set_selected_color(2)

        # Set tool to Pencil
        controller.set_tool("pencil")

        # Perform a stroke
        controller.handle_pixel_press(0, 0)
        assert controller.image_model.get_pixel(0, 0) == 2, "Pencil press should set pixel to 2"

        controller.handle_pixel_move(0, 1)
        assert controller.image_model.get_pixel(0, 1) == 2, "Pencil move should set pixel to 2"


class TestEdgeConditionsForInjection:
    """Tests for edge conditions in the edit-to-injection pipeline."""

    def test_default_image_handling(self, qtbot, editing_controller: EditingController) -> None:
        """Verify controller starts with valid default state.

        Note: EditingController always has an image (ImageModel has default data).
        This test verifies the default state is injection-ready.
        """
        # Controller always has an image (default state)
        assert editing_controller.has_image() is True
        # Default image data should be accessible
        assert editing_controller.get_image_data() is not None

        # Default state should be valid for ROM
        editing_controller.force_validation()
        assert editing_controller.is_valid_for_rom() is True

    def test_single_tile_image(self, qtbot, editing_controller: EditingController) -> None:
        """Verify single tile (8x8) image works for injection."""
        data = np.zeros((8, 8), dtype=np.uint8)
        data[:, :] = 3
        editing_controller.load_image(data)

        editing_controller.force_validation()
        assert editing_controller.is_valid_for_rom() is True

        result = editing_controller.get_image_data()
        assert result.shape == (8, 8)

    def test_large_sprite_image(self, qtbot, editing_controller: EditingController) -> None:
        """Verify large sprite (e.g., 64x64) works for injection."""
        data = np.zeros((64, 64), dtype=np.uint8)
        for i in range(16):
            row = i // 4
            col = i % 4
            data[row * 16 : (row + 1) * 16, col * 16 : (col + 1) * 16] = i

        editing_controller.load_image(data)
        editing_controller.force_validation()

        assert editing_controller.is_valid_for_rom() is True
        assert editing_controller.get_image_data().shape == (64, 64)

    def test_all_black_image(self, qtbot, editing_controller: EditingController) -> None:
        """Verify all-black (index 0) image is valid for injection."""
        data = np.zeros((8, 8), dtype=np.uint8)  # All zeros
        editing_controller.load_image(data)

        editing_controller.force_validation()
        assert editing_controller.is_valid_for_rom() is True

    def test_all_max_index_image(self, qtbot, editing_controller: EditingController) -> None:
        """Verify all max-index (15) image is valid for injection."""
        data = np.full((8, 8), 15, dtype=np.uint8)
        editing_controller.load_image(data)

        editing_controller.force_validation()
        assert editing_controller.is_valid_for_rom() is True
