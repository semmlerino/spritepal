
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
            sprite_library=mock_sprite_library
        )
        return ctrl

    @patch("core.rom_validator.ROMValidator.validate_rom_file")
    @patch("core.rom_validator.ROMValidator.validate_rom_header")
    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.stat")
    def test_mesen_captures_lost_on_rom_load(self, mock_stat, mock_exists, mock_validate_header, mock_validate_file, controller, mock_view, mock_log_watcher):
        """
        Reproduction test for UI-logic desync:
        Mesen captures are cleared from the Asset Browser when loading a new ROM
        and are not re-populated, even though they persist in LogWatcher.
        """
        # Setup mocks for ROM loading
        mock_exists.return_value = True
        mock_stat.return_value.st_size = 1024 * 1024
        mock_validate_file.return_value = (True, "")
        mock_header = MagicMock()
        mock_header.title = "Test ROM"
        mock_header.mapping_type = "LoROM"
        mock_header.header_offset = 0  # SMC header offset (0 for headerless ROM)
        mock_validate_header.return_value = (mock_header, None)
        
        # 1. Setup initial state: 1 capture in LogWatcher
        capture = CapturedOffset(
            offset=0x123456,
            frame=123,
            timestamp=datetime.now(),
            raw_line="FILE OFFSET: 0x123456 frame=123"
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
