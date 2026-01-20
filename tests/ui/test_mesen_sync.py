from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from core.mesen_integration.log_watcher import CapturedOffset
from ui.main_window import MainWindow, WorkspaceMode


def test_mesen_captures_synced_on_workspace_switch(qtbot, app_context):
    """
    Test that Mesen captures are synchronized from LogWatcher
    to the Asset Browser when switching to the Sprite Editor workspace.
    """
    # 1. Setup: Create real MainWindow with mocked dependencies
    # Note: app_context is required because MainWindow._setup_managers() calls get_app_context()
    mock_settings = MagicMock()
    mock_rom_cache = MagicMock()
    mock_session = MagicMock()
    mock_core_ops = MagicMock()
    mock_log_watcher = MagicMock()
    mock_preview = MagicMock()
    mock_rom_ext = MagicMock()
    mock_library = MagicMock()

    # Configure log_watcher to have a capture
    capture = CapturedOffset(
        offset=0x1234, frame=100, timestamp=datetime.now(tz=UTC), raw_line="FILE OFFSET: 0x001234 frame=100"
    )
    mock_log_watcher.recent_captures = [capture]
    mock_log_watcher.load_persistent_clicks.return_value = []

    window = MainWindow(
        settings_manager=mock_settings,
        rom_cache=mock_rom_cache,
        session_manager=mock_session,
        core_operations_manager=mock_core_ops,
        log_watcher=mock_log_watcher,
        preview_generator=mock_preview,
        rom_extractor=mock_rom_ext,
        sprite_library=mock_library,
    )
    qtbot.addWidget(window)

    # 2. Action: Switch to Sprite Editor workspace (Mode 1)
    window.switch_to_workspace(WorkspaceMode.SPRITE_EDITOR)

    # 3. Verify: Asset browser should have been synced
    browser = window._sprite_editor_workspace.rom_page.asset_browser
    assert browser.has_mesen_capture(0x1234)
