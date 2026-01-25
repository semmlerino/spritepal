"""
Tests for SourceBar action button state synchronization.

Bug context: After preview completes (success or error), the action button
stays disabled because set_action_loading(False) is a no-op and the
controller doesn't explicitly re-enable the button.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

import pytest

from core.services.signal_payloads import PreviewData

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


@pytest.fixture
def source_bar(qtbot: QtBot):
    """Create a SourceBar widget."""
    from ui.sprite_editor.views.widgets.source_bar import SourceBar

    bar = SourceBar()
    qtbot.addWidget(bar)
    return bar


class TestActionButtonLoadingState:
    """Tests for action button enabled state after loading completes."""

    def test_action_button_disabled_during_loading(self, source_bar) -> None:
        """Action button should be disabled when loading is True."""
        source_bar.set_action_loading(True)

        assert source_bar.action_btn.isEnabled() is False
        assert source_bar.action_btn.text() == "Loading..."

    def test_action_button_stays_disabled_after_loading_false_no_reenable(self, source_bar) -> None:
        """
        set_action_loading(False) does NOT re-enable the button (by design).

        This test documents the documented API behavior - the controller
        must explicitly call set_action_enabled(True).
        """
        source_bar.set_action_loading(True)
        source_bar.set_action_loading(False)

        # The button stays disabled - this is the documented behavior
        assert source_bar.action_btn.isEnabled() is False

    def test_action_button_enabled_after_explicit_reenable(self, source_bar) -> None:
        """After loading, explicit set_action_enabled(True) re-enables button."""
        source_bar.set_action_loading(True)
        source_bar.set_action_loading(False)
        source_bar.set_action_enabled(True)

        assert source_bar.action_btn.isEnabled() is True


class TestControllerPreviewButtonSync:
    """Integration tests for controller re-enabling button after preview."""

    def test_action_button_enabled_after_preview_ready(self, qtbot: QtBot) -> None:
        """
        BUG REPRODUCTION: After successful preview, button should be enabled.

        This test will FAIL before the fix is applied.
        """
        from ui.sprite_editor.controllers.rom_workflow_controller import (
            ROMWorkflowController,
        )

        # Create mock source bar that tracks calls
        mock_source_bar = Mock()
        mock_source_bar.action_btn = Mock()

        # Create mock view with the source bar
        mock_view = Mock()
        mock_view.source_bar = mock_source_bar
        mock_view.workspace = None
        mock_view.asset_browser = Mock()

        with patch("ui.sprite_editor.controllers.rom_workflow_controller.SmartPreviewCoordinator"):
            controller = ROMWorkflowController(
                parent=None,
                editing_controller=Mock(has_unsaved_changes=Mock(return_value=False)),
                rom_extractor=Mock(),
            )
            controller._view = mock_view
            controller.current_offset = 0x1000

            # Simulate preview ready callback
            controller._on_preview_ready(
                PreviewData(
                    tile_data=bytes(32),
                    width=8,
                    height=8,
                    sprite_name="Test",
                    compressed_size=32,
                    slack_size=0,
                    actual_offset=0x1000,
                    hal_succeeded=True,
                    header_bytes=b"",
                )
            )

            # Verify set_action_enabled(True) was called
            mock_source_bar.set_action_enabled.assert_called_with(True)

    def test_action_button_enabled_after_preview_error(self, qtbot: QtBot) -> None:
        """
        BUG REPRODUCTION: After preview error, button should be enabled.

        This test will FAIL before the fix is applied.
        """
        from ui.sprite_editor.controllers.rom_workflow_controller import (
            ROMWorkflowController,
        )

        mock_source_bar = Mock()
        mock_view = Mock()
        mock_view.source_bar = mock_source_bar
        mock_view.workspace = None

        with patch("ui.sprite_editor.controllers.rom_workflow_controller.SmartPreviewCoordinator"):
            controller = ROMWorkflowController(
                parent=None,
                editing_controller=Mock(has_unsaved_changes=Mock(return_value=False)),
                rom_extractor=Mock(),
            )
            controller._view = mock_view
            controller._message_service = Mock()

            # Simulate preview error callback
            controller._on_preview_error("Decompression failed")

            # Verify set_action_enabled(True) was called
            mock_source_bar.set_action_enabled.assert_called_with(True)
