"""Tests for workspace handling of stale entries on project load."""

from unittest.mock import Mock

from ui.workspaces.frame_mapping_workspace import FrameMappingWorkspace


class TestWorkspaceStaleLoad:
    """Test workspace handling of stale_entries_on_load signal."""

    def test_workspace_handler_exists(self, app_context: object) -> None:
        """Verify that _on_stale_entries_detected_on_load handler exists."""
        # Create workspace with minimal setup (tests handler method exists)
        workspace = FrameMappingWorkspace()

        # Verify the handler method exists and is callable
        assert hasattr(workspace, "_on_stale_entries_detected_on_load")
        assert callable(workspace._on_stale_entries_detected_on_load)

    def test_workspace_handler_shows_message(self, app_context: object) -> None:
        """Handler should call message service with appropriate message."""
        # Create workspace
        mock_message_service = Mock()
        workspace = FrameMappingWorkspace(message_service=mock_message_service)

        # Call handler directly with test data
        stale_frame_ids = ["F1234", "F5678", "F9999"]
        workspace._on_stale_entries_detected_on_load(stale_frame_ids)

        # Verify message service was called
        mock_message_service.show_message.assert_called_once()
        call_args = mock_message_service.show_message.call_args

        # Check the message contains the count and mentions stale entries
        message_text = call_args.args[0]
        assert "3" in message_text
        assert "stale" in message_text.lower()

        # Check the timeout is set
        timeout = call_args.kwargs.get("timeout")
        assert timeout is not None
        assert timeout >= 5000  # At least 5 seconds for a warning

    def test_workspace_handler_handles_empty_list(self, app_context: object) -> None:
        """Handler should handle empty stale list gracefully."""
        mock_message_service = Mock()
        workspace = FrameMappingWorkspace(message_service=mock_message_service)

        # Call handler with empty list
        workspace._on_stale_entries_detected_on_load([])

        # Message service should still be called
        mock_message_service.show_message.assert_called_once()
        call_args = mock_message_service.show_message.call_args
        message_text = call_args.args[0]
        assert "0" in message_text

    def test_workspace_handler_no_message_service(self, app_context: object) -> None:
        """Handler should not crash if message service is None."""
        workspace = FrameMappingWorkspace(message_service=None)

        # Should not crash
        workspace._on_stale_entries_detected_on_load(["F1234", "F5678"])
