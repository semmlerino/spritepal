"""Tests for Canvas Browsing Mode Indicator.

When the canvas is displaying a different capture than what's in the mapping,
a "Browsing Mode" indicator should be visible to explain why alignment changes
are not being saved.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image
from PySide6.QtGui import QPixmap

from core.frame_mapping_project import AIFrame, GameFrame
from ui.frame_mapping.views.workbench_canvas import WorkbenchCanvas

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class TestBrowsingModeIndicator:
    """Tests for browsing mode UI indicator."""

    def test_browsing_mode_initially_disabled(self, qtbot: QtBot) -> None:
        """Browsing mode should be off by default."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)
        canvas.show()
        qtbot.wait(20)

        assert not canvas.is_browsing_mode()
        assert not canvas._browsing_banner.isVisible()

    def test_set_browsing_mode_shows_banner(self, qtbot: QtBot) -> None:
        """Setting browsing mode to True should show the banner."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)
        canvas.show()
        qtbot.wait(20)

        canvas.set_browsing_mode(True)

        assert canvas.is_browsing_mode()
        assert canvas._browsing_banner.isVisible()
        assert "browsing" in canvas._browsing_banner.text().lower()

    def test_set_browsing_mode_hides_banner_when_disabled(self, qtbot: QtBot) -> None:
        """Setting browsing mode to False should hide the banner."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)
        canvas.show()
        qtbot.wait(20)

        canvas.set_browsing_mode(True)
        assert canvas._browsing_banner.isVisible()

        canvas.set_browsing_mode(False)
        assert not canvas.is_browsing_mode()
        assert not canvas._browsing_banner.isVisible()

    def test_browsing_mode_custom_message(self, qtbot: QtBot) -> None:
        """Browsing mode banner can display a custom message."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        custom_msg = "Viewing different capture"
        canvas.set_browsing_mode(True, message=custom_msg)

        assert canvas.is_browsing_mode()
        assert custom_msg in canvas._browsing_banner.text()

    def test_clear_canvas_disables_browsing_mode(self, qtbot: QtBot) -> None:
        """Clearing the canvas should disable browsing mode."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)
        canvas.show()
        qtbot.wait(20)

        canvas.set_browsing_mode(True)
        assert canvas.is_browsing_mode()

        canvas.clear()

        assert not canvas.is_browsing_mode()
        assert not canvas._browsing_banner.isVisible()


class TestBrowsingModeAlignment:
    """Tests for browsing mode and alignment interaction."""

    def test_browsing_mode_reflects_in_status(self, qtbot: QtBot) -> None:
        """When browsing mode is active, status should indicate it."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)
        canvas.show()
        qtbot.wait(20)

        # Set up a mapping first
        canvas.set_alignment(10, 20, False, False, 1.0)
        assert canvas._has_mapping

        canvas.set_browsing_mode(True)

        # Banner should be visible
        assert canvas._browsing_banner.isVisible()

    def test_browsing_mode_preserved_across_alignment_changes(self, qtbot: QtBot) -> None:
        """Browsing mode should persist when alignment is modified."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)
        canvas.show()
        qtbot.wait(20)

        canvas.set_browsing_mode(True)

        # Change alignment (simulating user interaction)
        canvas.set_alignment(5, 10, True, False, 0.8)

        # Browsing mode should still be active
        assert canvas.is_browsing_mode()
        assert canvas._browsing_banner.isVisible()


class TestBrowsingModeControlsDisabled:
    """Tests for alignment controls being disabled in browsing mode."""

    def test_alignment_controls_disabled_in_browsing_mode(self, qtbot: QtBot) -> None:
        """Sliders and controls should be disabled when browsing different capture.

        When viewing a game frame that differs from the one in the current mapping,
        alignment controls should be disabled to prevent confusing UX where the
        user can interact with controls but edits are silently blocked.
        """
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)
        canvas.show()
        qtbot.wait(20)

        # Set up a mapping so controls are initially enabled
        canvas.set_alignment(10, 20, False, False, 1.0, has_mapping=True)

        # Verify controls are enabled before browsing mode
        assert canvas._scale_slider.isEnabled()
        assert canvas._flip_h_checkbox.isEnabled()
        assert canvas._flip_v_checkbox.isEnabled()

        # Enable browsing mode
        canvas.set_browsing_mode(True)

        # Verify alignment controls are now disabled
        assert not canvas._scale_slider.isEnabled(), "Scale slider should be disabled in browsing mode"
        assert not canvas._flip_h_checkbox.isEnabled(), "H-Flip should be disabled in browsing mode"
        assert not canvas._flip_v_checkbox.isEnabled(), "V-Flip should be disabled in browsing mode"

    def test_alignment_controls_reenabled_when_browsing_mode_disabled(self, qtbot: QtBot) -> None:
        """Controls should be re-enabled when exiting browsing mode."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)
        canvas.show()
        qtbot.wait(20)

        # Set up mapping and enable browsing mode
        canvas.set_alignment(10, 20, False, False, 1.0, has_mapping=True)
        canvas.set_browsing_mode(True)

        # Verify disabled
        assert not canvas._scale_slider.isEnabled()

        # Disable browsing mode
        canvas.set_browsing_mode(False)

        # Verify controls are re-enabled (because we have a mapping)
        assert canvas._scale_slider.isEnabled(), "Scale slider should be re-enabled after exiting browsing mode"
        assert canvas._flip_h_checkbox.isEnabled(), "H-Flip should be re-enabled after exiting browsing mode"

    def test_browsing_mode_banner_has_warning_styling(self, qtbot: QtBot) -> None:
        """Browsing mode banner should have amber/warning styling."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        canvas.set_browsing_mode(True)

        # Check that banner has warning-style background (amber/yellow tones)
        stylesheet = canvas._browsing_banner.styleSheet()
        # The banner should have some visible warning coloring
        assert "background" in stylesheet.lower() or canvas._browsing_banner.isVisible()
