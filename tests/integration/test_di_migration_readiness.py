"""
AppContext Access Tests.

These tests validate that components can access managers via AppContext.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest

from core.app_context import get_app_context, get_app_context_optional

if TYPE_CHECKING:
    from core.app_context import AppContext

pytestmark = [
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.skip_thread_cleanup(reason="Tests create real managers which may spawn threads"),
]


class TestAppContextAccess:
    """Test that all managers can be accessed via AppContext."""

    def test_app_context_is_initialized(self, app_context: AppContext):
        """Verify AppContext is properly initialized after manager init."""
        ctx = get_app_context_optional()
        assert ctx is not None, "AppContext should be available after manager init"

    def test_access_application_state_manager(self, app_context: AppContext):
        """Test ApplicationStateManager access via AppContext."""
        settings = app_context.application_state_manager
        assert settings is not None
        assert hasattr(settings, "get")
        assert hasattr(settings, "set")
        assert hasattr(settings, "get_session_data")

    def test_access_core_operations_manager(self, app_context: AppContext):
        """Test CoreOperationsManager access via AppContext."""
        ops = app_context.core_operations_manager
        assert ops is not None
        assert hasattr(ops, "validate_extraction_params")
        assert hasattr(ops, "start_injection")

    def test_access_sprite_preset_manager(self, app_context: AppContext):
        """Test SpritePresetManager access via AppContext."""
        presets = app_context.sprite_preset_manager
        assert presets is not None

    def test_access_rom_cache(self, app_context: AppContext):
        """Test ROMCache access via AppContext."""
        cache = app_context.rom_cache
        assert cache is not None
        assert hasattr(cache, "get_cache_stats")

    def test_access_rom_extractor(self, app_context: AppContext):
        """Test ROMExtractor access via AppContext."""
        extractor = app_context.rom_extractor
        assert extractor is not None


class TestPureAppContextComponentInitialization:
    """Test components can initialize with explicit AppContext deps."""

    def test_extraction_controller_pure_di(self, app_context: AppContext):
        """Test ExtractionController works with all deps from AppContext."""
        from ui.extraction_controller import ExtractionController

        # Get all dependencies via AppContext
        extraction_mgr = app_context.core_operations_manager
        session_mgr = app_context.application_state_manager
        injection_mgr = app_context.core_operations_manager
        settings_mgr = app_context.application_state_manager
        preview_gen = app_context.preview_generator

        # Create mock main window
        mock_window = Mock()
        mock_window.extract_requested = Mock()
        mock_window.open_in_editor_requested = Mock()
        mock_window.arrange_rows_requested = Mock()
        mock_window.arrange_grid_requested = Mock()
        mock_window.inject_requested = Mock()
        mock_window.extraction_panel = Mock()
        mock_window.extraction_panel.offset_changed = Mock()

        # Suppress deprecation warnings - we're passing all required params
        import warnings

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning)

            # Create with explicit deps
            controller = ExtractionController(
                mock_window,
                extraction_manager=extraction_mgr,
                session_manager=session_mgr,
                injection_manager=injection_mgr,
                settings_manager=settings_mgr,
                preview_generator=preview_gen,
            )

        # Verify managers are the injected ones
        assert controller.extraction_manager is extraction_mgr
        assert controller.session_manager is session_mgr
        assert controller.injection_manager is injection_mgr
        assert controller.settings_manager is settings_mgr
        assert controller.preview_generator is preview_gen

    def test_main_window_pure_di(self, app_context: AppContext, qtbot):
        """Test MainWindow works with all deps from AppContext.

        Note: Uses app_context because MainWindow saves settings on init,
        which modifies shared state.
        """
        from ui.main_window import MainWindow

        settings_mgr = app_context.application_state_manager
        rom_cache = app_context.rom_cache
        session_mgr = app_context.application_state_manager

        # Create window with explicit deps
        window = MainWindow(
            settings_manager=settings_mgr,
            rom_cache=rom_cache,
            session_manager=session_mgr,
        )

        try:
            assert window.settings_manager is settings_mgr
            assert window.rom_cache is rom_cache
            assert window.session_manager is session_mgr
        finally:
            window.close()
            window.deleteLater()

    def test_injection_dialog_pure_di(self, app_context: AppContext, qtbot):
        """Test InjectionDialog works with injection_manager from AppContext."""
        from ui.injection_dialog import InjectionDialog

        injection_mgr = app_context.core_operations_manager
        settings_mgr = app_context.application_state_manager

        # Create with explicit deps
        dialog = InjectionDialog(
            injection_manager=injection_mgr,
            settings_manager=settings_mgr,
        )

        try:
            assert dialog.injection_manager is injection_mgr
        finally:
            dialog.close()
            dialog.deleteLater()

    def test_rom_extraction_panel_pure_di(self, app_context: AppContext, qtbot):
        """Test ROMExtractionPanel works with explicit dependencies from AppContext."""
        from ui.rom_extraction_panel import ROMExtractionPanel

        extraction_mgr = app_context.core_operations_manager
        state_mgr = app_context.application_state_manager
        rom_cache = app_context.rom_cache

        # Create with explicit deps
        panel = ROMExtractionPanel(
            extraction_manager=extraction_mgr,
            state_manager=state_mgr,
            rom_cache=rom_cache,
        )

        try:
            assert panel.extraction_manager is extraction_mgr
            assert panel.state_manager is state_mgr
            assert panel.rom_cache is rom_cache
        finally:
            panel.deleteLater()


class TestAppContextErrorBehavior:
    """Test behavior when AppContext is not initialized."""

    def test_get_app_context_before_init_raises(self, clean_registry_state):
        """Test that get_app_context() raises clear error if not initialized."""
        from core.app_context import reset_app_context

        reset_app_context()

        with pytest.raises(RuntimeError, match="AppContext not initialized"):
            get_app_context()

    def test_get_app_context_optional_returns_none(self, clean_registry_state):
        """Test that get_app_context_optional() returns None if not initialized."""
        from core.app_context import reset_app_context

        reset_app_context()

        ctx = get_app_context_optional()
        assert ctx is None

    def test_deprecated_functions_were_removed(self, app_context: AppContext):
        """Verify deprecated convenience functions have been removed."""
        import core.managers

        # These functions should no longer exist at module level
        assert not hasattr(core.managers, "get_extraction_manager"), "get_extraction_manager should have been removed"
        assert not hasattr(core.managers, "get_injection_manager"), "get_injection_manager should have been removed"
        assert not hasattr(core.managers, "get_session_manager"), "get_session_manager should have been removed"
        assert not hasattr(core.managers, "get_navigation_manager"), "get_navigation_manager should have been removed"

        # ManagerRegistry class has been removed
        assert not hasattr(core.managers, "ManagerRegistry"), "ManagerRegistry class should have been removed"


class TestManagerDependencyAccess:
    """Test managers' internal dependency access."""

    def test_core_ops_manager_session_access(self, app_context: AppContext):
        """Test CoreOperationsManager can access session manager."""
        ops_mgr = app_context.core_operations_manager

        # CoreOperationsManager has _ensure_session_manager() - verify it works
        if hasattr(ops_mgr, "_ensure_session_manager"):
            session = ops_mgr._ensure_session_manager()
            assert session is not None

    def test_rom_cache_has_expected_methods(self, app_context: AppContext):
        """Test ROMCache has expected interface."""
        cache = app_context.rom_cache
        assert cache is not None

        assert hasattr(cache, "get_cache_stats")
        assert hasattr(cache, "cache_enabled")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
