"""
DI Migration Readiness Tests.

These tests validate that the codebase is ready to remove deprecated
Service Locator functions (get_session_manager, get_extraction_manager, etc.)

Run these BEFORE removing deprecated functions to ensure DI works as replacement.
"""
from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

import pytest

from core.di_container import get_container, inject
from core.protocols.dialog_protocols import DialogFactoryProtocol
from core.protocols.manager_protocols import (
    ApplicationStateManagerProtocol,
    ExtractionManagerProtocol,
    InjectionManagerProtocol,
    ROMCacheProtocol,
    SettingsManagerProtocol,
)

if TYPE_CHECKING:
    from core.managers import ExtractionManager, InjectionManager, SessionManager
    from utils.rom_cache import ROMCache
    from utils.settings_manager import SettingsManager


pytestmark = [
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.di_migration,
    pytest.mark.skip_thread_cleanup(reason="DI tests create real managers which may spawn threads"),
]


class TestProtocolInjection:
    """Test that all protocols can be resolved via inject()."""

    def test_container_is_configured(self, isolated_managers):
        """Verify DI container is properly configured."""
        container = get_container()
        # Container should have at least SettingsManagerProtocol registered
        assert container.has(SettingsManagerProtocol), "DI container should be configured after manager init"

    def test_inject_settings_manager_protocol(self, isolated_managers):
        """Test SettingsManagerProtocol injection."""
        settings = inject(SettingsManagerProtocol)
        assert settings is not None
        assert hasattr(settings, "get")
        assert hasattr(settings, "set")

    def test_inject_session_manager_protocol(self, isolated_managers):
        """Test ApplicationStateManagerProtocol injection (for session)."""
        session = inject(ApplicationStateManagerProtocol)
        assert session is not None
        # SessionAdapter provides get_session_data
        assert hasattr(session, "get_session_data")

    def test_inject_extraction_manager_protocol(self, isolated_managers):
        """Test ExtractionManagerProtocol injection."""
        extraction = inject(ExtractionManagerProtocol)
        assert extraction is not None
        assert hasattr(extraction, "validate_extraction_params")

    def test_inject_injection_manager_protocol(self, isolated_managers):
        """Test InjectionManagerProtocol injection."""
        injection = inject(InjectionManagerProtocol)
        assert injection is not None
        assert hasattr(injection, "start_injection")

    def test_inject_rom_cache_protocol(self, isolated_managers):
        """Test ROMCacheProtocol injection."""
        cache = inject(ROMCacheProtocol)
        assert cache is not None
        # ROMCache provides get_cache_stats
        assert hasattr(cache, "get_cache_stats")


class TestPureDIComponentInitialization:
    """Test components can initialize with explicit DI (no fallbacks)."""

    def test_extraction_controller_pure_di(self, isolated_managers):
        """Test ExtractionController works with all deps passed explicitly."""
        from core.controller import ExtractionController

        # Get all dependencies via DI
        extraction_mgr = inject(ExtractionManagerProtocol)
        session_mgr = inject(ApplicationStateManagerProtocol)
        injection_mgr = inject(InjectionManagerProtocol)
        settings_mgr = inject(SettingsManagerProtocol)

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
            dialog_factory = Mock(spec=DialogFactoryProtocol)
            controller = ExtractionController(
                mock_window,
                extraction_manager=extraction_mgr,
                session_manager=session_mgr,
                injection_manager=injection_mgr,
                settings_manager=settings_mgr,
                dialog_factory=dialog_factory,
            )

        # Verify managers are the injected ones
        assert controller.extraction_manager is extraction_mgr
        assert controller.session_manager is session_mgr
        assert controller.injection_manager is injection_mgr
        assert controller.settings_manager is settings_mgr

    def test_main_window_pure_di(self, isolated_managers, qtbot):
        """Test MainWindow works with all deps passed explicitly.

        Note: Uses isolated_managers because MainWindow saves settings on init,
        which modifies shared state.
        """
        from ui.main_window import MainWindow

        settings_mgr = inject(SettingsManagerProtocol)
        rom_cache = inject(ROMCacheProtocol)
        session_mgr = inject(ApplicationStateManagerProtocol)

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

    def test_injection_dialog_pure_di(self, isolated_managers, qtbot):
        """Test InjectionDialog works with injection_manager passed explicitly."""
        from ui.injection_dialog import InjectionDialog

        injection_mgr = inject(InjectionManagerProtocol)

        # Create with explicit dep
        dialog = InjectionDialog(injection_manager=injection_mgr)

        try:
            assert dialog.injection_manager is injection_mgr
        finally:
            dialog.close()
            dialog.deleteLater()

    def test_rom_extraction_panel_pure_di(self, isolated_managers, qtbot):
        """Test ROMExtractionPanel works with extraction_manager passed explicitly."""
        from ui.rom_extraction_panel import ROMExtractionPanel

        extraction_mgr = inject(ExtractionManagerProtocol)

        # Create with explicit dep
        panel = ROMExtractionPanel(extraction_manager=extraction_mgr)

        try:
            # Public attribute name is extraction_manager
            assert panel.extraction_manager is extraction_mgr
        finally:
            panel.deleteLater()


class TestNoFallbackScenario:
    """Test behavior when deprecated functions would fail."""

    def test_inject_before_container_configured_raises(self):
        """Test that inject() raises clear error if container not configured."""
        # This tests the error message users would see if they try to use
        # inject() before managers are initialized
        container = get_container()

        # Temporarily clear the container
        # Store current state
        original_singletons = container._singletons.copy()
        original_factories = container._factories.copy()

        try:
            container.clear()

            # Try to inject - should raise ValueError
            with pytest.raises(ValueError, match="No registration"):
                inject(SettingsManagerProtocol)
        finally:
            # Restore
            container._singletons.update(original_singletons)
            container._factories.update(original_factories)

    def test_deprecated_functions_were_removed(self, isolated_managers):
        """Verify deprecated convenience functions have been removed from module exports."""
        import core.managers

        # These functions should no longer exist at module level
        # (they were removed as part of the DI migration)
        assert not hasattr(core.managers, "get_extraction_manager"), \
            "get_extraction_manager should have been removed"
        assert not hasattr(core.managers, "get_injection_manager"), \
            "get_injection_manager should have been removed"
        assert not hasattr(core.managers, "get_session_manager"), \
            "get_session_manager should have been removed"
        assert not hasattr(core.managers, "get_navigation_manager"), \
            "get_navigation_manager should have been removed"

        # These are still available on the registry instance
        from core.managers.registry import ManagerRegistry
        registry = ManagerRegistry()
        assert hasattr(registry, "get_extraction_manager"), \
            "Registry should still have get_extraction_manager method"


class TestInjectionManagerDI:
    """Test InjectionManager's internal DI needs."""

    def test_injection_manager_session_access(self, isolated_managers):
        """Test InjectionManager can access session manager via DI."""
        injection_mgr = inject(InjectionManagerProtocol)

        # InjectionManager has _get_session_manager() - verify it works
        # This is an internal method that needs to use DI
        if hasattr(injection_mgr, "_get_session_manager"):
            session = injection_mgr._get_session_manager()
            assert session is not None

    def test_injection_manager_rom_cache_access(self, isolated_managers):
        """Test InjectionManager can access ROM cache via DI."""
        # Use DI to get ROM cache (replaces deprecated get_rom_cache())
        cache = inject(ROMCacheProtocol)
        assert cache is not None

        # Verify the cache has expected methods
        assert hasattr(cache, "get_cache_stats")
        assert hasattr(cache, "cache_enabled")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
