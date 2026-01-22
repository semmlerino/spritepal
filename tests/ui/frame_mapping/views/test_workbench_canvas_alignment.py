"""Tests for WorkbenchCanvas alignment controls state management.

Bug #2: clear_alignment() sets _has_mapping=False then calls set_alignment()
which unconditionally sets _has_mapping=True, re-enabling controls incorrectly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ui.frame_mapping.views.workbench_canvas import WorkbenchCanvas

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class TestAlignmentControlsState:
    """Tests for Bug #2: alignment controls enabled without mapping."""

    def test_clear_alignment_disables_controls(self, qtbot: QtBot) -> None:
        """clear_alignment must leave controls disabled."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # First set a mapping to enable controls
        canvas.set_alignment(10, 20, True, False, 1.5)
        assert canvas._has_mapping is True
        assert canvas._flip_h_checkbox.isEnabled()
        assert canvas._flip_v_checkbox.isEnabled()
        assert canvas._scale_slider.isEnabled()

        # Now clear alignment - controls should be disabled
        canvas.clear_alignment()

        assert canvas._has_mapping is False
        assert not canvas._flip_h_checkbox.isEnabled()
        assert not canvas._flip_v_checkbox.isEnabled()
        assert not canvas._scale_slider.isEnabled()

    def test_clear_alignment_resets_values_to_defaults(self, qtbot: QtBot) -> None:
        """clear_alignment should reset values to defaults while keeping controls disabled."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Set non-default values
        canvas.set_alignment(50, -30, True, True, 2.0)

        # Clear should reset to 0,0 no-flip 1.0x
        canvas.clear_alignment()

        # Values should be reset
        assert canvas._flip_h_checkbox.isChecked() is False
        assert canvas._flip_v_checkbox.isChecked() is False
        assert canvas._scale_slider.value() == 100  # 1.0x
        # Controls should still be disabled
        assert canvas._has_mapping is False

    def test_set_alignment_enables_controls(self, qtbot: QtBot) -> None:
        """set_alignment (normal call) should enable controls."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Initially no mapping
        assert canvas._has_mapping is False
        assert not canvas._flip_h_checkbox.isEnabled()

        # Set alignment should enable
        canvas.set_alignment(0, 0, False, False, 1.0)

        assert canvas._has_mapping is True
        assert canvas._flip_h_checkbox.isEnabled()
        assert canvas._flip_v_checkbox.isEnabled()
        assert canvas._scale_slider.isEnabled()
