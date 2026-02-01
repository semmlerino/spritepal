"""Tests for AutoSaveManager.

Tests debounced auto-save functionality for Frame Mapping projects.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QThreadPool, QTimer
from pytestqt.qtbot import QtBot

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


def _wait_for_threadpool(qtbot: QtBot, timeout_ms: int = 5000) -> None:
    """Wait for QThreadPool to complete all tasks."""

    def check_done() -> bool:
        return QThreadPool.globalInstance().activeThreadCount() == 0

    qtbot.waitUntil(check_done, timeout=timeout_ms)


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

    def test_perform_save_calls_save_project(self, mock_project_path: Path, mock_timer: QTimer, qtbot: QtBot) -> None:
        """perform_save calls the save_project callback with path in background."""
        save_fn = MagicMock()
        manager = AutoSaveManager(
            timer=mock_timer,
            get_project_path=lambda: mock_project_path,
            save_project=save_fn,
        )

        manager.perform_save()
        _wait_for_threadpool(qtbot)

        save_fn.assert_called_once_with(mock_project_path)

    def test_perform_save_shows_message_on_success(
        self, mock_project_path: Path, mock_timer: QTimer, qtbot: QtBot
    ) -> None:
        """perform_save shows status message on success."""
        msg_fn = MagicMock()
        manager = AutoSaveManager(
            timer=mock_timer,
            get_project_path=lambda: mock_project_path,
            save_project=MagicMock(),
            show_message=msg_fn,
        )

        manager.perform_save()
        _wait_for_threadpool(qtbot)

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

    def test_perform_save_handles_exception(self, mock_project_path: Path, mock_timer: QTimer, qtbot: QtBot) -> None:
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
        _wait_for_threadpool(qtbot)

    def test_perform_save_shows_error_dialog_on_failure(
        self, mock_project_path: Path, mock_timer: QTimer, qapp: None, qtbot: QtBot
    ) -> None:
        """perform_save shows error dialog when save fails and parent exists."""
        save_fn = MagicMock(side_effect=RuntimeError("Save failed"))

        # Need a real widget for QMessageBox
        from PySide6.QtWidgets import QWidget

        parent_widget = QWidget()

        manager = AutoSaveManager(
            timer=mock_timer,
            get_project_path=lambda: mock_project_path,
            save_project=save_fn,
            parent_widget=parent_widget,
        )

        with patch("ui.frame_mapping.auto_save_manager.QMessageBox") as mock_box:
            manager.perform_save()
            _wait_for_threadpool(qtbot)

            mock_box.warning.assert_called_once()
            args = mock_box.warning.call_args
            assert args[0][0] is parent_widget
            assert "Auto-Save Failed" in args[0][1]

        parent_widget.deleteLater()

    def test_perform_save_skips_if_save_in_progress(
        self, mock_project_path: Path, mock_timer: QTimer, qtbot: QtBot
    ) -> None:
        """perform_save skips if another save is already in progress."""
        save_fn = MagicMock()
        manager = AutoSaveManager(
            timer=mock_timer,
            get_project_path=lambda: mock_project_path,
            save_project=save_fn,
        )

        # Manually set in-progress flag
        manager._save_in_progress = True

        manager.perform_save()

        # Should not have called save_project since we're in progress
        save_fn.assert_not_called()

    def test_perform_save_clears_in_progress_flag_on_completion(
        self, mock_project_path: Path, mock_timer: QTimer, qtbot: QtBot
    ) -> None:
        """perform_save clears the in-progress flag after completion."""
        manager = AutoSaveManager(
            timer=mock_timer,
            get_project_path=lambda: mock_project_path,
            save_project=MagicMock(),
        )

        manager.perform_save()
        _wait_for_threadpool(qtbot)

        # Wait for signal to be processed (queued connection from worker thread)
        def check_flag_cleared() -> bool:
            return not manager._save_in_progress

        qtbot.waitUntil(check_flag_cleared, timeout=1000)

        assert not manager._save_in_progress


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


class TestSaveLock:
    """Test save lock prevents concurrent auto/manual saves."""

    def test_try_acquire_save_lock_succeeds_when_not_held(self, auto_save_manager: AutoSaveManager) -> None:
        """try_acquire_save_lock returns True when lock is not held."""
        result = auto_save_manager.try_acquire_save_lock()

        assert result is True
        # Cleanup
        auto_save_manager.release_save_lock()

    def test_try_acquire_save_lock_fails_when_already_held(self, auto_save_manager: AutoSaveManager) -> None:
        """try_acquire_save_lock returns False when lock is already held."""
        # Acquire lock first time
        first_acquire = auto_save_manager.try_acquire_save_lock()
        assert first_acquire is True

        # Second acquire should fail
        second_acquire = auto_save_manager.try_acquire_save_lock()
        assert second_acquire is False

        # Cleanup
        auto_save_manager.release_save_lock()

    def test_perform_save_skips_when_lock_held(self, mock_project_path: Path, mock_timer: QTimer) -> None:
        """perform_save skips if lock is already held (manual save in progress)."""
        save_fn = MagicMock()
        manager = AutoSaveManager(
            timer=mock_timer,
            get_project_path=lambda: mock_project_path,
            save_project=save_fn,
        )

        # Simulate manual save holding the lock
        lock_acquired = manager.try_acquire_save_lock()
        assert lock_acquired is True

        # Auto-save should skip
        manager.perform_save()

        # Should not have called save_project since lock is held
        save_fn.assert_not_called()

        # Cleanup
        manager.release_save_lock()

    def test_is_save_in_progress_reflects_save_state(
        self, mock_project_path: Path, mock_timer: QTimer, qtbot: QtBot
    ) -> None:
        """is_save_in_progress property reflects the current save state."""
        manager = AutoSaveManager(
            timer=mock_timer,
            get_project_path=lambda: mock_project_path,
            save_project=MagicMock(),
        )

        # Initially not in progress
        assert not manager.is_save_in_progress

        # Start save
        manager.perform_save()

        # Should be in progress immediately
        assert manager.is_save_in_progress

        # Wait for completion
        _wait_for_threadpool(qtbot)

        def check_completed() -> bool:
            return not manager.is_save_in_progress

        qtbot.waitUntil(check_completed, timeout=1000)

        # Should be done after completion
        assert not manager.is_save_in_progress
