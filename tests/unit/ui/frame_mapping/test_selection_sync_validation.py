"""Tests for selection sync validation functionality.

Tests that the debug validation mechanism correctly detects when cached
selection state diverges from pane state.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from ui.frame_mapping.workspace_state_manager import WorkspaceStateManager


@pytest.fixture
def state_manager() -> WorkspaceStateManager:
    """Create a WorkspaceStateManager for testing."""
    return WorkspaceStateManager()


@pytest.fixture
def mock_ai_pane() -> MagicMock:
    """Create a mock AI pane with SelectionPane interface."""
    pane = MagicMock()
    pane.get_selected_id.return_value = "frame_001.png"
    return pane


@pytest.fixture
def mock_captures_pane() -> MagicMock:
    """Create a mock captures pane with SelectionPane interface."""
    pane = MagicMock()
    pane.get_selected_id.return_value = "capture_abc"
    return pane


class TestSelectionSyncValidation:
    """Tests for selection sync validation."""

    def test_validate_sync_skipped_without_env_var(
        self,
        state_manager: WorkspaceStateManager,
        mock_ai_pane: MagicMock,
        mock_captures_pane: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Validation is skipped when SPRITEPAL_DEBUG_STATE is not set."""
        # Ensure env var is not set
        os.environ.pop("SPRITEPAL_DEBUG_STATE", None)

        # Set up mismatch
        state_manager._selected_ai_frame_id = "wrong_id"

        # Call validate - should do nothing
        state_manager.validate_selection_sync(mock_ai_pane, mock_captures_pane)

        # No warning should be logged
        assert "STATE SYNC" not in caplog.text

    def test_validate_sync_logs_ai_mismatch_when_enabled(
        self,
        state_manager: WorkspaceStateManager,
        mock_ai_pane: MagicMock,
        mock_captures_pane: MagicMock,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Validation logs warning when AI selection mismatches."""
        # Enable debug mode
        monkeypatch.setenv("SPRITEPAL_DEBUG_STATE", "1")

        # Set up mismatch: pane says "frame_001.png" but cache says "wrong_id"
        state_manager._selected_ai_frame_id = "wrong_id"

        # Sync game selection to avoid second warning
        state_manager._selected_game_id = "capture_abc"

        # Call validate
        state_manager.validate_selection_sync(mock_ai_pane, mock_captures_pane)

        # Warning should be logged
        assert "STATE SYNC: AI frame selection mismatch" in caplog.text
        assert "wrong_id" in caplog.text

    def test_validate_sync_logs_game_mismatch_when_enabled(
        self,
        state_manager: WorkspaceStateManager,
        mock_ai_pane: MagicMock,
        mock_captures_pane: MagicMock,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Validation logs warning when game selection mismatches."""
        # Enable debug mode
        monkeypatch.setenv("SPRITEPAL_DEBUG_STATE", "1")

        # Sync AI selection to avoid first warning
        state_manager._selected_ai_frame_id = "frame_001.png"

        # Set up mismatch: pane says "capture_abc" but cache says "wrong_capture"
        state_manager._selected_game_id = "wrong_capture"

        # Call validate
        state_manager.validate_selection_sync(mock_ai_pane, mock_captures_pane)

        # Warning should be logged
        assert "STATE SYNC: Game frame selection mismatch" in caplog.text
        assert "wrong_capture" in caplog.text

    def test_validate_sync_no_warning_when_synced(
        self,
        state_manager: WorkspaceStateManager,
        mock_ai_pane: MagicMock,
        mock_captures_pane: MagicMock,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """No warning logged when cached state matches pane state."""
        # Enable debug mode
        monkeypatch.setenv("SPRITEPAL_DEBUG_STATE", "1")

        # Sync both selections correctly
        state_manager._selected_ai_frame_id = "frame_001.png"
        state_manager._selected_game_id = "capture_abc"

        # Call validate
        state_manager.validate_selection_sync(mock_ai_pane, mock_captures_pane)

        # No warning should be logged
        assert "STATE SYNC" not in caplog.text
