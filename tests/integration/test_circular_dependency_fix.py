from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from core.app_context import get_app_context

pytestmark = [pytest.mark.integration]

"""Test that MainWindow can be created without hanging due to circular dependencies.

Note: ExtractionController was removed in Phase 4e refactoring. The original circular
dependency issue no longer exists since MainWindow now handles extraction directly.
"""


def test_mainwindow_initialization(qtbot, isolated_managers, app_context):
    """Verify MainWindow can be initialized without infinite recursion/deadlock."""
    from ui.main_window import MainWindow

    window = MainWindow(
        settings_manager=app_context.application_state_manager,
        rom_cache=app_context.rom_cache,
        session_manager=app_context.application_state_manager,
        core_operations_manager=app_context.core_operations_manager,
        log_watcher=app_context.log_watcher,
        preview_generator=app_context.preview_generator,
        rom_extractor=app_context.rom_extractor,
        sprite_library=app_context.sprite_library,
    )
    qtbot.addWidget(window)
    assert window is not None
