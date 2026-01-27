"""Tests for AutoSaveManager.

Tests debounced auto-save functionality for Frame Mapping projects.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QTimer

from ui.frame_mapping.auto_save_manager import AutoSaveManager


@pytest.fixture
def mock_timer() -> QTimer:
    """Create a mock QTimer for testing."""
    timer = MagicMock(spec=QTimer)
    timer.start = MagicMock()
    return timer


@pytest.fixture
def mock_project_path(tmp_path: Path) -> Path:
    """Create a mock project path."""
    return tmp_path / "test_project.spritepal-mapping.json"


@pytest.fixture
def auto_save_manager(mock_timer: QTimer, mock_project_path: Path) -> AutoSaveManager:
    """Create an AutoSaveManager for testing."""
    return AutoSaveManager(
        timer=mock_timer,
        get_project_path=lambda: mock_project_path,
        save_project=MagicMock(),
        show_message=MagicMock(),
        parent_widget=None,
    )


class TestAutoSaveManagerInit:
    """Test AutoSaveManager initialization."""

    def test_init_stores_dependencies(self, mock_timer: QTimer, mock_project_path: Path) -> None:
        """AutoSaveManager stores provided dependencies."""
        save_fn = MagicMock()
        msg_fn = MagicMock()

        manager = AutoSaveManager(
            timer=mock_timer,
            get_project_path=lambda: mock_project_path,
            save_project=save_fn,
            show_message=msg_fn,
        )

        assert manager._timer is mock_timer
        assert manager._save_project is save_fn
        assert manager._show_message is msg_fn


class TestScheduleSave:
    """Test schedule_save method."""

    def test_schedule_save_starts_timer(self, auto_save_manager: AutoSaveManager, mock_timer: QTimer) -> None:
        """schedule_save starts the debounce timer."""
        auto_save_manager.schedule_save()

        mock_timer.start.assert_called_once()

    def test_schedule_save_no_path_logs_warning(self, mock_timer: QTimer, caplog: pytest.LogCaptureFixture) -> None:
        """schedule_save logs warning when no project path."""
        manager = AutoSaveManager(
            timer=mock_timer,
            get_project_path=lambda: None,
            save_project=MagicMock(),
        )

        manager.schedule_save()

        mock_timer.start.assert_not_called()
        assert "Cannot auto-save: no project path set" in caplog.text


class TestPerformSave:
    """Test perform_save method."""

    def test_perform_save_calls_save_project(self, mock_project_path: Path, mock_timer: QTimer) -> None:
        """perform_save calls the save_project callback with path."""
        save_fn = MagicMock()
        manager = AutoSaveManager(
            timer=mock_timer,
            get_project_path=lambda: mock_project_path,
            save_project=save_fn,
        )

        manager.perform_save()

        save_fn.assert_called_once_with(mock_project_path)

    def test_perform_save_shows_message_on_success(self, mock_project_path: Path, mock_timer: QTimer) -> None:
        """perform_save shows status message on success."""
        msg_fn = MagicMock()
        manager = AutoSaveManager(
            timer=mock_timer,
            get_project_path=lambda: mock_project_path,
            save_project=MagicMock(),
            show_message=msg_fn,
        )

        manager.perform_save()

        msg_fn.assert_called_once_with("Project auto-saved", 2000)

    def test_perform_save_no_path_does_nothing(self, mock_timer: QTimer) -> None:
        """perform_save does nothing when no project path."""
        save_fn = MagicMock()
        manager = AutoSaveManager(
            timer=mock_timer,
            get_project_path=lambda: None,
            save_project=save_fn,
        )

        manager.perform_save()

        save_fn.assert_not_called()

    def test_perform_save_handles_exception(self, mock_project_path: Path, mock_timer: QTimer) -> None:
        """perform_save handles save errors gracefully."""
        save_fn = MagicMock(side_effect=RuntimeError("Save failed"))
        manager = AutoSaveManager(
            timer=mock_timer,
            get_project_path=lambda: mock_project_path,
            save_project=save_fn,
            parent_widget=None,  # No dialog shown without parent
        )

        # Should not raise
        manager.perform_save()

    def test_perform_save_shows_error_dialog_on_failure(
        self, mock_project_path: Path, mock_timer: QTimer, qapp: None
    ) -> None:
        """perform_save shows error dialog when save fails and parent exists."""
        save_fn = MagicMock(side_effect=RuntimeError("Save failed"))
        mock_widget = MagicMock()

        manager = AutoSaveManager(
            timer=mock_timer,
            get_project_path=lambda: mock_project_path,
            save_project=save_fn,
            parent_widget=mock_widget,
        )

        with patch("ui.frame_mapping.auto_save_manager.QMessageBox") as mock_box:
            manager.perform_save()

            mock_box.warning.assert_called_once()
            args = mock_box.warning.call_args
            assert args[0][0] is mock_widget
            assert "Auto-Save Failed" in args[0][1]


class TestSetMessageService:
    """Test set_message_service method."""

    def test_set_message_service_updates_callback(self, auto_save_manager: AutoSaveManager) -> None:
        """set_message_service updates the show_message callback."""
        new_msg_fn = MagicMock()

        auto_save_manager.set_message_service(new_msg_fn)

        assert auto_save_manager._show_message is new_msg_fn

    def test_set_message_service_to_none(self, auto_save_manager: AutoSaveManager) -> None:
        """set_message_service can set callback to None."""
        auto_save_manager.set_message_service(None)

        assert auto_save_manager._show_message is None


class TestSetParentWidget:
    """Test set_parent_widget method."""

    def test_set_parent_widget_updates_widget(self, auto_save_manager: AutoSaveManager) -> None:
        """set_parent_widget updates the parent widget."""
        mock_widget = MagicMock()

        auto_save_manager.set_parent_widget(mock_widget)

        assert auto_save_manager._parent_widget is mock_widget
