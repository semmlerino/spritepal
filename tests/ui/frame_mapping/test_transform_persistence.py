"""Tests for transform persistence when switching between AI frames.

Bug: Scale changes are lost when moving to a different AI frame and back.
Offset and flip changes persist correctly because their handlers call
_emit_alignment_changed(), but _on_scale_slider_changed did not.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.fixtures.timeouts import signal_timeout
from ui.frame_mapping.views.workbench_types import AlignmentState

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

from ui.frame_mapping.views.workbench_canvas import WorkbenchCanvas


class TestScalePersistence:
    """Tests for scale transform persistence via alignment_changed signal."""

    def test_scale_slider_emits_alignment_changed(self, qtbot: QtBot) -> None:
        """Scale slider change should emit alignment_changed signal.

        Bug: _on_scale_slider_changed() did not call _emit_alignment_changed(),
        so scale changes were never persisted to the mapping.

        This test verifies that changing the scale slider emits the signal
        that triggers persistence to the project mapping.
        """
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Enable controls (requires set_alignment to have been called)
        canvas.set_alignment(0, 0, False, False, 1.0)
        assert canvas._scale_slider.isEnabled()

        # Start with default scale
        default_scale = canvas._scale_slider.value()
        assert default_scale == 1000  # 1.0x

        # Record emitted values
        emitted_values: list[AlignmentState] = []

        def record_emission(state: AlignmentState) -> None:
            emitted_values.append(state)

        canvas.alignment_changed.connect(record_emission)

        # Change scale to 0.5x (500/1000)
        canvas._scale_slider.setValue(500)

        # ASSERTION: Signal should have been emitted with new scale value
        assert len(emitted_values) >= 1, "alignment_changed signal not emitted on scale change"

        # The last emission should contain scale=0.5
        last_state = emitted_values[-1]
        assert abs(last_state.scale - 0.5) < 0.01, f"Expected scale=0.5, got {last_state.scale}"

    def test_scale_persistence_matches_flip_pattern(self, qtbot: QtBot) -> None:
        """Scale handler should follow the same emit pattern as flip handler.

        Both _on_flip_changed and _on_scale_slider_changed should emit
        alignment_changed signal to persist transforms.

        Note: Slider range is 10-100 (0.1x to 1.0x), so we use 50 (0.5x).
        """
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Enable controls with initial scale 1.0 (100%)
        canvas.set_alignment(0, 0, False, False, 1.0)

        flip_emissions: list[AlignmentState] = []
        scale_emissions: list[AlignmentState] = []

        def record_flip(state: AlignmentState) -> None:
            flip_emissions.append(state)

        def record_scale(state: AlignmentState) -> None:
            scale_emissions.append(state)

        # Test flip emits signal
        canvas.alignment_changed.connect(record_flip)
        canvas._flip_h_checkbox.setChecked(True)
        canvas.alignment_changed.disconnect(record_flip)

        # Reset flip for clean state
        canvas._flip_h_checkbox.setChecked(False)

        # Test scale emits signal (must use value in range 10-1000, different from current)
        canvas.alignment_changed.connect(record_scale)
        canvas._scale_slider.setValue(500)  # 0.5x - valid and different from initial 1.0
        canvas.alignment_changed.disconnect(record_scale)

        # Both should emit
        assert len(flip_emissions) >= 1, "Flip did not emit alignment_changed"
        assert len(scale_emissions) >= 1, "Scale did not emit alignment_changed (BUG)"

    def test_scale_changes_trigger_preview_update(self, qtbot: QtBot) -> None:
        """Scale changes should schedule preview update like flip changes.

        _on_flip_changed calls _schedule_preview_update() to update the
        in-game preview. _on_scale_slider_changed should do the same.
        """
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Enable controls and preview
        canvas.set_alignment(0, 0, False, False, 1.0)
        canvas._preview_enabled = True

        # Track preview_snapshot which is set by _schedule_preview_update
        initial_snapshot = canvas._preview_snapshot

        # Change scale
        canvas._scale_slider.setValue(750)  # 0.75x

        # Preview snapshot should have been updated
        # _schedule_preview_update captures (offset_x, offset_y, flip_h, flip_v, scale)
        assert canvas._preview_snapshot is not None, "Preview snapshot not set"
        if initial_snapshot is not None:
            # Check scale component changed
            _, _, _, _, snapshot_scale = canvas._preview_snapshot
            assert abs(snapshot_scale - 0.75) < 0.01, f"Preview snapshot scale={snapshot_scale}, expected 0.75"
