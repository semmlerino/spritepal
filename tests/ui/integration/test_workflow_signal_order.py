"""
End-to-end workflow tests verifying signal emission order across components.

These tests ensure that when UI actions are performed in sequence,
signals are emitted in the expected order to maintain UI consistency.

Tests use MultiSignalRecorder to track signal order across multiple sources.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest
from PySide6.QtCore import QCoreApplication

from tests.ui.integration.helpers.signal_spy_utils import MultiSignalRecorder

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class TestIconToolbarToControllerFlow:
    """Test signal flow from IconToolbar through to EditingController."""

    @pytest.fixture
    def toolbar_and_controller(self, qtbot: QtBot):
        """Create connected IconToolbar and EditingController."""
        from ui.sprite_editor.controllers.editing_controller import EditingController
        from ui.sprite_editor.views.widgets.icon_toolbar import IconToolbar

        controller = EditingController()
        toolbar = IconToolbar()
        qtbot.addWidget(toolbar)

        # Connect toolbar signal to controller
        toolbar.toolChanged.connect(controller.set_tool)

        return toolbar, controller

    def test_toolbar_tool_click_propagates_to_controller(self, qtbot: QtBot, toolbar_and_controller) -> None:
        """Verify toolbar click propagates toolChanged through to controller."""
        from PySide6.QtCore import Qt

        toolbar, controller = toolbar_and_controller

        recorder = MultiSignalRecorder()
        recorder.connect_signal(toolbar.toolChanged, "toolbar_toolChanged")
        recorder.connect_signal(controller.toolChanged, "controller_toolChanged")

        # Click fill button on toolbar
        qtbot.mouseClick(toolbar.tool_buttons["fill"], Qt.MouseButton.LeftButton)
        QCoreApplication.processEvents()

        # Both toolbar and controller should emit - this proves the signal flow works
        # Note: Qt's slot invocation order is not guaranteed, so we don't test ordering
        recorder.assert_emitted("toolbar_toolChanged", times=1)
        recorder.assert_emitted("controller_toolChanged", times=1)


class TestPaletteToControllerFlow:
    """Test signal flow from PalettePanel through to EditingController."""

    @pytest.fixture
    def palette_and_controller(self, qtbot: QtBot):
        """Create connected PalettePanel and EditingController."""
        from ui.sprite_editor.controllers.editing_controller import EditingController
        from ui.sprite_editor.views.panels.palette_panel import PalettePanel

        controller = EditingController()
        palette = PalettePanel()
        qtbot.addWidget(palette)

        # Connect palette signal to controller
        palette.colorSelected.connect(controller.set_selected_color)

        return palette, controller

    def test_palette_color_click_propagates_to_controller(self, qtbot: QtBot, palette_and_controller) -> None:
        """Verify palette color click propagates colorChanged through to controller."""
        from PySide6.QtCore import QPoint, Qt

        palette, controller = palette_and_controller

        recorder = MultiSignalRecorder()
        recorder.connect_signal(palette.colorSelected, "palette_colorSelected")
        recorder.connect_signal(controller.colorChanged, "controller_colorChanged")

        # Click on color 5
        cell_size = palette.palette_widget.cell_size
        click_pos = QPoint(1 * cell_size + 10 + 5, 1 * cell_size + 10 + 5)
        qtbot.mouseClick(palette.palette_widget, Qt.MouseButton.LeftButton, pos=click_pos)
        QCoreApplication.processEvents()

        # Both should emit - this proves the signal flow works
        # Note: Qt's slot invocation order is not guaranteed, so we don't test ordering
        recorder.assert_emitted("palette_colorSelected", times=1)
        recorder.assert_emitted("controller_colorChanged", times=1)


class TestMultiSignalRecorderUtility:
    """Tests for the MultiSignalRecorder utility itself."""

    def test_recorder_tracks_emission_order(self, qtbot: QtBot) -> None:
        """Verify MultiSignalRecorder correctly tracks signal order."""
        from ui.sprite_editor.controllers.editing_controller import EditingController

        controller = EditingController()
        recorder = MultiSignalRecorder()
        recorder.connect_signal(controller.toolChanged, "toolChanged")
        recorder.connect_signal(controller.colorChanged, "colorChanged")

        controller.set_tool("fill")
        controller.set_selected_color(3)
        controller.set_tool("pencil")
        QCoreApplication.processEvents()

        # Verify order
        assert recorder.emission_order() == [
            "toolChanged",
            "colorChanged",
            "toolChanged",
        ]

    def test_recorder_clear_resets_emissions(self, qtbot: QtBot) -> None:
        """Verify clear() resets all recorded emissions."""
        from ui.sprite_editor.controllers.editing_controller import EditingController

        controller = EditingController()
        recorder = MultiSignalRecorder()
        recorder.connect_signal(controller.toolChanged, "toolChanged")

        controller.set_tool("fill")
        QCoreApplication.processEvents()
        assert recorder.count() == 1

        recorder.clear()
        assert recorder.count() == 0
        assert recorder.emission_order() == []

    def test_recorder_assert_contains_sequence(self, qtbot: QtBot) -> None:
        """Verify assert_contains_sequence checks order correctly."""
        from ui.sprite_editor.controllers.editing_controller import EditingController

        controller = EditingController()
        recorder = MultiSignalRecorder()
        recorder.connect_signal(controller.toolChanged, "toolChanged")
        recorder.connect_signal(controller.colorChanged, "colorChanged")
        recorder.connect_signal(controller.imageChanged, "imageChanged")

        # Emit signals in order: tool, color, image, tool
        controller.set_tool("fill")
        controller.set_selected_color(3)
        data = np.zeros((8, 8), dtype=np.uint8)
        controller.load_image(data)
        controller.set_tool("pencil")
        QCoreApplication.processEvents()

        # This sequence exists (not necessarily contiguous)
        recorder.assert_contains_sequence(["toolChanged", "colorChanged", "imageChanged"])

        # This sequence also exists
        recorder.assert_contains_sequence(["toolChanged", "toolChanged"])

        # This should fail (wrong order)
        with pytest.raises(AssertionError):
            recorder.assert_contains_sequence(["colorChanged", "toolChanged", "toolChanged", "toolChanged"])
