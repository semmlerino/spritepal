"""Tests for AIFramesPane tabbed interface functionality.

Features:
- Multiple folders as tabs for comparing sprite sheet versions
- Add/close tabs
- Tab switching emits signal to reload frames
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ui.frame_mapping.views.ai_frames_pane import AIFramesPane

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class TestTabInitialState:
    """Tests for initial tab state."""

    def test_starts_with_single_empty_tab(self, qtbot: QtBot) -> None:
        """Pane should start with a single 'New' tab."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        assert pane._tab_bar.count() == 1
        assert pane._tab_bar.tabText(0) == "New"
        assert pane.get_current_tab_folder() is None

    def test_tab_folders_list_matches_tabs(self, qtbot: QtBot) -> None:
        """_tab_folders list should match tab count."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        assert len(pane._tab_folders) == 1
        assert pane._tab_folders[0] is None


class TestAddFolderTab:
    """Tests for add_folder_tab method."""

    def test_add_folder_tab_creates_new_tab(self, qtbot: QtBot, tmp_path: Path) -> None:
        """add_folder_tab should create a new tab with folder name."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        folder = tmp_path / "v1_sprites"
        folder.mkdir()

        index = pane.add_folder_tab(folder)

        assert index == 1  # Second tab (after initial "New")
        assert pane._tab_bar.count() == 2
        assert pane._tab_bar.tabText(1) == "v1_sprites"
        assert pane._tab_bar.currentIndex() == 1  # Switched to new tab

    def test_add_folder_tab_updates_folders_list(self, qtbot: QtBot, tmp_path: Path) -> None:
        """add_folder_tab should update _tab_folders list."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        folder = tmp_path / "sprites"
        folder.mkdir()

        pane.add_folder_tab(folder)

        assert len(pane._tab_folders) == 2
        assert pane._tab_folders[1] == folder

    def test_add_folder_tab_emits_signal(self, qtbot: QtBot, tmp_path: Path) -> None:
        """add_folder_tab should emit tab_folder_changed signal."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        folder = tmp_path / "sprites"
        folder.mkdir()

        emitted_paths: list[Path | None] = []
        pane.tab_folder_changed.connect(lambda p: emitted_paths.append(p))

        pane.add_folder_tab(folder)

        assert len(emitted_paths) == 1
        assert emitted_paths[0] == folder


class TestCloseTab:
    """Tests for close_tab method."""

    def test_close_tab_removes_tab(self, qtbot: QtBot, tmp_path: Path) -> None:
        """close_tab should remove the specified tab."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        folder = tmp_path / "sprites"
        folder.mkdir()
        pane.add_folder_tab(folder)

        assert pane._tab_bar.count() == 2

        pane.close_tab(1)

        assert pane._tab_bar.count() == 1
        assert len(pane._tab_folders) == 1

    def test_close_last_tab_creates_empty_tab(self, qtbot: QtBot) -> None:
        """Closing the last tab should create a new empty tab."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        pane.close_tab(0)

        assert pane._tab_bar.count() == 1
        assert pane._tab_bar.tabText(0) == "New"
        assert pane._tab_folders == [None]

    def test_close_tab_emits_signal_for_new_current(self, qtbot: QtBot, tmp_path: Path) -> None:
        """close_tab should emit signal for the now-current tab."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        folder1 = tmp_path / "v1"
        folder1.mkdir()
        folder2 = tmp_path / "v2"
        folder2.mkdir()

        pane.set_current_tab_folder(folder1)
        pane.add_folder_tab(folder2)

        emitted_paths: list[Path | None] = []
        pane.tab_folder_changed.connect(lambda p: emitted_paths.append(p))

        # Close the second tab (v2), should switch back to first (v1)
        pane.close_tab(1)

        assert len(emitted_paths) == 1
        assert emitted_paths[0] == folder1

    def test_close_tab_invalid_index_ignored(self, qtbot: QtBot) -> None:
        """close_tab with invalid index should do nothing."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        pane.close_tab(-1)
        pane.close_tab(99)

        assert pane._tab_bar.count() == 1  # Still has initial tab


class TestSetCurrentTabFolder:
    """Tests for set_current_tab_folder method."""

    def test_set_current_tab_folder_updates_tab(self, qtbot: QtBot, tmp_path: Path) -> None:
        """set_current_tab_folder should update tab text and folder."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        folder = tmp_path / "my_sprites"
        folder.mkdir()

        pane.set_current_tab_folder(folder)

        assert pane._tab_bar.tabText(0) == "my_sprites"
        assert pane.get_current_tab_folder() == folder


class TestGetCurrentTabFolder:
    """Tests for get_current_tab_folder method."""

    def test_get_current_tab_folder_returns_none_for_empty(self, qtbot: QtBot) -> None:
        """get_current_tab_folder should return None for empty tab."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        assert pane.get_current_tab_folder() is None

    def test_get_current_tab_folder_returns_folder(self, qtbot: QtBot, tmp_path: Path) -> None:
        """get_current_tab_folder should return the folder for current tab."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        folder = tmp_path / "sprites"
        folder.mkdir()
        pane.set_current_tab_folder(folder)

        assert pane.get_current_tab_folder() == folder


class TestTabSwitching:
    """Tests for tab switching behavior."""

    def test_switch_tab_emits_signal(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Switching tabs should emit tab_folder_changed signal."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        folder1 = tmp_path / "v1"
        folder1.mkdir()
        folder2 = tmp_path / "v2"
        folder2.mkdir()

        pane.set_current_tab_folder(folder1)
        pane.add_folder_tab(folder2)

        emitted_paths: list[Path | None] = []
        pane.tab_folder_changed.connect(lambda p: emitted_paths.append(p))

        # Switch back to first tab
        pane._tab_bar.setCurrentIndex(0)

        assert len(emitted_paths) == 1
        assert emitted_paths[0] == folder1

    def test_switch_to_empty_tab_emits_none(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Switching to empty tab should emit None."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        folder = tmp_path / "sprites"
        folder.mkdir()
        pane.add_folder_tab(folder)

        emitted_paths: list[Path | None] = []
        pane.tab_folder_changed.connect(lambda p: emitted_paths.append(p))

        # Switch back to first (empty) tab
        pane._tab_bar.setCurrentIndex(0)

        assert len(emitted_paths) == 1
        assert emitted_paths[0] is None


class TestAddTabButton:
    """Tests for add tab button."""

    def test_add_tab_button_creates_empty_tab(self, qtbot: QtBot) -> None:
        """Clicking add tab button should create a new empty tab."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        pane._on_add_tab_clicked()

        assert pane._tab_bar.count() == 2
        assert pane._tab_bar.tabText(1) == "New"
        assert pane._tab_bar.currentIndex() == 1
        assert pane._tab_folders[1] is None

    def test_add_tab_button_emits_none(self, qtbot: QtBot) -> None:
        """Clicking add tab button should emit None for new empty tab."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        emitted_paths: list[Path | None] = []
        pane.tab_folder_changed.connect(lambda p: emitted_paths.append(p))

        pane._on_add_tab_clicked()

        assert len(emitted_paths) == 1
        assert emitted_paths[0] is None


class TestClearResetsTabs:
    """Tests for clear() method tab reset behavior."""

    def test_clear_resets_to_single_empty_tab(self, qtbot: QtBot, tmp_path: Path) -> None:
        """clear() should reset tabs to single empty tab."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        folder1 = tmp_path / "v1"
        folder1.mkdir()
        folder2 = tmp_path / "v2"
        folder2.mkdir()

        pane.set_current_tab_folder(folder1)
        pane.add_folder_tab(folder2)

        assert pane._tab_bar.count() == 2

        pane.clear()

        assert pane._tab_bar.count() == 1
        assert pane._tab_bar.tabText(0) == "New"
        assert pane._tab_folders == [None]


class TestTabFolderPreservation:
    """Tests for tab folder preservation when switching tabs.

    Bug: When adding a new tab, the previous tab's folder association was lost,
    causing frames to not reload when switching back.
    """

    def test_switching_back_to_original_tab_emits_folder(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Switching back to original tab should emit its folder path."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        folder1 = tmp_path / "v1_sprites"
        folder1.mkdir()

        # Set folder on first tab
        pane.set_current_tab_folder(folder1)
        assert pane._tab_bar.tabText(0) == "v1_sprites"
        assert pane.get_current_tab_folder() == folder1

        # Add new empty tab
        pane._on_add_tab_clicked()
        assert pane._tab_bar.count() == 2
        assert pane._tab_bar.currentIndex() == 1
        assert pane.get_current_tab_folder() is None

        # Collect signals when switching back
        emitted_paths: list[Path | None] = []
        pane.tab_folder_changed.connect(lambda p: emitted_paths.append(p))

        # Switch back to first tab
        pane._tab_bar.setCurrentIndex(0)

        # Should emit folder1 path for reloading frames
        assert len(emitted_paths) == 1
        assert emitted_paths[0] == folder1

    def test_tab_folder_survives_add_tab(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Adding a new tab should not affect previous tab's folder."""
        pane = AIFramesPane()
        qtbot.addWidget(pane)

        folder = tmp_path / "sprites"
        folder.mkdir()

        # Set folder on first tab
        pane.set_current_tab_folder(folder)

        # Add new tab (switches to it)
        pane._on_add_tab_clicked()

        # First tab should still have its folder
        assert pane._tab_folders[0] == folder
        assert pane._tab_bar.tabText(0) == "sprites"
