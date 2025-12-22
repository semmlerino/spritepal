"""Tests for focused protocol composition.

This module verifies that:
1. ApplicationStateManager satisfies all focused protocols via structural typing
2. Focused protocols can be injected via DI and resolve to the same singleton
3. The composite ApplicationStateManagerProtocol maintains backward compatibility

These tests ensure the Interface Segregation Principle refactoring works correctly.
"""

from __future__ import annotations

import pytest


@pytest.mark.shared_state_safe
class TestFocusedProtocolComposition:
    """Verify ApplicationStateManager implements all focused protocols."""

    def test_application_state_manager_implements_workflow_protocol(
        self, session_managers
    ) -> None:
        """Verify WorkflowStateProtocol is satisfied."""
        from core.di_container import inject
        from core.protocols import WorkflowStateProtocol

        workflow = inject(WorkflowStateProtocol)
        assert workflow is not None

        # Verify key attributes/methods exist
        assert hasattr(workflow, "workflow_state")
        assert hasattr(workflow, "is_workflow_busy")
        assert hasattr(workflow, "can_extract")
        assert hasattr(workflow, "transition_workflow")
        assert hasattr(workflow, "workflow_state_changed")

    def test_application_state_manager_implements_session_protocol(
        self, session_managers
    ) -> None:
        """Verify SessionPersistenceProtocol is satisfied."""
        from core.di_container import inject
        from core.protocols import SessionPersistenceProtocol

        session = inject(SessionPersistenceProtocol)
        assert session is not None

        # Verify key methods exist
        assert hasattr(session, "save_session")
        assert hasattr(session, "load_session")
        assert hasattr(session, "get_session_data")
        assert hasattr(session, "clear_session")
        assert hasattr(session, "update_session_data")
        assert hasattr(session, "session_changed")

    def test_application_state_manager_implements_settings_protocol(
        self, session_managers
    ) -> None:
        """Verify SettingsAccessProtocol is satisfied."""
        from core.di_container import inject
        from core.protocols import SettingsAccessProtocol

        settings = inject(SettingsAccessProtocol)
        assert settings is not None

        # Verify key methods exist
        assert hasattr(settings, "get_setting")
        assert hasattr(settings, "set_setting")
        assert hasattr(settings, "save_settings")
        assert hasattr(settings, "get")
        assert hasattr(settings, "set")
        assert hasattr(settings, "get_window_geometry")
        assert hasattr(settings, "update_window_state")
        assert hasattr(settings, "settings_saved")

    def test_application_state_manager_implements_cache_stats_protocol(
        self, session_managers
    ) -> None:
        """Verify CacheStatsProtocol is satisfied."""
        from core.di_container import inject
        from core.protocols import CacheStatsProtocol

        cache = inject(CacheStatsProtocol)
        assert cache is not None

        # Verify key methods exist
        assert hasattr(cache, "record_cache_hit")
        assert hasattr(cache, "record_cache_miss")
        assert hasattr(cache, "get_cache_session_stats")
        assert hasattr(cache, "cache_stats_updated")

    def test_application_state_manager_implements_runtime_state_protocol(
        self, session_managers
    ) -> None:
        """Verify RuntimeStateProtocol is satisfied."""
        from core.di_container import inject
        from core.protocols import RuntimeStateProtocol

        runtime = inject(RuntimeStateProtocol)
        assert runtime is not None

        # Verify key methods exist
        assert hasattr(runtime, "get_state")
        assert hasattr(runtime, "set_state")
        assert hasattr(runtime, "clear_state")
        assert hasattr(runtime, "state_changed")

    def test_application_state_manager_implements_current_offset_protocol(
        self, session_managers
    ) -> None:
        """Verify CurrentOffsetProtocol is satisfied."""
        from core.di_container import inject
        from core.protocols import CurrentOffsetProtocol

        offset = inject(CurrentOffsetProtocol)
        assert offset is not None

        # Verify key methods exist
        assert hasattr(offset, "set_current_offset")
        assert hasattr(offset, "get_current_offset")
        assert hasattr(offset, "current_offset_changed")
        assert hasattr(offset, "preview_ready")


@pytest.mark.shared_state_safe
class TestFocusedProtocolSingletonIdentity:
    """Verify all focused protocols resolve to the same singleton."""

    def test_all_focused_protocols_resolve_to_same_instance(
        self, session_managers
    ) -> None:
        """All 6 focused protocols should resolve to the same ApplicationStateManager."""
        from core.di_container import inject
        from core.protocols import (
            ApplicationStateManagerProtocol,
            CacheStatsProtocol,
            CurrentOffsetProtocol,
            RuntimeStateProtocol,
            SessionPersistenceProtocol,
            SettingsAccessProtocol,
            WorkflowStateProtocol,
        )

        # Inject all protocols
        composite = inject(ApplicationStateManagerProtocol)
        workflow = inject(WorkflowStateProtocol)
        session = inject(SessionPersistenceProtocol)
        settings = inject(SettingsAccessProtocol)
        cache = inject(CacheStatsProtocol)
        runtime = inject(RuntimeStateProtocol)
        offset = inject(CurrentOffsetProtocol)

        # All should be the exact same object
        assert workflow is composite
        assert session is composite
        assert settings is composite
        assert cache is composite
        assert runtime is composite
        assert offset is composite


@pytest.mark.shared_state_safe
class TestCompositeProtocolBackwardCompatibility:
    """Verify ApplicationStateManagerProtocol maintains backward compatibility."""

    def test_composite_protocol_has_all_methods(self, session_managers) -> None:
        """Composite protocol should have all 24 methods from original."""
        from core.di_container import inject
        from core.protocols import ApplicationStateManagerProtocol

        mgr = inject(ApplicationStateManagerProtocol)

        # Settings methods
        assert hasattr(mgr, "get_setting")
        assert hasattr(mgr, "set_setting")
        assert hasattr(mgr, "save_settings")

        # Session methods
        assert hasattr(mgr, "save_session")
        assert hasattr(mgr, "load_session")
        assert hasattr(mgr, "get_session_data")
        assert hasattr(mgr, "clear_session")
        assert hasattr(mgr, "update_session_data")
        assert hasattr(mgr, "get")
        assert hasattr(mgr, "set")
        assert hasattr(mgr, "get_window_geometry")
        assert hasattr(mgr, "update_window_state")

        # Runtime state methods
        assert hasattr(mgr, "get_state")
        assert hasattr(mgr, "set_state")
        assert hasattr(mgr, "clear_state")

        # Workflow methods
        assert hasattr(mgr, "workflow_state")
        assert hasattr(mgr, "is_workflow_busy")
        assert hasattr(mgr, "can_extract")
        assert hasattr(mgr, "transition_workflow")

        # Cache methods
        assert hasattr(mgr, "record_cache_hit")
        assert hasattr(mgr, "record_cache_miss")
        assert hasattr(mgr, "get_cache_session_stats")

        # Offset methods
        assert hasattr(mgr, "set_current_offset")
        assert hasattr(mgr, "get_current_offset")

    def test_composite_protocol_has_all_signals(self, session_managers) -> None:
        """Composite protocol should have all implemented signals.

        Note: The protocol defines application_state_snapshot, history_updated, and
        sprite_added, but these are not yet implemented on ApplicationStateManager.
        We test only the signals that are actually implemented.
        """
        from core.di_container import inject
        from core.protocols import ApplicationStateManagerProtocol

        mgr = inject(ApplicationStateManagerProtocol)

        # Signals from focused protocols (implemented)
        assert hasattr(mgr, "state_changed")
        assert hasattr(mgr, "workflow_state_changed")
        assert hasattr(mgr, "session_changed")
        assert hasattr(mgr, "files_updated")
        assert hasattr(mgr, "settings_saved")
        assert hasattr(mgr, "session_restored")
        assert hasattr(mgr, "cache_stats_updated")
        assert hasattr(mgr, "current_offset_changed")
        assert hasattr(mgr, "preview_ready")

        # Note: These signals are defined in protocol but not yet implemented:
        # - application_state_snapshot
        # - history_updated
        # - sprite_added
