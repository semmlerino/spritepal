from datetime import datetime
from unittest.mock import ANY, MagicMock, patch

import pytest
from PySide6.QtCore import QObject

from core.mesen_integration.log_watcher import CapturedOffset
from ui.sprite_editor.controllers.rom_workflow_controller import ROMWorkflowController


class TestSyncCapturesRepro:
    @pytest.fixture
    def mock_view(self):
        view = MagicMock()
        view.asset_browser = MagicMock()
        return view

    @pytest.fixture
    def mock_log_watcher(self):
        watcher = MagicMock()
        watcher.recent_captures = []
        watcher.load_persistent_clicks.return_value = []
        return watcher

    @pytest.fixture
    def controller(self, mock_view, mock_log_watcher):
        # Mock EditingController as it is a required dependency
        mock_editing_ctrl = MagicMock()

        # Mock dependencies
        mock_rom_cache = MagicMock()
        mock_rom_extractor = MagicMock()
        mock_sprite_library = MagicMock()

        ctrl = ROMWorkflowController(
            parent=None,
            editing_controller=mock_editing_ctrl,
            rom_cache=mock_rom_cache,
            rom_extractor=mock_rom_extractor,
            log_watcher=mock_log_watcher,
            sprite_library=mock_sprite_library,
        )
        return ctrl

    @patch("core.rom_validator.ROMValidator.validate_rom_file")
    @patch("core.rom_validator.ROMValidator.validate_rom_header")
    @patch("core.rom_validator.ROMValidator.verify_rom_checksum")
    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.stat")
    def test_mesen_captures_lost_on_rom_load(
        self,
        mock_stat,
        mock_exists,
        mock_verify_checksum,
        mock_validate_header,
        mock_validate_file,
        controller,
        mock_view,
        mock_log_watcher,
    ):
        """
        Reproduction test for UI-logic desync:
        Mesen captures are cleared from the Asset Browser when loading a new ROM
        and are not re-populated, even though they persist in LogWatcher.
        """
        # Setup mocks for ROM loading
        mock_exists.return_value = True
        mock_stat.return_value.st_size = 1024 * 1024
        mock_validate_file.return_value = (True, "")
        mock_verify_checksum.return_value = True
        mock_header = MagicMock()
        mock_header.title = "Test ROM"
        mock_header.mapping_type = "LoROM"
        mock_header.header_offset = 0
        mock_header.checksum = 0x1234
        mock_validate_header.return_value = (mock_header, None)

        # 1. Setup initial state: 1 capture in LogWatcher
        capture = CapturedOffset(
            offset=0x123456, frame=123, timestamp=datetime.now(), raw_line="FILE OFFSET: 0x123456 frame=123"
        )
        mock_log_watcher.recent_captures = [capture]

        # 2. Connect view -> should populate browser
        controller.set_view(mock_view)

        # Verify initial population
        mock_view.add_mesen_capture.assert_called_with(ANY, 0x123456)
        mock_view.add_mesen_capture.reset_mock()

        # 3. Load a new ROM
        # This triggers clear_asset_browser()
        controller.load_rom("test.sfc")

        # Verify clear was called
        mock_view.clear_asset_browser.assert_called()

        # 4. Verify re-population (THIS SHOULD FAIL CURRENTLY)
        # The controller should re-add the existing Mesen captures after clearing
        mock_view.add_mesen_capture.assert_called_with(ANY, 0x123456)


class TestThumbnailRequeueOnAlignment:
    """Tests for thumbnail re-queuing when offset alignment occurs.

    The refactored approach uses signals:
    1. _on_preview_ready() calls update_sprite_offset()
    2. update_sprite_offset() emits item_offset_changed signal
    3. _on_item_offset_changed() handler queues thumbnail

    These tests verify each part of the chain.
    """

    @pytest.fixture
    def mock_view(self):
        view = MagicMock()
        view.asset_browser = MagicMock()
        view.asset_browser.update_sprite_offset.return_value = True
        return view

    @pytest.fixture
    def mock_thumbnail_controller(self):
        return MagicMock()

    @pytest.fixture
    def controller(self, mock_view, mock_thumbnail_controller):
        from ui.sprite_editor.controllers.rom_workflow_controller import ROMWorkflowController

        mock_editing_ctrl = MagicMock()
        mock_rom_cache = MagicMock()
        mock_rom_extractor = MagicMock()
        mock_log_watcher = MagicMock()
        mock_log_watcher.recent_captures = []
        mock_log_watcher.load_persistent_clicks.return_value = []
        mock_sprite_library = MagicMock()

        ctrl = ROMWorkflowController(
            parent=None,
            editing_controller=mock_editing_ctrl,
            rom_cache=mock_rom_cache,
            rom_extractor=mock_rom_extractor,
            log_watcher=mock_log_watcher,
            sprite_library=mock_sprite_library,
        )
        ctrl.set_view(mock_view)
        ctrl._thumbnail_controller = mock_thumbnail_controller
        ctrl.current_offset = 0x1000
        return ctrl

    def test_preview_calls_update_sprite_offset_on_alignment(
        self,
        controller,
        mock_view,
    ):
        """Verify _on_preview_ready calls update_sprite_offset when offset is adjusted."""
        tile_data = b"\x00" * 32
        actual_offset = 0x1004  # Adjusted from 0x1000

        controller._on_preview_ready(
            tile_data=tile_data,
            width=8,
            height=8,
            sprite_name="Test Sprite",
            compressed_size=32,
            slack_size=0,
            actual_offset=actual_offset,
            hal_succeeded=True,
        )

        # The key behavior: update_sprite_offset is called with old and new offsets
        mock_view.asset_browser.update_sprite_offset.assert_called_with(0x1000, 0x1004)

    def test_no_update_when_offset_unchanged(
        self,
        controller,
        mock_view,
    ):
        """Verify update_sprite_offset is NOT called when offset matches."""
        tile_data = b"\x00" * 32
        actual_offset = 0x1000  # Same as current_offset

        controller._on_preview_ready(
            tile_data=tile_data,
            width=8,
            height=8,
            sprite_name="Test Sprite",
            compressed_size=32,
            slack_size=0,
            actual_offset=actual_offset,
            hal_succeeded=True,
        )

        mock_view.asset_browser.update_sprite_offset.assert_not_called()

    def test_offset_changed_handler_queues_thumbnail(
        self,
        controller,
        mock_thumbnail_controller,
    ):
        """Verify _on_item_offset_changed handler queues thumbnail for new offset.

        This tests the signal handler directly (the signal wiring is tested separately).
        """
        controller._on_item_offset_changed(0x1000, 0x1004)

        mock_thumbnail_controller.queue_thumbnail.assert_called_with(0x1004)

    def test_offset_changed_handler_no_op_without_thumbnail_controller(
        self,
        controller,
    ):
        """Verify handler is safe when thumbnail controller is None."""
        controller._thumbnail_controller = None

        # Should not raise
        controller._on_item_offset_changed(0x1000, 0x1004)
