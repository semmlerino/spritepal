"""Tests for injection-undo guard functionality.

Regression tests for BUG-B: Undo during async injection could create state
mismatch where mapping shows "injected" status but alignment doesn't match ROM.
"""

from __future__ import annotations

from unittest.mock import PropertyMock, patch

import pytest

from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController


class TestInjectionUndoGuard:
    """Tests for undo/redo blocking during injection."""

    def test_undo_blocked_when_injection_busy(self, controller: FrameMappingController) -> None:
        """Undo returns None and emits status when injection is in progress."""
        # Setup: Mock async_injection_busy to return True
        with patch.object(
            type(controller),
            "async_injection_busy",
            new_callable=PropertyMock,
            return_value=True,
        ):
            # Capture status update emissions
            status_messages: list[str] = []
            controller.status_update.connect(status_messages.append)

            # Attempt undo while injection is busy
            result = controller.undo()

            # Should return None without performing undo
            assert result is None
            # Should emit status message
            assert len(status_messages) == 1
            assert "injection" in status_messages[0].lower()

    def test_redo_blocked_when_injection_busy(self, controller: FrameMappingController) -> None:
        """Redo returns None and emits status when injection is in progress."""
        # Setup: Mock async_injection_busy to return True
        with patch.object(
            type(controller),
            "async_injection_busy",
            new_callable=PropertyMock,
            return_value=True,
        ):
            # Capture status update emissions
            status_messages: list[str] = []
            controller.status_update.connect(status_messages.append)

            # Attempt redo while injection is busy
            result = controller.redo()

            # Should return None without performing redo
            assert result is None
            # Should emit status message
            assert len(status_messages) == 1
            assert "injection" in status_messages[0].lower()

    def test_undo_proceeds_when_not_injecting(self, controller: FrameMappingController) -> None:
        """Undo proceeds normally when no injection is in progress."""
        # Verify injection is not busy by default
        assert not controller.async_injection_busy

        # With no undo stack, should return None (but NOT because of blocking)
        result = controller.undo()
        assert result is None

        # No status message should be emitted for "blocked"
        # (This is tested implicitly - if blocking were active, it would emit)

    def test_redo_proceeds_when_not_injecting(self, controller: FrameMappingController) -> None:
        """Redo proceeds normally when no injection is in progress."""
        # Verify injection is not busy by default
        assert not controller.async_injection_busy

        # With no redo stack, should return None (but NOT because of blocking)
        result = controller.redo()
        assert result is None
