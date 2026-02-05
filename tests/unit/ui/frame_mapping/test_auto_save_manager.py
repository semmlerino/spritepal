"""Tests for AutoSaveManager and _SaveWorker from ui/frame_mapping/auto_save_manager.py.

Tests the background save worker and auto-save manager's handling of
successful saves, failed saves, and exception cases.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QTimer

from ui.frame_mapping.auto_save_manager import AutoSaveManager, _SaveWorker


class TestSaveWorker:
    """Tests for _SaveWorker background save operations."""

    def test_worker_emits_success_when_save_returns_true(self) -> None:
        """Worker calls save_project(path) -> returns True -> emits finished(True, "")."""
        # Arrange
        mock_save = MagicMock(return_value=True)
        test_path = Path("/tmp/test.spritepal-mapping.json")
        worker = _SaveWorker(mock_save, test_path)

        results: list[tuple[bool, str]] = []
        worker.signals.finished.connect(lambda success, msg: results.append((success, msg)))

        # Act
        worker.run()

        # Assert
        assert results == [(True, "")]
        mock_save.assert_called_once_with(test_path)

    def test_worker_emits_failure_when_save_returns_false(self) -> None:
        """Worker calls save_project(path) -> returns False -> emits finished(False, error msg)."""
        # Arrange
        mock_save = MagicMock(return_value=False)
        test_path = Path("/tmp/test.spritepal-mapping.json")
        worker = _SaveWorker(mock_save, test_path)

        results: list[tuple[bool, str]] = []
        worker.signals.finished.connect(lambda success, msg: results.append((success, msg)))

        # Act
        worker.run()

        # Assert
        assert results == [(False, "Save operation returned failure")]
        mock_save.assert_called_once_with(test_path)

    def test_worker_emits_failure_on_exception(self) -> None:
        """Worker calls save_project(path) -> raises RuntimeError -> emits finished(False, error msg)."""
        # Arrange
        mock_save = MagicMock(side_effect=RuntimeError("disk full"))
        test_path = Path("/tmp/test.spritepal-mapping.json")
        worker = _SaveWorker(mock_save, test_path)

        results: list[tuple[bool, str]] = []
        worker.signals.finished.connect(lambda success, msg: results.append((success, msg)))

        # Act
        worker.run()

        # Assert
        assert results == [(False, "disk full")]
        mock_save.assert_called_once_with(test_path)


class TestAutoSaveManager:
    """Tests for AutoSaveManager's handling of save success/failure."""

    def test_auto_save_manager_clears_dirty_only_on_success(self, qtbot) -> None:
        """AutoSaveManager receives finished(True) -> save_succeeded emitted -> on_save_success callback runs.

        On finished(False) -> save_failed emitted -> callback NOT called.
        """
        # Arrange
        mock_timer = MagicMock(spec=QTimer)
        mock_get_path = MagicMock(return_value=Path("/tmp/test.spritepal-mapping.json"))
        mock_save = MagicMock(return_value=True)
        on_save_success_called = []

        def on_success_callback() -> None:
            on_save_success_called.append(True)

        manager = AutoSaveManager(
            timer=mock_timer,
            get_project_path=mock_get_path,
            save_project=mock_save,
            show_message=None,
            parent_widget=None,
            on_save_success=on_success_callback,
        )

        # Test success case
        success_signals: list[bool] = []
        manager.save_succeeded.connect(lambda: success_signals.append(True))

        # Acquire lock to simulate normal flow (perform_save acquires it)
        manager._save_in_progress = True
        manager._save_lock.acquire()

        # Act - Simulate successful save completion
        manager._on_save_finished(True, "")

        # Assert - Success signal emitted and callback invoked
        assert success_signals == [True]
        assert on_save_success_called == [True]
        assert manager._save_in_progress is False

        # Test failure case
        on_save_success_called.clear()
        failed_signals: list[bool] = []
        manager.save_failed.connect(lambda: failed_signals.append(True))

        # Acquire lock again for failure case
        manager._save_in_progress = True
        manager._save_lock.acquire()

        # Act - Simulate failed save completion
        manager._on_save_finished(False, "disk full")

        # Assert - Failure signal emitted, callback NOT invoked
        assert failed_signals == [True]
        assert on_save_success_called == []  # Callback should NOT run on failure
        assert manager._save_in_progress is False
