"""Tests for UI reflection bugs from docs/assessments/UI_BUG_SPECIFICATIONS.md.

Each test reproduces a bug that was discovered in production.
Tests are written to fail before the bug is fixed.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, Mock, patch

import numpy as np
import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QPixmap

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from tests.fixtures.timeouts import signal_timeout


class TestBug4ModifiedIndicatorOrdering:
    """Bug 4: Modified indicator shows stale state.

    Root cause: self.state = "edit" is set AFTER load_image() emits undoStateChanged,
    so the signal handler sees the old state ("preview") instead of "edit".

    Expected: No "[Modified]" in source bar after open_in_editor() with clean undo stack.
    """

    def test_state_is_edit_before_undoStateChanged_signal(self, qtbot: object, mocker: MockerFixture) -> None:
        """State must be 'edit' BEFORE load_image triggers undoStateChanged signal.

        This test verifies the fix by capturing the controller state at the
        moment undoStateChanged is emitted during open_in_editor().
        """
        from ui.sprite_editor.controllers.editing_controller import EditingController
        from ui.sprite_editor.controllers.rom_workflow_controller import (
            ROMWorkflowController,
        )

        # Create mock editing controller
        mock_editing_controller = MagicMock(spec=EditingController)
        mock_editing_controller.validationChanged = MagicMock()
        mock_editing_controller.paletteSourceSelected = MagicMock()
        mock_editing_controller.paletteChanged = MagicMock()
        mock_editing_controller.undoStateChanged = MagicMock()

        # Create controller with mocked dependencies
        controller = ROMWorkflowController(
            parent=None,
            editing_controller=mock_editing_controller,
        )
        controller._view = MagicMock()
        controller._view.clear_rom_palette_sources = MagicMock()
        controller._view.hide_palette_warning = MagicMock()
        controller._view.show_palette_warning = MagicMock()
        controller._view.set_action_text = MagicMock()
        controller._view.set_workflow_state = MagicMock()
        controller._view.workspace = None
        controller._message_service = None
        controller._sprite_library = None

        # Set up minimal state for open_in_editor to proceed
        controller.current_offset = 0x1000
        controller.current_tile_offset = 0x1000
        controller.current_tile_data = bytes(32 * 4)  # 4 tiles minimum
        controller.current_width = 0
        controller.current_height = 0
        controller.current_compression_type = None
        controller._current_arrangement = None
        controller._current_rom_map_data = None
        controller.current_sprite_name = "test_sprite"

        # Track what state was observed when load_image was called
        observed_state_at_load: list[str] = []

        def capture_state_on_load(*args: object, **kwargs: object) -> None:
            observed_state_at_load.append(controller.state)

        mock_editing_controller.load_image.side_effect = capture_state_on_load
        mock_editing_controller.ensure_last_palette_loaded.return_value = None
        mock_editing_controller.clear_palette_sources.return_value = None

        # Execute
        controller.open_in_editor()

        # Verify: state should be "edit" when load_image is called
        assert len(observed_state_at_load) == 1, "load_image should be called once"
        assert observed_state_at_load[0] == "edit", (
            f"State was '{observed_state_at_load[0]}' when load_image was called, "
            "but should be 'edit' so undoStateChanged handler sees correct state"
        )


class TestBug2DeleteWrongItemOnCollision:
    """Bug 2: Deleting library sprite at offset X also removes ROM sprite at offset X.

    Root cause: remove_sprite_by_offset() ignores source_type parameter,
    removing the first matching offset regardless of source.

    Expected: Only the item matching both offset AND source_type is removed.
    """

    def test_remove_sprite_by_offset_respects_source_type(self, qtbot: object) -> None:
        """remove_sprite_by_offset should only remove items matching both offset and source_type."""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication

        from ui.sprite_editor.views.widgets.sprite_asset_browser import (
            SpriteAssetBrowser,
        )

        # Ensure QApplication exists
        app = QApplication.instance()
        if app is None:
            pytest.skip("QApplication required")

        browser = SpriteAssetBrowser()
        browser.show()
        qtbot.addWidget(browser)  # type: ignore[attr-defined]

        # Add a ROM sprite at offset 0x1000
        browser.add_rom_sprite("ROM Sprite", 0x1000)

        # Add a Library sprite at the SAME offset 0x1000 (collision)
        browser.add_library_sprite("Library Sprite", 0x1000)

        # Verify both exist
        offsets_before = browser.get_all_offsets()
        assert 0x1000 in offsets_before

        # Count items with offset 0x1000
        def count_items_at_offset(offset: int) -> dict[str, int]:
            from PySide6.QtWidgets import QTreeWidgetItemIterator

            counts: dict[str, int] = {"rom": 0, "library": 0}
            iterator = QTreeWidgetItemIterator(browser.tree)
            while iterator.value():
                item = iterator.value()
                data = item.data(0, Qt.ItemDataRole.UserRole)
                if isinstance(data, dict) and data.get("offset") == offset:
                    source_type = data.get("source_type", "unknown")
                    if source_type in counts:
                        counts[source_type] += 1
                iterator += 1
            return counts

        counts_before = count_items_at_offset(0x1000)
        assert counts_before["rom"] == 1, "Should have 1 ROM sprite at 0x1000"
        assert counts_before["library"] == 1, "Should have 1 Library sprite at 0x1000"

        # Delete ONLY the library sprite at 0x1000
        result = browser.remove_sprite_by_offset(0x1000, source_type="library")
        assert result is True, "Should return True when item was removed"

        # Verify: ROM sprite should still exist, library sprite should be gone
        counts_after = count_items_at_offset(0x1000)
        assert counts_after["rom"] == 1, "ROM sprite at 0x1000 should NOT be deleted when deleting library sprite"
        assert counts_after["library"] == 0, "Library sprite at 0x1000 should be deleted"


class TestBug5DragDropPrerequisiteSync:
    """Bug 5: Drag-drop files into ExtractTab doesn't enable Generate button.

    Root cause: Drop zone updates the view UI (shows file path) but doesn't
    update the controller's vram_file/cgram_file properties. The
    _validate_prerequisites() method checks controller state, not view state.

    Expected: After drag-drop, generate_multi_btn.isEnabled() == True.
    """

    def test_drag_drop_updates_controller_state(self, qtbot: object, tmp_path: Path) -> None:
        """Drag-dropping a file should update both view AND controller state."""
        from PySide6.QtWidgets import QApplication

        from ui.sprite_editor.controllers.extraction_controller import (
            ExtractionController,
        )
        from ui.sprite_editor.views.tabs.extract_tab import ExtractTab
        from ui.sprite_editor.views.tabs.multi_palette_tab import MultiPaletteTab

        # Ensure QApplication exists
        app = QApplication.instance()
        if app is None:
            pytest.skip("QApplication required")

        # Create real components
        extract_tab = ExtractTab()
        multi_palette_tab = MultiPaletteTab()
        controller = ExtractionController()

        qtbot.addWidget(extract_tab)  # type: ignore[attr-defined]
        qtbot.addWidget(multi_palette_tab)  # type: ignore[attr-defined]

        # Wire up: controller <-> views
        controller.set_view(extract_tab)
        controller.set_multi_palette_view(multi_palette_tab)

        # Create test files
        vram_file = tmp_path / "test.vram"
        cgram_file = tmp_path / "test.cgram"
        vram_file.write_bytes(b"\x00" * 0x4000)
        cgram_file.write_bytes(b"\x00" * 0x200)

        # Simulate drag-drop by emitting file_dropped signal
        extract_tab.vram_drop.file_dropped.emit(str(vram_file))
        extract_tab.cgram_drop.file_dropped.emit(str(cgram_file))

        # Verify: controller state should be updated
        assert controller.vram_file == str(vram_file), (
            f"Controller vram_file should be '{vram_file}' after drag-drop, but was '{controller.vram_file}'"
        )
        assert controller.cgram_file == str(cgram_file), (
            f"Controller cgram_file should be '{cgram_file}' after drag-drop, but was '{controller.cgram_file}'"
        )

        # Verify: Generate button should be enabled
        multi_palette_tab._validate_prerequisites()
        assert multi_palette_tab.generate_multi_btn.isEnabled(), (
            "Generate button should be enabled after drag-dropping both VRAM and CGRAM files"
        )


class TestBug1LibraryThumbnailsWipedOnRefresh:
    """Bug 1: Library thumbnails disappear after clicking Refresh.

    Root cause: _on_asset_browser_refresh() clears all thumbnails and
    only re-requests ROM/Mesen thumbnails via _request_all_asset_thumbnails().
    Library thumbnails come from saved files, not the thumbnail worker.

    Expected: Library sprite thumbnail present after refresh.
    """

    def test_library_thumbnails_restored_after_refresh(
        self, qtbot: object, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """Library thumbnails should be restored from saved files after refresh."""
        from PySide6.QtWidgets import QApplication

        from ui.sprite_editor.controllers.editing_controller import EditingController
        from ui.sprite_editor.controllers.rom_workflow_controller import (
            ROMWorkflowController,
        )
        from ui.sprite_editor.views.widgets.sprite_asset_browser import (
            SpriteAssetBrowser,
        )

        # Ensure QApplication exists
        app = QApplication.instance()
        if app is None:
            pytest.skip("QApplication required")

        # Create mock sprite library with one sprite
        mock_sprite = MagicMock()
        mock_sprite.name = "Test Library Sprite"
        mock_sprite.rom_offset = 0x2000
        mock_sprite.rom_hash = "test_hash_123"

        mock_library = MagicMock()
        mock_library.sprites = [mock_sprite]
        mock_library.compute_rom_hash.return_value = "test_hash_123"

        # Create mock editing controller
        mock_editing_controller = MagicMock(spec=EditingController)
        mock_editing_controller.validationChanged = MagicMock()
        mock_editing_controller.paletteSourceSelected = MagicMock()
        mock_editing_controller.paletteChanged = MagicMock()
        mock_editing_controller.undoStateChanged = MagicMock()

        # Create controller with mocked dependencies
        controller = ROMWorkflowController(
            parent=None,
            editing_controller=mock_editing_controller,
            sprite_library=mock_library,
        )
        controller.rom_path = str(tmp_path / "test.sfc")

        # Create mock view with real browser
        browser = SpriteAssetBrowser()
        qtbot.addWidget(browser)  # type: ignore[attr-defined]

        mock_view = MagicMock()
        mock_view.asset_browser = browser
        controller._view = mock_view

        # Create a mock thumbnail that library sprites use
        test_thumbnail = QPixmap(32, 32)
        test_thumbnail.fill()  # Fill with default color

        # Mock _load_library_thumbnail to return a valid thumbnail
        mocker.patch.object(controller, "_load_library_thumbnail", return_value=test_thumbnail)

        # Mock thumbnail service's internal controller
        mock_thumb_ctrl = MagicMock()
        mock_thumb_ctrl.worker = MagicMock()
        controller._thumbnail_service._thumbnail_controller = mock_thumb_ctrl

        # Mock rom_cache
        controller.rom_cache = MagicMock()
        controller.rom_cache.clear_preview_cache.return_value = 0

        # Add library sprite to browser (simulating initial load)
        browser.add_library_sprite("Test Library Sprite", 0x2000, thumbnail=test_thumbnail)

        # Verify thumbnail exists before refresh
        def has_thumbnail_at_offset(offset: int, source_type: str = "library") -> bool:
            from PySide6.QtCore import Qt
            from PySide6.QtWidgets import QTreeWidgetItemIterator

            iterator = QTreeWidgetItemIterator(browser.tree)
            while iterator.value():
                item = iterator.value()
                data = item.data(0, Qt.ItemDataRole.UserRole)
                if isinstance(data, dict) and data.get("offset") == offset:
                    if data.get("source_type") == source_type:
                        thumbnail = data.get("thumbnail")
                        return thumbnail is not None and not thumbnail.isNull()
                iterator += 1
            return False

        assert has_thumbnail_at_offset(0x2000), "Library sprite should have thumbnail before refresh"

        # Simulate what happens after refresh: thumbnail worker clears the thumbnail
        # (because it re-generates from ROM data, not library saved files)
        # This mimics the actual bug where library thumbnails get wiped
        browser.set_thumbnail(0x2000, QPixmap(), source_type="library")

        # Verify thumbnail is now gone (simulating the bug)
        assert not has_thumbnail_at_offset(0x2000), "Thumbnail should be cleared after worker processes"

        # Execute refresh - should restore library thumbnails
        controller._on_asset_browser_refresh()

        # Verify: Library thumbnail should be restored after refresh
        # (The fix would call _restore_library_thumbnails after _request_all_asset_thumbnails)
        assert has_thumbnail_at_offset(0x2000), "Library sprite thumbnail should be restored after refresh"


class TestBug3OffsetAlignmentPersistence:
    """Bug 3: ROM offset alignment changes aren't persisted to library.

    Root cause: update_sprite_offset() in browser updates the tree item's
    UserRole data, but doesn't persist the change to the sprite library.

    Expected: After alignment, library sprite's rom_offset is updated on disk.
    """

    def test_offset_alignment_persists_to_library(self, qtbot: object, tmp_path: Path, mocker: MockerFixture) -> None:
        """Offset alignment in browser should persist to sprite library."""
        from core.services.library_service import LibraryService
        from core.sprite_library import LibrarySprite, SpriteLibrary

        # Create a real sprite library
        library_path = tmp_path / "sprites"
        library_path.mkdir()
        library = SpriteLibrary(library_path)

        # Mock ROM path
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(b"\x00" * 100)

        # Add a test sprite to the library using the proper method
        test_sprite = library.add_sprite(
            rom_offset=0x1000,  # Original offset
            rom_path=rom_path,
            name="Test Sprite",
        )
        assert test_sprite is not None, "Failed to add test sprite to library"

        # Create library service
        service = LibraryService()
        service.set_sprite_library(library)

        # Update offset (simulating alignment correction)
        old_offset = 0x1000
        new_offset = 0x1008  # Aligned offset

        result = service.update_sprite_offset(old_offset, new_offset, rom_path)

        # Verify: method should return True and sprite should be updated
        assert result is True, "update_sprite_offset should return True on success"
        assert test_sprite.rom_offset == new_offset, (
            f"Sprite rom_offset should be {new_offset:#x}, but was {test_sprite.rom_offset:#x}"
        )

        # Verify: change should be persisted (reload library)
        library2 = SpriteLibrary(library_path)
        library2.load()
        assert len(library2.sprites) == 1
        assert library2.sprites[0].rom_offset == new_offset, "Offset change should be persisted to disk"
