"""Tests for global palette edit feedback.

Verifies that editing a palette color shows a confirmation dialog
with the number of affected pixels.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from ui.sprite_editor.controllers.editing_controller import EditingController


class TestPaletteEditFeedback:
    """Tests for palette edit feedback on global color changes."""

    @pytest.fixture
    def controller_with_image(self, qtbot) -> EditingController:
        """Create a controller with a loaded image."""
        ctrl = EditingController()
        # Create 8x8 image with varied indices (64 pixels total)
        # Index 0: 4 pixels (2x2 block)
        # Index 1: 12 pixels (2 rows, cols 2-7 = 2*6=12)
        # Index 2: 48 pixels (6 rows * 8 cols)
        data = np.full((8, 8), 2, dtype=np.uint8)  # Start with all index 2
        data[0:2, 0:2] = 0  # 4 pixels of index 0
        data[0:2, 2:8] = 1  # 12 pixels of index 1 (2 rows * 6 cols)
        # Remaining: rows 2-7 (6 rows) * 8 cols = 48 pixels of index 2
        ctrl.load_image(data)
        return ctrl

    def test_controller_has_count_pixels_method(
        self,
        qtbot,
        controller_with_image: EditingController,
    ) -> None:
        """Controller should have a method to count pixels using a given index."""
        assert hasattr(controller_with_image, "count_pixels_using_index")
        # Count pixels using index 1
        count = controller_with_image.count_pixels_using_index(1)
        assert count == 12

    def test_count_pixels_index_0(
        self,
        qtbot,
        controller_with_image: EditingController,
    ) -> None:
        """Should correctly count pixels using index 0."""
        count = controller_with_image.count_pixels_using_index(0)
        assert count == 4

    def test_count_pixels_index_2(
        self,
        qtbot,
        controller_with_image: EditingController,
    ) -> None:
        """Should correctly count pixels using index 2."""
        count = controller_with_image.count_pixels_using_index(2)
        assert count == 48

    def test_count_pixels_default_image(
        self,
        qtbot,
    ) -> None:
        """Default 8x8 image has 64 pixels of index 0."""
        ctrl = EditingController()
        # Default is an 8x8 array of zeros
        count = ctrl.count_pixels_using_index(0)
        assert count == 64
        # No pixels of index 1 in default
        count = ctrl.count_pixels_using_index(1)
        assert count == 0

    @patch("PySide6.QtWidgets.QColorDialog")
    @patch("PySide6.QtWidgets.QMessageBox")
    def test_edit_color_shows_confirmation_when_pixels_affected(
        self,
        mock_msgbox: MagicMock,
        mock_color_dialog: MagicMock,
        qtbot,
        controller_with_image: EditingController,
    ) -> None:
        """Should show confirmation dialog when editing a color that affects pixels."""
        # Setup: Select index 2 which has 48 pixels
        controller_with_image.set_selected_color(2)

        # Mock color dialog to return a valid color
        mock_color = MagicMock()
        mock_color.isValid.return_value = True
        mock_color.red.return_value = 255
        mock_color.green.return_value = 0
        mock_color.blue.return_value = 0
        mock_color_dialog.getColor.return_value = mock_color

        # Mock confirmation to return Yes
        mock_msgbox.question.return_value = mock_msgbox.StandardButton.Yes

        # Edit the color
        controller_with_image.handle_edit_color()

        # Verify confirmation was shown
        mock_msgbox.question.assert_called_once()
        call_args = mock_msgbox.question.call_args
        # Check message mentions pixel count
        assert "48" in str(call_args)

    @patch("PySide6.QtWidgets.QColorDialog")
    @patch("PySide6.QtWidgets.QMessageBox")
    def test_edit_color_cancelled_when_user_declines_confirmation(
        self,
        mock_msgbox: MagicMock,
        mock_color_dialog: MagicMock,
        qtbot,
        controller_with_image: EditingController,
    ) -> None:
        """Should not apply color change when user declines confirmation."""
        # Setup: Select index 2
        controller_with_image.set_selected_color(2)

        # Get original color
        original_color = controller_with_image.palette_model.get_color(2)

        # Mock color dialog to return a valid color
        mock_color = MagicMock()
        mock_color.isValid.return_value = True
        mock_color.red.return_value = 255
        mock_color.green.return_value = 0
        mock_color.blue.return_value = 0
        mock_color_dialog.getColor.return_value = mock_color

        # Mock confirmation to return No (decline)
        mock_msgbox.question.return_value = mock_msgbox.StandardButton.No

        # Edit the color
        controller_with_image.handle_edit_color()

        # Verify color was NOT changed
        current_color = controller_with_image.palette_model.get_color(2)
        assert current_color == original_color
