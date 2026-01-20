"""
Regression tests for palette loading synchronization issues.

Bug: When loading a palette JSON file in the ROM workflow:
- Palette panel shows correct colors (loaded palette)
- Canvas shows wrong colors (stale/different palette)
- Warning banner "Using default palette" persists after custom palette loaded

These tests verify that palette changes propagate correctly through:
1. EditingController -> PixelCanvas (color LUT update)
2. EditingController -> ROMWorkflowController (warning banner dismissal)
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PySide6.QtCore import QCoreApplication

if TYPE_CHECKING:
    from pathlib import Path

    from pytestqt.qtbot import QtBot


@pytest.fixture
def canvas_with_controller(qtbot: QtBot):
    """Create a PixelCanvas with EditingController and loaded image."""
    from ui.sprite_editor.controllers.editing_controller import EditingController
    from ui.sprite_editor.views.widgets.pixel_canvas import PixelCanvas

    # Prevent auto-loading last palette from settings to avoid state pollution.
    # We mock the 'state_manager' property (a @property, not a method) to return None.
    # This is safe because properties are simple Python descriptors, not Qt signals.
    # DO NOT patch QObject methods directly - it causes segfaults due to Qt/PySide6 internals.
    with patch.object(EditingController, "state_manager", new_callable=lambda: property(lambda self: None)):
        controller = EditingController()

    canvas = PixelCanvas(controller)
    qtbot.addWidget(canvas)

    # Load a simple 8x8 test image with all pixel indices used
    data = np.arange(16, dtype=np.uint8).reshape(4, 4)
    data = np.tile(data, (2, 2))  # 8x8 with indices 0-15 repeated
    controller.load_image(data)

    canvas.show()
    qtbot.waitExposed(canvas)
    QCoreApplication.processEvents()

    return canvas, controller


@pytest.fixture
def red_palette_json(tmp_path: Path) -> Path:
    """Create a test palette JSON with all red colors."""
    palette_file = tmp_path / "red_palette.pal.json"
    palette_data = {
        "name": "Test Red Palette",
        "colors": [[255, 0, 0]] * 16,  # All red
    }
    palette_file.write_text(json.dumps(palette_data))
    return palette_file


@pytest.mark.parallel_unsafe
class TestCanvasPaletteLoadSync:
    """Verify PixelCanvas updates colors when palette is loaded."""

    def test_canvas_receives_palette_changed_signal(
        self, qtbot: QtBot, canvas_with_controller: tuple, red_palette_json: Path
    ) -> None:
        """
        Regression: paletteChanged signal must trigger canvas color cache update.

        Bug: Canvas may not update colors when palette is loaded via handle_load_palette.
        """
        canvas, controller = canvas_with_controller

        # Track if _on_palette_changed was called
        signal_received = []
        original_handler = canvas._on_palette_changed

        def tracking_handler():
            signal_received.append(True)
            original_handler()

        canvas._on_palette_changed = tracking_handler

        # Load palette via controller (mock file dialog)
        with patch(
            "PySide6.QtWidgets.QFileDialog.getOpenFileName",
            return_value=(str(red_palette_json), ""),
        ):
            controller.handle_load_palette()

        QCoreApplication.processEvents()

        # ASSERTION: Canvas must receive palette changed signal
        assert len(signal_received) > 0, (
            "BUG: Canvas._on_palette_changed was NOT called after handle_load_palette(). "
            "The paletteChanged signal is not reaching the canvas."
        )

    def test_canvas_color_lut_updated_after_palette_load(
        self, qtbot: QtBot, canvas_with_controller: tuple, red_palette_json: Path
    ) -> None:
        """
        Regression: Canvas color LUT must reflect newly loaded palette colors.

        Bug: Canvas shows wrong colors after loading custom palette because
        the color LUT is not properly invalidated/rebuilt.
        """
        canvas, controller = canvas_with_controller

        # Force initial render to populate caches
        canvas.update()
        QCoreApplication.processEvents()

        # Verify initial state: not all red
        initial_lut = canvas._color_lut.copy() if canvas._color_lut is not None else None
        if initial_lut is not None:
            # Check index 1 (non-transparent) is not red initially
            assert not (initial_lut[1][0] == 255 and initial_lut[1][1] == 0 and initial_lut[1][2] == 0), (
                "Precondition failed: initial palette should not be all red"
            )

        # Load red palette via controller
        with patch(
            "PySide6.QtWidgets.QFileDialog.getOpenFileName",
            return_value=(str(red_palette_json), ""),
        ):
            controller.handle_load_palette()

        # Process events to allow cache updates
        QCoreApplication.processEvents()

        # Force another render to trigger cache rebuild
        canvas.update()
        QCoreApplication.processEvents()

        # ASSERTION: Color LUT must now have red colors
        # Access internal state for verification (acceptable in regression tests)
        canvas._update_color_lut()  # Ensure LUT is rebuilt
        lut = canvas._color_lut

        assert lut is not None, "BUG: Color LUT is None after palette load"

        # Check that non-transparent colors (indices 1-15) are red
        for i in range(1, 16):
            rgb = lut[i]
            assert rgb[0] == 255, f"BUG: Color index {i} red channel = {rgb[0]}, expected 255"
            assert rgb[1] == 0, f"BUG: Color index {i} green channel = {rgb[1]}, expected 0"
            assert rgb[2] == 0, f"BUG: Color index {i} blue channel = {rgb[2]}, expected 0"

    def test_controller_palette_colors_match_loaded_file(
        self, qtbot: QtBot, canvas_with_controller: tuple, red_palette_json: Path
    ) -> None:
        """
        Verify controller.get_current_colors() returns loaded palette colors.

        This is the source of truth that canvas should use.
        """
        canvas, controller = canvas_with_controller

        # Load red palette
        with patch(
            "PySide6.QtWidgets.QFileDialog.getOpenFileName",
            return_value=(str(red_palette_json), ""),
        ):
            controller.handle_load_palette()

        QCoreApplication.processEvents()

        # ASSERTION: Controller should return red colors
        colors = controller.get_current_colors()
        assert len(colors) == 16, f"Expected 16 colors, got {len(colors)}"

        # All colors should be red (255, 0, 0)
        for i, color in enumerate(colors):
            assert color == (255, 0, 0), f"Color {i} is {color}, expected (255, 0, 0)"


class TestWarningBannerDismissal:
    """Verify warning banner hides when custom palette is loaded."""

    def test_warning_banner_hides_after_file_palette_loaded(self, qtbot: QtBot, tmp_path: Path) -> None:
        """
        Regression: 'Using default palette' warning should dismiss when user loads custom palette.

        Bug: ROMWorkflowController does not listen to paletteSourceSelected signal,
        so warning banner persists even after custom palette is loaded.
        """
        from ui.sprite_editor.controllers.editing_controller import EditingController
        from ui.sprite_editor.controllers.rom_workflow_controller import ROMWorkflowController

        # Setup controllers - ROMWorkflowController requires (parent, editing_controller)
        editing_controller = EditingController()
        rom_workflow_controller = ROMWorkflowController(None, editing_controller)

        # Create mock view with hide_palette_warning method
        mock_view = MagicMock()
        mock_view.hide_palette_warning = MagicMock()
        rom_workflow_controller._view = mock_view

        # Simulate showing the warning (as if ROM palette wasn't found)
        mock_view.show_palette_warning = MagicMock()
        if hasattr(rom_workflow_controller, "_view") and rom_workflow_controller._view:
            rom_workflow_controller._view.show_palette_warning(
                "Using default palette. ROM palette configuration not available."
            )

        # Create test palette file
        palette_file = tmp_path / "custom.pal.json"
        palette_data = {"name": "Custom", "colors": [[0, 128, 255]] * 16}
        palette_file.write_text(json.dumps(palette_data))

        # Load custom palette via EditingController
        with patch(
            "PySide6.QtWidgets.QFileDialog.getOpenFileName",
            return_value=(str(palette_file), ""),
        ):
            editing_controller.handle_load_palette()

        QCoreApplication.processEvents()

        # ASSERTION: Warning banner should be hidden
        # This test will FAIL if ROMWorkflowController doesn't listen to paletteSourceSelected
        (
            mock_view.hide_palette_warning.assert_called(),
            (
                "BUG: hide_palette_warning was NOT called after loading custom palette. "
                "ROMWorkflowController must listen to EditingController.paletteSourceSelected signal."
            ),
        )


class TestScaledImageCacheInvalidation:
    """Verify scaled image cache is invalidated when palette changes."""

    def test_scaled_cache_invalidated_on_palette_change(
        self, qtbot: QtBot, canvas_with_controller: tuple, red_palette_json: Path
    ) -> None:
        """
        Regression: _qimage_scaled must be invalidated when palette changes.

        Bug: _invalidate_color_cache() does not clear _qimage_scaled,
        potentially leaving stale rendering even after palette update.
        """
        canvas, controller = canvas_with_controller

        # Set zoom > 1 to trigger scaled image caching
        canvas.set_zoom(4)

        # Force initial render to populate scaled cache
        canvas.update()
        QCoreApplication.processEvents()

        # Get initial scaled palette version
        initial_scaled_version = canvas._cached_scaled_palette_version

        # Load new palette
        with patch(
            "PySide6.QtWidgets.QFileDialog.getOpenFileName",
            return_value=(str(red_palette_json), ""),
        ):
            controller.handle_load_palette()

        QCoreApplication.processEvents()

        # After palette change, either:
        # 1. _qimage_scaled should be None (fully invalidated), OR
        # 2. _cached_scaled_palette_version should be different (version mismatch will trigger rebuild)

        # The safest fix is explicit invalidation (option 1)
        # But version mismatch (option 2) should also work theoretically

        # Force a render to check actual state
        canvas.update()
        QCoreApplication.processEvents()

        # Verify palette version was incremented
        current_palette_version = canvas._palette_version
        assert current_palette_version > initial_scaled_version, (
            f"BUG: _palette_version not incremented. Initial: {initial_scaled_version}, "
            f"Current: {current_palette_version}"
        )

        # After render with new palette, scaled version should match current palette version
        # This verifies the cache was properly rebuilt with new colors
        canvas._get_scaled_qimage()  # Force cache update
        assert canvas._cached_scaled_palette_version == current_palette_version, (
            f"BUG: Scaled cache version mismatch. "
            f"Expected {current_palette_version}, got {canvas._cached_scaled_palette_version}. "
            "The scaled image cache may still contain old colors."
        )
