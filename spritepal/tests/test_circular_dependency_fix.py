"""Test that the circular dependency between MainWindow and ExtractionController is fixed."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication

from core.controller import ExtractionController
from core.di_container import inject
from core.protocols.manager_protocols import (
    ROMCacheProtocol,
    SessionManagerProtocol,
    SettingsManagerProtocol,
)
from ui.main_window import MainWindow


@pytest.mark.gui
@pytest.mark.skip_thread_cleanup(reason="MainWindow spawns background threads during initialization")
class TestCircularDependencyFix:
    """Test suite for circular dependency fix."""

    @pytest.fixture
    def app(self):
        """Create QApplication for tests."""
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield app
        app.quit()

    @pytest.fixture
    def main_window_deps(self, setup_managers):
        """Get MainWindow dependencies from DI container."""
        return {
            "settings_manager": inject(SettingsManagerProtocol),
            "rom_cache": inject(ROMCacheProtocol),
            "session_manager": inject(SessionManagerProtocol),
        }

    def test_main_window_creates_without_controller(self, qtbot, app, main_window_deps):
        """Test that MainWindow can be created without initializing the controller.

        This tests the lazy initialization - controller should not be created
        during MainWindow.__init__, breaking the circular dependency.
        """
        # Create MainWindow with DI dependencies - this should NOT create the controller
        window = MainWindow(**main_window_deps)
        qtbot.addWidget(window)  # Ensure proper cleanup

        # Verify controller is not created yet (lazy initialization)
        assert window._controller is None, "Controller should not be created during __init__"


    def test_controller_setter_works(self, qtbot, app, main_window_deps):
        """Test that controller setter works for testing purposes."""
        window = MainWindow(**main_window_deps)
        qtbot.addWidget(window)  # Ensure proper cleanup

        # Create a mock controller
        mock_controller = MagicMock(spec=ExtractionController)

        # Set the controller
        window.controller = mock_controller

        # Verify it was set
        assert window.controller is mock_controller, "Controller setter should work"
        assert window._controller is mock_controller, "Internal reference should be updated"


    def test_no_circular_import_at_module_level(self):
        """Test that there's no circular import at module level.

        This test verifies that we can import both modules without issues.
        """
        # These imports should work without circular dependency
        from core.controller import ExtractionController
        from ui.main_window import MainWindow

        # Verify classes are importable
        assert MainWindow is not None
        assert ExtractionController is not None

    @pytest.mark.timeout(5)  # Should complete quickly, not hang
    def test_main_window_creation_doesnt_hang(self, qtbot, app, main_window_deps):
        """Test that MainWindow creation doesn't hang due to circular dependency.

        This test has a timeout to ensure it doesn't hang forever.
        """
        # This should complete quickly, not hang
        window = MainWindow(**main_window_deps)
        qtbot.addWidget(window)  # Ensure proper cleanup

        # If we get here, it didn't hang
        assert window is not None

