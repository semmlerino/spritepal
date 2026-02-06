"""Tests for FileSelector widget."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ui.components.inputs.file_selector import FileSelector

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


pytestmark = pytest.mark.gui


@pytest.fixture
def mock_settings() -> Mock:
    """Create mock settings manager."""
    return Mock()


@pytest.fixture
def widget(qtbot: QtBot, mock_settings: Mock) -> FileSelector:
    """Create default FileSelector widget."""
    w = FileSelector(settings_manager=mock_settings)
    qtbot.addWidget(w)
    return w


@pytest.fixture
def widget_save_mode(qtbot: QtBot, mock_settings: Mock) -> FileSelector:
    """Create FileSelector in save mode."""
    w = FileSelector(mode="save", settings_manager=mock_settings)
    qtbot.addWidget(w)
    return w


@pytest.fixture
def existing_file(tmp_path: Path) -> Path:
    """Create a temporary existing file."""
    file = tmp_path / "test_file.txt"
    file.write_text("test content")
    return file


class TestFileSelectorSignals:
    """Tests for signal emission."""

    def test_path_changed_emits_on_text_change(self, qtbot: QtBot, widget: FileSelector) -> None:
        """path_changed emits when text changes."""
        received_paths: list[str] = []

        def capture(path: str) -> None:
            received_paths.append(path)

        _ = widget.path_changed.connect(capture)

        widget.set_path("/new/path.rom")

        assert len(received_paths) == 1
        assert received_paths[0] == "/new/path.rom"

    def test_file_selected_emits_on_browse(self, qtbot: QtBot, widget: FileSelector) -> None:
        """file_selected emits when file is selected via browse."""
        received_files: list[str] = []

        def capture(path: str) -> None:
            received_files.append(path)

        _ = widget.file_selected.connect(capture)

        # Mock the file dialog helper to return a file
        with patch("ui.components.inputs.file_selector.FileDialogHelper") as mock_helper:
            mock_helper.browse_open_file.return_value = "/selected/file.rom"

            qtbot.mouseClick(widget.browse_button, Qt.MouseButton.LeftButton)

        assert len(received_files) == 1
        assert received_files[0] == "/selected/file.rom"


class TestFileSelectorValidation:
    """Tests for path validation."""

    def test_is_valid_empty_path(self, widget: FileSelector) -> None:
        """Empty path is considered valid (optional field)."""
        widget.set_path("")
        assert widget.is_valid() is True

    def test_is_valid_existing_file_open_mode(self, widget: FileSelector, existing_file: Path) -> None:
        """Existing file is valid in open mode."""
        widget.set_path(str(existing_file))
        assert widget.is_valid() is True

    def test_is_valid_nonexistent_file_open_mode(self, widget: FileSelector, tmp_path: Path) -> None:
        """Non-existent file is invalid in open mode."""
        widget.set_path(str(tmp_path / "nonexistent.rom"))
        assert widget.is_valid() is False

    def test_is_valid_directory_open_mode(self, widget: FileSelector, tmp_path: Path) -> None:
        """Directory is invalid in open mode (expects file)."""
        widget.set_path(str(tmp_path))
        assert widget.is_valid() is False

    def test_is_valid_existing_parent_save_mode(self, widget_save_mode: FileSelector, tmp_path: Path) -> None:
        """File with existing parent directory is valid in save mode."""
        widget_save_mode.set_path(str(tmp_path / "newfile.rom"))
        assert widget_save_mode.is_valid() is True

    def test_is_valid_nonexistent_parent_save_mode(self, widget_save_mode: FileSelector, tmp_path: Path) -> None:
        """File with non-existent parent directory is invalid in save mode."""
        widget_save_mode.set_path(str(tmp_path / "nonexistent_dir" / "newfile.rom"))
        assert widget_save_mode.is_valid() is False


class TestFileSelectorBrowse:
    """Tests for browse functionality."""

    def test_browse_open_mode_calls_helper(self, qtbot: QtBot, widget: FileSelector) -> None:
        """Browse in open mode calls browse_open_file."""
        with patch("ui.components.inputs.file_selector.FileDialogHelper") as mock_helper:
            mock_helper.browse_open_file.return_value = None

            qtbot.mouseClick(widget.browse_button, Qt.MouseButton.LeftButton)

            mock_helper.browse_open_file.assert_called_once()

    def test_browse_save_mode_calls_helper(self, qtbot: QtBot, widget_save_mode: FileSelector) -> None:
        """Browse in save mode calls browse_save_file."""
        with patch("ui.components.inputs.file_selector.FileDialogHelper") as mock_helper:
            mock_helper.browse_save_file.return_value = None

            qtbot.mouseClick(widget_save_mode.browse_button, Qt.MouseButton.LeftButton)

            mock_helper.browse_save_file.assert_called_once()

    def test_browse_updates_path(self, qtbot: QtBot, widget: FileSelector) -> None:
        """Browse updates path on selection."""
        with patch("ui.components.inputs.file_selector.FileDialogHelper") as mock_helper:
            mock_helper.browse_open_file.return_value = "/selected/file.rom"

            qtbot.mouseClick(widget.browse_button, Qt.MouseButton.LeftButton)

            assert widget.get_path() == "/selected/file.rom"

    def test_browse_no_selection_keeps_path(self, qtbot: QtBot, widget: FileSelector) -> None:
        """Browse with no selection keeps current path."""
        widget.set_path("/original/path.rom")

        with patch("ui.components.inputs.file_selector.FileDialogHelper") as mock_helper:
            mock_helper.browse_open_file.return_value = None  # No selection

            qtbot.mouseClick(widget.browse_button, Qt.MouseButton.LeftButton)

            assert widget.get_path() == "/original/path.rom"

    def test_browse_calls_selection_callback(self, qtbot: QtBot, mock_settings: Mock) -> None:
        """Browse calls selection callback on file selection."""
        callback = Mock()
        w = FileSelector(selection_callback=callback, settings_manager=mock_settings)
        qtbot.addWidget(w)

        with patch("ui.components.inputs.file_selector.FileDialogHelper") as mock_helper:
            mock_helper.browse_open_file.return_value = "/selected/file.rom"

            qtbot.mouseClick(w.browse_button, Qt.MouseButton.LeftButton)

            callback.assert_called_once_with("/selected/file.rom")

    def test_browse_callback_exception_handled(self, qtbot: QtBot, mock_settings: Mock) -> None:
        """Browse handles callback exceptions gracefully."""
        callback = Mock(side_effect=RuntimeError("callback error"))
        w = FileSelector(selection_callback=callback, settings_manager=mock_settings)
        qtbot.addWidget(w)

        with patch("ui.components.inputs.file_selector.FileDialogHelper") as mock_helper:
            mock_helper.browse_open_file.return_value = "/selected/file.rom"

            # Should not raise
            qtbot.mouseClick(w.browse_button, Qt.MouseButton.LeftButton)

            callback.assert_called_once()
