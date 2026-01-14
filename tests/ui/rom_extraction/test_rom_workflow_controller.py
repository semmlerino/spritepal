"""
Tests for ROMWorkflowController logic and regression fixes.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import ANY, MagicMock, patch

import pytest

from core.mesen_integration.log_watcher import CapturedOffset
from ui.sprite_editor.controllers.rom_workflow_controller import ROMWorkflowController


class TestROMWorkflowControllerRegression:
    """Regression tests for ROMWorkflowController desync issues."""

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
        # Mock dependencies
        mock_editing_ctrl = MagicMock()
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
        controller.load_rom("test.sfc")

        # Verify re-population
        # The controller should re-add the existing Mesen captures after clearing
        mock_view.add_mesen_capture.assert_called_with(ANY, 0x123456)


class TestThumbnailRequeueOnAlignment:
    """Tests for thumbnail re-queuing when offset alignment occurs."""

    @pytest.fixture
    def mock_view(self):
        view = MagicMock()
        view.asset_browser = MagicMock()
        view.asset_browser.update_sprite_offset.return_value = True
        return view

    @pytest.fixture
    def controller(self, mock_view):
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

        mock_view.asset_browser.update_sprite_offset.assert_called_with(0x1000, 0x1004)

    def test_offset_changed_handler_queues_thumbnail(
        self,
        controller,
    ):
        """Verify _on_item_offset_changed handler queues thumbnail for new offset."""
        mock_thumb_ctrl = MagicMock()
        controller._thumbnail_controller = mock_thumb_ctrl
        
        controller._on_item_offset_changed(0x1000, 0x1004)

        mock_thumb_ctrl.queue_thumbnail.assert_called_with(0x1004)
