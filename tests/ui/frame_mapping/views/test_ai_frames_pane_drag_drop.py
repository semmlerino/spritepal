"""Tests for AIFramesPane drag-and-drop functionality.

Features:
- Drop folders onto the pane to load AI frames
- Drop PNG files to load from their parent folder
- Visual feedback during drag
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent

from ui.frame_mapping.views.ai_frames_pane import AIFramesPane

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class TestDragEnterAcceptance:
    """Tests for drag enter event acceptance logic."""

    def test_accepts_folder_drag(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Drag containing a folder should be accepted."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        folder = tmp_path / "ai_frames"
        folder.mkdir()

        mime_data = QMimeData()
        mime_data.setUrls([QUrl.fromLocalFile(str(folder))])

        event = MagicMock(spec=QDragEnterEvent)
        event.mimeData.return_value = mime_data

        pane.dragEnterEvent(event)

        event.acceptProposedAction.assert_called_once()

    def test_accepts_png_file_drag(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Drag containing a PNG file should be accepted."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        png_file = tmp_path / "frame.png"
        png_file.write_bytes(b"fake png")

        mime_data = QMimeData()
        mime_data.setUrls([QUrl.fromLocalFile(str(png_file))])

        event = MagicMock(spec=QDragEnterEvent)
        event.mimeData.return_value = mime_data

        pane.dragEnterEvent(event)

        event.acceptProposedAction.assert_called_once()

    def test_rejects_non_png_file_drag(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Drag containing non-PNG file should be rejected."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        txt_file = tmp_path / "notes.txt"
        txt_file.write_text("hello")

        mime_data = QMimeData()
        mime_data.setUrls([QUrl.fromLocalFile(str(txt_file))])

        event = MagicMock(spec=QDragEnterEvent)
        event.mimeData.return_value = mime_data

        pane.dragEnterEvent(event)

        event.ignore.assert_called_once()
        event.acceptProposedAction.assert_not_called()

    def test_rejects_empty_mime_data(self, qtbot: QtBot) -> None:
        """Drag with no URLs should be rejected."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        mime_data = QMimeData()  # No URLs

        event = MagicMock(spec=QDragEnterEvent)
        event.mimeData.return_value = mime_data

        pane.dragEnterEvent(event)

        event.ignore.assert_called_once()


class TestDragLeaveEvent:
    """Tests for drag leave event handling."""

    def test_drag_leave_resets_style(self, qtbot: QtBot) -> None:
        """Drag leave should reset visual feedback."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        # Simulate some style being set
        pane._list.setStyleSheet("border: 2px dashed green;")

        event = MagicMock(spec=QDragLeaveEvent)
        pane.dragLeaveEvent(event)

        assert pane._list.styleSheet() == ""
        event.accept.assert_called_once()


class TestDropEvent:
    """Tests for drop event handling."""

    def test_drop_folder_emits_signal(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Dropping a folder should emit folder_dropped signal."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        folder = tmp_path / "ai_frames"
        folder.mkdir()

        mime_data = QMimeData()
        mime_data.setUrls([QUrl.fromLocalFile(str(folder))])

        event = MagicMock(spec=QDropEvent)
        event.mimeData.return_value = mime_data

        dropped_paths: list[Path] = []
        pane.folder_dropped.connect(lambda p: dropped_paths.append(p))

        pane.dropEvent(event)

        assert len(dropped_paths) == 1
        assert dropped_paths[0] == folder
        event.acceptProposedAction.assert_called_once()

    def test_drop_png_emits_parent_folder(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Dropping a PNG should emit parent folder path."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        frames_dir = tmp_path / "frames"
        frames_dir.mkdir()
        png_file = frames_dir / "frame001.png"
        png_file.write_bytes(b"fake png")

        mime_data = QMimeData()
        mime_data.setUrls([QUrl.fromLocalFile(str(png_file))])

        event = MagicMock(spec=QDropEvent)
        event.mimeData.return_value = mime_data

        dropped_paths: list[Path] = []
        pane.folder_dropped.connect(lambda p: dropped_paths.append(p))

        pane.dropEvent(event)

        assert len(dropped_paths) == 1
        assert dropped_paths[0] == frames_dir  # Parent of PNG
        event.acceptProposedAction.assert_called_once()

    def test_drop_resets_visual_feedback(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Drop event should reset visual feedback regardless of content."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        # Set some visual feedback style
        pane._list.setStyleSheet("border: 2px dashed green;")

        folder = tmp_path / "ai_frames"
        folder.mkdir()

        mime_data = QMimeData()
        mime_data.setUrls([QUrl.fromLocalFile(str(folder))])

        event = MagicMock(spec=QDropEvent)
        event.mimeData.return_value = mime_data

        pane.dropEvent(event)

        assert pane._list.styleSheet() == ""

    def test_drop_invalid_content_ignored(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Dropping invalid content should be ignored."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        txt_file = tmp_path / "notes.txt"
        txt_file.write_text("hello")

        mime_data = QMimeData()
        mime_data.setUrls([QUrl.fromLocalFile(str(txt_file))])

        event = MagicMock(spec=QDropEvent)
        event.mimeData.return_value = mime_data

        dropped_paths: list[Path] = []
        pane.folder_dropped.connect(lambda p: dropped_paths.append(p))

        pane.dropEvent(event)

        assert len(dropped_paths) == 0
        event.ignore.assert_called_once()
