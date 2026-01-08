"""Test that MainWindow can be created without hanging due to circular dependencies.

Note: ExtractionController was removed in Phase 4e refactoring. The original circular
dependency issue no longer exists since MainWindow now handles extraction directly.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from core.app_context import get_app_context
from ui.main_window import MainWindow


@pytest.mark.gui
@pytest.mark.skip_thread_cleanup(reason="MainWindow spawns background threads during initialization")
class TestMainWindowInitialization:
    """Test suite for MainWindow initialization (formerly circular dependency tests)."""

    @pytest.fixture
    def app(self):
        """Create QApplication for tests."""
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield app
        app.quit()

    @pytest.fixture
    def main_window_deps(self, isolated_managers):
        """Get MainWindow dependencies from app context."""
        context = get_app_context()
        return {
            "settings_manager": context.application_state_manager,
            "rom_cache": context.rom_cache,
            "session_manager": context.application_state_manager,
            "core_operations_manager": context.core_operations_manager,
            "log_watcher": context.log_watcher,
            "preview_generator": context.preview_generator,
            "rom_extractor": context.rom_extractor,
            "sprite_library": context.sprite_library,
        }

    @pytest.mark.timeout(5)  # Should complete quickly, not hang
    def test_main_window_creation_doesnt_hang(self, qtbot, app, main_window_deps):
        """Test that MainWindow creation doesn't hang.

        This test has a timeout to ensure it doesn't hang forever.
        MainWindow now handles extraction directly without ExtractionController.
        """
        # This should complete quickly, not hang
        window = MainWindow(**main_window_deps)
        qtbot.addWidget(window)  # Ensure proper cleanup

        # If we get here, it didn't hang
        assert window is not None

    def test_main_window_has_extraction_methods(self, qtbot, app, main_window_deps):
        """Test that MainWindow has the direct extraction methods.

        After Phase 4 refactoring, extraction is handled directly by MainWindow.
        """
        window = MainWindow(**main_window_deps)
        qtbot.addWidget(window)

        # Verify extraction methods exist (moved from ExtractionController)
        assert hasattr(window, "_start_vram_extraction")
        assert hasattr(window, "_start_rom_extraction")
        assert hasattr(window, "_start_injection")

    def test_main_window_has_dialog_coordinator(self, qtbot, app, main_window_deps):
        """Test that MainWindow has DialogCoordinator for dialog operations."""
        window = MainWindow(**main_window_deps)
        qtbot.addWidget(window)

        # Verify dialog coordinator is accessible
        coordinator = window.dialog_coordinator
        assert coordinator is not None
        assert hasattr(coordinator, "open_in_editor")
        assert hasattr(coordinator, "open_row_arrangement")
        assert hasattr(coordinator, "open_grid_arrangement")
