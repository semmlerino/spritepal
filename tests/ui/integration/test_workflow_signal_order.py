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


class TestEditingControllerSignalOrder:
    """Test signal emission order for EditingController workflows."""

    @pytest.fixture
    def editing_controller(self):
        """Create an EditingController for testing."""
        from ui.sprite_editor.controllers.editing_controller import EditingController

        controller = EditingController()
        return controller

    def test_load_image_emits_imageChanged(self, qtbot: QtBot, editing_controller) -> None:
        """Verify load_image emits imageChanged signal."""
        recorder = MultiSignalRecorder()
        recorder.connect_signal(editing_controller.imageChanged, "imageChanged")

        # Load an image
        data = np.zeros((8, 8), dtype=np.uint8)
        editing_controller.load_image(data)
        QCoreApplication.processEvents()

        recorder.assert_emitted("imageChanged", times=1)

    def test_set_tool_emits_toolChanged(self, qtbot: QtBot, editing_controller) -> None:
        """Verify set_tool emits toolChanged signal."""
        recorder = MultiSignalRecorder()
        recorder.connect_signal(editing_controller.toolChanged, "toolChanged")

        editing_controller.set_tool("fill")
        QCoreApplication.processEvents()

        recorder.assert_emitted("toolChanged", times=1)
        assert recorder.get_args("toolChanged") == ("fill",)

    def test_set_color_emits_colorChanged(self, qtbot: QtBot, editing_controller) -> None:
        """Verify set_selected_color emits colorChanged signal."""
        recorder = MultiSignalRecorder()
        recorder.connect_signal(editing_controller.colorChanged, "colorChanged")

        editing_controller.set_selected_color(5)
        QCoreApplication.processEvents()

        recorder.assert_emitted("colorChanged", times=1)
        assert recorder.get_args("colorChanged") == (5,)

    def test_tool_then_color_signal_order(self, qtbot: QtBot, editing_controller) -> None:
        """Verify tool selection, then color selection signal sequence."""
        recorder = MultiSignalRecorder()
        recorder.connect_signal(editing_controller.toolChanged, "toolChanged")
        recorder.connect_signal(editing_controller.colorChanged, "colorChanged")

        # Actions in sequence
        editing_controller.set_tool("fill")
        editing_controller.set_selected_color(5)
        QCoreApplication.processEvents()

        # Verify order: tool first, then color
        recorder.assert_emission_order(["toolChanged", "colorChanged"])

    def test_load_image_then_tool_signal_order(self, qtbot: QtBot, editing_controller) -> None:
        """Verify load_image, then set_tool signal sequence."""
        recorder = MultiSignalRecorder()
        recorder.connect_signal(editing_controller.imageChanged, "imageChanged")
        recorder.connect_signal(editing_controller.toolChanged, "toolChanged")

        # Actions in sequence
        data = np.zeros((8, 8), dtype=np.uint8)
        editing_controller.load_image(data)
        editing_controller.set_tool("picker")
        QCoreApplication.processEvents()

        # Verify order
        recorder.assert_emission_order(["imageChanged", "toolChanged"])

    def test_multiple_tool_changes_signal_order(self, qtbot: QtBot, editing_controller) -> None:
        """Verify multiple tool changes emit signals in order."""
        recorder = MultiSignalRecorder()
        recorder.connect_signal(editing_controller.toolChanged, "toolChanged")

        # Change tools multiple times
        editing_controller.set_tool("fill")
        editing_controller.set_tool("picker")
        editing_controller.set_tool("eraser")
        editing_controller.set_tool("pencil")
        QCoreApplication.processEvents()

        # Verify all emissions and their order
        assert recorder.count("toolChanged") == 4
        all_args = recorder.all_args("toolChanged")
        assert all_args == [("fill",), ("picker",), ("eraser",), ("pencil",)]


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
