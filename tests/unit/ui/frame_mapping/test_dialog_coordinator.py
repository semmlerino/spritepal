"""Tests for CaptureImportCoordinator.

Tests dialog orchestration without GUI interactions by mocking all dialogs.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.mesen_integration.click_extractor import CaptureResult, OAMEntry
from ui.frame_mapping.dialog_coordinator import CaptureImportCoordinator


@pytest.fixture
def coordinator():
    """Create a dialog coordinator."""
    return CaptureImportCoordinator()


@pytest.fixture
def mock_capture_result():
    """Create a mock capture result."""
    entry = OAMEntry(
        id=0,
        x=10,
        y=20,
        width=16,
        height=16,
        tile=0,
        palette=0,
        priority=2,
        flip_h=False,
        flip_v=False,
    )
    return CaptureResult(
        frame=100,
        visible_count=1,
        obsel=0,
        entries=[entry],
        palettes=[[0, 0, 0] for _ in range(16)],
        timestamp="2024-01-01T00:00:00",
    )


@pytest.fixture
def mock_controller():
    """Create a mock frame mapping controller."""
    controller = MagicMock()
    controller.complete_capture_import = MagicMock(return_value=None)
    return controller


def test_initial_state(coordinator):
    """Test coordinator starts with empty queue."""
    assert coordinator.get_queue_size() == 0


def test_queue_capture(coordinator, mock_capture_result):
    """Test queuing a capture for import."""
    capture_path = Path("/test/capture.json")
    coordinator.queue_capture_import(mock_capture_result, capture_path)

    assert coordinator.get_queue_size() == 1


def test_queue_multiple_captures(coordinator, mock_capture_result):
    """Test queuing multiple captures."""
    path1 = Path("/test/capture1.json")
    path2 = Path("/test/capture2.json")

    coordinator.queue_capture_import(mock_capture_result, path1)
    coordinator.queue_capture_import(mock_capture_result, path2)

    assert coordinator.get_queue_size() == 2


def test_clear_queue(coordinator, mock_capture_result):
    """Test clearing the queue."""
    coordinator.queue_capture_import(mock_capture_result, Path("/test/capture.json"))
    assert coordinator.get_queue_size() == 1

    coordinator.clear_queue()
    assert coordinator.get_queue_size() == 0


def test_show_sprite_selection_accepted(coordinator, mock_capture_result):
    """Test sprite selection dialog when user accepts."""
    capture_path = Path("/test/capture.json")
    mock_entry = mock_capture_result.entries[0]

    with patch("ui.frame_mapping.dialog_coordinator.SpriteSelectionDialog") as mock_dialog_cls:
        # Create mock dialog instance
        mock_dialog = MagicMock()
        mock_dialog.exec.return_value = 1  # QDialog.DialogCode.Accepted
        mock_dialog.selected_entries = [mock_entry]
        mock_dialog_cls.return_value = mock_dialog

        result = coordinator.show_sprite_selection(coordinator, mock_capture_result, capture_path)

        assert result == [mock_entry]
        mock_dialog.exec.assert_called_once()


def test_show_sprite_selection_rejected(coordinator, mock_capture_result):
    """Test sprite selection dialog when user rejects."""
    capture_path = Path("/test/capture.json")

    with patch("ui.frame_mapping.dialog_coordinator.SpriteSelectionDialog") as mock_dialog_cls:
        # Create mock dialog instance
        mock_dialog = MagicMock()
        mock_dialog.exec.return_value = 0  # QDialog.DialogCode.Rejected
        mock_dialog_cls.return_value = mock_dialog

        result = coordinator.show_sprite_selection(coordinator, mock_capture_result, capture_path)

        assert result is None
        mock_dialog.exec.assert_called_once()




def test_process_empty_queue(qtbot, coordinator, mock_controller):
    """Test processing empty queue emits finished signal immediately."""
    with qtbot.waitSignal(coordinator.queue_processing_finished, timeout=1000) as blocker:
        coordinator.process_capture_import_queue(coordinator, mock_controller)

    # Should emit 0 for empty queue
    assert blocker.args == [0]


def test_process_queue_with_accepted_dialog(qtbot, coordinator, mock_capture_result, mock_controller):
    """Test processing queue when user accepts dialog."""
    capture_path = Path("/test/capture.json")
    mock_entry = mock_capture_result.entries[0]

    # Set up controller to return a frame
    mock_frame = MagicMock()
    mock_frame.id = "game_01"
    mock_controller.complete_capture_import.return_value = mock_frame

    # Queue the capture
    coordinator.queue_capture_import(mock_capture_result, capture_path)

    with patch("ui.frame_mapping.dialog_coordinator.SpriteSelectionDialog") as mock_dialog_cls:
        # Mock dialog accepting
        mock_dialog = MagicMock()
        mock_dialog.exec.return_value = 1  # Accepted
        mock_dialog.selected_entries = [mock_entry]
        mock_dialog_cls.return_value = mock_dialog

        # Process queue
        with qtbot.waitSignal(coordinator.queue_processing_finished, timeout=1000) as blocker:
            coordinator.process_capture_import_queue(coordinator, mock_controller)

        # Should emit 1 successful import
        assert blocker.args == [1]
        mock_controller.complete_capture_import.assert_called_once()


def test_process_queue_with_rejected_dialog(qtbot, coordinator, mock_capture_result, mock_controller):
    """Test processing queue when user rejects dialog."""
    capture_path = Path("/test/capture.json")

    # Queue the capture
    coordinator.queue_capture_import(mock_capture_result, capture_path)

    with patch("ui.frame_mapping.dialog_coordinator.SpriteSelectionDialog") as mock_dialog_cls:
        # Mock dialog rejecting
        mock_dialog = MagicMock()
        mock_dialog.exec.return_value = 0  # Rejected
        mock_dialog_cls.return_value = mock_dialog

        # Process queue
        with qtbot.waitSignal(coordinator.queue_processing_finished, timeout=1000) as blocker:
            coordinator.process_capture_import_queue(coordinator, mock_controller)

        # Should emit 0 (user cancelled)
        assert blocker.args == [0]
        mock_controller.complete_capture_import.assert_not_called()


def test_process_queue_multiple_captures(qtbot, coordinator, mock_capture_result, mock_controller):
    """Test processing queue with multiple captures."""
    path1 = Path("/test/capture1.json")
    path2 = Path("/test/capture2.json")
    mock_entry = mock_capture_result.entries[0]

    # Set up controller to return frames
    mock_frame1 = MagicMock()
    mock_frame1.id = "game_01"
    mock_frame2 = MagicMock()
    mock_frame2.id = "game_02"
    mock_controller.complete_capture_import.side_effect = [mock_frame1, mock_frame2]

    # Queue captures
    coordinator.queue_capture_import(mock_capture_result, path1)
    coordinator.queue_capture_import(mock_capture_result, path2)

    with patch("ui.frame_mapping.dialog_coordinator.SpriteSelectionDialog") as mock_dialog_cls:
        # Mock dialog accepting both times
        mock_dialog = MagicMock()
        mock_dialog.exec.return_value = 1  # Accepted
        mock_dialog.selected_entries = [mock_entry]
        mock_dialog_cls.return_value = mock_dialog

        # Process queue
        with qtbot.waitSignal(coordinator.queue_processing_finished, timeout=1000) as blocker:
            coordinator.process_capture_import_queue(coordinator, mock_controller)

        # Should emit 2 successful imports
        assert blocker.args == [2]
        assert mock_controller.complete_capture_import.call_count == 2


def test_successful_import_increments_count(qtbot, coordinator, mock_capture_result, mock_controller):
    """Test successful import increments the import count."""
    capture_path = Path("/test/capture.json")
    mock_entry = mock_capture_result.entries[0]

    # Set up controller to return a frame
    mock_frame = MagicMock()
    mock_frame.id = "game_01"
    mock_controller.complete_capture_import.return_value = mock_frame

    # Queue the capture
    coordinator.queue_capture_import(mock_capture_result, capture_path)

    with patch("ui.frame_mapping.dialog_coordinator.SpriteSelectionDialog") as mock_dialog_cls:
        # Mock dialog accepting
        mock_dialog = MagicMock()
        mock_dialog.exec.return_value = 1  # Accepted
        mock_dialog.selected_entries = [mock_entry]
        mock_dialog_cls.return_value = mock_dialog

        # Process queue and verify final count via queue_processing_finished signal
        with qtbot.waitSignal(coordinator.queue_processing_finished, timeout=1000) as blocker:
            coordinator.process_capture_import_queue(coordinator, mock_controller)

        # Should emit 1 for single successful import
        assert blocker.args == [1]
