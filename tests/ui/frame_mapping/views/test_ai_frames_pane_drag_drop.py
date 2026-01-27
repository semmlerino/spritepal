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

import pytest
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

    def test_drop_png_emits_file_dropped(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Dropping a PNG should emit file_dropped with the file path."""
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

        dropped_files: list[Path] = []
        pane.file_dropped.connect(lambda p: dropped_files.append(p))

        pane.dropEvent(event)

        assert len(dropped_files) == 1
        assert dropped_files[0] == png_file  # The actual file, not parent
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


class TestSetAIFramesResponsiveness:
    """Tests that setting AI frames doesn't freeze the UI.

    Regression test for bug: Dragging images from Windows Explorer
    into the AI frames column causes the app to freeze because
    thumbnail creation happens synchronously on the main thread
    during _refresh_list().
    """

    @pytest.mark.skip(reason="AsyncThumbnailLoader has Qt threading cleanup issues in tests - to be fixed separately")
    @pytest.mark.allows_registry_state(reason="Skipped test triggers teardown check")
    def test_set_ai_frames_with_many_images_remains_responsive(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Setting many AI frames should not block main thread excessively.

        Creates 20 valid PNG files and verifies that set_ai_frames()
        completes within a reasonable time bound. The current
        synchronous implementation blocks because create_quantized_thumbnail()
        is called for each frame in _refresh_list().

        This test documents the expected responsiveness threshold.
        With async thumbnail loading, the method should return quickly
        while thumbnails load in background.
        """
        import time

        from PIL import Image

        from core.frame_mapping_project import AIFrame
        from tests.fixtures.timeouts import perf_bound

        pane = AIFramesPane()
        qtbot.addWidget(pane)

        # Create folder with valid PNG files
        frames_dir = tmp_path / "frames"
        frames_dir.mkdir()

        # Create 20 simple but valid PNG images (64x64 each)
        ai_frames: list[AIFrame] = []
        for i in range(20):
            img_path = frames_dir / f"frame_{i:03d}.png"
            img = Image.new("RGBA", (64, 64), color=(i * 10, 100, 150, 255))
            img.save(img_path)
            ai_frames.append(AIFrame(path=img_path, index=i, width=64, height=64))

        # Measure how long set_ai_frames takes
        # With async thumbnails, this should return quickly
        start = time.perf_counter()
        pane.set_ai_frames(ai_frames)
        elapsed = time.perf_counter() - start

        # With 20 frames, synchronous thumbnail creation takes 500ms-2s
        # depending on system. With async loading, should be < 100ms.
        # Use 200ms as threshold - synchronous will fail, async will pass.
        max_allowed = perf_bound(0.2)
        assert elapsed < max_allowed, (
            f"set_ai_frames took {elapsed:.3f}s for 20 frames - UI freezes. "
            f"Threshold: {max_allowed:.3f}s. "
            "Thumbnail creation should happen asynchronously."
        )
